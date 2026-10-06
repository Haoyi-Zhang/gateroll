#!/usr/bin/env python3
"""Recount fresh RPC evidence and check the observed serialized replica premise."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from gateroll.rpcutil import atomic_json
from gateroll.portable_runtime import filesystem_path, plain_path, private_path


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def inspect(directory: Path, historical: Path) -> dict:
    directory = filesystem_path(directory)
    runs = csv_rows(directory / "campaign_runs.csv")
    transactions = csv_rows(directory / "campaign_transactions.csv")
    summary = json.loads((directory / "campaign_summary.json").read_text(encoding="utf-8"))
    baseline = json.loads(historical.read_text(encoding="utf-8"))
    errors = []
    certified = Counter({field: 0 for field in (
        "attempts", "retry_attempts", "delay_tagged_requests", "service_timeout_responses",
        "replica_snapshots", "successful_replica_observations", "successful_replica_disagreements",
        "unavailable_or_denied_replica_disagreements",
    )})
    cleanup = Counter()
    calls = 0
    for run in runs:
        campaign, strategy = run["campaign_id"], run["strategy"]
        selected = [row for row in transactions if row["campaign_id"] == campaign and row["strategy"] == strategy]
        key = f"{int(campaign.split('-')[-1]):02d}-{strategy}"
        jobs = sorted((directory / "jobs").glob(f"{key}-attempt-*.json"))
        if not jobs:
            errors.append(f"{key}:missing-job")
            continue
        payload = json.loads(jobs[-1].read_text(encoding="utf-8"))
        cleanup.update(payload["harness_cleanup"])
        path = directory / "runs" / jobs[-1].stem / "rpc_observations.jsonl"
        trace = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        calls += len(trace)
        attempts = []
        for entry in trace:
            if entry["attempt"] == 1:
                attempts.append([entry])
            else:
                attempts[-1].append(entry)
        if len(selected) != 36 or len(attempts) != 36 or len(trace) != int(run["proxy_calls"]):
            errors.append(f"{key}:record-count")
            continue
        if sum(int(row["semantic_violation"]) for row in selected) != int(run["semantic_violations"]):
            errors.append(f"{key}:violation-total")
        for label, predicate in (("overall", lambda row: True),
                                 ("affected", lambda row: row["key_class"] == "affected"),
                                 ("unaffected", lambda row: row["key_class"] == "unaffected")):
            group = [row for row in selected if int(row["authorized"]) and predicate(row)]
            actual = sum(int(row["available"]) for row in group) / len(group)
            if abs(actual - float(run[f"availability_{label}"])) > 1e-12:
                errors.append(f"{key}:availability-{label}")
        # Recompute labels from actual final-attempt replies, not summary rows.
        expected = {}
        for row, sequence in zip(selected, attempts):
            entry = sequence[-1]
            request, response = entry["request"], entry["response"]
            target, record_key = request["target"], request["key"]
            state_key = (target, record_key)
            if state_key not in expected:
                # Independent fixture role order (not key-sorted config order).
                names = {
                    "chain3": ("gateway", "ledger", "store"),
                    "diamond4": ("gateway", "auth", "ledger", "store"),
                    "fanout4": ("gateway", "ledger", "queue", "store"),
                    "cycle5": ("gateway", "profile", "ledger", "queue", "store"),
                }[row["topology"]]
                expected[state_key] = 10 * (names.index(target) + 1) + {"a0": 1, "a1": 2, "u0": 3, "u1": 4}[record_key]
            authorized = request["op"] == "read" or request["role"] in ("writer", "admin")
            duplicate = bool(request.get("logical_duplicate"))
            value = expected[state_key] + (int(request.get("delta", 1))
                                          if request["op"] == "inc" and authorized and not duplicate else 0)
            available = bool(response.get("available"))
            violation = False
            if authorized and available:
                violation = bool(response.get("denied") or not response.get("ok") or
                                 not response.get("shape_ok", True) or not response.get("protocol_ok", True) or
                                 response.get("value") != value)
                if not violation and request["op"] == "inc" and not duplicate:
                    expected[state_key] = value
            elif not authorized and available and not response.get("denied"):
                violation = True
            if (int(violation) != int(row["semantic_violation"]) or value != int(row["expected_value"]) or
                    int(authorized and available) != int(row["available"]) or
                    row["target"] != target or int(row["attempts"]) != len(sequence)):
                errors.append(f"{key}:reply-label:{row['tx_index']}")
        if strategy == "certified":
            certified["attempts"] += len(trace)
            certified["retry_attempts"] += sum(e["attempt"] > 1 for e in trace)
            for entry in trace:
                response = entry["response"]
                certified["delay_tagged_requests"] += bool(entry["request"].get("delay_after_ms"))
                certified["service_timeout_responses"] += response.get("error") == "service-timeout"
                if "replicas" not in entry:
                    continue
                old, new = (entry["replicas"][version] for version in ("old", "new"))
                agree = old["values"] == new["values"] and set(old["receipts"]) == set(new["receipts"])
                certified["replica_snapshots"] += 1
                if response.get("available") and response.get("ok") and not response.get("denied"):
                    certified["successful_replica_observations"] += 1
                    if not agree:
                        certified["successful_replica_disagreements"] += 1
                elif not agree:
                    certified["unavailable_or_denied_replica_disagreements"] += 1
    totals = {strategy: sum(int(row["semantic_violation"]) for row in transactions
                            if row["strategy"] == strategy) for strategy in summary["strategies"]}
    if any(totals[s] != summary["strategies"][s]["semantic_violations"] for s in totals):
        errors.append("strategy-total")
    if certified["successful_replica_disagreements"] or cleanup["residual_after"]:
        errors.append("certified-replica-or-child-cleanup")
    return {
        "schema": "gateroll.fresh-runtime-recount.v1", "pass": not errors, "errors": errors,
        "runs": len(runs), "transactions": len(transactions), "rpc_attempts": calls,
        "violation_totals": totals, "certified_observations": dict(certified),
        "harness_cleanup_totals": dict(cleanup), "historical_campaign_summary_match": summary == baseline,
        "premise_scope": "Observed replica values and receipt-ID sets at serialized target snapshots; no concurrent proof.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaigns", type=Path, required=True)
    parser.add_argument("--historical-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = inspect(args.campaigns.resolve(), args.historical_summary.resolve())
    atomic_json(args.output, result)
    if args.manifest is not None:
        root = Path(__file__).resolve().parents[1]
        manifest_path = private_path(root, args.manifest)
        if manifest_path.exists():
            raise FileExistsError(manifest_path)
        anchor = filesystem_path(root / "results/runtime_reproductions")
        files = sorted(str(plain_path(path)) for path in anchor.rglob("*") if path.is_file())
        atomic_json(manifest_path, {"scope": str(plain_path(anchor)), "file_count": len(files), "files": files})
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
