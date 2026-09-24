"""Separately structured explicit-state oracle.

It uses base-3 integer states and forward depth-first search rather than the
planner's tuple-based reverse reachability.
"""
from __future__ import annotations

from .model import B, N, O, Manifest


def _digit(code: int, position: int) -> int:
    return (code // (3 ** position)) % 3


def _valid(manifest: Manifest, code: int) -> bool:
    position = {s.name: i for i, s in enumerate(manifest.services)}
    for i, service in enumerate(manifest.services):
        mode = _digit(code, i)
        if mode == B:
            if not service.bridge or not service.auth or not service.idem or not service.session:
                return False
            if service.stateful and not service.migrate:
                return False
        elif mode == N:
            if not service.refine or not service.auth or not service.idem:
                return False
        elif mode != O:
            return False
    for edge in manifest.edges:
        source = _digit(code, position[edge.src])
        target = _digit(code, position[edge.dst])
        if source >= B and target == O and not edge.n2o:
            return False
        if source <= B and target == N and not edge.o2n:
            return False
    return True


def admitted(manifest: Manifest) -> bool:
    count = len(manifest.services)
    target = sum(N * (3 ** i) for i in range(count))
    if not _valid(manifest, 0) or not _valid(manifest, target):
        return False
    stack = [0]
    seen = {0}
    while stack:
        code = stack.pop()
        if code == target:
            return True
        for i in range(count):
            value = _digit(code, i)
            if value < N:
                nxt = code + 3 ** i
                if nxt not in seen and _valid(manifest, nxt):
                    seen.add(nxt)
                    stack.append(nxt)
    return False
