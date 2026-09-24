"""Stateful old/new service process for the local campaign harness."""
from __future__ import annotations

import argparse
import json
import os
import socketserver
import threading
import time
from pathlib import Path
from typing import Any

from .rpcutil import atomic_json


class Store:
    def __init__(self, path: Path, version: str, idempotent: bool, auth_weak: bool, response_break: bool):
        self.path = path
        self.version = version
        self.idempotent = idempotent
        self.auth_weak = auth_weak
        self.response_break = response_break
        self.lock = threading.Lock()
        if not path.exists():
            atomic_json(path, {"values": {}, "receipts": {}})

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        atomic_json(self.path, state)

    def _decode(self, value: Any) -> int:
        if self.version == "old":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("old representation mismatch")
            return value
        if not isinstance(value, dict) or set(value) != {"n", "epoch"} or value.get("epoch") != 1:
            raise ValueError("new representation mismatch")
        return int(value["n"])

    def _encode(self, value: int) -> Any:
        return value if self.version == "old" else {"n": value, "epoch": 1}

    def canonical_dump(self) -> dict[str, Any]:
        state = self._read()
        return {
            "values": {key: self._decode(value) for key, value in state["values"].items()},
            "receipts": dict(state.get("receipts", {})),
        }

    def load(self, values: dict[str, int], receipts: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock:
            encoded = {str(key): self._encode(int(value)) for key, value in values.items()}
            state = {"values": encoded, "receipts": dict(receipts or {})}
            self._write(state)
        return {"ok": True, "count": len(encoded)}

    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = str(request["req_id"])
        key = str(request["key"])
        op = str(request["op"])
        role = str(request["role"])
        delta = int(request.get("delta", 1))
        delay_after_ms = int(request.get("delay_after_ms", 0))
        with self.lock:
            state = self._read()
            receipts = state.setdefault("receipts", {})
            if self.idempotent and req_id in receipts:
                response = dict(receipts[req_id])
                response["replayed"] = True
                return response
            if op == "inc" and role not in {"writer", "admin"} and not self.auth_weak:
                return {"ok": False, "denied": True, "version": self.version}
            try:
                current = self._decode(state["values"].get(key, self._encode(0)))
            except ValueError as exc:
                return {"ok": False, "representation_error": str(exc), "version": self.version}
            if op == "inc":
                current += delta
                state["values"][key] = self._encode(current)
                effect = "write"
            elif op == "read":
                effect = "read"
            else:
                return {"ok": False, "protocol_error": "unknown operation", "version": self.version}
            if self.response_break and self.version == "new":
                response: dict[str, Any] = {
                    "ok": True,
                    "payload": {"count": current},
                    "effect": effect,
                    "version": self.version,
                }
            elif self.version == "old":
                response = {"ok": True, "value": current, "effect": effect, "version": self.version}
            else:
                response = {"ok": True, "result": {"value": current}, "effect": effect, "version": self.version}
            if self.idempotent and op == "inc":
                receipts[req_id] = response
            self._write(state)
        if delay_after_ms > 0:
            time.sleep(delay_after_ms / 1000.0)
        return response


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(2_000_000)
        try:
            request = json.loads(raw.decode("utf-8"))
            cmd = request.get("cmd")
            store: Store = self.server.store  # type: ignore[attr-defined]
            if cmd == "health":
                response = {
                    "ok": True,
                    "version": store.version,
                    "idempotent": store.idempotent,
                    "auth_guard": not store.auth_weak,
                    "response_refines": not store.response_break,
                }
            elif cmd == "dump":
                response = {"ok": True, **store.canonical_dump()}
            elif cmd == "load":
                response = store.load(request.get("values", {}), request.get("receipts", {}))
            elif cmd == "apply":
                response = store.apply(request)
            elif cmd == "stop":
                response = {"ok": True}
                threading.Thread(target=self.server.shutdown, daemon=True).start()  # type: ignore[attr-defined]
            else:
                response = {"ok": False, "error": "unknown command"}
        except Exception as exc:
            response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            self.wfile.write(json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        except (BrokenPipeError, ConnectionResetError):
            # The one-request harness may close immediately after consuming the
            # newline-delimited response.  The response has already been fully
            # produced and persisted, so a peer-close while flushing is benign.
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port: int, state_path: str, service_version: str, idempotent: bool, auth_weak: bool, response_break: bool) -> None:
    store = Store(Path(state_path), service_version, idempotent, auth_weak, response_break)
    with Server(("127.0.0.1", port), Handler) as server:
        server.store = store  # type: ignore[attr-defined]
        server.serve_forever(poll_interval=0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--service-version", choices=("old", "new"), required=True)
    parser.add_argument("--idempotent", choices=("yes", "no"), default="yes")
    parser.add_argument("--auth-weak", choices=("yes", "no"), default="no")
    parser.add_argument("--response-break", choices=("yes", "no"), default="no")
    args = parser.parse_args()
    serve(
        args.port,
        str(args.state),
        args.service_version,
        args.idempotent == "yes",
        args.auth_weak == "yes",
        args.response_break == "yes",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
