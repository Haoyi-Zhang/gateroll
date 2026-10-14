"""Owned receipt histories; no service/target is contacted by these red controls."""
from pathlib import Path
import unittest
from unittest.mock import patch

from gateroll.campaigns import RuntimeRun
from gateroll.model import Manifest, Service


class CompletionOracleTests(unittest.TestCase):
    def setUp(self):
        manifest = Manifest('owned-replay', 'owned', 'owned', 'one', (Service('gateway'),), ())
        self.runtime = RuntimeRun(Path('.'), Path('.'), manifest, {}, 'certified', 'none')

    def transaction(self, identifier, value, *, duplicate=False, op='inc', available=True):
        request = {'target': 'gateway', 'key': 'a0', 'op': op, 'role': 'writer',
                   'delta': 1, 'client_shape': 'old', 'req_id': identifier,
                   'logical_duplicate': duplicate}
        response = {'available': available, 'ok': True, 'shape_ok': True,
                    'protocol_ok': True, 'value': value}
        with patch.object(self.runtime, '_logical_request', return_value=request), \
             patch.object(self.runtime, '_send', return_value=(response, 0.0, 1)):
            return self.runtime.transact(0, 'owned')

    def establish_two_completions(self):
        self.assertEqual(self.transaction('first', 12)['semantic_violation'], 0)
        self.assertEqual(self.transaction('second', 13)['semantic_violation'], 0)

    def test_late_replay_returns_saved_completion_not_current_value(self):
        self.establish_two_completions()
        row = self.transaction('first', 12, duplicate=True)
        self.assertEqual(row['expected_value'], 12)
        self.assertEqual(row['semantic_violation'], 0)
        self.assertEqual(self.runtime.expected['gateway']['a0'], 13)

    def test_late_replay_with_current_value_is_rejected(self):
        self.establish_two_completions()
        self.assertEqual(self.transaction('first', 13, duplicate=True)['semantic_violation'], 1)

    def test_identity_recognizes_replay_without_generator_hint(self):
        self.establish_two_completions()
        self.assertEqual(self.transaction('first', 12)['semantic_violation'], 0)
        self.assertEqual(self.transaction('observe', 13, op='read')['semantic_violation'], 0)

    def test_unavailable_attempt_does_not_invent_a_saved_completion(self):
        self.assertEqual(self.transaction('first', None, available=False)['semantic_violation'], 0)
        row = self.transaction('first', 12, duplicate=True)
        self.assertEqual(row['expected_value'], 12)
        self.assertEqual(row['semantic_violation'], 0)
        self.assertEqual(self.runtime.expected['gateway']['a0'], 12)


if __name__ == '__main__':
    unittest.main()
