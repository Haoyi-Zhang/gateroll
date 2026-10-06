#!/usr/bin/env python3
"""Recompute claim-facing tables from raw finite and campaign records."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

STRATEGY_ORDER = (
    "certified",
    "stop_the_world",
    "naive_rolling",
    "schema_only",
    "version_negotiation",
    "health_rollback",
)
DISPLAY = {
    "certified": "Certified GATEROLL",
    "stop_the_world": "Stop-the-world",
    "naive_rolling": "Naive rolling",
    "schema_only": "Schema-only",
    "version_negotiation": "Version negotiation",
    "health_rollback": "Health rollback",
    "health_gate": "Health gate",
}
DIMENSION_ORDER = (
    "authorization",
    "bridge",
    "session",
    "endpoint_refinement",
    "replay",
    "state_migration",
    "ordering",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    names = list(fieldnames or rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = (len(ordered) - 1) * q
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - rank) + ordered[hi] * (rank - lo)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.raw.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    finite = json.loads((raw / "finite" / "finite_summary.json").read_text(encoding="utf-8"))
    tiny = json.loads((raw / "tiny_exhaustive.json").read_text(encoding="utf-8"))
    campaigns = json.loads((raw / "campaigns" / "campaign_summary.json").read_text(encoding="utf-8"))
    matrix = json.loads((raw / "campaigns" / "matrix_execution.json").read_text(encoding="utf-8"))
    runs = read_csv(raw / "campaigns" / "campaign_runs.csv")
    transactions = read_csv(raw / "campaigns" / "campaign_transactions.csv")

    baseline_rows = []
    method_order = ("certified", "stop_the_world", "version_negotiation", "schema_only", "naive_rolling", "health_gate")
    for method in method_order:
        if method == "certified":
            fa = fb = 0
            correct = int(finite["case_count"])
        else:
            row = finite["baselines"][method]
            fa, fb, correct = int(row["false_admission"]), int(row["false_block"]), int(row["correct"])
        baseline_rows.append({
            "method": DISPLAY.get(method, method),
            "false_admission": fa,
            "false_block": fb,
            "correct": correct,
            "accuracy": round(correct / int(finite["case_count"]), 6),
        })
    write_csv(output / "finite_classification.csv", baseline_rows)

    ablation_rows = [{
        "removed_dimension": dimension.replace("_", " "),
        "new_false_admissions": int(finite["dimension_ablations"][dimension]),
    } for dimension in DIMENSION_ORDER]
    write_csv(output / "dimension_ablations.csv", ablation_rows)

    cost_rows = []
    for key, label, unit in (
        ("planner_ms", "Planner", "ms"),
        ("checker_ms", "Checker", "ms"),
        ("certificate_bytes", "Certificate", "bytes"),
    ):
        row = finite["costs"][key]
        cost_rows.append({
            "measure": label,
            "unit": unit,
            "sample_count": int(finite["costs"]["sample_count"]),
            "median": round(float(row["median"]), 6),
            "p95": round(float(row["p95"]), 6),
            "maximum": round(float(row["max"]), 6),
        })
    write_csv(output / "offline_costs.csv", cost_rows)

    runtime_rows = []
    for strategy in STRATEGY_ORDER:
        row = campaigns["strategies"][strategy]
        runtime_rows.append({
            "strategy": DISPLAY[strategy],
            "runs": int(row["runs"]),
            "unaffected_availability": round(float(row["mean_unaffected_availability"]), 6),
            "affected_availability": round(float(row["mean_affected_availability"]), 6),
            "overall_availability": round(float(row["mean_overall_availability"]), 6),
            "semantic_violations": int(row["semantic_violations"]),
            "violating_runs": int(row["violating_runs"]),
            "completed_expected_cutovers": int(row["completed_expected_cutovers"]),
            "expected_cutover_runs": int(row["expected_cutover_runs"]),
            "all_new_runs": int(row["all_new_runs"]),
            "blocked_runs": int(row["blocked_runs"]),
        })
    write_csv(output / "runtime_strategies.csv", runtime_rows)

    def group_runtime(field: str, out_name: str) -> None:
        groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in runs:
            groups[(row["strategy"], row[field])].append(row)
        out = []
        for strategy in STRATEGY_ORDER:
            values = sorted({key[1] for key in groups if key[0] == strategy})
            for value in values:
                rows = groups[(strategy, value)]
                out.append({
                    "strategy": DISPLAY[strategy],
                    field: value,
                    "runs": len(rows),
                    "semantic_violations": sum(int(x["semantic_violations"]) for x in rows),
                    "violating_runs": sum(int(x["violating_run"]) for x in rows),
                    "all_new_runs": sum(int(x["final_new"]) for x in rows),
                    "mean_unaffected_availability": round(statistics.fmean(float(x["availability_unaffected"]) for x in rows), 6),
                    "mean_affected_availability": round(statistics.fmean(float(x["availability_affected"]) for x in rows), 6),
                    "mean_overall_availability": round(statistics.fmean(float(x["availability_overall"]) for x in rows), 6),
                })
        write_csv(output / out_name, out)

    group_runtime("fault", "runtime_by_fault.csv")
    group_runtime("topology", "runtime_by_topology.csv")

    latency_rows = []
    by_strategy: dict[str, list[float]] = defaultdict(list)
    for row in transactions:
        if int(row["authorized"]) and int(row["available"]):
            by_strategy[row["strategy"]].append(float(row["latency_ms"]))
    for strategy in STRATEGY_ORDER:
        values = by_strategy[strategy]
        latency_rows.append({
            "strategy": DISPLAY[strategy],
            "available_authorized_responses": len(values),
            "median_latency_ms": round(statistics.median(values), 6),
            "p95_latency_ms": round(pct(values, 0.95), 6),
            "maximum_latency_ms": round(max(values), 6),
        })
    write_csv(output / "runtime_latency.csv", latency_rows)

    certified = [row for row in runs if row["strategy"] == "certified"]
    fault_rows = []
    for fault in sorted({row["fault"] for row in certified}):
        subset = [row for row in certified if row["fault"] == fault]
        fault_rows.append({
            "fault": fault,
            "runs": len(subset),
            "model_unsafe": sum(1 - int(x["model_admitted"]) for x in subset),
            "blocked": sum(1 - int(x["strategy_admitted"]) for x in subset),
            "all_new": sum(int(x["final_new"]) for x in subset),
            "semantic_violations": sum(int(x["semantic_violations"]) for x in subset),
            "mean_unaffected_availability": round(statistics.fmean(float(x["availability_unaffected"]) for x in subset), 6),
            "mean_affected_availability": round(statistics.fmean(float(x["availability_affected"]) for x in subset), 6),
            "block_reasons": ";".join(sorted({x["block_reason"] for x in subset if x["block_reason"]})),
        })
    write_csv(output / "certified_fault_outcomes.csv", fault_rows)

    semantic = {
        "finite": {
            "cases": int(finite["case_count"]),
            "families": int(finite["family_count"]),
            "release_pairs": int(finite["pair_count"]),
            "admitted": int(finite["admitted"]),
            "blocked": int(finite["blocked"]),
            "planner_oracle_agreement": int(finite["planner_oracle_agreement"]),
            "checker_accepts": int(finite["checker_accepts"]),
            "certificate_mutations": dict(finite["certificate_mutations"]),
            "baselines": finite["baselines"],
            "dimension_ablations": finite["dimension_ablations"],
        },
        "tiny_exhaustive": tiny,
        "runtime": {
            "campaigns": int(campaigns["campaigns"]),
            "topologies": int(campaigns["topologies"]),
            "fault_classes": int(campaigns["fault_classes"]),
            "strategy_runs": int(campaigns["strategy_runs"]),
            "transaction_records": int(campaigns["transaction_records"]),
            "strategies": campaigns["strategies"],
        },
    }
    (output / "semantic_summary.json").write_text(json.dumps(semantic, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    timing = {
        "offline_cost_sample": finite["costs"],
        "campaign_matrix": matrix,
        "runtime_latency": latency_rows,
        "run_rollout_ms": {
            strategy: {
                "median": round(statistics.median(float(x["rollout_ms"]) for x in runs if x["strategy"] == strategy), 6),
                "p95": round(pct([float(x["rollout_ms"]) for x in runs if x["strategy"] == strategy], 0.95), 6),
                "maximum": round(max(float(x["rollout_ms"]) for x in runs if x["strategy"] == strategy), 6),
            }
            for strategy in STRATEGY_ORDER
        },
    }
    (output / "timing_summary.json").write_text(json.dumps(timing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"semantic": semantic, "timing": timing}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
