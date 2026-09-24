from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_campaign_case import execute


class RuntimePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def run_case(self, campaign: int, strategy: str = "certified") -> dict:
        with tempfile.TemporaryDirectory(prefix="gateroll-test-") as temp:
            return execute(self.root, campaign, strategy, Path(temp) / "run")

    def test_live_inventory_and_certificate_preflights(self) -> None:
        for campaign, reason in ((5, "missing-adapter"), (6, "authorization-mismatch"), (8, "certificate-rejected")):
            payload = self.run_case(campaign)
            self.assertEqual(payload["run"]["block_reason"], reason)
            self.assertEqual(payload["run"]["strategy_admitted"], 0)
            self.assertEqual(payload["run"]["semantic_violations"], 0)

    def test_partial_migration_is_detected_by_cardinality(self) -> None:
        payload = self.run_case(7)
        self.assertEqual(payload["run"]["block_reason"], "migration-cardinality")
        aborts = [row for row in payload["journal"] if row.get("action") == "abort"]
        self.assertEqual(len(aborts), 1)
        self.assertEqual(aborts[0]["reason"], "cardinality")
        loads = [row for row in payload["journal"] if row.get("action") == "load"]
        self.assertTrue(any(int(row["source_count"]) != int(row["target_count"]) for row in loads))


if __name__ == "__main__":
    unittest.main()
