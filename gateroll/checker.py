"""Independent certificate checker.

The checker intentionally does not import planner procedures.  It reconstructs
closure and backward reachability with integer state encodings.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Any

from .model import B, N, O, Edge, Manifest, Service, apply_defects, false_atoms, repaired


class CertificateError(ValueError):
    pass


def _decode(code: int, count: int) -> tuple[int, ...]:
    return tuple((code // (3 ** i)) % 3 for i in range(count))


def _encode(config: tuple[int, ...]) -> int:
    return sum(value * (3 ** i) for i, value in enumerate(config))


def _closed_codes(manifest: Manifest) -> set[int]:
    count = len(manifest.services)
    position = {s.name: i for i, s in enumerate(manifest.services)}
    good: set[int] = set()
    for code in range(3 ** count):
        modes = _decode(code, count)
        okay = True
        for i, service in enumerate(manifest.services):
            mode = modes[i]
            if mode == B:
                okay = service.bridge and service.auth and service.idem and service.session
                if service.stateful:
                    okay = okay and service.migrate
            elif mode == N:
                okay = service.refine and service.auth and service.idem
            elif mode != O:
                okay = False
            if not okay:
                break
        if not okay:
            continue
        for edge in manifest.edges:
            left = modes[position[edge.src]]
            right = modes[position[edge.dst]]
            if left in (B, N) and right == O and not edge.n2o:
                okay = False
                break
            if left in (O, B) and right == N and not edge.o2n:
                okay = False
                break
        if okay:
            good.add(code)
    return good


def _frontier_codes(manifest: Manifest) -> set[int]:
    count = len(manifest.services)
    closed = _closed_codes(manifest)
    target = sum(N * (3 ** i) for i in range(count))
    if target not in closed:
        return set()
    reverse = {target}
    pending = deque([target])
    while pending:
        code = pending.popleft()
        modes = _decode(code, count)
        for i, value in enumerate(modes):
            if value > O:
                prev = code - 3 ** i
                if prev in closed and prev not in reverse:
                    reverse.add(prev)
                    pending.append(prev)
    return reverse


def _schedulable(manifest: Manifest) -> bool:
    return 0 in _frontier_codes(manifest)


def check(manifest: Manifest, certificate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(certificate, dict):
        raise CertificateError("certificate is not an object")
    if certificate.get("case_id") != manifest.case_id:
        raise CertificateError("case identity mismatch")
    if certificate.get("family") != manifest.family or certificate.get("pair") != manifest.pair:
        raise CertificateError("release-pair identity mismatch")
    if certificate.get("topology") != manifest.topology:
        raise CertificateError("topology mismatch")
    if tuple(certificate.get("services", ())) != manifest.names:
        raise CertificateError("service order mismatch")

    count = len(manifest.services)
    computed = _frontier_codes(manifest)
    supplied_configs = certificate.get("frontier", [])
    if not isinstance(supplied_configs, list):
        raise CertificateError("frontier is not a list")
    supplied: set[int] = set()
    for config in supplied_configs:
        if not isinstance(config, list) or len(config) != count or any(type(x) is not int or x not in (O, B, N) for x in config):
            raise CertificateError("malformed frontier configuration")
        supplied.add(_encode(tuple(config)))
    if supplied != computed:
        raise CertificateError("frontier is not exact")

    computed_admitted = 0 in computed
    if type(certificate.get("admitted")) is not bool or certificate["admitted"] != computed_admitted:
        raise CertificateError("admission bit mismatch")

    schedule = certificate.get("schedule", [])
    witness_payload = certificate.get("witness", [])
    if not isinstance(schedule, list):
        raise CertificateError("schedule is not a list")
    if not isinstance(witness_payload, list) or any(not isinstance(x, str) for x in witness_payload):
        raise CertificateError("malformed witness")
    witness = tuple(witness_payload)
    if len(set(witness)) != len(witness) or not set(witness) <= set(false_atoms(manifest)):
        raise CertificateError("witness must be a set of false manifest atoms")
    target_code = sum(N * (3 ** i) for i in range(count))
    if computed_admitted:
        if witness:
            raise CertificateError("admitted certificate contains witness")
        if not schedule:
            raise CertificateError("admitted certificate lacks schedule")
        codes = []
        for config in schedule:
            if not isinstance(config, list) or len(config) != count or any(type(x) is not int or x not in (O, B, N) for x in config):
                raise CertificateError("malformed schedule state")
            code = _encode(tuple(config))
            if code not in computed:
                raise CertificateError("schedule leaves frontier")
            codes.append(code)
        if codes[0] != 0 or codes[-1] != target_code:
            raise CertificateError("schedule endpoints invalid")
        for left, right in zip(codes, codes[1:]):
            diff = right - left
            if diff not in {3 ** i for i in range(count)}:
                raise CertificateError("schedule changes more than one role")
            pos = next(i for i in range(count) if diff == 3 ** i)
            if _decode(right, count)[pos] != _decode(left, count)[pos] + 1:
                raise CertificateError("schedule is not monotone")
    else:
        if schedule:
            raise CertificateError("blocked certificate contains schedule")
        if not witness:
            raise CertificateError("blocked certificate lacks witness")
        base = repaired(manifest)
        blocked = apply_defects(base, witness)
        if _schedulable(blocked):
            raise CertificateError("witness does not block repaired model")
        for atom in witness:
            reduced = tuple(x for x in witness if x != atom)
            if not _schedulable(apply_defects(base, reduced)):
                raise CertificateError("witness is not deletion-minimal")
    return {
        "accepted": True,
        "admitted": computed_admitted,
        "frontier_states": len(computed),
        "schedule_steps": max(0, len(schedule) - 1),
        "witness_atoms": len(witness),
    }
