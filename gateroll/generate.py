"""Deterministic 24-pair, 12,000-case corpus generator."""
from __future__ import annotations

import random
from itertools import combinations
from typing import Iterable

from .families import base_manifest
from .model import Manifest, apply_defects, atom_universe, repaired

CASES_PER_PAIR = 500


def generate_pair_cases(spec: dict, pair_index: int) -> list[Manifest]:
    declared = base_manifest(spec, pair_index)
    base = repaired(declared)
    universe = tuple(atom_universe(base))
    cases: list[Manifest] = []
    selected: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def add(defects: tuple[str, ...]) -> None:
        key = tuple(sorted(defects))
        if key not in seen and len(selected) < CASES_PER_PAIR:
            seen.add(key)
            selected.append(key)

    # Preserve the named controlled pair exactly and include the repaired control.
    add(tuple(declared.declared_defects))
    add(())

    # Every singleton obligation is represented.
    for atom in universe:
        add((atom,))

    # Bias a bounded tranche toward directional combinations. These exercise
    # order selection rather than merely making a terminal service invalid.
    directional = tuple(a for a in universe if a.endswith(":n2o") or a.endswith(":o2n"))
    direction_pool: list[tuple[str, ...]] = []
    for size in range(2, min(4, len(directional)) + 1):
        direction_pool.extend(combinations(directional, size))
    random.Random(4_001 + pair_index * 313).shuffle(direction_pool)
    for combo in direction_pool[:96]:
        add(tuple(combo))

    # Fill the remainder from all bounded defect combinations. The space is
    # much larger than 500 even for the smallest topology.
    pool: list[tuple[str, ...]] = []
    for size in range(2, 5):
        pool.extend(combinations(universe, size))
    random.Random(91_117 + pair_index * 10_007).shuffle(pool)
    for combo in pool:
        add(tuple(combo))
        if len(selected) == CASES_PER_PAIR:
            break
    if len(selected) != CASES_PER_PAIR:
        raise RuntimeError(f"insufficient distinct cases: {len(selected)}")

    for index, defects in enumerate(selected):
        cases.append(
            apply_defects(
                base, defects, case_id=f"pair-{pair_index:02d}-case-{index:03d}"
            )
        )
    return cases


def generate_all(specs: Iterable[dict]) -> list[Manifest]:
    out: list[Manifest] = []
    for pair_index, spec in enumerate(specs):
        out.extend(generate_pair_cases(spec, pair_index))
    return out
