"""Bounded, network-free compact/reference differential repair checks.

No processes, services, sockets, credentials, compilers or external inputs.
Writes one local JSON result; hard bounds are fixed in this entrypoint.
"""
from dataclasses import asdict
from itertools import product
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compact_precedence.model import Manifest as CM, ServiceFacts, EdgeFacts
from compact_precedence.planner import plan as compact_plan, explicit_frontier, frontier_member
from compact_precedence.checker import check_certificate
from gateroll.model import Manifest, Service, Edge, enumerate_configs, is_closed, false_atoms
from gateroll.planner import exact_frontier, minimum_blocking_witness
from gateroll.oracle import admitted as forward_admitted
from gateroll.families import load_pair_specs
from gateroll.generate import generate_all


def convert(m):
    return CM.build(m.names,
                    {s.name: ServiceFacts(**{k: v for k, v in asdict(s).items() if k != "name"})
                     for s in m.services},
                    [EdgeFacts(e.src, e.dst, e.n2o, e.o2n) for e in m.edges], m.case_id)


def run():
    counts = {k: 0 for k in ("cases", "decision_mismatches", "frontier_mismatches",
                              "checker_failures", "admitted_dead_end_failures",
                              "minimum_witness_checks", "minimum_witness_failures",
                              "historical_none_decision_artifacts")}
    groups = {}
    modes = ("O", "B", "N")

    def compare(m, group, minimum=False):
        cm = convert(m)
        cert = compact_plan(cm)
        frontier = exact_frontier(m)
        admitted = (0,) * len(m.services) in frontier
        counts["cases"] += 1
        groups[group] = groups.get(group, 0) + 1
        counts["decision_mismatches"] += (cert["admitted"] != admitted or
                                            forward_admitted(m) != admitted)
        counts["checker_failures"] += not check_certificate(cm, cert)[0]
        # Reconstruct the pre-repair oracle bug without importing an old file:
        # it returned None exactly when all-new was not closed.
        target_closed = is_closed(m, (2,) * len(m.services))
        if group == "two_service_14_atom_cube" and not target_closed:
            counts["historical_none_decision_artifacts"] += cert["admitted"] != None
        compact_explicit, compact_admitted = explicit_frontier(cm)
        expected_text = {tuple(modes[d] for d in cfg) for cfg in frontier}
        if compact_explicit != expected_text or compact_admitted != admitted:
            counts["frontier_mismatches"] += 1
        for cfg in enumerate_configs(m):
            text = tuple(modes[d] for d in cfg)
            if frontier_member(cm, dict(zip(m.names, text))) != (cfg in frontier):
                counts["frontier_mismatches"] += 1
        if admitted:
            closed = {cfg for cfg in enumerate_configs(m) if is_closed(m, cfg)}
            counts["admitted_dead_end_failures"] += frontier != closed
        elif minimum:
            counts["minimum_witness_checks"] += 1
            reference = minimum_blocking_witness(m)
            counts["minimum_witness_failures"] += len(reference) != len(cert["witness"]["atoms"])

    fields = ("refine", "bridge", "migrate", "auth", "idem", "session")
    for mask in range(1 << 14):
        bits = tuple(bool(mask & (1 << bit)) for bit in range(14))
        services = tuple(Service(s, **dict(zip(fields, bits[6*i:6*i+6])))
                         for i, s in enumerate(("a", "b")))
        m = Manifest(f"cube-{mask}", "repair", "cube", "two roles", services,
                     (Edge("a", "b", *bits[12:14]),))
        compare(m, "two_service_14_atom_cube", minimum=(mask % 64 == 0))

    # All one-role local/self-edge facts, including irrelevant stateless migration.
    for stateful in (False, True):
        for mask in range(1 << 8):
            bits = tuple(bool(mask & (1 << bit)) for bit in range(8))
            service = Service("a", stateful=stateful, **dict(zip(fields, bits[:6])))
            m = Manifest(f"self-{stateful}-{mask}", "repair", "self", "one role",
                         (service,), (Edge("a", "a", *bits[6:]),))
            compare(m, "one_service_self_edge_cube", minimum=True)

    # Every directional assignment on all six non-self edges of three roles.
    pairs = tuple((a, b) for a in ("a", "b", "c") for b in ("a", "b", "c") if a != b)
    for mask in range(1 << 12):
        edges = tuple(Edge(a, b, bool(mask & (1 << (2*i))), bool(mask & (1 << (2*i+1))))
                      for i, (a, b) in enumerate(pairs))
        m = Manifest(f"directions-{mask}", "repair", "directions", "three roles",
                     tuple(Service(s) for s in ("a", "b", "c")), edges)
        compare(m, "three_service_direction_cube", minimum=(mask % 32 == 0))

    # Direct use of the retained manifests avoids regenerating or changing them.
    corpus = ROOT / "results" / "raw" / "finite" / "generated_cases.jsonl"
    corpus_count = 0
    with corpus.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            corpus_count += 1
            if corpus_count > 12000:
                raise AssertionError("corpus exceeds the authorized finite bound")
            compare(Manifest.from_dict(json.loads(line)), "retained_12000_manifests")
    assert corpus_count == 12000
    # Verify that the generator really reconstructs the retained finite inputs.
    generated = generate_all(load_pair_specs(ROOT / "inputs"))
    with corpus.open(encoding="utf-8") as handle:
        retained = [json.loads(line) for line in handle if line.strip()]
    assert [m.to_dict() for m in generated] == retained

    failures = sum(counts[k] for k in ("decision_mismatches", "frontier_mismatches",
                                      "checker_failures", "admitted_dead_end_failures",
                                      "minimum_witness_failures"))
    return {"scope": "deterministic finite models only; no runtime services",
            "counts": counts, "groups": groups, "retained_generator_match": True,
            "pass": failures == 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "results" / "repair_checks"):
        raise SystemExit("output must stay in artifact/results/repair_checks")
    result = run()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
