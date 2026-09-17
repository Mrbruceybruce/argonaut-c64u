import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser import c64_ai_bridge_alert as alert


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


class C64AIBridgeAlertTests(unittest.TestCase):
    def test_changed_failure_and_recovery_alert_once(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            state = base / 'state.json'
            notices = []
            notify = lambda title, body: notices.append((title, body)) or True
            statuses = iter(('pass', 'fail', 'fail', 'pass'))
            for _ in range(4):
                alert.check(base / 'bridge.json', base / 'config.json', state,
                            notify, lambda _path: report(next(statuses)))
            self.assertEqual(len(notices), 2)
            self.assertIn('failed', notices[0][1])
            self.assertIn('recovered', notices[1][0])
            self.assertEqual(alert.read_state(state), 'pass')
            if os.name != 'nt':
                self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_failed_notification_retries_without_advancing_state(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            state = base / 'state.json'
            result, saved = alert.check(
                base / 'bridge.json', base / 'config.json', state,
                lambda *_args: False, lambda _path: report('fail'))
            self.assertEqual(result['report']['status'], 'fail')
            self.assertFalse(saved)
            self.assertFalse(state.exists())

    def test_cli_output_and_exit_are_deterministic(self):
        result = {
            'report': report('fail'), 'comparison': None, 'saved': True}
        output = io.StringIO()
        with patch('c64u_browser.c64_ai_bridge_alert.check',
                   return_value=(result, True)):
            code = alert.main(
                ['--config', '/private/bridge',
                 '--preferences', '/private/preferences',
                 '--state', '/private/state'],
                stdout=output, stderr=io.StringIO())
        self.assertEqual(code, 1)
        value = json.loads(output.getvalue())
        self.assertEqual(value['report']['status'], 'fail')
        self.assertNotIn('/private', output.getvalue())


if __name__ == '__main__':
    unittest.main()
