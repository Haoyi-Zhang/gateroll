from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from gateroll.pending_writes import PendingWrites
from gateroll.portable_runtime import fresh_directory
from gateroll.proxy_process import ProxyState
from gateroll.rpcutil import atomic_json
from scripts.run_dual_write_recovery import CASES, execute_case

ROOT = Path(__file__).resolve().parents[1]


class PendingWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = fresh_directory(ROOT, ROOT / "results/runtime_reproductions" / f"pending-test-{uuid.uuid4().hex}")
        self.config_path = self.directory / "proxy-config.json"
        self.config = {"strategy": "certified", "auth_guard": True, "edges": [],
                       "services": {"gateway": {"mode": "B", "preferred": "old", "adapter": True,
                                                 "dual_write": True, "old": {"live": True, "port": 1},
                                                 "new": {"live": True, "port": 2}}}}
        atomic_json(self.config_path, self.config)
        self.proxy = ProxyState(self.config_path)
        self.request = {"target": "gateway", "path": ["gateway"], "key": "a0", "req_id": "one",
                        "op": "inc", "role": "writer", "delta": 1, "client_shape": "old"}

    @staticmethod
    def response(value=12):
        return {"ok": True, "value": value, "effect": "write", "version": "old"}

    def test_intent_persisted_before_first_endpoint_call(self):
        def endpoint(port, rpc, **kwargs):
            intent = self.proxy.pending.for_key("gateway", "a0")
            self.assertEqual(intent["rpc"], PendingWrites.effect(self.request))
            return self.response()
        with patch("gateroll.proxy_process.call", side_effect=endpoint) as transport:
            self.assertTrue(self.proxy.handle(self.request)["ok"])
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(self.proxy.pending.read(), {})

    def test_persistence_failure_sends_no_effect(self):
        with patch("gateroll.pending_writes.atomic_json", side_effect=OSError("injected file failure")), \
             patch("gateroll.proxy_process.call") as transport:
            with self.assertRaises(OSError):
                self.proxy.handle(self.request)
            transport.assert_not_called()

    def test_primary_timeout_retains_intent_and_blocks_reads(self):
        with patch("gateroll.proxy_process.call", side_effect=TimeoutError):
            self.assertEqual(self.proxy.handle(self.request)["error"], "service-timeout")
        restarted = ProxyState(self.config_path)
        with patch("gateroll.proxy_process.call") as transport:
            for stale in (False, True):
                read = {**self.request, "req_id": "read", "op": "read", "stale_route": stale}
                self.assertEqual(restarted.handle(read)["error"], "pending-dual-write")
            transport.assert_not_called()

    def test_secondary_disagreement_does_not_clear_or_succeed(self):
        with patch("gateroll.proxy_process.call", side_effect=[self.response(12), self.response(13)]):
            self.assertEqual(self.proxy.handle(self.request)["error"], "dual-write-disagreement")
        self.assertTrue(self.proxy.pending.for_key("gateway", "a0"))

    def test_known_dead_peer_is_not_silent_single_write_success(self):
        self.config["services"]["gateway"]["new"]["live"] = False
        atomic_json(self.config_path, self.config)
        with patch("gateroll.proxy_process.call", return_value=self.response()):
            response = self.proxy.handle(self.request)
        self.assertFalse(response["available"])
        self.assertEqual(response["error"], "dual-write-failed")
        self.assertTrue(self.proxy.pending.for_key("gateway", "a0"))

    def test_changed_effect_or_phase_is_refused_before_forwarding(self):
        self.proxy.pending.begin("gateway", "B", self.request)
        with patch("gateroll.proxy_process.call") as transport:
            for field, value in (("delta", 2), ("role", "admin")):
                self.assertEqual(self.proxy.handle({**self.request, field: value})["error"], "pending-request-mismatch")
            self.config["services"]["gateway"]["mode"] = "N"
            atomic_json(self.config_path, self.config)
            self.assertEqual(self.proxy.handle(self.request)["error"], "pending-phase-mismatch")
            transport.assert_not_called()

    def test_clear_failure_leaves_replayable_intent(self):
        with patch("gateroll.proxy_process.call", return_value=self.response()), \
             patch.object(self.proxy.pending, "finish", side_effect=OSError("injected clear cut")):
            with self.assertRaises(OSError):
                self.proxy.handle(self.request)
        restarted = ProxyState(self.config_path)
        self.assertTrue(restarted.pending.for_key("gateway", "a0"))
        with patch("gateroll.proxy_process.call", return_value={**self.response(), "replayed": True}):
            response = restarted.handle(self.request)
        self.assertTrue(response["replayed"])
        self.assertEqual(restarted.pending.read(), {})

    def test_malformed_pending_file_fails_closed(self):
        atomic_json(self.proxy.pending.path, {"schema": "wrong", "intents": {}})
        with patch("gateroll.proxy_process.call") as transport:
            with self.assertRaises(ValueError):
                self.proxy.handle({**self.request, "op": "read"})
            transport.assert_not_called()

    def test_guard_denial_does_not_create_an_intent(self):
        with patch("gateroll.proxy_process.call") as transport:
            self.assertTrue(self.proxy.handle({**self.request, "role": "guest"})["denied"])
            transport.assert_not_called()
        self.assertFalse(self.proxy.pending.path.exists())

    def test_completion_preserves_other_pending_keys(self):
        self.proxy.pending.begin("gateway", "B", self.request)
        other = {**self.request, "key": "u0", "req_id": "two"}
        self.proxy.pending.begin("gateway", "B", other)
        with self.assertRaises(RuntimeError):
            self.proxy.pending.begin("gateway", "B", self.request)
        with patch("gateroll.proxy_process.call", return_value=self.response()):
            self.assertTrue(self.proxy.handle(self.request)["ok"])
        self.assertIsNone(self.proxy.pending.for_key("gateway", "a0"))
        self.assertEqual(self.proxy.pending.for_key("gateway", "u0")["rpc"], PendingWrites.effect(other))
        self.assertTrue(self.proxy.pending.for_target("gateway"))


class LiveRecoveryTests(unittest.TestCase):
    def test_real_localhost_faults_and_crash_cuts(self):
        for case in CASES:
            with self.subTest(case=case):
                output = ROOT / "results/runtime_reproductions" / f"recovery-test-{uuid.uuid4().hex}"
                result = execute_case(ROOT, output, case)
                self.assertTrue(result["pass"])
                self.assertEqual(result["pending_after_resolution"], {})


if __name__ == "__main__":
    unittest.main()
