#!/usr/bin/env python3
"""Execute one isolated campaign/strategy run and emit its raw record."""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

from gateroll.campaigns import RuntimeRun, STRATEGIES, scenario_specs
from gateroll.portable_runtime import private_path, filesystem_path
from gateroll.checker import check
from gateroll.families import base_manifest
from gateroll.model import Manifest
from gateroll.planner import plan
from gateroll.rpcutil import atomic_json


def execute(artifact_root: Path, campaign_index: int, strategy: str, run_dir: Path) -> dict[str, Any]:
    scenarios = scenario_specs(artifact_root / "inputs")
    topology, fault, pair_index, spec = scenarios[campaign_index]
    base = base_manifest(spec, pair_index)
    manifest = Manifest(
        case_id=f"campaign-{campaign_index:02d}",
        family=base.family,
        pair=base.pair,
        topology=base.topology,
        services=base.services,
        edges=base.edges,
        declared_defects=base.declared_defects,
    )
    certificate = plan(manifest)
    check(manifest, certificate)
    runtime = RuntimeRun(artifact_root, run_dir, manifest, certificate, strategy, fault)
    try:
        transactions, run = runtime.run()
    finally:
        runtime.close()
    journal: list[dict[str, Any]] = []
    if runtime.journal_path.exists():
        for line in runtime.journal_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                journal.append(json.loads(line))
    return {"run": run, "transactions": transactions, "journal": journal}



def _reap_residual_children() -> dict[str, int]:
    """Defensively terminate any process object left outside RuntimeRun's registry."""
    children = multiprocessing.active_children()
    for child in children:
        try:
            child.terminate()
        except Exception:
            pass
    deadline = time.monotonic() + 0.5
    for child in children:
        try:
            child.join(timeout=max(0.0, deadline - time.monotonic()))
            if child.is_alive():
                child.kill()
                child.join(timeout=0.2)
        except Exception:
            pass
    remaining = len(multiprocessing.active_children())
    return {"residual_before": len(children), "residual_after": remaining}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--campaign", type=int, required=True)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-gate", type=Path)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    if not 0 <= args.campaign < 40:
        parser.error("campaign must lie within [0,40)")
    output = filesystem_path(private_path(artifact_root, args.output))
    if output.exists():
        raise FileExistsError(output)
    if args.start_gate is not None:
        gate = filesystem_path(private_path(artifact_root, args.start_gate))
        deadline = time.monotonic() + 10
        while not gate.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("parent did not release owned-process start gate")
            time.sleep(0.01)
    # No children are spawned before the parent attaches its Windows Job Object.
    try:
        payload = execute(artifact_root, args.campaign, args.strategy, args.run_dir)
    finally:
        cleanup = _reap_residual_children()
    payload["harness_cleanup"] = cleanup
    if cleanup["residual_after"]:
        raise RuntimeError(f"owned children remain: {cleanup}")
    atomic_json(output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
