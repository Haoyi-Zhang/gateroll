#!/usr/bin/env python3
"""Run bounded reproduction; distinguish scientific checks from release provenance."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-B", str(ROOT / "reproduce_base.py"),
                    "--output", str(args.output), "--workers", str(args.workers)],
                   check=True, cwd=ROOT, env=env, timeout=1800)
    out = args.output.resolve()
    compact = out / "compact-precedence-audit.json"
    subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_compact_precedence_audit.py"),
                    "--output", str(compact), "--random-cases", "12000"],
                   check=True, cwd=ROOT, env=env, timeout=600)
    observed = json.loads(compact.read_text(encoding="utf-8"))
    frozen = json.loads((ROOT / "results/compact-precedence-audit.json").read_text(encoding="utf-8"))
    compact_match = observed["semantic_sha256"] == frozen["semantic_sha256"]
    history = out / "public-history-verification.json"
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/verify_public_history.py"),
                             "--root", str(ROOT), "--output", str(history)],
                            check=False, cwd=ROOT, env=env, timeout=60)
    history_result = json.loads(history.read_text(encoding="utf-8"))
    scientific = bool(observed["pass"])
    release = bool(compact_match and history_result["pass"] is True)
    summary = {
        "schema": "gateroll.reviewer-hardening-reproduction.v2",
        "base_command_succeeded": True, "scientific_complete": scientific,
        "compact_precedence_pass": observed["pass"], "compact_semantic_match": compact_match,
        "compact_semantic_sha256": observed["semantic_sha256"],
        "historical_compact_pass": frozen["pass"],
        "public_history_status": history_result["status"], "public_history_pass": history_result["pass"],
        "release_complete": release, "complete": scientific and release,
    }
    (out / "reviewer-hardening-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    # Missing optional history is unavailable evidence, not a fabricated pass.
    return 0 if scientific and result.returncode in (0, 2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
