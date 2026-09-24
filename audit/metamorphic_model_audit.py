#!/usr/bin/env python3
"""Independent semantic and metamorphic audit for the frozen GATEROLL model.

This module deliberately does not import the planner, certificate checker, or
runtime.  It re-expresses the published finite closure rules twice, using two
representations, and checks differential and metamorphic properties.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

O, B, N = 0, 1, 2
MODE_NAMES = ("O", "B", "N")
LOCAL_NAMES = ("refine", "bridge", "migrate", "auth", "idem", "session")


@dataclass(frozen=True)
class Model:
    n: int
    edges: Tuple[Tuple[int, int], ...]
    local: Tuple[Tuple[bool, bool, bool, bool, bool, bool], ...]
    edge: Tuple[Tuple[bool, bool], ...]  # n2o, o2n in edge order
    stateful: Tuple[bool, ...]


def closed_a(model: Model, cfg: Tuple[int, ...]) -> bool:
    """Tuple-oriented implementation of the four published closure rules."""
    for i, mode in enumerate(cfg):
        refine, bridge, migrate, auth, idem, session = model.local[i]
        if mode == B:
            if not (bridge and auth and idem and session):
                return False
            if model.stateful[i] and not migrate:
                return False
        elif mode == N:
            if not (refine and auth and idem):
                return False
    for j, (src, dst) in enumerate(model.edges):
        n2o, o2n = model.edge[j]
        if cfg[src] in (B, N) and cfg[dst] == O and not n2o:
            return False
        if cfg[src] in (O, B) and cfg[dst] == N and not o2n:
            return False
    return True


def frontier_a(model: Model) -> Tuple[set[Tuple[int, ...]], List[Tuple[int, ...]] | None]:
    configs = list(itertools.product((O, B, N), repeat=model.n))
    closed = {c for c in configs if closed_a(model, c)}
    target = (N,) * model.n
    if target not in closed:
        return set(), None
    predecessors: Dict[Tuple[int, ...], List[Tuple[int, ...]]] = {c: [] for c in closed}
    for c in closed:
        for i, mode in enumerate(c):
            if mode == N:
                prev = list(c)
                prev[i] = B
                p = tuple(prev)
                if p in closed:
                    predecessors[c].append(p)
            elif mode == B:
                prev = list(c)
                prev[i] = O
                p = tuple(prev)
                if p in closed:
                    predecessors[c].append(p)
    frontier = {target}
    q: deque[Tuple[int, ...]] = deque([target])
    while q:
        c = q.popleft()
        for p in predecessors[c]:
            if p not in frontier:
                frontier.add(p)
                q.append(p)
    start = (O,) * model.n
    if start not in frontier:
        return frontier, None
    q2: deque[Tuple[int, ...]] = deque([start])
    parent: Dict[Tuple[int, ...], Tuple[int, ...] | None] = {start: None}
    while q2:
        c = q2.popleft()
        if c == target:
            path: List[Tuple[int, ...]] = []
            cur: Tuple[int, ...] | None = c
            while cur is not None:
                path.append(cur)
                cur = parent[cur]
            path.reverse()
            return frontier, path
        for i, mode in enumerate(c):
            if mode < N:
                nxt = list(c)
                nxt[i] += 1
                t = tuple(nxt)
                if t in frontier and t not in parent:
                    parent[t] = c
                    q2.append(t)
    raise AssertionError("frontier contained start but no path was reconstructed")


# A separate dictionary-oriented implementation.  It intentionally avoids
# calling closed_a/frontier_a and explores only forward schedules.
def schedulable_b(model: Model) -> bool:
    names = tuple(range(model.n))
    local_maps = [dict(zip(LOCAL_NAMES, vals)) for vals in model.local]
    edge_maps = {
        pair: {"new_to_old": vals[0], "old_to_new": vals[1]}
        for pair, vals in zip(model.edges, model.edge)
    }

    def ok(state: Mapping[int, str]) -> bool:
        for i in names:
            mode = state[i]
            facts = local_maps[i]
            if mode == "bridge":
                required = ("bridge", "auth", "idem", "session")
                if any(not facts[k] for k in required):
                    return False
                if model.stateful[i] and not facts["migrate"]:
                    return False
            elif mode == "new":
                if any(not facts[k] for k in ("refine", "auth", "idem")):
                    return False
        for (src, dst), facts in edge_maps.items():
            sm, dm = state[src], state[dst]
            if sm in ("bridge", "new") and dm == "old" and not facts["new_to_old"]:
                return False
            if sm in ("old", "bridge") and dm == "new" and not facts["old_to_new"]:
                return False
        return True

    start = {i: "old" for i in names}
    target = tuple("new" for _ in names)
    if not ok(start):
        return False
    stack = [start]
    visited = {tuple(start[i] for i in names)}
    while stack:
        state = stack.pop()
        key = tuple(state[i] for i in names)
        if key == target:
            return True
        for i in names:
            if state[i] == "new":
                continue
            nxt = dict(state)
            nxt[i] = "bridge" if state[i] == "old" else "new"
            nk = tuple(nxt[j] for j in names)
            if nk not in visited and ok(nxt):
                visited.add(nk)
                stack.append(nxt)
    return False


def model_from_mask(mask: int) -> Model:
    # Two stateful services, one directed edge 0 -> 1, fourteen independent facts.
    bits = [(mask >> i) & 1 == 1 for i in range(14)]
    local = (tuple(bits[0:6]), tuple(bits[6:12]))
    edge = ((bits[12], bits[13]),)
    return Model(2, ((0, 1),), local, edge, (True, True))


def repair_bit(model: Model, bit: int) -> Model:
    local = [list(v) for v in model.local]
    edges = [list(v) for v in model.edge]
    if bit < 12:
        local[bit // 6][bit % 6] = True
    else:
        edges[0][bit - 12] = True
    return Model(model.n, model.edges, tuple(tuple(v) for v in local), tuple(tuple(v) for v in edges), model.stateful)


def permute_model(model: Model, perm: Sequence[int]) -> Model:
    """Rename service i to perm[i], preserving the directed graph and facts."""
    inv = [0] * model.n
    for old, new in enumerate(perm):
        inv[new] = old
    new_local = tuple(model.local[inv[new]] for new in range(model.n))
    new_stateful = tuple(model.stateful[inv[new]] for new in range(model.n))
    edge_fact_by_pair = {e: f for e, f in zip(model.edges, model.edge)}
    new_pairs_with_facts = []
    for (src, dst), facts in edge_fact_by_pair.items():
        new_pairs_with_facts.append(((perm[src], perm[dst]), facts))
    new_pairs_with_facts.sort()
    return Model(
        model.n,
        tuple(p for p, _ in new_pairs_with_facts),
        new_local,
        tuple(f for _, f in new_pairs_with_facts),
        new_stateful,
    )


def random_model(rng: random.Random, n: int, trial: int) -> Model:
    # Rotate among chain, ring, and star to vary graph structure deterministically.
    shape = trial % 3
    if shape == 0:
        edges = [(i, i + 1) for i in range(n - 1)]
    elif shape == 1:
        edges = [(i, (i + 1) % n) for i in range(n)]
    else:
        edges = [(0, i) for i in range(1, n)] + [(i, 0) for i in range(1, n) if i % 2 == 0]
    local = []
    for _ in range(n):
        local.append(tuple(rng.random() < 0.82 for _ in range(6)))
    edge = [tuple(rng.random() < 0.78 for _ in range(2)) for _ in edges]
    stateful = tuple(rng.random() < 0.75 for _ in range(n))
    return Model(n, tuple(edges), tuple(local), tuple(edge), stateful)


def minimal_blocking_subset(model: Model, false_positions: Sequence[int]) -> Tuple[int, ...] | None:
    # Start from an all-repaired two-service model and reapply defect subsets.
    repaired = model_from_mask((1 << 14) - 1)
    for k in range(1, len(false_positions) + 1):
        for subset in itertools.combinations(false_positions, k):
            m = repaired
            local = [list(v) for v in m.local]
            edge = [list(v) for v in m.edge]
            for bit in subset:
                if bit < 12:
                    local[bit // 6][bit % 6] = False
                else:
                    edge[0][bit - 12] = False
            candidate = Model(2, ((0, 1),), tuple(tuple(v) for v in local), tuple(tuple(v) for v in edge), (True, True))
            if not schedulable_b(candidate):
                return tuple(subset)
    return None


def canonical_digest(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def run(seed: int = 20260916) -> dict:
    t0 = time.perf_counter()
    admitted = 0
    differential_disagreements = 0
    frontier_invariant_failures = 0
    monotonicity_failures = 0
    permutation_failures = 0
    path_length_failures = 0
    blocked_masks: List[int] = []

    swap = (1, 0)
    for mask in range(1 << 14):
        model = model_from_mask(mask)
        frontier, path = frontier_a(model)
        a = path is not None
        b = schedulable_b(model)
        if a != b:
            differential_disagreements += 1
        if a:
            admitted += 1
            if len(path or []) != 5:  # four one-mode steps for two services
                path_length_failures += 1
        else:
            blocked_masks.append(mask)
        target = (N, N)
        for cfg in frontier:
            if not closed_a(model, cfg):
                frontier_invariant_failures += 1
                break
            # A frontier member must itself have a forward path to target.
            sub = Model(model.n, model.edges, model.local, model.edge, model.stateful)
            # Search forward from cfg under closed_a.
            stack = [cfg]
            seen = {cfg}
            reached = False
            while stack:
                cur = stack.pop()
                if cur == target:
                    reached = True
                    break
                for i, mode in enumerate(cur):
                    if mode < N:
                        nxt = list(cur); nxt[i] += 1; nxt_t = tuple(nxt)
                        if nxt_t not in seen and closed_a(sub, nxt_t):
                            seen.add(nxt_t); stack.append(nxt_t)
            if not reached:
                frontier_invariant_failures += 1
                break
        if a:
            for bit in range(14):
                if not ((mask >> bit) & 1):
                    if frontier_a(repair_bit(model, bit))[1] is None:
                        monotonicity_failures += 1
        pm = permute_model(model, swap)
        if (frontier_a(pm)[1] is not None) != a:
            permutation_failures += 1

    # Validate minimum-cardinality/subset-minimal blockers on a deterministic sample.
    witness_checks = 0
    witness_failures = 0
    for mask in blocked_masks[::max(1, len(blocked_masks) // 256)][:256]:
        false_positions = [i for i in range(14) if not ((mask >> i) & 1)]
        witness = minimal_blocking_subset(model_from_mask(mask), false_positions)
        if witness is None:
            witness_failures += 1
            continue
        witness_checks += 1
        # Reconstruct and verify deletion minimality with the other implementation.
        for removed in witness:
            remaining = tuple(x for x in witness if x != removed)
            repaired = model_from_mask((1 << 14) - 1)
            local = [list(v) for v in repaired.local]
            edge = [list(v) for v in repaired.edge]
            for bit in remaining:
                if bit < 12: local[bit // 6][bit % 6] = False
                else: edge[0][bit - 12] = False
            candidate = Model(2, ((0, 1),), tuple(tuple(v) for v in local), tuple(tuple(v) for v in edge), (True, True))
            if not schedulable_b(candidate):
                witness_failures += 1
                break

    rng = random.Random(seed)
    random_cases = 0
    random_disagreements = 0
    random_permutation_failures = 0
    by_n = {}
    for n in range(3, 9):
        trials = 128
        n_admitted = 0
        for trial in range(trials):
            model = random_model(rng, n, trial)
            a = frontier_a(model)[1] is not None
            b = schedulable_b(model)
            random_cases += 1
            n_admitted += int(a)
            if a != b:
                random_disagreements += 1
            perm = list(range(n)); rng.shuffle(perm)
            pm = permute_model(model, perm)
            if (frontier_a(pm)[1] is not None) != a:
                random_permutation_failures += 1
        by_n[str(n)] = {"cases": trials, "admitted": n_admitted}

    semantic = {
        "model": "frozen O/B/N closure with six local and two directional edge obligations",
        "exhaustive_two_service_assignments": 1 << 14,
        "exhaustive_two_service_admitted": admitted,
        "exhaustive_two_service_blocked": (1 << 14) - admitted,
        "differential_disagreements": differential_disagreements,
        "frontier_invariant_failures": frontier_invariant_failures,
        "repair_monotonicity_failures": monotonicity_failures,
        "permutation_invariance_failures": permutation_failures,
        "shortest_path_length_failures": path_length_failures,
        "minimal_witness_checks": witness_checks,
        "minimal_witness_failures": witness_failures,
        "random_topology_cases": random_cases,
        "random_differential_disagreements": random_disagreements,
        "random_permutation_failures": random_permutation_failures,
        "random_cases_by_service_count": by_n,
        "seed": seed,
    }
    failures = sum(
        semantic[k]
        for k in (
            "differential_disagreements",
            "frontier_invariant_failures",
            "repair_monotonicity_failures",
            "permutation_invariance_failures",
            "shortest_path_length_failures",
            "minimal_witness_failures",
            "random_differential_disagreements",
            "random_permutation_failures",
        )
    )
    result = {
        "schema_version": 1,
        "complete": failures == 0,
        "semantic": semantic,
        "semantic_sha256": canonical_digest(semantic),
        "elapsed_seconds": round(time.perf_counter() - t0, 6),
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20260916)
    args = ap.parse_args()
    result = run(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not result["complete"]:
        raise SystemExit("metamorphic model audit found a discrepancy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
