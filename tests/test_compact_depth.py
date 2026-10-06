"""Owned finite structural regressions for compact graph traversal depth."""
from dataclasses import replace
import sys
import unittest

from compact_precedence.model import Manifest, ServiceFacts, EdgeFacts
from compact_precedence.planner import plan, frontier_member
from compact_precedence.checker import check_certificate


def depth_manifest(layer, *, cycle=False, local_block=False, count=1200):
    names = tuple(f"s{i:04d}" for i in range(count))
    pairs = list(zip(names, names[1:]))
    if cycle:
        pairs.append((names[-1], names[0]))
    edges = [EdgeFacts(b, a, False, True) if layer == "B"
             else EdgeFacts(a, b, True, False) for a, b in pairs]
    local = {s: ServiceFacts() for s in names}
    if local_block:
        local[names[-1]] = replace(local[names[-1]], bridge=False)
    return Manifest.build(names, local, edges, f"owned-depth-{layer}-{cycle}-{local_block}")


def structural_certificate(manifest, layer, *, cycle=False, local_block=False):
    """Construct expected fields from the chain/ring shape, not planner output."""
    names = manifest.services
    events = sorted(f"{layer}:{s}" for s in names)
    admitted = not cycle and not local_block
    if local_block:
        witness = {"kind": "local", "atoms": [f"local:{names[-1]}:bridge"],
                   "minimum_cardinality": 1}
    elif cycle:
        atoms = ([f"edge:{b}->{a}:n2o" for a, b in zip(names, names[1:] + names[:1])]
                 if layer == "B" else
                 [f"edge:{a}->{b}:o2n" for a, b in zip(names, names[1:] + names[:1])])
        witness = {"kind": "cycle", "layer": layer, "atoms": atoms,
                   "services": list(names) + [names[0]], "minimum_cardinality": len(names)}
    else:
        witness = None
    return {
        "schema": "gateroll.compact-precedence.v1",
        "manifest_digest": manifest.digest(), "services": list(names),
        "admitted": admitted,
        "frontier_summary": {
            "target_closed": True, "cyclic_sccs": [events] if cycle else [],
            "mandatory_events": events if cycle else [],
            "disabled_events": [f"B:{names[-1]}"] if local_block else [],
            "frontier_empty": False,
        },
        "event_order": ([f"{kind}:{s}" for kind in ("B", "N") for s in names]
                        if admitted else None), "witness": witness,
    }


class CompactDepthTests(unittest.TestCase):
    def verify_shape(self, layer, *, cycle=False, local_block=False):
        limit = sys.getrecursionlimit()
        manifest = depth_manifest(layer, cycle=cycle, local_block=local_block)
        expected = structural_certificate(manifest, layer, cycle=cycle, local_block=local_block)
        # This checker call is isolated from the planner: it also failed before
        # the repair on an independently supplied admissible chain certificate.
        self.assertEqual(check_certificate(manifest, expected), (True, "ok"))
        actual = plan(manifest)
        self.assertEqual(actual["admitted"], expected["admitted"])
        self.assertEqual(actual["frontier_summary"], expected["frontier_summary"])
        self.assertEqual(check_certificate(manifest, actual), (True, "ok"))
        if not expected["admitted"]:
            self.assertEqual(actual["witness"]["minimum_cardinality"],
                             expected["witness"]["minimum_cardinality"])
        self.assertTrue(frontier_member(manifest, {s: "N" for s in manifest.services}))
        self.assertEqual(frontier_member(manifest, {s: "O" for s in manifest.services}),
                         expected["admitted"])
        self.assertEqual(sys.getrecursionlimit(), limit)

    def test_deep_bridge_layer_dag(self):
        self.verify_shape("B")

    def test_deep_new_layer_dag(self):
        self.verify_shape("N")

    def test_deep_bridge_layer_ring(self):
        self.verify_shape("B", cycle=True)

    def test_deep_new_layer_ring(self):
        self.verify_shape("N", cycle=True)

    def test_deep_dag_with_disabled_bridge(self):
        self.verify_shape("B", local_block=True)

    def test_deep_ring_with_smaller_local_blocker(self):
        self.verify_shape("N", cycle=True, local_block=True)


if __name__ == "__main__":
    unittest.main()
