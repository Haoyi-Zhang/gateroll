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

from gateroll.campaigns import RuntimeRun, scenario_specs
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
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve()
    payload = execute(artifact_root, args.campaign, args.strategy, args.run_dir)
    payload["harness_cleanup"] = _reap_residual_children()
    atomic_json(args.output, payload)
    # The job has no in-memory result left to flush.  A direct exit avoids
    # interpreter-finalizer stalls after thousands of short-lived forked
    # servers; the explicit child reap above is the cleanup authority.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
