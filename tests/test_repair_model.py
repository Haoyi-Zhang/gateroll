"""Network-free regression checks for the finite rolling-upgrade model."""
from copy import deepcopy
from dataclasses import replace
import unittest

from gateroll.model import Edge, Manifest, Service
from gateroll.planner import plan
from gateroll.checker import CertificateError, check
from compact_precedence.model import Manifest as CompactManifest, ServiceFacts, EdgeFacts
from compact_precedence.planner import plan as compact_plan, explicit_frontier, frontier_member, closed
from compact_precedence.checker import check_certificate


class CertificateDomainTests(unittest.TestCase):
    def setUp(self):
        self.manifest = Manifest("boundary", "boundary", "boundary", "two roles",
                                 (Service("a"), Service("b")), ())

    def test_schedule_digits_are_valid_before_encoding(self):
        authentic = plan(self.manifest)
        for malformed in ([4, -1], [True, 0], [1.0, 0], ["1", 0]):
            candidate = deepcopy(authentic)
            candidate["schedule"][1] = malformed
            with self.subTest(malformed=malformed), self.assertRaises(CertificateError):
                check(self.manifest, candidate)

    def test_witness_must_be_unique_and_false_in_manifest(self):
        manifest = replace(self.manifest, services=(Service("a", bridge=False), Service("b")))
        authentic = plan(manifest)
        for atoms in (["service:b:bridge"], ["service:a:bridge"] * 2, ["unknown"], [0]):
            candidate = deepcopy(authentic)
            candidate["witness"] = atoms
            with self.subTest(atoms=atoms), self.assertRaises(CertificateError):
                check(manifest, candidate)
        self.assertTrue(check(manifest, authentic)["accepted"])

    def test_empty_manifest_is_admitted(self):
        manifest = replace(self.manifest, services=())
        self.assertTrue(check(manifest, plan(manifest))["admitted"])

    def test_actual_false_bridge_witness_must_be_deletion_minimal(self):
        manifest = replace(self.manifest,
                           services=(Service("a", bridge=False), Service("b", bridge=False)))
        authentic = plan(manifest)
        for atom in ("service:a:bridge", "service:b:bridge"):
            singleton = deepcopy(authentic)
            singleton["witness"] = [atom]
            self.assertTrue(check(manifest, singleton)["accepted"])
        redundant = deepcopy(authentic)
        redundant["witness"] = ["service:a:bridge", "service:b:bridge"]
        with self.assertRaisesRegex(CertificateError, "^witness is not deletion-minimal$"):
            check(manifest, redundant)

    def test_actual_false_cycle_plus_local_witness_is_redundant(self):
        manifest = replace(self.manifest,
                           services=(Service("a", bridge=False), Service("b"), Service("c")),
                           edges=(Edge("a", "b", n2o=False), Edge("b", "c", n2o=False),
                                  Edge("c", "a", n2o=False)))
        authentic = plan(manifest)
        cycle = ["edge:a>b:n2o", "edge:b>c:n2o", "edge:c>a:n2o"]
        local = ["service:a:bridge"]
        for witness in (cycle, local):
            minimal = deepcopy(authentic)
            minimal["witness"] = witness
            self.assertTrue(check(manifest, minimal)["accepted"])
        redundant = deepcopy(authentic)
        redundant["witness"] = cycle + local
        with self.assertRaisesRegex(CertificateError, "^witness is not deletion-minimal$"):
            check(manifest, redundant)

    def test_admission_requires_a_boolean(self):
        certificate = plan(self.manifest)
        certificate["admitted"] = "true"
        with self.assertRaises(CertificateError):
            check(self.manifest, certificate)


class CompactBoundaryTests(unittest.TestCase):
    def test_self_direction_guards_are_vacuous(self):
        for n2o in (False, True):
            for o2n in (False, True):
                manifest = CompactManifest.build(("a",), {"a": ServiceFacts()},
                                                 [EdgeFacts("a", "a", n2o, o2n)])
                certificate = compact_plan(manifest)
                frontier, admitted = explicit_frontier(manifest)
                self.assertTrue(admitted)
                self.assertTrue(certificate["admitted"])
                self.assertEqual(frontier, {("O",), ("B",), ("N",)})
                self.assertTrue(check_certificate(manifest, certificate)[0])
                for mode in ("O", "B", "N"):
                    self.assertTrue(frontier_member(manifest, {"a": mode}))

    def test_invalid_target_has_boolean_blocked_decision(self):
        manifest = CompactManifest.build(("a",), {"a": ServiceFacts(refine=False)}, [])
        self.assertEqual(explicit_frontier(manifest), (set(), False))

    def test_configuration_domain_is_exact(self):
        manifest = CompactManifest.build(("a",), {"a": ServiceFacts()}, [])
        for config in ({}, {"a": "invalid"}, {"a": "O", "extra": "O"}):
            self.assertFalse(closed(manifest, config))
            self.assertFalse(frontier_member(manifest, config))

    def test_bridge_defect_can_be_in_past_but_not_crossed(self):
        manifest = CompactManifest.build(("a",), {"a": ServiceFacts(bridge=False)}, [])
        self.assertEqual(explicit_frontier(manifest), ({("N",)}, False))
        self.assertFalse(frontier_member(manifest, {"a": "O"}))
        self.assertTrue(frontier_member(manifest, {"a": "N"}))

    def test_checker_rejects_nonminimum_cycle_and_false_cardinality(self):
        names = ("a", "b", "c", "d", "e")
        local = {s: ServiceFacts() for s in names}
        long_edges = [EdgeFacts("c", "d", False), EdgeFacts("d", "e", False),
                      EdgeFacts("e", "c", False)]
        manifest = CompactManifest.build(names, local,
                                         long_edges + [EdgeFacts("a", "b", False), EdgeFacts("b", "a", False)])
        certificate = compact_plan(manifest)
        self.assertTrue(check_certificate(manifest, certificate)[0])
        self.assertEqual(certificate["witness"]["minimum_cardinality"], 2)
        candidate = deepcopy(certificate)
        candidate["witness"] = compact_plan(CompactManifest.build(names, local, long_edges))["witness"]
        self.assertEqual(check_certificate(manifest, candidate), (False, "witness-minimum"))
        candidate = deepcopy(certificate)
        candidate["witness"]["minimum_cardinality"] = 99
        self.assertEqual(check_certificate(manifest, candidate), (False, "witness-minimum"))


if __name__ == "__main__":
    unittest.main()
