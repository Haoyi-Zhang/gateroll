"""Session-aware local TCP proxy used by end-to-end campaigns."""
from __future__ import annotations

import argparse
import json
import socket
import socketserver
import threading
from pathlib import Path
from typing import Any

from .rpcutil import call
from .pending_writes import PendingWrites


class ProxyState:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.pins: dict[str, str] = {}
        self.lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.pending = PendingWrites(config_path)

    def config(self) -> dict[str, Any]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    @staticmethod
    def _mode_rank(mode: str) -> int:
        return {"O": 0, "B": 1, "N": 2}[mode]

    def _direction_supported(self, config: dict[str, Any], path: list[str]) -> bool:
        services = config["services"]
        edge_map = {(x["src"], x["dst"]): x for x in config["edges"]}
        for left, right in zip(path, path[1:]):
            edge = edge_map.get((left, right))
            if edge is None:
                continue
            lm = self._mode_rank(services[left]["mode"])
            rm = self._mode_rank(services[right]["mode"])
            if lm >= 1 and rm == 0 and not edge["n2o"]:
                return False
            if lm <= 1 and rm == 2 and not edge["o2n"]:
                return False
        return True

    def _select_version(self, config: dict[str, Any], request: dict[str, Any], service: dict[str, Any]) -> str:
        strategy = config["strategy"]
        session_id = request.get("session_id")
        if strategy == "version_negotiation":
            selected = "old" if request["client_shape"] == "old" else "new"
        else:
            selected = service["preferred"]
        if request.get("stale_route"):
            alternate = "old" if selected == "new" else "new"
            if service.get(alternate, {}).get("live"):
                selected = alternate
        if session_id:
            with self.lock:
                if service.get("session_support"):
                    selected = self.pins.setdefault(str(session_id), selected)
                elif request.get("session_continuation") and request.get("session_origin") != selected:
                    return "protocol-mismatch"
        return selected

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        # One coordinator serializes forwarding/intent updates. Controller
        # actions are separately serialized with requests by the harness.
        with self.request_lock:
            return self._handle(request)

    def _handle(self, request: dict[str, Any]) -> dict[str, Any]:
        config = self.config()
        target = str(request["target"])
        service = config["services"][target]
        key = str(request["key"])
        if key in set(config.get("quiesced_keys", [])):
            return {"available": False, "error": "selective-quiescence", "target": target}
        if not self._direction_supported(config, list(request.get("path", []))):
            return {"available": False, "error": "unsupported-mixed-direction", "target": target}
        if config.get("auth_guard") and request["op"] == "inc" and request["role"] not in {"writer", "admin"}:
            return {"available": True, "denied": True, "target": target, "proxy_guard": True}

        recovery = config.get("pending_dual_write", config["strategy"] == "certified")
        intent = self.pending.for_key(target, key) if recovery else None
        if intent is not None:
            if request["op"] != "inc" or str(request["req_id"]) != intent["rpc"]["req_id"]:
                return {"available": False, "error": "pending-dual-write", "target": target}
            if PendingWrites.effect(request) != intent["rpc"]:
                return {"available": False, "error": "pending-request-mismatch", "target": target}
            if service["mode"] != intent["mode"] or not service.get("dual_write"):
                return {"available": False, "error": "pending-phase-mismatch", "target": target}

        selected = self._select_version(config, request, service)
        if selected == "protocol-mismatch":
            return {
                "available": True,
                "ok": True,
                "protocol_ok": False,
                "shape": request["client_shape"],
                "value": None,
                "target": target,
            }
        endpoint = service.get(selected, {})
        if not endpoint.get("live"):
            return {"available": False, "error": "endpoint-unavailable", "target": target}

        client_shape = str(request["client_shape"])
        if client_shape != selected and not service.get("adapter"):
            return {"available": False, "error": "missing-adapter", "target": target}

        rpc = {
            "cmd": "apply",
            "req_id": request["req_id"],
            "key": key,
            "op": request["op"],
            "delta": request.get("delta", 1),
            "role": request["role"],
            "delay_after_ms": request.get("delay_after_ms", 0),
        }
        dual = request["op"] == "inc" and service.get("dual_write") and service["mode"] in {"B", "N"}
        if recovery and dual and intent is None:
            # Must persist BEFORE either endpoint can apply the write. Do not
            # consume unavailable reads/new IDs to silently finish another ID.
            self.pending.begin(target, service["mode"], rpc)
        try:
            primary = call(int(endpoint["port"]), rpc, timeout=float(config.get("service_timeout", 0.25)))
        except (TimeoutError, socket.timeout, OSError, ConnectionError) as exc:
            return {"available": False, "error": "service-timeout", "target": target}

        if dual:
            other = "old" if selected == "new" else "new"
            peer = service.get(other, {})
            if peer.get("live"):
                try:
                    secondary = call(int(peer["port"]), rpc, timeout=float(config.get("service_timeout", 0.25)))
                    if not secondary.get("ok") and not secondary.get("denied"):
                        return {"available": False, "error": "dual-write-failed", "target": target}
                except Exception:
                    return {"available": False, "error": "dual-write-failed", "target": target}
            elif recovery:
                return {"available": False, "error": "dual-write-failed", "target": target}
            if recovery:
                def write_value(reply):
                    if not reply.get("ok") or reply.get("denied") or reply.get("effect") != "write":
                        return None
                    if "value" in reply:
                        return reply["value"]
                    return reply.get("result", {}).get("value")

                value = write_value(primary)
                if value is None or value != write_value(secondary):
                    return {"available": False, "error": "dual-write-disagreement", "target": target}
                self.pending.finish(target, key)

        if primary.get("denied"):
            return {"available": True, "denied": True, "target": target, "service_version": selected}
        if not primary.get("ok"):
            return {"available": False, "error": primary.get("representation_error") or primary.get("protocol_error") or primary.get("error", "service-error"), "target": target}

        shape_ok = True
        value = None
        if "value" in primary:
            service_shape = "old"
            value = primary["value"]
        elif isinstance(primary.get("result"), dict) and "value" in primary["result"]:
            service_shape = "new"
            value = primary["result"]["value"]
        elif isinstance(primary.get("payload"), dict) and "count" in primary["payload"]:
            service_shape = "broken"
            value = primary["payload"]["count"]
        else:
            service_shape = "broken"

        if service_shape == "broken":
            shape_ok = False
            delivered_shape = "broken"
        elif service_shape != client_shape:
            if service.get("adapter"):
                delivered_shape = client_shape
            else:
                delivered_shape = service_shape
                shape_ok = False
        else:
            delivered_shape = service_shape
        return {
            "available": True,
            "ok": True,
            "denied": False,
            "value": value,
            "shape": delivered_shape,
            "shape_ok": shape_ok,
            "protocol_ok": True,
            "target": target,
            "service_version": selected,
            "replayed": bool(primary.get("replayed")),
        }


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            request = json.loads(self.rfile.readline(2_000_000).decode("utf-8"))
            state: ProxyState = self.server.state  # type: ignore[attr-defined]
            if request.get("cmd") == "health":
                response = {"ok": True}
            elif request.get("cmd") == "stop":
                response = {"ok": True}
                threading.Thread(target=self.server.shutdown, daemon=True).start()  # type: ignore[attr-defined]
            elif request.get("cmd") == "request":
                response = state.handle(request)
            else:
                response = {"available": False, "error": "unknown-command"}
        except Exception as exc:
            response = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        self.wfile.write(json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(port: int, config_path: str) -> None:
    state = ProxyState(Path(config_path))
    with Server(("127.0.0.1", port), Handler) as server:
        server.state = state  # type: ignore[attr-defined]
        server.serve_forever(poll_interval=0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    serve(args.port, str(args.config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
