#!/usr/bin/env python3
"""Reproduce all claim-critical finite and multi-process evidence."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from gateroll.portable_runtime import WindowsJob, fresh_directory
from gateroll.rpcutil import atomic_json


def run_step(name: str, command: Sequence[str], root: Path, log_dir: Path, timeout: float) -> dict:
    stdout_path = log_dir / f"{name}.stdout"
    stderr_path = log_dir / f"{name}.stderr"
    started = time.perf_counter()
    gate = log_dir / f"{name}.gate.json"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            list(command),
            cwd=root,
            env={**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1",
                 "PYTHONDONTWRITEBYTECODE": "1", "GATEROLL_START_GATE": str(gate)},
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        owner = None
        try:
            owner = WindowsJob(process)
            atomic_json(gate, {"ready": True})
            process.wait(timeout=timeout)
        finally:
            if owner is not None:
                owner.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    elapsed = time.perf_counter() - started
    if process.returncode != 0:
        tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"{name} failed with exit {process.returncode}:\n{tail}")
    return {"step": name, "exit_code": process.returncode, "elapsed_seconds": round(elapsed, 6)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise SystemExit("workers must be in [1,4]")
    root = Path(__file__).resolve().parent
    if args.replace:
        parser.error("replacement is disabled; choose a fresh private reproduction directory")
    output = fresh_directory(root, args.output)
    raw = output / "raw"
    summary = output / "summary"
    logs = output / "logs"
    logs.mkdir(parents=True)
    steps: list[dict] = []
    started = time.perf_counter()

    steps.append(run_step(
        "finite",
        [sys.executable, "-B", "scripts/run_finite.py", "--artifact-root", str(root), "--output", str(raw / "finite")],
        root, logs, 1200,
    ))
    steps.append(run_step(
        "tiny-exhaustive",
        [sys.executable, "-B", "scripts/run_tiny.py", "--output", str(raw / "tiny_exhaustive.json")],
        root, logs, 120,
    ))
    steps.append(run_step(
        "campaign-matrix",
        [
            sys.executable, "-B", "scripts/run_campaign_matrix.py",
            "--artifact-root", str(root),
            "--output", str(raw / "campaigns"),
            "--workers", str(args.workers),
            "--timeout-seconds", "30",
        ],
        root, logs, 1200,
    ))
    steps.append(run_step(
        "aggregate",
        [sys.executable, "-B", "scripts/aggregate_results.py", "--raw", str(raw), "--output", str(summary)],
        root, logs, 120,
    ))
    steps.append(run_step(
        "verify",
        [
            sys.executable, "-B", "scripts/verify_results.py",
            "--expected", str(root / "results" / "expected" / "semantic_summary.json"),
            "--actual", str(summary / "semantic_summary.json"),
            "--report", str(output / "verification_report.json"),
        ],
        root, logs, 120,
    ))
    steps.append(run_step(
        "tests",
        [sys.executable, "-B", "scripts/run_tests.py", "--artifact-root", str(root), "--results", str(raw)],
        root, logs, 300,
    ))

    report = json.loads((output / "verification_report.json").read_text(encoding="utf-8"))
    reproduction = {
        "complete": bool(report["semantic_match"]),
        "workers": args.workers,
        "steps": steps,
        "total_elapsed_seconds": round(time.perf_counter() - started, 6),
        "semantic_summary": str((summary / "semantic_summary.json").relative_to(output)),
        "verification_report": "verification_report.json",
    }
    (output / "reproduction_summary.json").write_text(json.dumps(reproduction, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(reproduction, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
