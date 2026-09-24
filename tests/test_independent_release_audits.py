from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class IndependentReleaseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = load("metamorphic_model_audit", ROOT / "audit" / "metamorphic_model_audit.py")
        cls.scale = load("frontier_scaling_audit", ROOT / "audit" / "frontier_scaling_audit.py")

    def test_two_independent_deciders_agree_on_boundary_masks(self):
        masks = [0, 1, (1 << 14) - 1, 0x1555, 0x2AAA, 0x3FFE]
        for mask in masks:
            model = self.meta.model_from_mask(mask)
            a = self.meta.frontier_a(model)[1] is not None
            b = self.meta.schedulable_b(model)
            self.assertEqual(a, b, hex(mask))

    def test_repair_monotonicity_on_boundary_masks(self):
        for mask in [0x3FFF, 0x3FFE, 0x1FFF, 0x2FFF, 0x37FF]:
            model = self.meta.model_from_mask(mask)
            admitted = self.meta.frontier_a(model)[1] is not None
            if admitted:
                for bit in range(14):
                    if not ((mask >> bit) & 1):
                        self.assertIsNotNone(self.meta.frontier_a(self.meta.repair_bit(model, bit))[1])

    def test_scale_structural_oracles_small(self):
        repaired = self.scale.exact_counts(5, "repaired_chain")
        self.assertEqual(repaired["frontier_configurations"], 3 ** 5)
        self.assertTrue(repaired["admitted"])
        self.assertFalse(self.scale.exact_counts(5, "direction_cycle")["admitted"])
        self.assertFalse(self.scale.exact_counts(5, "single_bridge_defect")["admitted"])

    def test_frozen_audit_evidence_complete(self):
        base = ROOT / "results" / "independent-audits"
        meta = json.loads((base / "metamorphic-model-audit.json").read_text())
        scale = json.loads((base / "frontier-scaling-audit.json").read_text())
        refs = json.loads((ROOT / "audit" / "reference-metadata-audit.json").read_text())
        self.assertTrue(meta["complete"])
        self.assertEqual(meta["semantic"]["exhaustive_two_service_assignments"], 16384)
        self.assertTrue(scale["complete"])
        self.assertEqual(len(scale["semantic"]["rows"]), 33)
        self.assertTrue(refs["complete"])
        self.assertGreaterEqual(refs["semantic"]["entry_count"], 55)
        self.assertEqual(refs["semantic"]["resolved_count"], refs["semantic"]["entry_count"])


if __name__ == "__main__":
    unittest.main()
