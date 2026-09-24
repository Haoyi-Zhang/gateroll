#!/usr/bin/env python3
"""Run the 40 x 6 campaign matrix in isolated, bounded subprocesses."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from gateroll.campaigns import STRATEGIES, _write_csv, aggregate
from gateroll.rpcutil import atomic_json


def _launch(
    artifact_root: Path,
    output_dir: Path,
    campaign: int,
    strategy: str,
    attempt: int,
) -> dict[str, Any]:
    key = f"{campaign:02d}-{strategy}"
    job_path = output_dir / "jobs" / f"{key}.json"
    run_dir = output_dir / "runs" / key
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    job_path.unlink(missing_ok=True)
    cmd = [
        sys.executable,
        "-B",
        str(artifact_root / "scripts" / "run_campaign_case.py"),
        "--artifact-root",
        str(artifact_root),
        "--campaign",
        str(campaign),
        "--strategy",
        strategy,
        "--run-dir",
        str(run_dir),
        "--output",
        str(job_path),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(artifact_root)
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{key}-attempt-{attempt}.stdout"
    stderr_path = log_dir / f"{key}-attempt-{attempt}.stderr"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        cmd,
        cwd=artifact_root,
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        start_new_session=True,
    )
    return {
        "campaign": campaign,
        "strategy": strategy,
        "attempt": attempt,
        "key": key,
        "job_path": job_path,
        "process": process,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "stdout_handle": stdout_handle,
        "stderr_handle": stderr_handle,
        "started": time.perf_counter(),
    }


def _finish(active: dict[str, Any], timed_out: bool) -> dict[str, Any]:
    process: subprocess.Popen[str] = active["process"]
    if timed_out and process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2.0)
    active["stdout_handle"].close()
    active["stderr_handle"].close()
    stdout = active["stdout_path"].read_text(encoding="utf-8", errors="replace")
    stderr = active["stderr_path"].read_text(encoding="utf-8", errors="replace")
    return {
        "campaign": active["campaign"],
        "strategy": active["strategy"],
        "attempt": active["attempt"],
        "elapsed_s": round(time.perf_counter() - active["started"], 6),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "stdout": stdout[-2000:],
        "stderr": stderr[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("results/raw/campaigns"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=40)
    parser.add_argument("--prune-runs", action="store_true")
    args = parser.parse_args()
    if not (1 <= args.workers <= 4):
        raise SystemExit("workers must be in [1,4]")
    if not (0 <= args.start < args.end <= 40):
        raise SystemExit("campaign range must lie within [0,40]")
    root = args.artifact_root.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    (output / "jobs").mkdir(parents=True)
    (output / "runs").mkdir(parents=True)

    started = time.perf_counter()
    tasks = [(campaign, strategy) for campaign in range(args.start, args.end) for strategy in STRATEGIES]
    pending = deque((campaign, strategy, 1) for campaign, strategy in tasks)
    active: dict[int, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    completed_keys: set[str] = set()

    # Launch and reap only from the main thread.  At most four isolated
    # campaign parents are live, and every strategy run owns a fresh set of
    # service processes and descriptors.
    while pending or active:
        while pending and len(active) < args.workers:
            campaign, strategy, attempt = pending.popleft()
            job = _launch(root, output, campaign, strategy, attempt)
            active[job["process"].pid] = job
        now = time.perf_counter()
        finished: list[tuple[int, bool]] = []
        for pid, job in active.items():
            process = job["process"]
            if process.poll() is not None:
                finished.append((pid, False))
            elif now - job["started"] > args.timeout_seconds:
                finished.append((pid, True))
        if not finished:
            time.sleep(0.02)
            continue
        for pid, timed_out in finished:
            job = active.pop(pid)
            event = _finish(job, timed_out)
            events.append(event)
            success = event["exit_code"] == 0 and job["job_path"].exists()
            if not success:
                if job["attempt"] < 2:
                    pending.append((job["campaign"], job["strategy"], job["attempt"] + 1))
                    continue
                raise RuntimeError(f"campaign job failed after two attempts: {job['key']}: {event}")
            completed_keys.add(job["key"])
            payload = json.loads(job["job_path"].read_text(encoding="utf-8"))
            row = payload["run"]
            print(
                f"campaign={job['campaign']:02d} strategy={job['strategy']} "
                f"violations={row['semantic_violations']} availability={row['availability_overall']:.3f}",
                flush=True,
            )

    if len(completed_keys) != len(tasks):
        raise AssertionError((len(completed_keys), len(tasks)))

    run_rows: list[dict[str, Any]] = []
    transaction_rows: list[dict[str, Any]] = []
    journal_rows: list[dict[str, Any]] = []
    for campaign, strategy in tasks:
        payload = json.loads((output / "jobs" / f"{campaign:02d}-{strategy}.json").read_text(encoding="utf-8"))
        run_rows.append(payload["run"])
        transaction_rows.extend(payload["transactions"])
        if strategy == "certified":
            for sequence, entry in enumerate(payload["journal"]):
                journal_rows.append({
                    "campaign_id": f"campaign-{campaign:02d}",
                    "sequence": sequence,
                    **entry,
                })

    expected_campaigns = args.end - args.start
    if len(run_rows) != expected_campaigns * len(STRATEGIES):
        raise AssertionError(len(run_rows))
    if len(transaction_rows) != expected_campaigns * len(STRATEGIES) * 36:
        raise AssertionError(len(transaction_rows))
    _write_csv(output / "campaign_runs.csv", run_rows)
    _write_csv(output / "campaign_transactions.csv", transaction_rows)
    if journal_rows:
        with (output / "certified_journals.jsonl").open("w", encoding="utf-8") as handle:
            for row in journal_rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    summary = aggregate(run_rows, transaction_rows)
    if args.start == 0 and args.end == 40:
        if summary["campaigns"] != 40 or summary["strategy_runs"] != 240 or summary["transaction_records"] != 8640:
            raise AssertionError(summary)
        if summary["strategies"]["certified"]["semantic_violations"] != 0:
            raise AssertionError("certified path returned a semantic violation")
        for strategy in STRATEGIES[1:]:
            if summary["strategies"][strategy]["violating_runs"] == 0:
                raise AssertionError(f"negative control did not violate: {strategy}")
    atomic_json(output / "campaign_summary.json", summary)

    events.sort(key=lambda x: (x["campaign"], STRATEGIES.index(x["strategy"]), x["attempt"]))
    with (output / "execution_events.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    execution = {
        "workers": args.workers,
        "timeout_seconds_per_strategy_run": args.timeout_seconds,
        "campaign_start": args.start,
        "campaign_end": args.end,
        "jobs": len(tasks),
        "attempts": len(events),
        "retries": len(events) - len(tasks),
        "timeouts": sum(int(event["timed_out"]) for event in events),
        "wall_seconds": round(time.perf_counter() - started, 6),
    }
    atomic_json(output / "matrix_execution.json", execution)
    if args.prune_runs:
        shutil.rmtree(output / "runs")
        shutil.rmtree(output / "jobs")
        shutil.rmtree(output / "logs")
    print(json.dumps({"summary": summary, "execution": execution}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
