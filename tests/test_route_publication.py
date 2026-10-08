"""Routing admission for the owned two-generation RPC model."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from gateroll.proxy_process import ProxyState


class RoutePublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp(prefix="gateroll-route-test-"))
        self.path = self.directory / "config.json"
        self.service = {"mode": "O", "preferred": "old", "adapter": True,
                        "dual_write": True, "session_support": True,
                        "old": {"live": True, "port": 19001},
                        "new": {"live": True, "port": 19002}}
        self.config = {"strategy": "certified", "auth_guard": True,
                       "services": {"ledger": self.service}, "edges": []}
        self.request = {"target": "ledger", "path": ["ledger"], "key": "a0",
                        "req_id": "owned-read", "op": "read", "role": "reader",
                        "client_shape": "old", "stale_route": True}
        self.state = ProxyState(self.path)

    def write_config(self) -> None:
        self.path.write_text(json.dumps(self.config), encoding="utf-8")

    def test_started_new_endpoint_is_not_published(self) -> None:
        self.assertEqual(self.state._select_version(self.config, self.request, self.service), "old")

    def test_stale_session_is_pinned_to_admitted_old_route(self) -> None:
        self.request.update(session_id="owned-session", session_origin="old")
        self.assertEqual(self.state._select_version(self.config, self.request, self.service), "old")
        self.assertEqual(self.state.pins["owned-session"], "old")

    def test_retained_new_pin_cannot_bypass_old_mode(self) -> None:
        self.request["session_id"] = "owned-session"
        self.state.pins["owned-session"] = "new"
        self.assertEqual(self.state._select_version(self.config, self.request, self.service), "old")

    def test_aborted_entry_forwards_read_to_old_store(self) -> None:
        self.write_config()
        def owned_reply(port, rpc, **kwargs):
            return {"ok": True, "value": 12 if port == 19001 else 0}
        with patch("gateroll.proxy_process.call", side_effect=owned_reply) as call:
            result = self.state.handle(self.request)
        self.assertTrue(result["available"])
        self.assertEqual(result["value"], 12)
        self.assertEqual(result["service_version"], "old")
        call.assert_called_once()
        self.assertEqual(call.call_args.args[0], 19001)

    def test_unavailable_old_endpoint_does_not_publish_new(self) -> None:
        self.service["old"]["live"] = False
        self.write_config()
        with patch("gateroll.proxy_process.call") as call:
            result = self.state.handle(self.request)
        self.assertFalse(result["available"])
        self.assertEqual(result["error"], "endpoint-unavailable")
        call.assert_not_called()

    def test_bridge_and_new_mode_keep_published_fallback(self) -> None:
        for mode in ("B", "N"):
            with self.subTest(mode=mode):
                self.service.update(mode=mode, preferred="new")
                self.assertEqual(self.state._select_version(self.config, self.request, self.service), "old")
                self.request["stale_route"] = False
                self.assertEqual(self.state._select_version(self.config, self.request, self.service), "new")
                self.request["stale_route"] = True

    def test_uncertified_control_retains_liveness_only_selection(self) -> None:
        self.config["strategy"] = "health_rollback"
        self.assertEqual(self.state._select_version(self.config, self.request, self.service), "new")

    def test_old_mode_route_over_loopback_tcp(self) -> None:
        from gateroll.proxy_process import Handler as ProxyHandler, Server as ProxyServer
        from gateroll.service_process import Handler as ServiceHandler, Server as ServiceServer, Store
        from gateroll.rpcutil import call

        servers, threads = [], []
        try:
            for version, values in (("old", {"a0": 12}), ("new", {})):
                server = ServiceServer(("127.0.0.1", 0), ServiceHandler)
                servers.append(server)
                server.store = Store(self.directory / (version + ".json"), version, True, False, False)
                server.store.load(values)
                self.service[version]["port"] = server.server_address[1]
            self.write_config()
            proxy = ProxyServer(("127.0.0.1", 0), ProxyHandler)
            servers.append(proxy)
            proxy.state = self.state
            for server in servers:
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
                thread.start()
                threads.append(thread)
            for retained_pin in (False, True):
                request = dict(self.request, cmd="request", session_id="tcp-session")
                if retained_pin:
                    self.state.pins["tcp-session"] = "new"
                response = call(proxy.server_address[1], request, timeout=2.0)
                self.assertTrue(response["available"])
                self.assertEqual(response["service_version"], "old")
                self.assertEqual(response["value"], 12)
            self.assertEqual(servers[1].store.canonical_dump()["values"], {})
        finally:
            # Only the three servers opened by this test are shut down.
            for server, thread in zip(servers, threads):
                if thread.is_alive():
                    server.shutdown()
            for server in servers:
                server.server_close()
            for thread in threads:
                thread.join(timeout=2.0)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
