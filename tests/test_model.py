from __future__ import annotations

import unittest

from gateroll.checker import CertificateError, check
from gateroll.model import Edge, Manifest, Service, apply_defects, is_closed, repaired
from gateroll.oracle import admitted as oracle_admitted
from gateroll.planner import exact_frontier, minimum_blocking_witness, plan, shortest_schedule


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Manifest(
            case_id="unit",
            family="unit",
            pair="unit",
            topology="cycle3",
            services=(Service("a"), Service("b"), Service("c")),
            edges=(Edge("a", "b"), Edge("b", "c"), Edge("c", "a")),
        )

    def test_repaired_manifest_has_complete_frontier_path(self) -> None:
        frontier = exact_frontier(self.base)
        schedule = shortest_schedule(self.base, frontier)
        self.assertIn((0, 0, 0), frontier)
        self.assertIn((2, 2, 2), frontier)
        self.assertIsNotNone(schedule)
        self.assertEqual(len(schedule or []), 7)
        self.assertTrue(oracle_admitted(self.base))

    def test_direction_cycle_is_blocking_and_minimum(self) -> None:
        defects = (
            "edge:a>b:n2o",
            "edge:b>c:n2o",
            "edge:c>a:n2o",
        )
        manifest = apply_defects(repaired(self.base), defects, case_id="cycle")
        cert = plan(manifest)
        self.assertFalse(cert["admitted"])
        self.assertEqual(tuple(cert["witness"]), defects)
        self.assertEqual(minimum_blocking_witness(manifest), defects)
        self.assertTrue(check(manifest, cert)["accepted"])
        for atom in defects:
            reduced = tuple(x for x in defects if x != atom)
            self.assertTrue(oracle_admitted(apply_defects(repaired(self.base), reduced)))

    def test_bridge_requires_local_obligations(self) -> None:
        broken = apply_defects(repaired(self.base), ("service:a:session",), case_id="session")
        self.assertFalse(is_closed(broken, (1, 0, 0)))
        self.assertTrue(is_closed(broken, (0, 0, 0)))

    def test_checker_rejects_frontier_omission(self) -> None:
        cert = plan(self.base)
        corrupted = dict(cert)
        corrupted["frontier"] = list(cert["frontier"][:-1])
        with self.assertRaises(CertificateError):
            check(self.base, corrupted)


if __name__ == "__main__":
    unittest.main()
