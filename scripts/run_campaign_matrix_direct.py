#!/usr/bin/env python3
"""Run 40 x 6 localhost campaigns with fresh attempts and bounded owned children."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from gateroll.campaigns import STRATEGIES, _write_csv, aggregate
from gateroll.portable_runtime import WindowsJob, fresh_directory, wait_start_gate
from gateroll.rpcutil import atomic_json


def _launch(root: Path, output: Path, campaign: int, strategy: str, attempt: int) -> dict[str, Any]:
    key = f"{campaign:02d}-{strategy}"
    attempt_key = f"{key}-attempt-{attempt}"
    job_path = output / "jobs" / f"{attempt_key}.json"
    run_dir = output / "runs" / attempt_key
    gate = output / "gates" / f"{attempt_key}.json"
    command = [
        sys.executable, "-B", "-m", "scripts.run_campaign_case",
        "--artifact-root", str(root), "--campaign", str(campaign), "--strategy", strategy,
        "--run-dir", str(run_dir), "--output", str(job_path), "--start-gate", str(gate),
    ]
    stdout_path = output / "logs" / f"{attempt_key}.stdout"
    stderr_path = output / "logs" / f"{attempt_key}.stderr"
    stdout = stdout_path.open("x", encoding="utf-8")
    stderr = stderr_path.open("x", encoding="utf-8")
    process = None
    owner = None
    try:
        process = subprocess.Popen(
            command, cwd=root,
            env={**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=stdout, stderr=stderr, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        owner = WindowsJob(process)
        atomic_json(gate, {"ready": True})
    except BaseException:
        if owner is not None:
            owner.close()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        stdout.close()
        stderr.close()
        raise
    return dict(campaign=campaign, strategy=strategy, attempt=attempt, key=key, job_path=job_path,
                process=process, owner=owner, stdout_path=stdout_path, stderr_path=stderr_path,
                stdout_handle=stdout, stderr_handle=stderr, started=time.perf_counter())


def _finish(active: dict[str, Any], timed_out: bool) -> dict[str, Any]:
    process = active["process"]
    # This handle owns only this campaign subtree, including stalled servers.
    active["owner"].close()
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    active["stdout_handle"].close()
    active["stderr_handle"].close()
    return {
        "campaign": active["campaign"], "strategy": active["strategy"], "attempt": active["attempt"],
        "elapsed_s": round(time.perf_counter() - active["started"], 6),
        "exit_code": process.returncode, "timed_out": timed_out,
        "stdout": active["stdout_path"].read_text(encoding="utf-8", errors="replace")[-2000:],
        "stderr": active["stderr_path"].read_text(encoding="utf-8", errors="replace")[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=40)
    parser.add_argument("--chunk-campaigns", type=int, help="legacy option; spawn needs no fork batches")
    parser.add_argument("--prune-runs", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be in [1,4]")
    if not 0 <= args.start < args.end <= 40:
        parser.error("campaign range must lie within [0,40]")
    if not 5 <= args.timeout_seconds <= 120:
        parser.error("timeout-seconds must be in [5,120]")
    if args.prune_runs:
        parser.error("pruning is disabled: raw attempts must be preserved")
    root = args.artifact_root.resolve()
    wait_start_gate(root)
    output = fresh_directory(root, args.output)
    for folder in ("jobs", "runs", "logs", "gates"):
        (output / folder).mkdir()
    started = time.perf_counter()
    tasks = [(c, s) for c in range(args.start, args.end) for s in STRATEGIES]
    pending = deque((c, s, 1) for c, s in tasks)
    active: dict[int, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    completed: dict[str, Path] = {}
    try:
        while pending or active:
            while pending and len(active) < args.workers:
                job = _launch(root, output, *pending.popleft())
                active[job["process"].pid] = job
            finished = [(pid, job["process"].poll() is None) for pid, job in active.items()
                        if job["process"].poll() is not None or
                        time.perf_counter() - job["started"] > args.timeout_seconds]
            if not finished:
                time.sleep(0.02)
                continue
            for pid, timed_out in finished:
                job = active.pop(pid)
                event = _finish(job, timed_out)
                events.append(event)
                with (output / "execution_events.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                if event["exit_code"] != 0 or not job["job_path"].exists():
                    if job["attempt"] < 2:
                        pending.append((job["campaign"], job["strategy"], job["attempt"] + 1))
                        continue
                    raise RuntimeError(f"campaign failed after two retained attempts: {job['key']}: {event}")
                completed[job["key"]] = job["job_path"]
                row = json.loads(job["job_path"].read_text(encoding="utf-8"))["run"]
                print(f"campaign={job['campaign']:02d} strategy={job['strategy']} "
                      f"violations={row['semantic_violations']} availability={row['availability_overall']:.3f}",
                      flush=True)
    except BaseException as exc:
        atomic_json(output / "matrix_failure.json", {"error": f"{type(exc).__name__}: {exc}",
                                                     "completed_runs": len(completed), "attempts": len(events)})
        raise
    finally:
        for job in active.values():
            _finish(job, True)
    runs: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    journals: list[dict[str, Any]] = []
    for campaign, strategy in tasks:
        payload = json.loads(completed[f"{campaign:02d}-{strategy}"].read_text(encoding="utf-8"))
        runs.append(payload["run"])
        transactions.extend(payload["transactions"])
        if strategy == "certified":
            journals.extend({"campaign_id": f"campaign-{campaign:02d}", "sequence": i, **entry}
                            for i, entry in enumerate(payload["journal"]))
    _write_csv(output / "campaign_runs.csv", runs)
    _write_csv(output / "campaign_transactions.csv", transactions)
    with (output / "certified_journals.jsonl").open("w", encoding="utf-8") as handle:
        for row in journals:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    summary = aggregate(runs, transactions)
    # Save raw outcomes even when assertions subsequently fail.
    atomic_json(output / "campaign_summary.json", summary)
    execution = {
        "workers": args.workers, "timeout_seconds_per_strategy_run": args.timeout_seconds,
        "campaign_start": args.start, "campaign_end": args.end, "jobs": len(tasks),
        "attempts": len(events), "retries": len(events) - len(tasks),
        "timeouts": sum(int(e["timed_out"]) for e in events),
        "wall_seconds": round(time.perf_counter() - started, 6),
        "start_method": "spawn", "platform": sys.platform,
        "owned_subtree_cleanup": "Windows Job Object" if os.name == "nt" else "direct process",
    }
    atomic_json(output / "matrix_execution.json", execution)
    failures = []
    if len(runs) != len(tasks) or len(transactions) != len(tasks) * 36:
        failures.append("record-count")
    if args.start == 0 and args.end == 40:
        if summary["strategies"]["certified"]["semantic_violations"]:
            failures.append("certified-semantic-violation")
        failures.extend(f"missing-negative-control:{s}" for s in STRATEGIES[1:]
                        if not summary["strategies"][s]["violating_runs"])
    atomic_json(output / "campaign_checks.json", {"pass": not failures, "failures": failures})
    print(json.dumps({"summary": summary, "execution": execution}, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
