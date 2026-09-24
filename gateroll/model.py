"""Finite contract model for mixed-version rollout planning.

The model is intentionally explicit and bounded.  It does not inspect service
programs; it checks consequences of a supplied manifest.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
from typing import Any, Iterable, Iterator

O, B, N = 0, 1, 2
MODE_NAME = {O: "O", B: "B", N: "N"}
LOCAL_ATOMS = ("refine", "bridge", "migrate", "auth", "idem", "session")
EDGE_ATOMS = ("n2o", "o2n")


@dataclass(frozen=True)
class Service:
    name: str
    stateful: bool = True
    refine: bool = True
    bridge: bool = True
    migrate: bool = True
    auth: bool = True
    idem: bool = True
    session: bool = True


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    n2o: bool = True
    o2n: bool = True


@dataclass(frozen=True)
class Manifest:
    case_id: str
    family: str
    pair: str
    topology: str
    services: tuple[Service, ...]
    edges: tuple[Edge, ...]
    declared_defects: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.services)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "family": self.family,
            "pair": self.pair,
            "topology": self.topology,
            "services": [s.__dict__ for s in self.services],
            "edges": [e.__dict__ for e in self.edges],
            "declared_defects": list(self.declared_defects),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        return cls(
            case_id=str(data["case_id"]),
            family=str(data["family"]),
            pair=str(data["pair"]),
            topology=str(data["topology"]),
            services=tuple(Service(**x) for x in data["services"]),
            edges=tuple(Edge(**x) for x in data["edges"]),
            declared_defects=tuple(data.get("declared_defects", ())),
        )


def local_atom(service: str, field: str) -> str:
    if field not in LOCAL_ATOMS:
        raise ValueError(f"unknown local atom: {field}")
    return f"service:{service}:{field}"


def edge_atom(src: str, dst: str, field: str) -> str:
    if field not in EDGE_ATOMS:
        raise ValueError(f"unknown edge atom: {field}")
    return f"edge:{src}>{dst}:{field}"


def atom_universe(manifest: Manifest) -> tuple[str, ...]:
    atoms: list[str] = []
    for service in manifest.services:
        for field in LOCAL_ATOMS:
            if field == "migrate" and not service.stateful:
                continue
            atoms.append(local_atom(service.name, field))
    for edge in manifest.edges:
        for field in EDGE_ATOMS:
            atoms.append(edge_atom(edge.src, edge.dst, field))
    return tuple(atoms)


def false_atoms(manifest: Manifest) -> tuple[str, ...]:
    out: list[str] = []
    for service in manifest.services:
        for field in LOCAL_ATOMS:
            if field == "migrate" and not service.stateful:
                continue
            if not getattr(service, field):
                out.append(local_atom(service.name, field))
    for edge in manifest.edges:
        for field in EDGE_ATOMS:
            if not getattr(edge, field):
                out.append(edge_atom(edge.src, edge.dst, field))
    return tuple(sorted(out))


def repaired(manifest: Manifest) -> Manifest:
    return replace(
        manifest,
        services=tuple(
            Service(name=s.name, stateful=s.stateful) for s in manifest.services
        ),
        edges=tuple(Edge(src=e.src, dst=e.dst) for e in manifest.edges),
        declared_defects=(),
    )


def apply_defects(manifest: Manifest, defects: Iterable[str], *, case_id: str | None = None) -> Manifest:
    defects_set = set(defects)
    services: list[Service] = []
    for service in manifest.services:
        values = service.__dict__.copy()
        for field in LOCAL_ATOMS:
            if local_atom(service.name, field) in defects_set:
                values[field] = False
        services.append(Service(**values))
    edges: list[Edge] = []
    for edge in manifest.edges:
        values = edge.__dict__.copy()
        for field in EDGE_ATOMS:
            if edge_atom(edge.src, edge.dst, field) in defects_set:
                values[field] = False
        edges.append(Edge(**values))
    known = set(atom_universe(manifest))
    unknown = defects_set - known
    if unknown:
        raise ValueError(f"unknown defect atoms: {sorted(unknown)}")
    return replace(
        manifest,
        case_id=manifest.case_id if case_id is None else case_id,
        services=tuple(services),
        edges=tuple(edges),
        declared_defects=tuple(sorted(defects_set)),
    )


def enumerate_configs(manifest: Manifest) -> Iterator[tuple[int, ...]]:
    return product((O, B, N), repeat=len(manifest.services))


def is_closed(manifest: Manifest, config: tuple[int, ...]) -> bool:
    if len(config) != len(manifest.services):
        return False
    index = {name: i for i, name in enumerate(manifest.names)}
    for i, service in enumerate(manifest.services):
        mode = config[i]
        if mode == B:
            if not (service.bridge and service.auth and service.idem and service.session):
                return False
            if service.stateful and not service.migrate:
                return False
        elif mode == N:
            if not (service.refine and service.auth and service.idem):
                return False
        elif mode != O:
            return False
    for edge in manifest.edges:
        src_mode = config[index[edge.src]]
        dst_mode = config[index[edge.dst]]
        if src_mode in (B, N) and dst_mode == O and not edge.n2o:
            return False
        if src_mode in (O, B) and dst_mode == N and not edge.o2n:
            return False
    return True


def successors(config: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    for i, value in enumerate(config):
        if value < N:
            nxt = list(config)
            nxt[i] += 1
            yield tuple(nxt)


def predecessors(config: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    for i, value in enumerate(config):
        if value > O:
            prev = list(config)
            prev[i] -= 1
            yield tuple(prev)


def config_text(config: tuple[int, ...]) -> str:
    return "".join(MODE_NAME[x] for x in config)
