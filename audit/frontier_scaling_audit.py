#!/usr/bin/env python3
"""Bounded exact-enumeration scale audit for the published O/B/N model.

The measurements are local observations, not machine-independent performance
claims.  Semantic counts are deterministic and are compared during release
verification; timings and RSS are intentionally excluded from semantic hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

O, B, N = 0, 1, 2


def decode_base3(index: int, n: int) -> List[int]:
    out = [0] * n
    for i in range(n):
        index, out[i] = divmod(index, 3)
    return out


def encode_base3(cfg: Sequence[int]) -> int:
    value = 0
    mul = 1
    for digit in cfg:
        value += digit * mul
        mul *= 3
    return value


def scenario_facts(n: int, scenario: str):
    # local facts: refine, bridge, migrate, auth, idem, session
    local = [[True] * 6 for _ in range(n)]
    if scenario == "repaired_chain":
        edges = [(i, i + 1) for i in range(n - 1)]
        edge = [[True, True] for _ in edges]
    elif scenario == "direction_cycle":
        edges = [(i, (i + 1) % n) for i in range(n)]
        edge = [[False, True] for _ in edges]  # every bridge/new caller is blocked by an old successor
    elif scenario == "single_bridge_defect":
        edges = [(i, i + 1) for i in range(n - 1)]
        edge = [[True, True] for _ in edges]
        local[n // 2][1] = False
    else:
        raise ValueError(scenario)
    return local, edges, edge


def exact_counts(n: int, scenario: str) -> Dict[str, int | bool]:
    local, edges, edge = scenario_facts(n, scenario)
    total = 3 ** n
    powers = [3 ** i for i in range(n)]
    closed = bytearray(total)

    def is_closed(cfg: Sequence[int]) -> bool:
        for i, mode in enumerate(cfg):
            refine, bridge, migrate, auth, idem, session = local[i]
            if mode == B and not (bridge and migrate and auth and idem and session):
                return False
            if mode == N and not (refine and auth and idem):
                return False
        for j, (src, dst) in enumerate(edges):
            n2o, o2n = edge[j]
            if cfg[src] in (B, N) and cfg[dst] == O and not n2o:
                return False
            if cfg[src] in (O, B) and cfg[dst] == N and not o2n:
                return False
        return True

    closed_count = 0
    for idx in range(total):
        cfg = decode_base3(idx, n)
        if is_closed(cfg):
            closed[idx] = 1
            closed_count += 1

    target = total - 1  # all digits are 2 in base 3
    viable = bytearray(total)
    if closed[target]:
        viable[target] = 1
        # Descending numeric order is a reverse topological order because every
        # O->B or B->N successor increases the base-3 index.
        for idx in range(target - 1, -1, -1):
            if not closed[idx]:
                continue
            cfg = decode_base3(idx, n)
            for i, mode in enumerate(cfg):
                if mode < N:
                    succ = idx + powers[i]
                    if closed[succ] and viable[succ]:
                        viable[idx] = 1
                        break
    frontier_count = int(sum(viable))
    return {
        "services": n,
        "configurations": total,
        "closed_configurations": closed_count,
        "frontier_configurations": frontier_count,
        "admitted": bool(viable[0]),
    }


def canonical_digest(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run(max_services: int = 12) -> dict:
    t0 = time.perf_counter()
    tracemalloc.start()
    rows = []
    for scenario in ("repaired_chain", "direction_cycle", "single_bridge_defect"):
        for n in range(2, max_services + 1):
            start = time.perf_counter()
            row = exact_counts(n, scenario)
            row["scenario"] = scenario
            row["elapsed_seconds"] = round(time.perf_counter() - start, 6)
            rows.append(row)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    semantic_rows = [
        {k: v for k, v in row.items() if k != "elapsed_seconds"}
        for row in rows
    ]
    # Structural expectations give this audit an executable oracle.
    failures = []
    for row in semantic_rows:
        n = int(row["services"])
        if row["scenario"] == "repaired_chain":
            if row["closed_configurations"] != 3 ** n or row["frontier_configurations"] != 3 ** n or not row["admitted"]:
                failures.append({"row": row, "reason": "repaired chain should expose the entire cube"})
        elif row["scenario"] == "direction_cycle":
            if row["admitted"]:
                failures.append({"row": row, "reason": "direction cycle unexpectedly admitted"})
        elif row["scenario"] == "single_bridge_defect":
            if row["admitted"]:
                failures.append({"row": row, "reason": "mandatory bridge defect unexpectedly admitted"})
    semantic = {
        "max_services": max_services,
        "scenario_count": 3,
        "rows": semantic_rows,
        "failures": failures,
    }
    return {
        "schema_version": 1,
        "complete": not failures,
        "semantic": semantic,
        "semantic_sha256": canonical_digest(semantic),
        "measurements": {
            "rows": rows,
            "total_elapsed_seconds": round(time.perf_counter() - t0, 6),
            "peak_tracemalloc_bytes": peak,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-services", type=int, default=12)
    args = ap.parse_args()
    if not (2 <= args.max_services <= 12):
        raise SystemExit("max-services must be in [2,12]")
    result = run(args.max_services)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not result["complete"]:
        raise SystemExit("frontier scaling audit failed structural expectations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
