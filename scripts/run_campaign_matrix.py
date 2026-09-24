#!/usr/bin/env python3
"""Run the bounded campaign matrix in fresh process batches and merge evidence."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

STRATEGIES = (
    "certified",
    "stop_the_world",
    "naive_rolling",
    "schema_only",
    "version_negotiation",
    "health_rollback",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def weighted_strategy_summary(parts: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(part["runs"]) for part in parts)
    if not total:
        raise ValueError("empty strategy summary")
    def weighted(field: str) -> float:
        return sum(float(part[field]) * int(part["runs"]) for part in parts) / total
    return {
        "runs": total,
        "mean_unaffected_availability": weighted("mean_unaffected_availability"),
        "mean_affected_availability": weighted("mean_affected_availability"),
        "mean_overall_availability": weighted("mean_overall_availability"),
        "semantic_violations": sum(int(part["semantic_violations"]) for part in parts),
        "violating_runs": sum(int(part["violating_runs"]) for part in parts),
        "completed_expected_cutovers": sum(int(part["completed_expected_cutovers"]) for part in parts),
        "expected_cutover_runs": sum(int(part["expected_cutover_runs"]) for part in parts),
        "all_new_runs": sum(int(part["all_new_runs"]) for part in parts),
        "blocked_runs": sum(int(part["blocked_runs"]) for part in parts),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("results/raw/campaigns"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=40)
    parser.add_argument("--chunk-campaigns", type=int, default=2)
    parser.add_argument("--prune-runs", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise SystemExit("workers must be in [1,4]")
    if not 0 <= args.start < args.end <= 40:
        raise SystemExit("campaign range must lie within [0,40]")
    if not 1 <= args.chunk_campaigns <= 10:
        raise SystemExit("chunk-campaigns must be in [1,10]")

    root = args.artifact_root.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    chunk_summaries: list[dict[str, Any]] = []
    chunk_executions: list[dict[str, Any]] = []
    run_rows: list[dict[str, str]] = []
    transaction_rows: list[dict[str, str]] = []
    journal_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="gateroll-campaign-batches-", dir=output.parent) as temporary:
        temp_root = Path(temporary)
        for start in range(args.start, args.end, args.chunk_campaigns):
            end = min(args.end, start + args.chunk_campaigns)
            chunk = temp_root / f"campaigns-{start:02d}-{end:02d}"
            command = [
                sys.executable,
                "-B",
                str(root / "scripts" / "run_campaign_matrix_direct.py"),
                "--artifact-root", str(root),
                "--output", str(chunk),
                "--workers", str(args.workers),
                "--timeout-seconds", str(args.timeout_seconds),
                "--start", str(start),
                "--end", str(end),
                "--prune-runs",
            ]
            completed = subprocess.run(
                command,
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(root)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"campaign batch {start}:{end} failed with exit {completed.returncode}:\n"
                    f"{completed.stderr[-4000:]}"
                )
            run_rows.extend(read_csv(chunk / "campaign_runs.csv"))
            transaction_rows.extend(read_csv(chunk / "campaign_transactions.csv"))
            journals = chunk / "certified_journals.jsonl"
            if journals.exists():
                journal_rows.extend(json.loads(line) for line in journals.read_text(encoding="utf-8").splitlines() if line)
            events = chunk / "execution_events.jsonl"
            event_rows.extend(json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line)
            chunk_summaries.append(json.loads((chunk / "campaign_summary.json").read_text(encoding="utf-8")))
            chunk_executions.append(json.loads((chunk / "matrix_execution.json").read_text(encoding="utf-8")))
            print(f"completed campaigns {start:02d}-{end - 1:02d}", flush=True)

    expected_campaigns = args.end - args.start
    expected_runs = expected_campaigns * len(STRATEGIES)
    expected_transactions = expected_runs * 36
    if len(run_rows) != expected_runs or len(transaction_rows) != expected_transactions:
        raise AssertionError((len(run_rows), len(transaction_rows), expected_runs, expected_transactions))

    run_rows.sort(key=lambda row: (int(row["campaign_id"].split("-")[-1]), STRATEGIES.index(row["strategy"])))
    transaction_rows.sort(key=lambda row: (int(row["campaign_id"].split("-")[-1]), STRATEGIES.index(row["strategy"]), int(row["tx_index"])))
    journal_rows.sort(key=lambda row: (row["campaign_id"], int(row["sequence"])))
    event_rows.sort(key=lambda row: (int(row["campaign"]), STRATEGIES.index(row["strategy"]), int(row["attempt"])))

    output.mkdir(parents=True)
    write_csv(output / "campaign_runs.csv", run_rows)
    write_csv(output / "campaign_transactions.csv", transaction_rows)
    with (output / "certified_journals.jsonl").open("w", encoding="utf-8") as handle:
        for row in journal_rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    with (output / "execution_events.jsonl").open("w", encoding="utf-8") as handle:
        for row in event_rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    summary = {
        "campaigns": expected_campaigns,
        "strategy_runs": expected_runs,
        "transaction_records": expected_transactions,
        "topologies": len({row["topology"] for row in run_rows}),
        "fault_classes": len({row["fault"] for row in run_rows}),
        "strategies": {
            strategy: weighted_strategy_summary([part["strategies"][strategy] for part in chunk_summaries])
            for strategy in STRATEGIES
        },
    }
    if args.start == 0 and args.end == 40:
        if summary["campaigns"] != 40 or summary["strategy_runs"] != 240 or summary["transaction_records"] != 8640:
            raise AssertionError(summary)
        if summary["strategies"]["certified"]["semantic_violations"] != 0:
            raise AssertionError("certified path returned a semantic violation")
        for strategy in STRATEGIES[1:]:
            if summary["strategies"][strategy]["violating_runs"] == 0:
                raise AssertionError(f"negative control did not violate: {strategy}")
    (output / "campaign_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    execution = {
        "workers": args.workers,
        "timeout_seconds_per_strategy_run": args.timeout_seconds,
        "campaign_start": args.start,
        "campaign_end": args.end,
        "jobs": expected_runs,
        "attempts": sum(int(part["attempts"]) for part in chunk_executions),
        "retries": sum(int(part["retries"]) for part in chunk_executions),
        "timeouts": sum(int(part["timeouts"]) for part in chunk_executions),
        "batches": len(chunk_executions),
        "wall_seconds": round(time.perf_counter() - started, 6),
    }
    (output / "matrix_execution.json").write_text(json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "execution": execution}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
