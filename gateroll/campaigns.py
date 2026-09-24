"""Deterministic multi-process rollout campaigns over four service topologies."""
from __future__ import annotations

import csv
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .baselines import BASELINES
from .checker import CertificateError, check
from .families import TOPOLOGIES, base_manifest, load_pair_specs
from .model import B, N, O, Manifest, config_text, false_atoms
from .planner import plan
from .rpcutil import atomic_json, call, free_port, wait_healthy
from .service_process import serve as serve_backend
from .proxy_process import serve as serve_proxy

FAULTS = (
    "none",
    "crash",
    "delay",
    "reorder",
    "stale_route",
    "missing_adapter",
    "authorization_mismatch",
    "partial_migration",
    "corrupt_certificate",
    "duplicate",
)
STRATEGIES = (
    "certified",
    "stop_the_world",
    "naive_rolling",
    "schema_only",
    "version_negotiation",
    "health_rollback",
)
PREFLIGHT_FAULTS = {
    "missing_adapter",
    "authorization_mismatch",
    "partial_migration",
    "corrupt_certificate",
}
# Two model-unsafe scenarios per topology, while every post-start fault still
# has safe executions in other topologies.
UNSAFE_FAULTS = {
    "chain3": {"stale_route", "duplicate"},
    "diamond4": {"delay", "reorder"},
    "fanout4": {"crash", "stale_route"},
    "cycle5": {"delay", "duplicate"},
}


@dataclass
class Backend:
    role: str
    version: str
    port: int
    state_path: Path
    process: Any
    idempotent: bool
    auth_weak: bool
    response_break: bool


class RolloutBlocked(RuntimeError):
    """Expected fail-closed rejection after an executable rollout check."""


class RuntimeRun:
    def __init__(
        self,
        artifact_root: Path,
        run_dir: Path,
        manifest: Manifest,
        certificate: dict[str, Any],
        strategy: str,
        fault: str,
    ):
        self.artifact_root = artifact_root
        self.run_dir = run_dir
        self.manifest = manifest
        self.certificate = certificate
        self.strategy = strategy
        self.fault = fault
        self.backends: dict[tuple[str, str], Backend] = {}
        self.proxy_process: Any | None = None
        self.proxy_port = 0
        self.config_path = run_dir / "proxy-config.json"
        self.journal_path = run_dir / "journal.jsonl"
        self.role_index = {name: i for i, name in enumerate(manifest.names)}
        self.initial: dict[str, dict[str, int]] = {
            role: {
                "a0": 10 * (i + 1) + 1,
                "a1": 10 * (i + 1) + 2,
                "u0": 10 * (i + 1) + 3,
                "u1": 10 * (i + 1) + 4,
            }
            for i, role in enumerate(manifest.names)
        }
        self.expected = {role: dict(values) for role, values in self.initial.items()}
        self.config: dict[str, Any] = {}
        self.recovery_ms = 0.0
        self.rollout_start = 0.0
        self.rollout_end = 0.0
        self.quiescence_recorded = False
        self.first_new_preferred: str | None = None
        self.crash_injected = False
        self.duplicate_seed: dict[str, Any] | None = None
        self.partial_fault_injected = False
        self.request_count = 0
        self.proxy_calls = 0
        self._log_handles: list[Any] = []
        self.mp = multiprocessing.get_context("fork")

    def _service_flags(self, role: str, version: str) -> tuple[bool, bool, bool]:
        false = set(false_atoms(self.manifest))
        idempotent = True
        auth_weak = False
        response_break = False
        if version == "new":
            idempotent = f"service:{role}:idem" not in false
            auth_weak = f"service:{role}:auth" in false
            response_break = f"service:{role}:refine" in false
            target = "ledger" if "ledger" in self.manifest.names else self.manifest.names[-1]
            if self.fault == "authorization_mismatch" and role == target:
                auth_weak = True
        # Strategies that do not enforce replay still expose a truthful service
        # implementation when the manifest says idempotent. The replay-break
        # controlled pairs and fault retries provide the negative controls.
        return idempotent, auth_weak, response_break

    def _spawn_backend(self, role: str, version: str, state_path: Path | None = None) -> Backend:
        port = free_port()
        if state_path is None:
            state_path = self.run_dir / f"{role}-{version}-state.json"
        idempotent, auth_weak, response_break = self._service_flags(role, version)
        process = self.mp.Process(
            target=serve_backend,
            args=(port, str(state_path), version, idempotent, auth_weak, response_break),
            daemon=True,
        )
        process.start()
        wait_healthy(port, process)
        backend = Backend(role, version, port, state_path, process, idempotent, auth_weak, response_break)
        self.backends[(role, version)] = backend
        return backend

    def _spawn_proxy(self) -> None:
        # Allocate after all backends are bound so the kernel cannot hand the
        # same ephemeral port to a service started in the interim.
        self.proxy_port = free_port()
        self.proxy_process = self.mp.Process(
            target=serve_proxy, args=(self.proxy_port, str(self.config_path)), daemon=True
        )
        self.proxy_process.start()
        wait_healthy(self.proxy_port, self.proxy_process)

    def _write_config(self) -> None:
        atomic_json(self.config_path, self.config)

    def _append_journal(self, action: str, **fields: Any) -> None:
        row = {"action": action, **fields}
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def start(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        services: dict[str, Any] = {}
        for role in self.manifest.names:
            old = self._spawn_backend(role, "old")
            call(old.port, {"cmd": "load", "values": self.initial[role], "receipts": {}})
            new = self._spawn_backend(role, "new")
            adapter = self.strategy in {"certified", "stop_the_world", "schema_only"}
            dual_write = self.strategy == "certified"
            session_support = self.strategy == "certified"
            # A declared local bridge/session defect is reflected in the runtime inventory.
            defects = set(false_atoms(self.manifest))
            if f"service:{role}:bridge" in defects:
                adapter = False
            if f"service:{role}:session" in defects:
                session_support = False
            target = "ledger" if "ledger" in self.manifest.names else self.manifest.names[-1]
            if self.fault == "missing_adapter" and role == target:
                adapter = False
            services[role] = {
                "mode": "O",
                "preferred": "old",
                "adapter": adapter,
                "dual_write": dual_write,
                "session_support": session_support,
                "old": {"port": old.port, "live": True},
                "new": {"port": new.port, "live": True},
            }
        self.config = {
            "strategy": self.strategy,
            "service_timeout": 0.12,
            "auth_guard": self.strategy == "certified",
            "quiesced_keys": [],
            "services": services,
            "edges": [edge.__dict__ for edge in self.manifest.edges],
        }
        self._write_config()
        self._spawn_proxy()

    def path_to(self, target: str) -> list[str]:
        source = "gateway" if "gateway" in self.manifest.names else self.manifest.names[0]
        if target == source:
            return [source]
        adjacency: dict[str, list[str]] = {name: [] for name in self.manifest.names}
        for edge in self.manifest.edges:
            adjacency[edge.src].append(edge.dst)
        queue = deque([[source]])
        seen = {source}
        while queue:
            path = queue.popleft()
            for nxt in adjacency[path[-1]]:
                if nxt == target:
                    return path + [nxt]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(path + [nxt])
        return [source, target]

    def _dump(self, role: str, version: str) -> dict[str, Any]:
        return call(self.backends[(role, version)].port, {"cmd": "dump"})

    def _migrate(self, role: str, *, publish: bool, partial: bool = False) -> tuple[int, int]:
        old_dump = self._dump(role, "old")
        values = dict(old_dump["values"])
        if partial or f"service:{role}:migrate" in set(false_atoms(self.manifest)):
            affected = sorted(k for k in values if k.startswith("a"))
            for key in affected[::2] or affected[:1]:
                values.pop(key, None)
        new = self.backends[(role, "new")]
        result = call(new.port, {"cmd": "load", "values": values, "receipts": old_dump.get("receipts", {})})
        source_count = len(old_dump["values"])
        target_count = int(result["count"])
        self._append_journal("load", role=role, source_count=source_count, target_count=target_count)
        if publish:
            self.config["services"][role]["mode"] = "B"
            self._write_config()
        return source_count, target_count

    def _certificate_for_preflight(self) -> dict[str, Any]:
        """Return the certificate presented to the runtime checker.

        The corrupt-certificate campaign removes one genuine frontier member.
        The checker, rather than the fault label, is the rejection authority.
        """
        candidate = deepcopy(self.certificate)
        if self.fault == "corrupt_certificate":
            frontier = list(candidate.get("frontier", []))
            if frontier:
                candidate["frontier"] = frontier[:-1]
            else:
                candidate["admitted"] = not bool(candidate.get("admitted"))
        return candidate

    def _inventory_preflight(self) -> str:
        """Compare the declared admitted obligations with live process metadata."""
        for service in self.manifest.services:
            runtime = self.config["services"][service.name]
            if service.bridge and not runtime.get("adapter"):
                return "missing-adapter"
            health = call(self.backends[(service.name, "new")].port, {"cmd": "health"})
            if service.auth and not health.get("auth_guard"):
                return "authorization-mismatch"
            if service.idem and not health.get("idempotent"):
                return "replay-mismatch"
            if service.refine and not health.get("response_refines"):
                return "response-refinement-mismatch"
        return ""

    def _reset_old_routes(self) -> None:
        """Fail closed by restoring every preferred route to the old endpoint."""
        self.config["quiesced_keys"] = []
        for service in self.config["services"].values():
            service["mode"] = "O"
            service["preferred"] = "old"
        self._write_config()

    def _step_certified(self, left: list[int], right: list[int]) -> None:
        changed = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(changed) != 1 or right[changed[0]] != left[changed[0]] + 1:
            raise RuntimeError("invalid certified step")
        i = changed[0]
        role = self.manifest.names[i]
        if left[i] == O and right[i] == B:
            self._append_journal("prepare", role=role, from_mode="O", to_mode="B")
            partial = self.fault == "partial_migration" and not self.partial_fault_injected
            if partial:
                self.partial_fault_injected = True
            source_count, target_count = self._migrate(role, publish=False, partial=partial)
            if source_count != target_count:
                self._append_journal("abort", role=role, reason="cardinality")
                raise RolloutBlocked("migration-cardinality")
            self.config["services"][role]["mode"] = "B"
            self.config["services"][role]["preferred"] = "old"
            self._write_config()
            self._append_journal("publish-bridge", role=role)
        elif left[i] == B and right[i] == N:
            self.config["services"][role]["mode"] = "N"
            self.config["services"][role]["preferred"] = "new"
            self._write_config()
            self._append_journal("prefer-new", role=role)
            if self.first_new_preferred is None:
                self.first_new_preferred = role
        else:
            raise RuntimeError("unexpected certified mode step")

    def _step_direct(self, role: str, *, stop_world: bool = False) -> None:
        partial = self.fault == "partial_migration" and role == ("ledger" if "ledger" in self.manifest.names else self.manifest.names[-1])
        self._migrate(role, publish=False, partial=partial)
        self.config["services"][role]["mode"] = "N"
        self.config["services"][role]["preferred"] = "new"
        self._write_config()
        if self.first_new_preferred is None:
            self.first_new_preferred = role

    def _crash_if_due(self) -> None:
        if self.fault != "crash" or self.crash_injected or self.first_new_preferred is None:
            return
        role = self.first_new_preferred
        backend = self.backends[(role, "new")]
        backend.process.kill()
        backend.process.join(timeout=2)
        self.config["services"][role]["new"]["live"] = False
        self._write_config()
        self.crash_injected = True
        start = time.perf_counter()
        if self.strategy == "certified":
            restarted = self._spawn_backend(role, "new", state_path=backend.state_path)
            self.config["services"][role]["new"] = {"port": restarted.port, "live": True}
            self._write_config()
            self._append_journal("restart", role=role)
        elif self.strategy == "health_rollback":
            self.config["services"][role]["preferred"] = "old"
            self.config["services"][role]["mode"] = "O"
            self._write_config()
            self._append_journal("health-rollback", role=role)
        self.recovery_ms += (time.perf_counter() - start) * 1000.0

    def _logical_request(self, tx_index: int, phase: str, force_quiesced: tuple[str, str] | None = None) -> dict[str, Any]:
        names = self.manifest.names
        target = names[tx_index % len(names)]
        key = ("a" if tx_index % 2 == 0 else "u") + str((tx_index // 2) % 2)
        pattern = tx_index % 4
        if pattern in (0, 3):
            op, caller_role = "inc", "writer"
        elif pattern == 1:
            op, caller_role = "read", "reader"
        else:
            op, caller_role = "inc", "guest"
        client_shape = "old" if tx_index % 2 == 0 else "new"
        if force_quiesced is not None:
            target, key = force_quiesced
            op, caller_role, client_shape = "read", "reader", "old"
        request = {
            "cmd": "request",
            "target": target,
            "path": self.path_to(target),
            "req_id": f"{self.manifest.case_id}:{self.strategy}:{tx_index:02d}",
            "key": key,
            "op": op,
            "delta": 1,
            "role": caller_role,
            "client_shape": client_shape,
            "phase": phase,
        }
        if tx_index == 8:
            request.update({"session_id": "sticky-1", "session_continuation": False, "session_origin": "old", "target": "gateway", "path": ["gateway"]})
        if tx_index == 21:
            if self.strategy == "stop_the_world":
                # A full stop drains the old session before traffic resumes;
                # the post-pause request starts a new-version session rather
                # than pretending an old continuation survived the outage.
                request.update({"session_id": "restart-1", "session_continuation": False, "session_origin": "new", "target": "gateway", "path": ["gateway"], "client_shape": "new", "op": "inc", "role": "writer", "key": "a1"})
            else:
                request.update({"session_id": "sticky-1", "session_continuation": True, "session_origin": "old", "target": "gateway", "path": ["gateway"], "client_shape": "new", "op": "inc", "role": "writer", "key": "a1"})
        if tx_index == 16:
            request.update({"op": "inc", "role": "writer", "key": "a0"})
            self.duplicate_seed = dict(request)
        if tx_index == 20 and self.fault in {"duplicate", "reorder"} and self.duplicate_seed is not None:
            saved = self.duplicate_seed
            request.update({
                "target": saved["target"],
                "path": saved["path"],
                "req_id": saved["req_id"],
                "key": saved["key"],
                "op": saved["op"],
                "role": saved["role"],
                "client_shape": saved["client_shape"],
                "logical_duplicate": True,
            })
        if tx_index == 18 and self.fault == "delay":
            request["delay_after_ms"] = 260
        if tx_index == 20 and self.fault == "stale_route" and phase in {"mixed", "new", "dual-version"}:
            request["stale_route"] = True
        # Before a rollout, and after a blocked preflight, only the old client
        # population is active. New-shape requests are introduced with the
        # mixed-version phase rather than being counted against old fallback.
        if phase in {"old", "blocked-old"}:
            request["client_shape"] = "old"
        return request

    def _send(self, request: dict[str, Any]) -> tuple[dict[str, Any], float, int]:
        start = time.perf_counter()
        attempts = 1
        response = call(self.proxy_port, request, timeout=0.5)
        self.proxy_calls += 1
        if self.fault == "delay" and request.get("delay_after_ms") and not response.get("available"):
            time.sleep(0.30)
            retry = dict(request)
            retry.pop("delay_after_ms", None)
            response = call(self.proxy_port, retry, timeout=0.5)
            self.proxy_calls += 1
            attempts = 2
        latency_ms = (time.perf_counter() - start) * 1000.0
        return response, latency_ms, attempts

    def transact(self, tx_index: int, phase: str, force_quiesced: tuple[str, str] | None = None) -> dict[str, Any]:
        request = self._logical_request(tx_index, phase, force_quiesced)
        target = str(request["target"])
        key = str(request["key"])
        op = str(request["op"])
        caller_role = str(request["role"])
        authorized = op == "read" or caller_role in {"writer", "admin"}
        logical_duplicate = bool(request.get("logical_duplicate"))
        before = self.expected[target].get(key, 0)
        if op == "inc" and authorized and not logical_duplicate:
            expected_value = before + int(request.get("delta", 1))
        else:
            expected_value = before
        try:
            response, latency_ms, attempts = self._send(request)
        except Exception as exc:
            response = {"available": False, "error": f"proxy-call:{type(exc).__name__}"}
            latency_ms = 0.0
            attempts = 1
        available = bool(response.get("available"))
        violation = False
        authorization_ok = True
        observed = response.get("value")
        if authorized:
            if available:
                if response.get("denied"):
                    violation = True
                elif not response.get("ok") or not response.get("shape_ok", True) or not response.get("protocol_ok", True):
                    violation = True
                elif observed != expected_value:
                    violation = True
                if not violation and op == "inc" and not logical_duplicate:
                    self.expected[target][key] = expected_value
            # Unavailable authorized traffic is an availability loss, not a wrong success.
        else:
            if available and response.get("denied"):
                authorization_ok = True
            elif available:
                authorization_ok = False
                violation = True
            else:
                authorization_ok = False
        row = {
            "campaign_id": self.manifest.case_id,
            "strategy": self.strategy,
            "topology": self.manifest.topology,
            "family": self.manifest.family,
            "pair": self.manifest.pair,
            "fault": self.fault,
            "tx_index": tx_index,
            "phase": phase,
            "key_class": "affected" if key.startswith("a") else "unaffected",
            "target": target,
            "operation": op,
            "caller_role": caller_role,
            "client_shape": request["client_shape"],
            "authorized": int(authorized),
            "available": int(available and authorized),
            "denied": int(bool(response.get("denied"))),
            "authorization_ok": int(authorization_ok),
            "semantic_violation": int(violation),
            "expected_value": expected_value,
            "observed_value": "" if observed is None else observed,
            "shape": response.get("shape", ""),
            "service_version": response.get("service_version", ""),
            "attempts": attempts,
            "latency_ms": round(latency_ms, 6),
            "error": response.get("error", ""),
            "logical_duplicate": int(logical_duplicate),
        }
        self.request_count += 1
        return row

    def _baseline_admission(self) -> bool:
        if self.strategy == "certified":
            return bool(self.certificate["admitted"])
        key = "health_gate" if self.strategy == "health_rollback" else self.strategy
        return bool(BASELINES[key](self.manifest))

    def run(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.start()
        rows: list[dict[str, Any]] = []
        decision = self._baseline_admission()
        block_reason = ""
        if self.strategy == "certified":
            if not decision:
                block_reason = "model-witness"
            else:
                # Neither the scenario label nor the planner decision is trusted
                # at the execution boundary.  The runtime checks the presented
                # certificate and live process inventory before changing routes.
                try:
                    check(self.manifest, self._certificate_for_preflight())
                except CertificateError:
                    decision = False
                    block_reason = "certificate-rejected"
                if decision:
                    block_reason = self._inventory_preflight()
                    if block_reason:
                        decision = False
        elif not decision:
            block_reason = "baseline-projection"

        for tx in range(12):
            rows.append(self.transact(tx, "old"))

        final_new = False
        # The scenario oracle expects cutover only when the finite model admits
        # the pair and no executable pre-cutover inconsistency was injected.
        # This ground-truth set is strategy independent (16 of 40 scenarios).
        safe_cutover_target = bool(self.certificate["admitted"] and self.fault not in PREFLIGHT_FAULTS)
        self.rollout_start = time.perf_counter()
        if not decision:
            for tx in range(12, 36):
                rows.append(self.transact(tx, "blocked-old"))
            self.rollout_end = time.perf_counter()
        elif self.strategy == "certified":
            schedule = self.certificate["schedule"]
            action_index = 0
            blocked_at: int | None = None
            for tx in range(12, 24):
                if action_index < len(schedule) - 1:
                    left, right = schedule[action_index], schedule[action_index + 1]
                    changed = next(i for i, (a, b) in enumerate(zip(left, right)) if a != b)
                    role = self.manifest.names[changed]
                    try:
                        if left[changed] == O and not self.quiescence_recorded:
                            self.config["quiesced_keys"] = ["a0"]
                            self._write_config()
                            rows.append(self.transact(tx, "bridge-entry", force_quiesced=(role, "a0")))
                            self.config["quiesced_keys"] = []
                            self._write_config()
                            self.quiescence_recorded = True
                            self._step_certified(left, right)
                        else:
                            self._step_certified(left, right)
                            self._crash_if_due()
                            rows.append(self.transact(tx, "mixed"))
                    except RolloutBlocked as exc:
                        decision = False
                        block_reason = str(exc)
                        self._reset_old_routes()
                        blocked_at = tx
                        break
                    action_index += 1
                else:
                    rows.append(self.transact(tx, "mixed"))
            if blocked_at is not None:
                for tx in range(blocked_at + 1, 36):
                    rows.append(self.transact(tx, "blocked-old"))
            else:
                while action_index < len(schedule) - 1:
                    try:
                        self._step_certified(schedule[action_index], schedule[action_index + 1])
                    except RolloutBlocked as exc:
                        decision = False
                        block_reason = str(exc)
                        self._reset_old_routes()
                        break
                    self._crash_if_due()
                    action_index += 1
                final_new = decision and all(s["mode"] == "N" for s in self.config["services"].values())
                for tx in range(24, 36):
                    rows.append(self.transact(tx, "new" if final_new else "blocked-old"))
            self.rollout_end = time.perf_counter()
        elif self.strategy == "stop_the_world":
            self.config["quiesced_keys"] = ["a0", "a1", "u0", "u1"]
            self._write_config()
            for tx in range(12, 16):
                rows.append(self.transact(tx, "global-pause"))
            for role in self.manifest.names:
                self._step_direct(role, stop_world=True)
            self.config["quiesced_keys"] = []
            self._write_config()
            self._crash_if_due()
            for tx in range(16, 36):
                rows.append(self.transact(tx, "new"))
            final_new = all(s["mode"] == "N" for s in self.config["services"].values())
            self.rollout_end = time.perf_counter()
        elif self.strategy == "version_negotiation":
            for role in self.manifest.names:
                self._migrate(role, publish=False, partial=self.fault == "partial_migration" and role == "ledger")
                self.config["services"][role]["mode"] = "B"
            self._write_config()
            self.first_new_preferred = self.manifest.names[0]
            self._crash_if_due()
            for tx in range(12, 36):
                rows.append(self.transact(tx, "dual-version"))
            # Old-client traffic still requires old endpoints, so this is not a
            # completed all-new cutover even when requests remain available.
            final_new = False
            self.rollout_end = time.perf_counter()
        else:
            roles = list(self.manifest.names)
            role_cursor = 0
            for tx in range(12, 24):
                if role_cursor < len(roles):
                    self._step_direct(roles[role_cursor])
                    self._crash_if_due()
                    role_cursor += 1
                rows.append(self.transact(tx, "mixed"))
            while role_cursor < len(roles):
                self._step_direct(roles[role_cursor])
                self._crash_if_due()
                role_cursor += 1
            for tx in range(24, 36):
                rows.append(self.transact(tx, "new"))
            final_new = all(s["mode"] == "N" for s in self.config["services"].values())
            self.rollout_end = time.perf_counter()

        authorized = [row for row in rows if row["authorized"]]
        affected = [row for row in authorized if row["key_class"] == "affected"]
        unaffected = [row for row in authorized if row["key_class"] == "unaffected"]
        run_row = {
            "campaign_id": self.manifest.case_id,
            "strategy": self.strategy,
            "topology": self.manifest.topology,
            "family": self.manifest.family,
            "pair": self.manifest.pair,
            "fault": self.fault,
            "model_admitted": int(bool(self.certificate["admitted"])),
            "strategy_admitted": int(decision),
            "block_reason": block_reason,
            "final_new": int(final_new),
            "safe_cutover_target": int(safe_cutover_target),
            "transaction_records": len(rows),
            "proxy_calls": self.proxy_calls,
            "availability_overall": sum(row["available"] for row in authorized) / len(authorized),
            "availability_affected": sum(row["available"] for row in affected) / len(affected),
            "availability_unaffected": sum(row["available"] for row in unaffected) / len(unaffected),
            "semantic_violations": sum(row["semantic_violation"] for row in rows),
            "violating_run": int(any(row["semantic_violation"] for row in rows)),
            "authorization_failures": sum(1 for row in rows if not row["authorized"] and not row["authorization_ok"]),
            "rollout_ms": (self.rollout_end - self.rollout_start) * 1000.0,
            "recovery_ms": self.recovery_ms,
        }
        return rows, run_row

    def close(self) -> None:
        """Bounded bulk cleanup after a campaign run.

        Campaign state is synchronously persisted before each response, so
        teardown is outside the measured rollout interval.  Children are
        signalled together and then reaped as a batch.
        """
        processes: list[Any] = []
        if self.proxy_process is not None:
            processes.append(self.proxy_process)
        seen: set[int] = set()
        for backend in list(self.backends.values()):
            marker = id(backend.process)
            if marker in seen:
                continue
            seen.add(marker)
            processes.append(backend.process)

        try:
            for process in processes:
                try:
                    if process.is_alive():
                        process.terminate()
                except ValueError:
                    pass
            for process in processes:
                try:
                    process.join(timeout=0.2)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=0.2)
                except ValueError:
                    pass
            for process in processes:
                try:
                    process.close()
                except ValueError:
                    pass
        finally:
            for handle in self._log_handles:
                try:
                    handle.close()
                except Exception:
                    pass



def scenario_specs(input_dir: Path) -> list[tuple[str, str, int, dict[str, Any]]]:
    specs = load_pair_specs(input_dir)
    indexed = list(enumerate(specs))
    out: list[tuple[str, str, int, dict[str, Any]]] = []
    for topology in TOPOLOGIES:
        candidates = [(i, spec) for i, spec in indexed if spec["topology"] == topology]
        safe = [(i, spec) for i, spec in candidates if not spec.get("default_defects")]
        unsafe = [(i, spec) for i, spec in candidates if spec.get("default_defects")]
        if len(unsafe) != 2 or len(safe) < 4:
            raise AssertionError(f"expected two unsafe and at least four safe pairs for {topology}")
        unsafe_iter = iter(unsafe)
        safe_cursor = 0
        for fault in FAULTS:
            if fault in UNSAFE_FAULTS[topology]:
                pair_index, spec = next(unsafe_iter)
            else:
                pair_index, spec = safe[safe_cursor % len(safe)]
                safe_cursor += 1
            out.append((topology, fault, pair_index, spec))
    if len(out) != 40:
        raise AssertionError(len(out))
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(run_rows: list[dict[str, Any]], tx_rows: list[dict[str, Any]]) -> dict[str, Any]:
    strategies: dict[str, Any] = {}
    for strategy in STRATEGIES:
        runs = [row for row in run_rows if row["strategy"] == strategy]
        safe_targets = [row for row in runs if row["safe_cutover_target"]]
        strategies[strategy] = {
            "runs": len(runs),
            "mean_unaffected_availability": sum(row["availability_unaffected"] for row in runs) / len(runs),
            "mean_affected_availability": sum(row["availability_affected"] for row in runs) / len(runs),
            "mean_overall_availability": sum(row["availability_overall"] for row in runs) / len(runs),
            "semantic_violations": sum(int(row["semantic_violations"]) for row in runs),
            "violating_runs": sum(int(row["violating_run"]) for row in runs),
            "completed_expected_cutovers": sum(int(row["final_new"]) for row in safe_targets),
            "expected_cutover_runs": len(safe_targets),
            "all_new_runs": sum(int(row["final_new"]) for row in runs),
            "blocked_runs": sum(1 for row in runs if not row["strategy_admitted"]),
        }
    return {
        "campaigns": len({row["campaign_id"] for row in run_rows}),
        "strategy_runs": len(run_rows),
        "transaction_records": len(tx_rows),
        "topologies": len({row["topology"] for row in run_rows}),
        "fault_classes": len({row["fault"] for row in run_rows}),
        "strategies": strategies,
    }


def run_all(artifact_root: Path, input_dir: Path, output_dir: Path, *, keep_run_dirs: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_tx: list[dict[str, Any]] = []
    all_runs: list[dict[str, Any]] = []
    scenarios = scenario_specs(input_dir)
    for campaign_index, (topology, fault, pair_index, spec) in enumerate(scenarios):
        manifest = base_manifest(spec, pair_index)
        manifest = Manifest(
            case_id=f"campaign-{campaign_index:02d}",
            family=manifest.family,
            pair=manifest.pair,
            topology=manifest.topology,
            services=manifest.services,
            edges=manifest.edges,
            declared_defects=manifest.declared_defects,
        )
        certificate = plan(manifest)
        # Campaign certificates are independently checked before any strategy run.
        check(manifest, certificate)
        for strategy in STRATEGIES:
            run_dir = output_dir / "runs" / f"{campaign_index:02d}-{strategy}"
            runtime = RuntimeRun(artifact_root, run_dir, manifest, certificate, strategy, fault)
            try:
                tx_rows, run_row = runtime.run()
                all_tx.extend(tx_rows)
                all_runs.append(run_row)
                print(
                    f"campaign={campaign_index:02d} strategy={strategy} "
                    f"violations={run_row['semantic_violations']} "
                    f"availability={run_row['availability_overall']:.3f}",
                    flush=True,
                )
            finally:
                runtime.close()
            if not keep_run_dirs:
                # Preserve only the certified journal and nonempty diagnostics.
                if strategy != "certified":
                    for path in run_dir.glob("*.stdout"):
                        if path.exists() and path.stat().st_size == 0:
                            path.unlink()
                    for path in run_dir.glob("*.stderr"):
                        if path.exists() and path.stat().st_size == 0:
                            path.unlink()
    if len(all_runs) != 240 or len(all_tx) != 8_640:
        raise AssertionError((len(all_runs), len(all_tx)))
    _write_csv(output_dir / "campaign_transactions.csv", all_tx)
    _write_csv(output_dir / "campaign_runs.csv", all_runs)
    summary = aggregate(all_runs, all_tx)
    (output_dir / "campaign_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
