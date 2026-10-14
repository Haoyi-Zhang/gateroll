"""Same manifest, full certificate and runtime contract; finite/native controls.

All workloads are owned local fixtures. No production or independent-runtime
claim: both policies use the same enforcement, checker, frontier and blockers.
Native costs include startup, workload and cleanup; child CPU/RSS and transient
storage are not measured. Both modes require fresh private output paths.
"""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from gateroll.campaigns import RuntimeRun, scenario_specs
from gateroll.checker import check
from gateroll.families import base_manifest, load_pair_specs
from gateroll.generate import generate_all
from gateroll.model import Manifest
from gateroll.planner import plan
from gateroll.portable_runtime import fresh_directory
from gateroll.rpcutil import atomic_json
from gateroll.simple_policy import certificate as policy_certificate


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def bind(root, output):
    names = sorted([p.relative_to(root).as_posix() for p in (root / 'gateroll').glob('*.py')]
                   + ['scripts/run_same_information.py', 'inputs/release_pairs.json'])
    atomic_json(output / 'bindings.json', {
        'source_sha256': {name: sha256((root / name).read_bytes()).hexdigest() for name in names},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'bytecode_disabled': bool(sys.dont_write_bytecode)},
        'literal_scope': 'Executed listed gateroll path and fixed pair inputs; shared runtime/specification, not independent semantic validation.',
    })


def finite(root, output):
    rows, costs = [], {'reference': [], 'simple_policy': []}
    for index, manifest in enumerate(generate_all(load_pair_specs(root / 'inputs'))):
        certificates = {}
        for name, builder in (('reference', plan), ('simple_policy', policy_certificate)):
            start = time.perf_counter_ns()
            supplied = builder(manifest)
            encoded = json.dumps(supplied, sort_keys=True, separators=(',', ':')).encode('utf-8')
            check(manifest, supplied)
            elapsed = (time.perf_counter_ns() - start) / 1e6
            certificates[name] = supplied
            if index % 10 == 0:
                costs[name].append(elapsed)
        left, right = certificates['reference'], certificates['simple_policy']
        assert left == right, manifest.case_id
        rows.append({'case_id': manifest.case_id, 'admitted': int(left['admitted']),
                     'certificate_equal': True, 'frontier_states': len(left['frontier']),
                     'full_certificate_bytes': len(encoded)})
    assert len(rows) == 12000
    with (output / 'decisions.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    atomic_json(output / 'cost_samples.json', costs)
    return {'cases': len(rows), 'exact_full_certificates_equal': len(rows),
            'admitted': sum(row['admitted'] for row in rows),
            'cost_scope': 'Current builder + serialization + common checker; full frontier and minimum blocker included; 1200 samples per mode. Fixed reference-then-policy order; no portable speedup inference.',
            'cost_ms': {name: {'samples': len(values), 'median': statistics.median(values),
                               'p95': percentile(values, .95)} for name, values in costs.items()}}


def native(root, output):
    samples = []
    for campaign_index, (_topology, fault, pair_index, spec) in enumerate(scenario_specs(root / 'inputs')):
        base = base_manifest(spec, pair_index)
        manifest = Manifest(f'campaign-{campaign_index:02d}', base.family, base.pair,
                            base.topology, base.services, base.edges, base.declared_defects)
        order = (('reference', plan), ('simple_policy', policy_certificate))
        if campaign_index % 2:
            order = tuple(reversed(order))
        pair = []
        for name, builder in order:
            start, cpu = time.perf_counter(), time.process_time()
            certificate = builder(manifest)
            check(manifest, certificate)
            admitted_seconds = time.perf_counter() - start
            run_dir = output / 'runs' / f'{campaign_index:02d}-{name}'
            runtime = RuntimeRun(root, run_dir, manifest, certificate, 'certified', fault)
            try:
                transactions, run = runtime.run()
            finally:
                runtime.close()
            duration, parent_cpu = time.perf_counter() - start, time.process_time() - cpu
            # Result packaging is outside the measured lifecycle.
            observations = [json.loads(line) for line in
                            (run_dir / 'rpc_observations.jsonl').read_text(encoding='utf-8').splitlines()]
            journal = ([json.loads(line) for line in runtime.journal_path.read_text(encoding='utf-8').splitlines()]
                       if runtime.journal_path.exists() else [])
            file_bytes = {path.relative_to(run_dir).as_posix(): path.stat().st_size
                          for path in run_dir.rglob('*') if path.is_file()}
            row = {'policy': name, 'campaign': campaign_index, 'manifest': manifest.to_dict(),
                   'certificate': certificate, 'run': run, 'transactions': transactions,
                   'rpc_observations': observations, 'journal': journal,
                   'admission_check_seconds': admitted_seconds, 'lifecycle_wall_seconds': duration,
                   'lifecycle_parent_cpu_seconds': parent_cpu, 'file_bytes': file_bytes,
                   'logical_final_file_bytes': sum(file_bytes.values()),
                   'native': 'Actual Python child services/proxy over localhost TCP; same runtime for both policies.'}
            pair.append(row)
            samples.append(row)
            print(f'campaign={campaign_index:02d} policy={name} violations={run["semantic_violations"]}', flush=True)
        left, right = pair
        assert left['certificate'] == right['certificate']
        for key in ('semantic_violations', 'final_new', 'strategy_admitted', 'block_reason',
                    'availability_overall', 'availability_affected', 'availability_unaffected'):
            assert left['run'][key] == right['run'][key], (campaign_index, key)
    assert len(samples) == 80
    with (output / 'samples.jsonl').open('x', encoding='utf-8') as handle:
        for row in samples:
            handle.write(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n')
    modes = {}
    for name in ('reference', 'simple_policy'):
        selected = [row for row in samples if row['policy'] == name]
        modes[name] = {'runs': len(selected),
                       'violations': sum(row['run']['semantic_violations'] for row in selected),
                       'preference_cutovers': sum(row['run']['final_new'] for row in selected),
                       'mean_unaffected_availability': statistics.mean(row['run']['availability_unaffected'] for row in selected),
                       'median_lifecycle_wall_seconds': statistics.median(row['lifecycle_wall_seconds'] for row in selected),
                       'median_parent_cpu_seconds': statistics.median(row['lifecycle_parent_cpu_seconds'] for row in selected),
                       'median_logical_final_file_bytes': statistics.median(row['logical_final_file_bytes'] for row in selected)}
    return {'modes': modes, 'paired_scenarios': 40, 'actual_runs': len(samples),
            'logical_transactions': sum(len(row['transactions']) for row in samples),
            'same_full_certificate_and_runtime_outcomes': True,
            'scope': 'Same manifest, full frontier/blocker certificate, checker, inventory, migration, pins, dual writes, faults and 36-request workload. Native actual fixtures, not production workloads.',
            'cost_scope': 'Builder/checker, service/proxy startup, migration, workload, fault handling, diagnostic I/O and cleanup wall; parent CPU only. Persistent logical final files include logs. Imports, result packaging, child CPU/RSS, transient storage, cold cache, network deployment and power loss excluded. No speedup claim.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=('finite', 'native'), required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    output = fresh_directory(root, args.output)
    bind(root, output)
    result = finite(root, output) if args.phase == 'finite' else native(root, output)
    atomic_json(output / 'summary.json', result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
