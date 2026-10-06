"""Small newline-delimited JSON RPC helpers used by the local harness."""
from __future__ import annotations

import json
import os
import socket
import struct
import tempfile
import time
from pathlib import Path
from typing import Any
from .portable_runtime import filesystem_path


def atomic_json(path: Path, value: Any) -> None:
    path = filesystem_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def call(port: int, request: dict[str, Any], timeout: float = 1.0) -> dict[str, Any]:
    payload = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        sock.sendall(payload)
        chunks = bytearray()
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.extend(data)
            if b"\n" in data:
                break
    finally:
        # Every local RPC is one request/response.  Close with an immediate RST
        # only after the complete response has been read so thousands of
        # bounded campaign calls do not consume the loopback ephemeral range
        # in TIME_WAIT.  This is harness transport cleanup, not a service fault.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                            struct.pack("hh" if os.name == "nt" else "ii", 1, 0))
        except OSError:
            pass
        sock.close()
    line = bytes(chunks).split(b"\n", 1)[0]
    if not line:
        raise ConnectionError("empty response")
    value = json.loads(line.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("response is not an object")
    return value


def wait_healthy(port: int, process, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        if hasattr(process, "poll"):
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"process exited with {code}")
        elif not process.is_alive():
            raise RuntimeError(f"process exited with {process.exitcode}")
        try:
            response = call(port, {"cmd": "health"}, timeout=0.2)
            if response.get("ok"):
                return
        except Exception as exc:  # bounded readiness polling
            last = exc
        time.sleep(0.02)
    raise TimeoutError(f"process did not become healthy: {last}")
