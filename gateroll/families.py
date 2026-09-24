"""Controlled release-pair construction from normalized public vocabularies."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Edge, Manifest, Service, apply_defects, repaired

TOPOLOGIES: dict[str, dict[str, Any]] = {
    "chain3": {
        "services": (("gateway", False), ("ledger", True), ("store", True)),
        "edges": (("gateway", "ledger"), ("ledger", "store")),
    },
    "diamond4": {
        "services": (("gateway", False), ("auth", False), ("ledger", True), ("store", True)),
        "edges": (("gateway", "auth"), ("gateway", "ledger"), ("auth", "store"), ("ledger", "store")),
    },
    "fanout4": {
        "services": (("gateway", False), ("ledger", True), ("queue", True), ("store", True)),
        "edges": (("gateway", "ledger"), ("gateway", "queue"), ("ledger", "store"), ("queue", "store")),
    },
    "cycle5": {
        "services": (("gateway", False), ("profile", True), ("ledger", True), ("queue", True), ("store", True)),
        "edges": (("gateway", "ledger"), ("ledger", "store"), ("store", "gateway"), ("gateway", "profile"), ("profile", "queue"), ("queue", "store")),
    },
}


def load_pair_specs(input_dir: Path) -> list[dict[str, Any]]:
    return json.loads((input_dir / "release_pairs.json").read_text(encoding="utf-8"))["pairs"]


def base_manifest(spec: dict[str, Any], pair_index: int) -> Manifest:
    topo = TOPOLOGIES[spec["topology"]]
    base = Manifest(
        case_id=f"pair-{pair_index:02d}-default",
        family=spec["family"],
        pair=spec["pair"],
        topology=spec["topology"],
        services=tuple(Service(name=name, stateful=stateful) for name, stateful in topo["services"]),
        edges=tuple(Edge(src=src, dst=dst) for src, dst in topo["edges"]),
    )
    return apply_defects(base, spec.get("default_defects", ()))
