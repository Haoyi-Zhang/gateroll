"""Reference planner: exact frontier, shortest schedule, and minimal defect witness."""
from __future__ import annotations

from collections import deque
from itertools import combinations
from typing import Any

from .model import (
    B,
    N,
    O,
    Manifest,
    apply_defects,
    enumerate_configs,
    false_atoms,
    is_closed,
    predecessors,
    repaired,
    successors,
)


def closed_set(manifest: Manifest) -> set[tuple[int, ...]]:
    return {c for c in enumerate_configs(manifest) if is_closed(manifest, c)}


def exact_frontier(manifest: Manifest) -> set[tuple[int, ...]]:
    closed = closed_set(manifest)
    target = (N,) * len(manifest.services)
    if target not in closed:
        return set()
    frontier = {target}
    queue = deque([target])
    while queue:
        current = queue.popleft()
        for prev in predecessors(current):
            if prev in closed and prev not in frontier:
                frontier.add(prev)
                queue.append(prev)
    return frontier


def shortest_schedule(manifest: Manifest, frontier: set[tuple[int, ...]] | None = None) -> list[tuple[int, ...]] | None:
    if frontier is None:
        frontier = exact_frontier(manifest)
    start = (O,) * len(manifest.services)
    target = (N,) * len(manifest.services)
    if start not in frontier or target not in frontier:
        return None
    parent: dict[tuple[int, ...], tuple[int, ...] | None] = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current == target:
            path: list[tuple[int, ...]] = []
            while current is not None:
                path.append(current)
                current = parent[current]  # type: ignore[assignment]
            return list(reversed(path))
        for nxt in successors(current):
            if nxt in frontier and nxt not in parent:
                parent[nxt] = current
                queue.append(nxt)
    return None


def schedulable(manifest: Manifest) -> bool:
    start = (O,) * len(manifest.services)
    return start in exact_frontier(manifest)


def minimum_blocking_witness(manifest: Manifest) -> tuple[str, ...]:
    defects = false_atoms(manifest)
    if not defects:
        return ()
    base = repaired(manifest)
    for size in range(1, len(defects) + 1):
        for subset in combinations(defects, size):
            candidate = apply_defects(base, subset)
            if not schedulable(candidate):
                return tuple(subset)
    return ()


def plan(manifest: Manifest) -> dict[str, Any]:
    frontier = exact_frontier(manifest)
    schedule = shortest_schedule(manifest, frontier)
    admitted = schedule is not None
    witness = () if admitted else minimum_blocking_witness(manifest)
    return {
        "case_id": manifest.case_id,
        "family": manifest.family,
        "pair": manifest.pair,
        "topology": manifest.topology,
        "services": list(manifest.names),
        "admitted": admitted,
        "frontier": [list(c) for c in sorted(frontier)],
        "schedule": [] if schedule is None else [list(c) for c in schedule],
        "witness": list(witness),
    }
