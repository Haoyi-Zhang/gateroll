"""Complete enumeration of a frozen two-service, eight-atom fragment."""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from .checker import check
from .model import Edge, Manifest, Service, apply_defects, repaired
from .oracle import admitted as oracle_admitted
from .planner import plan

ATOMS = (
    "service:a:refine",
    "service:a:bridge",
    "service:a:auth",
    "service:b:refine",
    "service:b:bridge",
    "service:b:auth",
    "edge:a>b:n2o",
    "edge:a>b:o2n",
)


def run(output_path: Path) -> dict:
    base = Manifest(
        case_id="tiny",
        family="frozen tiny fragment",
        pair="complete enumeration",
        topology="two-service edge",
        services=(Service("a", True), Service("b", True)),
        edges=(Edge("a", "b"),),
    )
    total = 0
    admitted = 0
    blocked = 0
    for mask in range(1 << len(ATOMS)):
        defects = tuple(ATOMS[i] for i in range(len(ATOMS)) if mask & (1 << i))
        manifest = apply_defects(repaired(base), defects, case_id=f"tiny-{mask:03d}")
        cert = plan(manifest)
        checked = check(manifest, cert)
        oracle = oracle_admitted(manifest)
        if cert["admitted"] != oracle or not checked["accepted"]:
            raise AssertionError(f"tiny disagreement at mask {mask}")
        total += 1
        if oracle:
            admitted += 1
        else:
            blocked += 1
    summary = {
        "atom_count": len(ATOMS),
        "models": total,
        "admitted": admitted,
        "blocked": blocked,
        "planner_oracle_checker_agreement": total,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
