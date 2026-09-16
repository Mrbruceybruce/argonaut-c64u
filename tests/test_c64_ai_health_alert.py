import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.c64_ai_bridge_control import BridgeStatus
from c64u_browser import c64_ai_health_alert as health


class C64AIHealthAlertTests(unittest.TestCase):
    def test_changed_failure_and_recovery_alert_once(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'health.json'
            notices = []
            notify = lambda title, body: notices.append((title, body)) or True
            statuses = [
                BridgeStatus('ready', 'Ready'),
                BridgeStatus('model_unavailable', 'Unavailable'),
                BridgeStatus('model_unavailable', 'Unavailable'),
                BridgeStatus('ready', 'Ready'),
            ]
            with patch('c64u_browser.c64_ai_health_alert.bridge_status',
                       side_effect=statuses):
                for _ in statuses:
                    health.check('/private/config', state, notify)
            self.assertEqual(len(notices), 2)
            self.assertIn('Ollama', notices[0][1])
            self.assertIn('recovered', notices[1][0])
            self.assertEqual(health.read_state(state), 'ready')
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_failed_notification_is_retried_without_advancing_state(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'health.json'
            status = BridgeStatus('stopped', 'Stopped')
            with patch('c64u_browser.c64_ai_health_alert.bridge_status',
                       return_value=status):
                result, saved = health.check('/private/config', state,
                                             lambda *_args: False)
            self.assertEqual(result.state, 'stopped')
            self.assertFalse(saved)
            self.assertFalse(state.exists())

    def test_cli_output_is_sanitized_and_exit_is_deterministic(self):
        status = BridgeStatus(
            'model_missing', 'secret-looking detail', 'gemma3:4b',
            '192.0.2.1', 6464, ('192.0.2.10',), True, 'model_missing')
        output = io.StringIO()
        with patch('c64u_browser.c64_ai_health_alert.check',
                   return_value=(status, True)):
            code = health.main(
                ['--config', '/private/config', '--state', '/private/state'],
                stdout=output, stderr=io.StringIO())
        value = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(value, {
            'schema': 1, 'state': 'model_missing',
            'model_status': 'model_missing', 'paired_addresses': 1})
        self.assertNotIn('192.0.2.1', output.getvalue())
        self.assertNotIn('secret-looking', output.getvalue())


if __name__ == '__main__':
    unittest.main()
