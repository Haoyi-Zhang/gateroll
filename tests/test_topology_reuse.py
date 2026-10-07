"""Portable owned finite topology/certificate reference; no runtime programmes."""
from copy import deepcopy
from dataclasses import replace
from itertools import combinations, product
import unittest
from unittest.mock import PropertyMock, patch

from gateroll import model, planner, checker, oracle
from gateroll.model import Edge, Manifest, Service


def scan_closed(manifest, config):
    """Four literal rules and last matching-name scan; no topology dictionary."""
    if len(config) != len(manifest.services):
        return False
    for mode, service in zip(config, manifest.services):
        if mode == 1:
            if not all((service.bridge, service.auth, service.idem, service.session)):
                return False
            if service.stateful and not service.migrate:
                return False
        elif mode == 2:
            if not all((service.refine, service.auth, service.idem)):
                return False
        elif mode != 0:
            return False

    def mode_at(name):
        hits = [i for i, service in enumerate(manifest.services) if service.name == name]
        if not hits:
            raise KeyError(name)
        return config[hits[-1]]

    for edge in manifest.edges:
        source, target = mode_at(edge.src), mode_at(edge.dst)
        if source in (1, 2) and target == 0 and not edge.n2o:
            return False
        if source in (0, 1) and target == 2 and not edge.o2n:
            return False
    return True


def cartesian_frontier(manifest):
    """Literal Cartesian enumeration and reverse topological dynamic program."""
    states = list(product((0, 1, 2), repeat=len(manifest.services)))
    closed = {state for state in states if scan_closed(manifest, state)}
    target = (2,) * len(manifest.services)
    viable = {target} if target in closed else set()
    for state in reversed(states):
        if state not in closed:
            continue
        for index, mode in enumerate(state):
            if mode < 2:
                child = state[:index] + (mode + 1,) + state[index + 1:]
                if child in viable:
                    viable.add(state)
    return closed, viable


def literal_certificate(manifest):
    closed, frontier = cartesian_frontier(manifest)
    start = (0,) * len(manifest.services)
    target = (2,) * len(manifest.services)
    admitted = start in frontier
    schedule = []
    witness = []
    if admitted:
        queue = [start]
        parent = {start: None}
        while queue:
            state = queue.pop(0)
            if state == target:
                while state is not None:
                    schedule.append(list(state))
                    state = parent[state]
                schedule.reverse()
                break
            for index, mode in enumerate(state):
                if mode == 2:
                    continue
                child = state[:index] + (mode + 1,) + state[index + 1:]
                if child in frontier and child not in parent:
                    parent[child] = state
                    queue.append(child)
    else:
        fields = ("refine", "bridge", "migrate", "auth", "idem", "session")
        false = []
        for service in manifest.services:
            for field in fields:
                if field != "migrate" or service.stateful:
                    if not getattr(service, field):
                        false.append("service:" + service.name + ":" + field)
        for edge in manifest.edges:
            for field in ("n2o", "o2n"):
                if not getattr(edge, field):
                    false.append("edge:" + edge.src + ">" + edge.dst + ":" + field)
        false.sort()
        for size in range(1, len(false) + 1):
            for subset in combinations(false, size):
                services = tuple(Service(
                    service.name, stateful=service.stateful,
                    **{field: "service:" + service.name + ":" + field not in subset
                       for field in fields}) for service in manifest.services)
                edges = tuple(Edge(edge.src, edge.dst,
                                   "edge:" + edge.src + ">" + edge.dst + ":n2o" not in subset,
                                   "edge:" + edge.src + ">" + edge.dst + ":o2n" not in subset)
                              for edge in manifest.edges)
                candidate = replace(manifest, services=services, edges=edges)
                if start not in cartesian_frontier(candidate)[1]:
                    witness = list(subset)
                    break
            if witness:
                break
    return {"case_id": manifest.case_id, "family": manifest.family, "pair": manifest.pair,
            "topology": manifest.topology, "services": [s.name for s in manifest.services],
            "admitted": admitted, "frontier": [list(c) for c in sorted(frontier)],
            "schedule": schedule, "witness": witness}


def finite_manifests():
    # Same frozen eight obligations, constructed directly rather than importing
    # corpus inputs, runtime fixtures or the producer's defect application.
    for mask in range(256):
        truth = [not bool(mask & (1 << i)) for i in range(8)]
        services = (Service("a", refine=truth[0], bridge=truth[1], auth=truth[2]),
                    Service("b", refine=truth[3], bridge=truth[4], auth=truth[5]))
        yield Manifest("cube-" + str(mask), "owned", "eight atoms", "two roles",
                       services, (Edge("a", "b", truth[6], truth[7]),))
    for size in range(6):
        for variant in range(4):
            services = tuple(Service("role-" + str(i), stateful=(i + variant) % 2 == 0,
                                     migrate=not (variant == 1 and i == 0),
                                     bridge=not (variant == 3 and i == size - 1))
                             for i in range(size))
            names = [service.name for service in services]
            edges = tuple(Edge(names[i], names[(i + 1) % size],
                               n2o=variant != 2, o2n=variant != 1) for i in range(size))
            if size:
                edges += (Edge(names[0], names[0], False, False),)
                if variant == 3:
                    edges += edges[:1]
            yield Manifest("shape-" + str(size) + "-" + str(variant), "owned", "finite",
                           "ring/repeated/self", services, edges)


def outcome(call):
    try:
        return ("return", call())
    except (KeyError, TypeError, ValueError, IndexError) as error:
        return (type(error).__name__, str(error))


def boundary_cases():
    normal = Manifest("boundary", "owned", "boundary", "two roles",
                      (Service("a"), Service("b")), (Edge("missing", "b"),))
    for config in ((), (0,), (0, 0, 0), (3, 0), ("0", 0), (True, 0), (1.0, 0),
                   (0, 0), (1, 0), (2, 2)):
        yield normal, config
    blocked = replace(normal, services=(Service("a", bridge=False), Service("b")))
    for config in ((1, 0), (0, 0), (2, 2), (3, 0)):
        yield blocked, config
    first_block = replace(normal, edges=(Edge("a", "b", n2o=False), Edge("missing", "b")))
    for config in ((1, 0), (0, 0), (2, 2)):
        yield first_block, config
    # Last-name-wins behavior is preserved, not silently replaced by a new
    # uniqueness admission rule in the data class.
    duplicate = replace(normal, services=(Service("a"), Service("a")),
                        edges=(Edge("a", "a", False, False),))
    for config in product((0, 1, 2), repeat=2):
        yield duplicate, config


class TopologyReuseRegression(unittest.TestCase):
    def test_every_frozen_closure_and_complete_certificate(self):
        cases = list(finite_manifests())
        self.assertEqual(len(cases), 280)
        for manifest in cases:
            with self.subTest(case=manifest.case_id):
                protected = manifest.to_dict()
                for config in product((0, 1, 2), repeat=len(manifest.services)):
                    self.assertEqual(model.is_closed(manifest, config), scan_closed(manifest, config))
                expected = literal_certificate(manifest)
                actual = planner.plan(manifest)
                self.assertEqual(actual, expected)
                self.assertEqual(planner.closed_set(manifest), cartesian_frontier(manifest)[0])
                self.assertEqual(planner.exact_frontier(manifest), cartesian_frontier(manifest)[1])
                verdict = checker.check(manifest, actual)
                self.assertEqual(verdict, {"accepted": True, "admitted": actual["admitted"],
                                          "frontier_states": len(actual["frontier"]),
                                          "schedule_steps": max(0, len(actual["schedule"]) - 1),
                                          "witness_atoms": len(actual["witness"])})
                self.assertEqual(oracle.admitted(manifest), expected["admitted"])
                self.assertEqual(manifest.to_dict(), protected)

    def test_lookup_constructed_once_per_closed_set(self):
        for manifest in list(finite_manifests())[-24:]:
            with patch.object(model.Manifest, "names", new_callable=PropertyMock,
                              return_value=tuple(s.name for s in manifest.services)) as names:
                result = planner.closed_set(manifest)
                self.assertEqual(names.call_count, 1)
            self.assertEqual(result, cartesian_frontier(manifest)[0])
        manifest = next(finite_manifests())
        with patch.object(model.Manifest, "names", new_callable=PropertyMock,
                          return_value=("a", "b")) as names:
            for config in product((0, 1, 2), repeat=2):
                model.is_closed(manifest, config)
            self.assertEqual(names.call_count, 9)

    def test_invalid_length_local_before_edge_and_edge_order(self):
        cases = list(boundary_cases())
        self.assertEqual(len(cases), 26)
        for manifest, config in cases:
            with self.subTest(config=config, manifest=manifest.to_dict()):
                self.assertEqual(outcome(lambda: model.is_closed(manifest, config)),
                                 outcome(lambda: scan_closed(manifest, config)))
        first = replace(cases[0][0], services=(Service("a", bridge=False), Service("b")),
                        edges=(Edge("missing", "b"),))
        self.assertFalse(model.is_closed(first, (1, 0)))
        with self.assertRaisesRegex(KeyError, "missing"):
            model.is_closed(first, (0, 0))

    def test_renaming_reordering_and_invocation_locality(self):
        base = list(finite_manifests())[-1]
        previous = planner.plan(base)
        for names in (["x" + str(i) for i in range(5)], ["λ" + str(i) for i in range(5)]):
            mapping = dict(zip([s.name for s in base.services], names))
            renamed = replace(base,
                              services=tuple(replace(s, name=mapping[s.name]) for s in reversed(base.services)),
                              edges=tuple(replace(e, src=mapping[e.src], dst=mapping[e.dst])
                                          for e in reversed(base.edges)))
            self.assertEqual(planner.plan(renamed), literal_certificate(renamed))
        changed = replace(base, services=tuple(replace(s, bridge=True, migrate=True)
                                              for s in base.services),
                          edges=tuple(replace(e, n2o=True, o2n=True) for e in base.edges))
        self.assertEqual(planner.plan(changed), literal_certificate(changed))
        self.assertNotEqual(planner.plan(changed), previous)
        self.assertEqual(planner.plan(base), previous)

    def test_false_atom_reference_checker_deletion_controls(self):
        manifest = Manifest("false", "owned", "false", "two roles",
                            (Service("a", bridge=False), Service("b", bridge=False)), ())
        authentic = literal_certificate(manifest)
        for witness in (["service:a:bridge"], ["service:b:bridge"]):
            candidate = deepcopy(authentic)
            candidate["witness"] = witness
            self.assertTrue(checker.check(manifest, candidate)["accepted"])
        candidate = deepcopy(authentic)
        candidate["witness"] = ["service:a:bridge", "service:b:bridge"]
        with self.assertRaisesRegex(checker.CertificateError, "^witness is not deletion-minimal$"):
            checker.check(manifest, candidate)
        # A larger deletion-minimal cycle is still acceptable to the reference
        # checker even though a smaller singleton exists in the same manifest.
        cyclic = replace(manifest, services=(Service("a", bridge=False), Service("b"), Service("c")),
                         edges=(Edge("a", "b", False), Edge("b", "c", False), Edge("c", "a", False)))
        cert = literal_certificate(cyclic)
        cycle = ["edge:a>b:n2o", "edge:b>c:n2o", "edge:c>a:n2o"]
        for witness in (cycle, ["service:a:bridge"]):
            candidate = deepcopy(cert)
            candidate["witness"] = witness
            self.assertTrue(checker.check(cyclic, candidate)["accepted"])
        candidate = deepcopy(cert)
        candidate["witness"] = cycle + ["service:a:bridge"]
        with self.assertRaisesRegex(checker.CertificateError, "^witness is not deletion-minimal$"):
            checker.check(cyclic, candidate)

    def test_checker_does_not_consume_producer_closure_helper(self):
        manifest = next(finite_manifests())
        certificate = literal_certificate(manifest)
        with patch.object(model, "_is_closed_indexed", side_effect=AssertionError("producer helper")):
            self.assertTrue(checker.check(manifest, certificate)["accepted"])
            self.assertTrue(oracle.admitted(manifest))


if __name__ == "__main__":
    unittest.main()
