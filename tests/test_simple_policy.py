"""Same-input policy controls, including null and blocked results."""
import unittest
from itertools import product
from unittest.mock import patch

from gateroll.checker import check
from gateroll.model import Edge, Manifest, Service, apply_defects, repaired
from gateroll.planner import plan
from gateroll.simple_policy import certificate, schedule


class SimplePolicyTests(unittest.TestCase):
    def base(self, services=3):
        names = tuple('abc'[:services])
        return Manifest('owned-policy', 'owned', 'owned', 'cycle',
                        tuple(Service(name) for name in names),
                        tuple(Edge(names[i], names[(i + 1) % services]) for i in range(services)))

    def test_full_certificate_contract_is_checked_not_donated(self):
        manifest = self.base()
        actual = certificate(manifest)
        self.assertEqual(actual, plan(manifest))
        self.assertTrue(check(manifest, actual)['accepted'])
        with patch('gateroll.simple_policy.schedule', return_value=None):
            with self.assertRaisesRegex(ValueError, 'disagrees with exact frontier'):
                certificate(manifest)

    def test_order_cycle_and_local_blocker_remain_blocked(self):
        manifest = self.base()
        for defects in (('edge:a>b:n2o', 'edge:b>c:n2o', 'edge:c>a:n2o'),
                        ('service:a:migrate',)):
            blocked = apply_defects(repaired(manifest), defects)
            self.assertIsNone(schedule(blocked))
            self.assertTrue(check(blocked, certificate(blocked))['accepted'])

    def test_every_direction_assignment_agrees_without_lookahead(self):
        manifest = self.base()
        atoms = tuple(f'edge:{edge.src}>{edge.dst}:{kind}' for edge in manifest.edges
                      for kind in ('n2o', 'o2n'))
        for mask in range(1 << len(atoms)):
            candidate = apply_defects(repaired(manifest),
                                      [atom for i, atom in enumerate(atoms) if mask & (1 << i)])
            supplied = certificate(candidate)
            self.assertEqual(supplied['admitted'], plan(candidate)['admitted'])
            self.assertTrue(check(candidate, supplied)['accepted'])

    def test_empty_stateless_and_self_edge_boundaries(self):
        empty = Manifest('empty', 'owned', 'owned', 'empty', (), ())
        self.assertEqual(schedule(empty), [[]])
        self_edge = Manifest('self', 'owned', 'owned', 'self',
                             (Service('a', stateful=False, migrate=False),),
                             (Edge('a', 'a', False, False),))
        self.assertEqual(schedule(self_edge), [[0], [1], [2]])
        self.assertTrue(check(self_edge, certificate(self_edge))['accepted'])


if __name__ == '__main__':
    unittest.main()
