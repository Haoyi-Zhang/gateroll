"""Benign bounded child-tree fixture for Windows timeout cleanup."""
from __future__ import annotations

import argparse
import multiprocessing
import time
from pathlib import Path

from gateroll.rpcutil import atomic_json, free_port, wait_healthy
from gateroll.service_process import serve


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--info", type=Path, required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 10
    while not args.gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("fixture gate")
        time.sleep(0.01)
    port = free_port()
    process = multiprocessing.get_context("spawn").Process(
        target=serve, args=(port, str(args.info.with_suffix(".state.json")), "old", True, False, False))
    process.start()
    try:
        wait_healthy(port, process, timeout=10)
        atomic_json(args.info, {"port": port, "pid": process.pid})
        time.sleep(30)  # parent is intentionally killed by the owned-job test
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
