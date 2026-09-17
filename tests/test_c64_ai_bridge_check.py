import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.c64_ai_bridge_check import main


def report(status):
    return {
        'schema': 1, 'suite': 'bridge', 'status': status,
        'checks': [{
            'id': 'bridge.end_to_end',
            'title': 'End-to-end local C64 AI bridge',
            'status': status,
            'error_kind': None if status == 'pass' else 'network',
            'duration_ms': 1.0,
            'operations': [],
        }],
    }


class BridgeCheckCLITests(unittest.TestCase):
    def test_pass_is_saved_and_emitted_as_structured_json(self):
        with tempfile.TemporaryDirectory() as folder:
            preferences = Path(folder) / 'config.json'
            output = io.StringIO()
            with patch('c64u_browser.c64_ai_bridge_check.run_bridge_checks',
                       return_value=report('pass')):
                code = main(['--config', str(Path(folder) / 'bridge.json'),
                             '--preferences', str(preferences)], stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result['report']['status'], 'pass')
            self.assertTrue(result['saved'])
            self.assertNotIn('token', output.getvalue().casefold())

    def test_failure_exit_is_determined_by_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = io.StringIO()
            with patch('c64u_browser.c64_ai_bridge_check.run_bridge_checks',
                       return_value=report('fail')):
                code = main(['--config', str(Path(folder) / 'bridge.json'),
                             '--preferences', str(Path(folder) / 'config.json')],
                            stdout=output)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())['report']['status'],
                             'fail')

    def test_invalid_result_returns_setup_error_without_private_details(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch('c64u_browser.c64_ai_bridge_check.run_with_history',
                   side_effect=ValueError('/private/token/location')):
            code = main([], stdout=output, stderr=errors)
        self.assertEqual(code, 3)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(
            errors.getvalue(),
            'Bridge readiness result could not be recorded.\n')


if __name__ == '__main__':
    unittest.main()
