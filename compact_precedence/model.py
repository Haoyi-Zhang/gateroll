from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
import hashlib, json

LOCAL_B = ("bridge", "auth", "idem", "session")
LOCAL_N = ("refine", "auth", "idem")

@dataclass(frozen=True)
class ServiceFacts:
    refine: bool = True
    bridge: bool = True
    migrate: bool = True
    auth: bool = True
    idem: bool = True
    session: bool = True
    stateful: bool = True

@dataclass(frozen=True)
class EdgeFacts:
    caller: str
    callee: str
    n2o: bool = True
    o2n: bool = True

@dataclass(frozen=True)
class Manifest:
    services: tuple[str, ...]
    local: tuple[tuple[str, ServiceFacts], ...]
    edges: tuple[EdgeFacts, ...]
    identity: str = "manifest"

    @staticmethod
    def build(services: Iterable[str], local: dict[str, ServiceFacts], edges: Iterable[EdgeFacts], identity: str="manifest") -> "Manifest":
        s=tuple(services)
        if len(set(s)) != len(s): raise ValueError("duplicate service")
        if set(local) != set(s): raise ValueError("local facts must cover exactly the services")
        es=tuple(edges)
        for e in es:
            if e.caller not in local or e.callee not in local: raise ValueError("edge endpoint missing")
        return Manifest(s, tuple((x, local[x]) for x in s), es, identity)

    def local_map(self) -> dict[str, ServiceFacts]:
        return dict(self.local)

    def canonical(self) -> dict:
        return {"identity": self.identity, "services": list(self.services),
                "local": {k: asdict(v) for k,v in self.local},
                "edges": [asdict(e) for e in sorted(self.edges, key=lambda x:(x.caller,x.callee))]}

    def digest(self) -> str:
        b=json.dumps(self.canonical(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(b).hexdigest()

    @staticmethod
    def from_dict(d: dict) -> "Manifest":
        services=tuple(d["services"])
        local={s: ServiceFacts(**d["local"][s]) for s in services}
        edges=[EdgeFacts(**x) for x in d.get("edges", [])]
        return Manifest.build(services, local, edges, d.get("identity", "manifest"))

def event(kind: str, service: str) -> str:
    if kind not in {"B","N"}: raise ValueError(kind)
    return f"{kind}:{service}"

def mode_events(service: str, mode: str) -> frozenset[str]:
    if mode == "O": return frozenset()
    if mode == "B": return frozenset({event("B",service)})
    if mode == "N": return frozenset({event("B",service), event("N",service)})
    raise ValueError(mode)
