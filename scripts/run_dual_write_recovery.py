#!/usr/bin/env python3
"""Real owned localhost recovery controls, including explicit crash cut states."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from gateroll.campaigns import RolloutBlocked, RuntimeRun
from gateroll.model import Manifest, Service
from gateroll.pending_writes import PendingWrites
from gateroll.planner import plan
from gateroll.portable_runtime import fresh_directory
from gateroll.rpcutil import atomic_json, call, free_port

CASES = ("secondary-down", "primary-timeout", "secondary-timeout",
         "intent-only-crash-cut", "both-committed-crash-cut")


def stop(process) -> None:
    process.kill()
    process.join(timeout=2)
    if process.is_alive():
        raise RuntimeError("owned process did not stop")
    process.close()


def execute_case(root: Path, output: Path, case: str) -> dict:
    output = fresh_directory(root, output)
    manifest = Manifest(f"recovery-{case}", "synthetic", "synthetic", "one-role",
                        (Service("gateway"),), ())
    certificate = plan(manifest)
    runtime = RuntimeRun(root, output / "run", manifest, certificate, "certified", "none")
    trace = []

    def observe(label, port, request):
        response = call(port, request, timeout=1)
        trace.append({"label": label, "request": request, "response": response})
        return response

    try:
        runtime.start()
        runtime._step_certified([0], [1])
        pending = PendingWrites(runtime.config_path)
        request = {"cmd": "request", "target": "gateway", "path": ["gateway"],
                   "req_id": f"recovery-{case}:inc", "key": "a0", "op": "inc",
                   "role": "writer", "client_shape": "old", "delta": 1}
        rpc = PendingWrites.effect(request)
        partial = None
        retry_while_down = None
        cut = None
        if case == "secondary-down":
            backend = runtime.backends[("gateway", "new")]
            stop(backend.process)
            runtime.config["services"]["gateway"]["new"]["port"] = free_port()
            runtime._write_config()
            partial = observe("interrupted-write", runtime.proxy_port, request)
            retry_while_down = observe("same-ID-retry-while-peer-down", runtime.proxy_port, request)
            restarted = runtime._spawn_backend("gateway", "new", state_path=backend.state_path)
            runtime.config["services"]["gateway"]["new"] = {"port": restarted.port, "live": True}
            runtime._write_config()
        elif case == "primary-timeout":
            partial = observe("post-commit-primary-timeout", runtime.proxy_port,
                              {**request, "delay_after_ms": 260})
            backend = runtime.backends[("gateway", "old")]
            stop(backend.process)
            restarted = runtime._spawn_backend("gateway", "old", state_path=backend.state_path)
            runtime.config["services"]["gateway"]["old"] = {"port": restarted.port, "live": True}
            runtime._write_config()
        else:
            # Explicit injected crash cuts: durable intent and actual endpoint
            # RPCs, not invented proxy completions. No proxy reply is claimed.
            pending.begin("gateway", "B", rpc)
            cut = {"kind": case, "intent_written": True, "endpoint_applications": []}
            if case in {"secondary-timeout", "both-committed-crash-cut"}:
                observe("cut-primary-apply", runtime.backends[("gateway", "old")].port, rpc)
                cut["endpoint_applications"].append("old")
            if case == "both-committed-crash-cut":
                observe("cut-secondary-apply", runtime.backends[("gateway", "new")].port, rpc)
                cut["endpoint_applications"].append("new")
            if case == "secondary-timeout":
                # Primary's saved receipt bypasses its delay. The secondary
                # really commits, then delays its response beyond the timeout.
                partial = observe("post-commit-secondary-timeout", runtime.proxy_port,
                                  {**request, "delay_after_ms": 260})

        before = {v: runtime._dump("gateway", v) for v in ("old", "new")}
        intent_before_restart = pending.read()
        stop(runtime.proxy_process)
        runtime._spawn_proxy()
        intent_after_restart = pending.read()
        read = {**request, "req_id": f"recovery-{case}:read", "op": "read", "role": "reader"}
        blocked_primary = observe("blocked-primary-read", runtime.proxy_port, read)
        blocked_peer = observe("blocked-peer-read", runtime.proxy_port, {**read, "stale_route": True})
        blocked_new = observe("blocked-new-write", runtime.proxy_port,
                              {**request, "req_id": f"recovery-{case}:other-inc"})
        mismatch = observe("blocked-changed-effect", runtime.proxy_port, {**request, "delta": 2})
        unrelated = observe("unaffected-key-read", runtime.proxy_port, {**read, "key": "u0"})
        phase_blocks = []
        for label, action in (("prefer-new", lambda: runtime._step_certified([1], [2])),
                              ("migration", lambda: runtime._migrate("gateway", publish=False)),
                              ("old-route-reset", runtime._reset_old_routes)):
            try:
                action()
            except RolloutBlocked as exc:
                phase_blocks.append({"action": label, "reason": str(exc)})
        retry = observe("same-ID-completion", runtime.proxy_port,
                        {**request, "stale_route": True} if case == "secondary-down" else request)
        after = {v: runtime._dump("gateway", v) for v in ("old", "new")}
        remaining = pending.read()
        primary_read = observe("resolved-primary-read", runtime.proxy_port, read)
        peer_read = observe("resolved-peer-read", runtime.proxy_port, {**read, "stale_route": True})
        repeated = observe("completed-ID-replay", runtime.proxy_port, request)
        replay_state = {v: runtime._dump("gateway", v) for v in ("old", "new")}
        runtime._step_certified([1], [2])
        new_read = observe("resolved-new-preference-read", runtime.proxy_port, read)

        errors = []
        if partial is not None and (partial.get("available") or partial.get("error") not in {"service-timeout", "dual-write-failed"}):
            errors.append("fault-did-not-produce-real-unavailability")
        if retry_while_down is not None and (retry_while_down.get("available") or retry_while_down.get("error") != "dual-write-failed"):
            errors.append("unresolved-retry-succeeded")
        expected_before = {
            "secondary-down": (12, 11), "primary-timeout": (12, 11),
            "secondary-timeout": (12, 12), "intent-only-crash-cut": (11, 11),
            "both-committed-crash-cut": (12, 12),
        }[case]
        if tuple(before[v]["values"]["a0"] for v in ("old", "new")) != expected_before:
            errors.append("unexpected-fault-state")
        if not intent_before_restart or intent_before_restart != intent_after_restart:
            errors.append("pending-intent-not-retained")
        for response in (blocked_primary, blocked_peer, blocked_new):
            if response.get("available") or response.get("error") != "pending-dual-write":
                errors.append("pending-observation-or-new-effect-allowed")
        if mismatch.get("available") or mismatch.get("error") != "pending-request-mismatch":
            errors.append("changed-effect-retry-allowed")
        if not unrelated.get("ok") or unrelated.get("value") != 13:
            errors.append("unaffected-key-blocked")
        if len(phase_blocks) != 3 or any(row["reason"] != "pending-dual-write" for row in phase_blocks):
            errors.append("pending-phase-not-blocked")
        for response in (retry, primary_read, peer_read, repeated, new_read):
            if not response.get("available") or not response.get("ok") or response.get("value") != 12:
                errors.append("resolution-or-observation-failed")
        if remaining:
            errors.append("pending-not-cleared-after-confirmation")
        if any(after[v]["values"]["a0"] != 12 for v in ("old", "new")) or after != replay_state:
            errors.append("replica-divergence-or-duplicate-effect")
        if set(after["old"]["receipts"]) != set(after["new"]["receipts"]):
            errors.append("receipt-ID-disagreement")
        result = {"schema": "gateroll.dual-write-recovery-control.v1", "case": case,
                  "pass": not errors, "errors": errors, "model_admitted": certificate["admitted"],
                  "pending_dual_write_enabled": True, "injected_crash_cut": cut,
                  "partial_response": partial, "retry_while_peer_down": retry_while_down,
                  "before_resolution": before,
                  "intent_before_proxy_restart": intent_before_restart,
                  "intent_after_proxy_restart": intent_after_restart,
                  "phase_blocks": phase_blocks, "after_resolution": after,
                  "pending_after_resolution": remaining, "trace": trace}
        atomic_json(output / "control.json", result)
        if errors:
            raise AssertionError(errors)
        return result
    finally:
        runtime.close()


def execute(root: Path, output: Path) -> dict:
    output = fresh_directory(root, output)
    results = [execute_case(root, output / case, case) for case in CASES]
    summary = {"schema": "gateroll.dual-write-recovery-controls.v1", "pass": all(r["pass"] for r in results),
               "cases": len(results), "case_names": list(CASES),
               "scope": "Single authority; serialized requests/actions; local persistent files; same-ID client retry."}
    atomic_json(output / "recovery_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.artifact_root.resolve(), args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
