from __future__ import annotations

import unittest
from pathlib import Path

from gateroll.checker import check
from gateroll.families import load_pair_specs
from gateroll.generate import CASES_PER_PAIR, generate_all
from gateroll.oracle import admitted as oracle_admitted
from gateroll.planner import plan


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.specs = load_pair_specs(cls.root / "inputs")
        cls.cases = generate_all(cls.specs)

    def test_frozen_counts_and_uniqueness(self) -> None:
        self.assertEqual(len(self.specs), 24)
        self.assertEqual(len({spec["family"] for spec in self.specs}), 8)
        self.assertEqual(len(self.cases), 24 * CASES_PER_PAIR)
        self.assertEqual(len({case.case_id for case in self.cases}), len(self.cases))
        for pair_index in range(24):
            subset = self.cases[pair_index * CASES_PER_PAIR:(pair_index + 1) * CASES_PER_PAIR]
            self.assertEqual(len({case.declared_defects for case in subset}), CASES_PER_PAIR)

    def test_representative_pairs_have_three_way_agreement(self) -> None:
        for pair_index in range(24):
            manifest = self.cases[pair_index * CASES_PER_PAIR]
            cert = plan(manifest)
            self.assertEqual(bool(cert["admitted"]), oracle_admitted(manifest))
            self.assertTrue(check(manifest, cert)["accepted"])


if __name__ == "__main__":
    unittest.main()
