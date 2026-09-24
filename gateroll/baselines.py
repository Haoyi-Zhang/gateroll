"""Information-projection baselines for the finite admission corpus."""
from __future__ import annotations

from .model import Manifest


def schema_only(manifest: Manifest) -> bool:
    return all(s.refine and s.bridge for s in manifest.services)


def version_negotiation(manifest: Manifest) -> bool:
    local = all(s.refine and s.bridge and s.session for s in manifest.services)
    directions = all(e.n2o and e.o2n for e in manifest.edges)
    return local and directions


def stop_the_world(manifest: Manifest) -> bool:
    return all(s.refine and s.auth and s.idem and (s.migrate or not s.stateful) for s in manifest.services)


def naive_rolling(manifest: Manifest) -> bool:
    return True


def health_gate(manifest: Manifest) -> bool:
    return True

BASELINES = {
    "schema_only": schema_only,
    "version_negotiation": version_negotiation,
    "stop_the_world": stop_the_world,
    "naive_rolling": naive_rolling,
    "health_gate": health_gate,
}
