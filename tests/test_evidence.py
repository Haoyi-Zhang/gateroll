from __future__ import annotations

import csv
import json
import os
import unittest
from pathlib import Path


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        artifact = Path(__file__).resolve().parents[1]
        cls.results = Path(os.environ.get("GATEROLL_RESULTS", artifact / "results" / "raw")).resolve()
        cls.finite = json.loads((cls.results / "finite" / "finite_summary.json").read_text(encoding="utf-8"))
        cls.tiny = json.loads((cls.results / "tiny_exhaustive.json").read_text(encoding="utf-8"))
        cls.campaign = json.loads((cls.results / "campaigns" / "campaign_summary.json").read_text(encoding="utf-8"))
        with (cls.results / "campaigns" / "campaign_runs.csv").open(encoding="utf-8", newline="") as handle:
            cls.runs = list(csv.DictReader(handle))

    def test_finite_evidence_closes(self) -> None:
        self.assertEqual(self.finite["case_count"], 12000)
        self.assertEqual(self.finite["planner_oracle_agreement"], 12000)
        self.assertEqual(self.finite["checker_accepts"], 12000)
        self.assertEqual(self.finite["certificate_mutations"], {"count": 96, "rejected": 96})
        self.assertEqual(self.tiny["models"], 256)
        self.assertEqual(self.tiny["planner_oracle_checker_agreement"], 256)

    def test_every_projection_has_a_negative_control(self) -> None:
        for name, row in self.finite["baselines"].items():
            self.assertGreater(row["false_admission"] + row["false_block"], 0, name)
        for dimension, count in self.finite["dimension_ablations"].items():
            self.assertGreater(count, 0, dimension)

    def test_campaign_dimensions(self) -> None:
        self.assertEqual(self.campaign["campaigns"], 40)
        self.assertEqual(self.campaign["topologies"], 4)
        self.assertEqual(self.campaign["fault_classes"], 10)
        self.assertEqual(self.campaign["strategy_runs"], 240)
        self.assertEqual(self.campaign["transaction_records"], 8640)

    def test_certified_outcomes(self) -> None:
        row = self.campaign["strategies"]["certified"]
        self.assertEqual(row["semantic_violations"], 0)
        self.assertEqual(row["violating_runs"], 0)
        self.assertEqual(row["completed_expected_cutovers"], 16)
        self.assertEqual(row["expected_cutover_runs"], 16)
        self.assertEqual(row["mean_unaffected_availability"], 1.0)

    def test_all_comparisons_expose_semantic_counterexamples(self) -> None:
        for strategy, row in self.campaign["strategies"].items():
            if strategy != "certified":
                self.assertGreater(row["violating_runs"], 0, strategy)

    def test_executable_preflight_reasons_and_journal(self) -> None:
        certified = {row["fault"]: [] for row in self.runs if row["strategy"] == "certified"}
        for row in self.runs:
            if row["strategy"] == "certified":
                certified[row["fault"]].append(row)
        expected = {
            "missing_adapter": "missing-adapter",
            "authorization_mismatch": "authorization-mismatch",
            "partial_migration": "migration-cardinality",
            "corrupt_certificate": "certificate-rejected",
        }
        for fault, reason in expected.items():
            rows = certified[fault]
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["block_reason"] == reason for row in rows))
            self.assertTrue(all(int(row["strategy_admitted"]) == 0 for row in rows))
            self.assertTrue(all(int(row["semantic_violations"]) == 0 for row in rows))
        journal = (self.results / "campaigns" / "certified_journals.jsonl").read_text(encoding="utf-8")
        self.assertIn('"action":"abort"', journal)
        self.assertIn('"reason":"cardinality"', journal)

    def test_no_fault_stop_world_is_semantically_clean(self) -> None:
        rows = [row for row in self.runs if row["strategy"] == "stop_the_world" and row["fault"] == "none"]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(int(row["semantic_violations"]) == 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
