#!/usr/bin/env python3
"""Mechanism-off negative control retaining the original interrupted-write bug."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gateroll.campaigns import RuntimeRun
from gateroll.model import Manifest, Service
from gateroll.planner import plan
from gateroll.portable_runtime import fresh_directory
from gateroll.rpcutil import atomic_json, call, free_port


def execute(root: Path, output: Path) -> dict:
    output = fresh_directory(root, output)
    manifest = Manifest("partial-write-control", "synthetic", "synthetic", "one-role",
                        (Service("gateway"),), ())
    certificate = plan(manifest)
    runtime = RuntimeRun(root, output / "run", manifest, certificate, "certified", "none")
    try:
        runtime.start()
        # Explicit ablation of the new recovery barrier. Do not delete or
        # relabel the real old counterexample as a repaired default execution.
        runtime.config["pending_dual_write"] = False
        runtime._write_config()
        runtime._step_certified([0], [1])
        # Lose the secondary endpoint before forwarding; no concurrent workload.
        secondary = runtime.backends[("gateway", "new")]
        secondary.process.kill()
        secondary.process.join(timeout=2)
        if secondary.process.is_alive():
            raise RuntimeError("owned secondary did not stop")
        secondary.process.close()
        # Use a freshly allocated loopback port with no listening service.
        # Peer metadata remains live to model an unobserved crash.
        runtime.config["services"]["gateway"]["new"]["port"] = free_port()
        runtime._write_config()
        request = {"cmd": "request", "target": "gateway", "path": ["gateway"],
                   "req_id": "partial-write-control:inc", "key": "a0", "op": "inc",
                   "role": "writer", "client_shape": "old", "delta": 1}
        response = call(runtime.proxy_port, request, timeout=1)
        primary = runtime._dump("gateway", "old")
        restarted = runtime._spawn_backend("gateway", "new", state_path=secondary.state_path)
        runtime.config["services"]["gateway"]["new"] = {"port": restarted.port, "live": True}
        runtime._write_config()
        peer = runtime._dump("gateway", "new")
        # Observe primary first, then peer: 12 -> 11 with no intervening write.
        primary_read = {**request, "req_id": "partial-write-control:primary-read", "op": "read"}
        primary_observation = call(runtime.proxy_port, primary_read, timeout=1)
        read = {**request, "req_id": "partial-write-control:peer-read", "op": "read", "stale_route": True}
        observation = call(runtime.proxy_port, read, timeout=1)
        result = {
            "schema": "gateroll.interrupted-dual-write-control.v1",
            "model_admitted": certificate["admitted"],
            "pending_dual_write_enabled": False,
            "request": request, "partial_response": response,
            "primary": primary, "peer_after_restart": peer,
            "primary_read_request": primary_read, "primary_read_response": primary_observation,
            "read_request": read, "read_response": observation,
            "replica_values_agree": primary["values"] == peer["values"],
            "synchronization_premise_satisfied": False,
            "claim_boundary": "Serialized execution alone does not reconcile an interrupted dual write.",
        }
        atomic_json(output / "counterexample.json", result)
        if response.get("available") or response.get("error") != "dual-write-failed":
            raise AssertionError("partial write did not produce the intended unavailable outcome")
        if primary["values"]["a0"] != 12 or peer["values"]["a0"] != 11:
            raise AssertionError("expected persisted split was not observed")
        if not primary_observation.get("available") or primary_observation.get("value") != 12:
            raise AssertionError("primary read was not reproduced")
        if not observation.get("available") or observation.get("value") != 11:
            raise AssertionError("stale peer observation not reproduced")
        return result
    finally:
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.artifact_root.resolve(), args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
