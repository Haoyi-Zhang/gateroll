"""A drawing projection cannot silently depart from received observations."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('completion_plot', ROOT / 'scripts/plot_completion_history.py')
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


class CompletionFigureInputTests(unittest.TestCase):
    def setUp(self):
        self.history = json.loads((ROOT / 'results/completion-oracle/history.json').read_text(encoding='utf-8'))

    def write_history(self, directory, value):
        path = Path(directory) / 'history.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_retained_history_has_all_ten_received_replies(self):
        rows = plot.read_history(ROOT / 'results/completion-oracle/history.json')
        self.assertEqual([row['request'] for row in rows], list(range(1, 11)))
        self.assertEqual([rows[index - 1]['reply'] for index in (3, 5, 7, 9)], [12] * 4)
        self.assertEqual(rows[-1]['current_expected'], 14)

    def test_csv_projection_must_match_every_retained_column(self):
        with tempfile.TemporaryDirectory() as directory:
            history = self.write_history(directory, self.history)
            rows = plot.read_history(history)
            csv_path = Path(directory) / 'history.csv'
            def write(values):
                with csv_path.open('w', encoding='utf-8', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(values)
            write(rows)
            self.assertEqual(plot.read_history(history, csv_path), rows)
            altered = copy.deepcopy(rows)
            altered[2]['reply'] = altered[2]['current_expected']
            write(altered)
            with self.assertRaises(ValueError):
                plot.read_history(history, csv_path)

    def test_unchecked_or_incomplete_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (dict(self.history, checks_passed=False), dict(self.history, trace=self.history['trace'][:-1])):
                with self.assertRaises(ValueError):
                    plot.read_history(self.write_history(directory, value))

    def test_booleans_nonfinite_values_and_unavailable_replies_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for field, value in (('observed_value', True), ('observed_value', float('nan')), ('available', True), ('available', 0)):
                altered = copy.deepcopy(self.history)
                altered['trace'][0]['transaction'][field] = value
                with self.assertRaises(ValueError):
                    plot.read_history(self.write_history(directory, altered))


if __name__ == '__main__':
    unittest.main()
