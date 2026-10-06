"""Local write-ahead intents for the single-authority serialized harness.

This is not a distributed commit protocol. The proxy's request lock and the
controller's serialized action convention are the only writers. Atomic local
files/receipts must survive process restart; machine/storage loss is excluded.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .rpcutil import atomic_json


class PendingWrites:
    def __init__(self, config_path: Path):
        self.path = config_path.with_name("pending-dual-writes.json")

    def read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("schema") != "gateroll.pending-dual-writes.v1" or not isinstance(state.get("intents"), dict):
            raise ValueError("invalid pending-write state; refusing observations")
        return state["intents"]

    @staticmethod
    def token(target: str, key: str) -> str:
        return json.dumps([target, key], separators=(",", ":"))

    def for_key(self, target: str, key: str) -> dict[str, Any] | None:
        return self.read().get(self.token(target, key))

    def for_target(self, target: str) -> bool:
        return any(intent["target"] == target for intent in self.read().values())

    @staticmethod
    def effect(rpc: dict[str, Any]) -> dict[str, Any]:
        # Delivery delay and route/client shape are not part of the effect.
        return {"cmd": "apply", "req_id": str(rpc["req_id"]), "key": str(rpc["key"]),
                "op": str(rpc["op"]), "delta": int(rpc.get("delta", 1)), "role": str(rpc["role"])}

    def begin(self, target: str, mode: str, rpc: dict[str, Any]) -> dict[str, Any]:
        state = self.read()
        token = self.token(target, str(rpc["key"]))
        if token in state:
            raise RuntimeError("pending intent must be completed, not overwritten")
        intent = {"target": target, "mode": mode, "rpc": self.effect(rpc)}
        state[token] = intent
        atomic_json(self.path, {"schema": "gateroll.pending-dual-writes.v1", "intents": state})
        return intent

    def finish(self, target: str, key: str) -> None:
        state = self.read()
        del state[self.token(target, key)]
        # Clear only after both successful matching write replies; a crash before
        # this replace leaves an intent whose same-ID replay has no extra effect.
        atomic_json(self.path, {"schema": "gateroll.pending-dual-writes.v1", "intents": state})
