import json
import os
import tempfile
import unittest
from pathlib import Path

from c64u_browser.test_lab_snapshot import save_latest


class TestLabSnapshotTests(unittest.TestCase):
    def test_saves_private_labeled_status(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test-lab/latest-status.json'
            saved = save_latest(
                path, 'Local AI simulation',
                'PASS — expected simulated failure was detected.',
                'UNAVAILABLE — enter a model name.')
            self.assertEqual(json.loads(path.read_text()), saved)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(saved['action'], 'Local AI simulation')
            self.assertIn('expected simulated failure',
                          saved['deterministic_result'])
            self.assertIn('UNAVAILABLE', saved['ai_analysis'])

    def test_rejects_empty_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                save_latest(Path(folder) / 'status.json', '', 'PASS', 'None')


if __name__ == '__main__':
    unittest.main()
