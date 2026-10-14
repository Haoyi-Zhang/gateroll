"""Actual owned late-replay history across migration, cutover and proxy restart."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

from gateroll.campaigns import RuntimeRun
from gateroll.model import Manifest, Service
from gateroll.planner import plan
from gateroll.portable_runtime import fresh_directory
from gateroll.rpcutil import atomic_json


def execute(root, output):
    output = fresh_directory(root, output)
    manifest = Manifest('owned-late-replay', 'owned', 'saved-completion', 'one-role',
                        (Service('gateway'),), ())
    runtime = RuntimeRun(root, output / 'run', manifest, plan(manifest), 'certified', 'none')
    trace = []

    def transaction(label, identifier, op='inc', shape='old'):
        request = {'cmd': 'request', 'target': 'gateway', 'path': ['gateway'],
                   'req_id': identifier, 'key': 'a0', 'op': op, 'role': 'writer',
                   'delta': 1, 'client_shape': shape}
        # This substitutes the owned request sequence, NOT replies/transport.
        with patch.object(runtime, '_logical_request', return_value=request):
            row = runtime.transact(len(trace), label)
        trace.append({'label': label, 'request': request, 'transaction': row,
                      'current_oracle_state': runtime.expected['gateway']['a0']})
        assert row['available'] and not row['semantic_violation'], row
        return row

    try:
        runtime.start()
        transaction('first-old-write', 'first')
        transaction('second-old-write', 'second')
        assert transaction('old-late-replay', 'first')['observed_value'] == 12
        assert transaction('old-current-read', 'read-old', 'read')['observed_value'] == 13
        runtime._step_certified([0], [1])
        assert transaction('bridge-late-replay', 'first')['observed_value'] == 12
        transaction('bridge-fresh-write', 'third')
        runtime._step_certified([1], [2])
        assert transaction('new-late-replay', 'first', shape='new')['observed_value'] == 12
        assert transaction('new-current-read', 'read-new', 'read', 'new')['observed_value'] == 14
        process = runtime.proxy_process
        process.kill()
        process.join(timeout=2)
        if process.is_alive():
            raise RuntimeError('owned proxy did not stop')
        process.close()
        runtime._spawn_proxy()
        assert transaction('restarted-proxy-late-replay', 'first', shape='new')['observed_value'] == 12
        assert transaction('restarted-current-read', 'read-restarted', 'read', 'new')['observed_value'] == 14
        replicas = {version: runtime._dump('gateway', version) for version in ('old', 'new')}
        assert all(dump['values']['a0'] == 14 for dump in replicas.values())
        assert all(set(dump['receipts']) == {'first', 'second', 'third'} for dump in replicas.values())
    finally:
        runtime.close()
    names = ['gateroll/campaigns.py', 'gateroll/model.py', 'gateroll/planner.py',
             'gateroll/checker.py', 'gateroll/proxy_process.py', 'gateroll/service_process.py',
             'gateroll/pending_writes.py', 'gateroll/rpcutil.py', 'gateroll/portable_runtime.py',
             'scripts/run_completion_history.py']
    result = {'scope': 'Actual one-role localhost old/new services and proxy; sequential completed replies; migration and new preference; actual proxy restart, not controller recovery.',
              'manifest': manifest.to_dict(), 'trace': trace, 'final_replicas': replicas,
              'rpc_observations': [json.loads(line) for line in
                                   (output / 'run/rpc_observations.jsonl').read_text(encoding='utf-8').splitlines()],
              'environment': {'python': sys.version, 'platform': platform.platform(),
                              'bytecode_disabled': bool(sys.dont_write_bytecode)},
              'source_sha256': {name: sha256((root / name).read_bytes()).hexdigest() for name in names},
              'checks_passed': True, 'observed_completed_requests': len(trace)}
    atomic_json(output / 'history.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = execute(args.artifact_root.resolve(), args.output)
    print(json.dumps({'checks_passed': result['checks_passed'],
                      'observed_completed_requests': result['observed_completed_requests']}))


if __name__ == '__main__':
    main()
