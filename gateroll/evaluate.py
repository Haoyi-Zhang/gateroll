"""Finite-corpus evaluation, ablations, cost sample, and certificate mutations."""
from __future__ import annotations

import csv
import json
import math
import statistics
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from .baselines import BASELINES
from .checker import CertificateError, check
from .families import load_pair_specs
from .generate import generate_all
from .model import Manifest, apply_defects, atom_universe, false_atoms, repaired
from .oracle import admitted as oracle_admitted
from .planner import plan

DIMENSION_FIELD = {
    "authorization": {"auth"},
    "bridge": {"bridge"},
    "session": {"session"},
    "endpoint_refinement": {"refine"},
    "replay": {"idem"},
    "state_migration": {"migrate"},
    "ordering": {"n2o", "o2n"},
}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def _ignore_dimension(manifest: Manifest, fields: set[str]) -> Manifest:
    keep = []
    for atom in false_atoms(manifest):
        field = atom.rsplit(":", 1)[-1]
        if field not in fields:
            keep.append(atom)
    return apply_defects(repaired(manifest), keep, case_id=manifest.case_id)


def _mutate_certificate(manifest: Manifest, cert: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    mutations: list[tuple[str, dict[str, Any]]] = []
    flipped = deepcopy(cert)
    flipped["admitted"] = not bool(flipped["admitted"])
    mutations.append(("flip-admission", flipped))

    frontier = deepcopy(cert)
    if frontier["frontier"]:
        frontier["frontier"] = frontier["frontier"][:-1]
    else:
        frontier["frontier"] = [[0] * len(frontier["services"])]
    mutations.append(("alter-frontier", frontier))

    schedule = deepcopy(cert)
    if cert["admitted"] and len(schedule["schedule"]) >= 2:
        bad = schedule["schedule"][0][:]
        if len(bad) >= 2:
            bad[0] = min(2, bad[0] + 1)
            bad[1] = min(2, bad[1] + 1)
        else:
            bad[0] = 2
        schedule["schedule"][1] = bad
    else:
        schedule["schedule"] = [[0] * len(cert["services"])]
    mutations.append(("invalid-schedule-payload", schedule))

    witness = deepcopy(cert)
    if cert["admitted"]:
        witness["witness"] = [next(iter(atom_universe(manifest)))]
    else:
        existing = set(witness["witness"])
        candidate = next(atom for atom in atom_universe(manifest) if atom not in existing)
        witness["witness"].append(candidate)
    mutations.append(("invalid-witness-payload", witness))
    return mutations


def run(input_dir: Path, output_dir: Path, *, write_cases: bool = True) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = load_pair_specs(input_dir)
    cases = generate_all(specs)
    if len(cases) != 12_000:
        raise AssertionError(f"expected 12000 cases, got {len(cases)}")

    case_path = output_dir / "generated_cases.jsonl"
    decision_path = output_dir / "case_decisions.csv"
    cert_dir = output_dir / "certificates"
    cert_dir.mkdir(exist_ok=True)

    baseline_counts = {name: {"false_admission": 0, "false_block": 0, "correct": 0} for name in BASELINES}
    admitted_count = 0
    blocked_count = 0
    checker_accepts = 0
    agreement = 0
    dimension_false_admissions = {name: 0 for name in DIMENSION_FIELD}
    sampled_planner_ms: list[float] = []
    sampled_checker_ms: list[float] = []
    sampled_cert_bytes: list[int] = []
    rows: list[dict[str, Any]] = []
    representative: dict[int, tuple[Manifest, dict[str, Any]]] = {}

    case_file = case_path.open("w", encoding="utf-8") if write_cases else None
    try:
        for index, manifest in enumerate(cases):
            if case_file is not None:
                case_file.write(json.dumps(manifest.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")

            measure = index % 10 == 0  # exactly 1,200 cases
            if measure:
                t0 = time.perf_counter_ns()
            cert = plan(manifest)
            if measure:
                t1 = time.perf_counter_ns()
            checked = check(manifest, cert)
            if measure:
                t2 = time.perf_counter_ns()
                sampled_planner_ms.append((t1 - t0) / 1_000_000)
                sampled_checker_ms.append((t2 - t1) / 1_000_000)
                sampled_cert_bytes.append(len(json.dumps(cert, sort_keys=True, separators=(",", ":")).encode("utf-8")))

            oracle = oracle_admitted(manifest)
            if bool(cert["admitted"]) == oracle:
                agreement += 1
            else:
                raise AssertionError(f"planner/oracle disagreement: {manifest.case_id}")
            if checked["accepted"]:
                checker_accepts += 1
            if oracle:
                admitted_count += 1
            else:
                blocked_count += 1

            for name, decision in BASELINES.items():
                predicted = bool(decision(manifest))
                if predicted and not oracle:
                    baseline_counts[name]["false_admission"] += 1
                elif not predicted and oracle:
                    baseline_counts[name]["false_block"] += 1
                else:
                    baseline_counts[name]["correct"] += 1

            if not oracle:
                for dimension, fields in DIMENSION_FIELD.items():
                    if oracle_admitted(_ignore_dimension(manifest, fields)):
                        dimension_false_admissions[dimension] += 1

            pair_index = index // 500
            if index % 500 == 0:
                representative[pair_index] = (manifest, cert)
                (cert_dir / f"pair-{pair_index:02d}.json").write_text(
                    json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )

            row = {
                "case_id": manifest.case_id,
                "family": manifest.family,
                "pair": manifest.pair,
                "topology": manifest.topology,
                "defect_count": len(manifest.declared_defects),
                "admitted": int(oracle),
                "frontier_states": len(cert["frontier"]),
                "schedule_steps": max(0, len(cert["schedule"]) - 1),
                "witness_size": len(cert["witness"]),
            }
            for name, decision in BASELINES.items():
                row[name] = int(bool(decision(manifest)))
            rows.append(row)
    finally:
        if case_file is not None:
            case_file.close()

    with decision_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    mutation_rows: list[dict[str, Any]] = []
    for pair_index, (manifest, cert) in sorted(representative.items()):
        for mutation_name, mutated in _mutate_certificate(manifest, cert):
            rejected = False
            error = ""
            try:
                check(manifest, mutated)
            except (CertificateError, ValueError) as exc:
                rejected = True
                error = str(exc)
            mutation_rows.append({
                "pair_index": pair_index,
                "case_id": manifest.case_id,
                "mutation": mutation_name,
                "rejected": rejected,
                "reason": error,
            })
    if not all(row["rejected"] for row in mutation_rows):
        raise AssertionError("checker accepted a certificate mutation")
    (output_dir / "certificate_mutations.json").write_text(
        json.dumps(mutation_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    costs = {
        "sample_count": len(sampled_planner_ms),
        "planner_ms": {
            "median": statistics.median(sampled_planner_ms),
            "p95": _percentile(sampled_planner_ms, 0.95),
            "max": max(sampled_planner_ms),
        },
        "checker_ms": {
            "median": statistics.median(sampled_checker_ms),
            "p95": _percentile(sampled_checker_ms, 0.95),
            "max": max(sampled_checker_ms),
        },
        "certificate_bytes": {
            "median": statistics.median(sampled_cert_bytes),
            "p95": _percentile([float(x) for x in sampled_cert_bytes], 0.95),
            "max": max(sampled_cert_bytes),
        },
    }
    summary = {
        "case_count": len(cases),
        "pair_count": len(specs),
        "family_count": len({s["family"] for s in specs}),
        "planner_oracle_agreement": agreement,
        "checker_accepts": checker_accepts,
        "admitted": admitted_count,
        "blocked": blocked_count,
        "baselines": baseline_counts,
        "dimension_ablations": dimension_false_admissions,
        "certificate_mutations": {
            "count": len(mutation_rows),
            "rejected": sum(int(row["rejected"]) for row in mutation_rows),
        },
        "costs": costs,
    }
    (output_dir / "finite_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
