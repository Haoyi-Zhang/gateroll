"""Benign recorded histories for the independent CSV/RPC recount, not native runs."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_runtime_outputs import inspect


class RuntimeRecountTests(unittest.TestCase):
    def recount(self, *, hinted, wrong_value=False, unavailable_first=False):
        def request(identifier, op='inc', duplicate=False, key='a0'):
            return {'target': 'gateway', 'key': key, 'op': op, 'role': 'writer',
                    'delta': 1, 'req_id': identifier, 'logical_duplicate': duplicate}

        if unavailable_first:
            requests = [request('first'), request('first', duplicate=True)]
            values, expected, available, violations = [None, 12], [12, 12], [0, 1], [0, 0]
            current = 12
        else:
            requests = [request('first'), request('second'), request('first', duplicate=hinted)]
            values = [12, 13, 13 if wrong_value else 12]
            expected, available, violations = [12, 13, 12], [1, 1, 1], [0, 0, int(wrong_value)]
            current = 13
        # The existing matrix recount has an exact 36-record contract. Padding
        # is explicit benign reads, not a claim of a new native workload.
        while len(requests) < 35:
            requests.append(request('read-' + str(len(requests)), op='read'))
            values.append(current)
            expected.append(current)
            available.append(1)
            violations.append(0)
        requests.append(request('unaffected-read', op='read', key='u0'))
        values.append(13)
        expected.append(13)
        available.append(1)
        violations.append(0)
        transactions, observations = [], []
        for index, rpc in enumerate(requests):
            transactions.append({'campaign_id': 'owned-00', 'strategy': 'certified',
                'topology': 'chain3', 'tx_index': index, 'authorized': 1,
                'available': available[index], 'semantic_violation': violations[index],
                'expected_value': expected[index], 'target': 'gateway', 'attempts': 1,
                'key_class': 'affected' if index < 35 else 'unaffected'})
            observations.append({'attempt': 1, 'request': rpc,
                'response': {'available': bool(available[index]), 'ok': True,
                             'shape_ok': True, 'protocol_ok': True, 'value': values[index]}})
        summary = {'strategies': {'certified': {'semantic_violations': sum(violations)}}}
        run = {'campaign_id': 'owned-00', 'strategy': 'certified', 'proxy_calls': 36,
               'semantic_violations': sum(violations), 'availability_overall': sum(available) / 36,
               'availability_affected': sum(available[:35]) / 35, 'availability_unaffected': 1.0}
        with tempfile.TemporaryDirectory(prefix='owned-recount-') as temporary:
            root = Path(temporary)
            for name, rows in (('campaign_runs.csv', [run]), ('campaign_transactions.csv', transactions)):
                with (root / name).open('w', encoding='utf-8', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            (root / 'campaign_summary.json').write_text(json.dumps(summary), encoding='utf-8')
            (root / 'historical.json').write_text(json.dumps(summary), encoding='utf-8')
            (root / 'jobs').mkdir()
            (root / 'jobs/00-certified-attempt-1.json').write_text(
                json.dumps({'harness_cleanup': {'residual_after': 0}}), encoding='utf-8')
            (root / 'runs/00-certified-attempt-1').mkdir(parents=True)
            (root / 'runs/00-certified-attempt-1/rpc_observations.jsonl').write_text(
                '\n'.join(json.dumps(row) for row in observations) + '\n', encoding='utf-8')
            return inspect(root, root / 'historical.json')

    def test_saved_late_replay_recount(self):
        result = self.recount(hinted=True)
        self.assertTrue(result['pass'], result['errors'])

    def test_wrong_current_replay_recount_retains_violation(self):
        result = self.recount(hinted=True, wrong_value=True)
        self.assertTrue(result['pass'], result['errors'])
        self.assertEqual(result['violation_totals']['certified'], 1)

    def test_unhinted_identifier_replay_recount(self):
        result = self.recount(hinted=False)
        self.assertTrue(result['pass'], result['errors'])

    def test_unavailable_attempt_recount_does_not_save_completion(self):
        result = self.recount(hinted=True, unavailable_first=True)
        self.assertTrue(result['pass'], result['errors'])


if __name__ == '__main__':
    unittest.main()
