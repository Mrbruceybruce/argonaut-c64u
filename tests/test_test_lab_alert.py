import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from c64u_browser import test_lab_alert
from c64u_browser.ai_gateway import GatewayError
from c64u_browser.test_lab_auto_analysis import CACHE_NAME, CONFIG_NAME, save_local_config


KEY = 'a' * 16


def fleet(status, check_id='hardware.identity', *, code=None):
    code = {'pass': 0, 'fail': 1, 'skip': 2, 'error': 3}[status] if code is None else code
    report = {'schema': 1, 'suite': 'hardware', 'status': status,
              'checks': [{'id': check_id, 'status': status}]}
    return code, {'schema': 1, 'suite': 'hardware_profiles', 'status': status,
                  'profiles': [{'key': KEY, 'exit_code': code, 'result': report}]}


class TestLabAlertTests(unittest.TestCase):
    def invoke(self, code, result, state, notify):
        output = io.StringIO()
        def run(_argv, stdin, stdout, stderr):
            if result is not None:
                stdout.write(json.dumps(result) + '\n')
            return code
        with patch('c64u_browser.test_lab_alert.run_fleet', side_effect=run):
            returned = test_lab_alert.main([], stdout=output, stderr=io.StringIO(),
                                            state_path=state, notify=notify)
        self.assertEqual(returned, code)
        if result is not None:
            self.assertEqual(json.loads(output.getvalue()), result)
        return output.getvalue()

    def test_alerts_only_on_new_changed_and_resolved_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'test-lab/alert-state.json'
            notices = []
            notify = lambda title, body: notices.append((title, body)) or True
            self.invoke(*fleet('pass'), state, notify)
            self.assertEqual(notices, [])
            self.invoke(*fleet('fail'), state, notify)
            self.assertEqual(len(notices), 1)
            self.assertIn('needs attention', notices[-1][0])
            self.invoke(*fleet('fail'), state, notify)
            self.assertEqual(len(notices), 1)
            changed = fleet('fail', 'hardware.drives')
            changed[1]['profiles'][0]['result']['checks'].append(
                {'id': 'hardware.identity', 'status': 'pass'})
            self.invoke(*changed, state, notify)
            self.assertEqual(len(notices), 2)
            self.assertIn('changed', notices[-1][0])
            self.invoke(*fleet('pass', 'hardware.drives'), state, notify)
            self.assertEqual(len(notices), 3)
            self.assertIn('recovered', notices[-1][0])
            self.assertEqual(json.loads(state.read_text())['failures'], [])
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_skipped_check_does_not_claim_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'alert-state.json'
            notices = []
            notify = lambda title, body: notices.append(title) or True
            self.invoke(*fleet('fail'), state, notify)
            self.invoke(*fleet('skip'), state, notify)
            self.assertEqual(len(notices), 1)
            self.assertEqual(json.loads(state.read_text())['failures'],
                             [KEY + ':hardware.identity'])
            self.invoke(*fleet('pass'), state, notify)
            self.assertEqual(len(notices), 2)

    def test_setup_error_and_failed_notification_preserve_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'alert-state.json'
            self.invoke(3, None, state, lambda _title, _body: False)
            self.assertFalse(state.exists())
            notices = []
            notify = lambda title, body: notices.append(title) or True
            self.invoke(3, None, state, notify)
            self.invoke(3, None, state, notify)
            self.assertEqual(len(notices), 1)
            self.assertEqual(json.loads(state.read_text())['failures'], ['setup'])
            self.invoke(*fleet('pass'), state, notify)
            self.assertEqual(len(notices), 2)

    def test_failure_state_excludes_invalid_profile_and_check_ids(self):
        code, result = fleet('fail')
        result['profiles'][0]['key'] = 'sensitive-host-name'
        self.assertEqual(test_lab_alert.failure_set(json.dumps(result), code), ())
        result['profiles'][0]['key'] = KEY
        result['profiles'][0]['result']['checks'][0]['id'] = 'password=private'
        self.assertEqual(test_lab_alert.failure_set(json.dumps(result), code), ())

    def test_opted_in_local_diagnosis_is_cached_and_attached_once(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'test-lab/alert-state.json'
            save_local_config(state.parent / CONFIG_NAME, 'local-test')
            code, result = fleet('fail')
            result['profiles'][0]['result']['history_saved'] = True
            result['profiles'][0]['result']['checks'][0]['error_kind'] = 'network'
            notices = []
            notify = lambda title, body: notices.append((title, body)) or True
            adapter = Mock(return_value='Check the cable.\nThen retry.')
            with patch('c64u_browser.test_lab_auto_analysis.AIGateway',
                       return_value=adapter) as gateway:
                self.invoke(code, result, state, notify)
                self.invoke(code, result, state, notify)
            self.assertEqual(len(notices), 1)
            self.assertIn('Local AI: Check the cable. Then retry.', notices[0][1])
            gateway.assert_called_once()
            adapter.assert_called_once()
            cache = state.parent / CACHE_NAME
            self.assertTrue(json.loads(cache.read_text())['notified'])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(state.read_text())['failures'],
                             [KEY + ':hardware.identity'])

    def test_model_outage_keeps_generic_alert_then_retries_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'test-lab/alert-state.json'
            save_local_config(state.parent / CONFIG_NAME, 'local-test')
            code, result = fleet('fail')
            result['profiles'][0]['result']['history_saved'] = True
            notices = []
            notify = lambda title, body: notices.append((title, body)) or True
            adapter = Mock(side_effect=[GatewayError('network', 'Unavailable'),
                                        'Check the connection.'])
            with patch('c64u_browser.test_lab_auto_analysis.AIGateway',
                       return_value=adapter):
                self.invoke(code, result, state, notify)
                self.assertFalse((state.parent / CACHE_NAME).exists())
                self.invoke(code, result, state, notify)
            self.assertEqual(len(notices), 2)
            self.assertIn('needs attention', notices[0][0])
            self.assertIn('local diagnosis ready', notices[1][0])
            self.assertIn('Local AI: Check the connection.', notices[1][1])
            self.assertEqual(json.loads(state.read_text())['failures'],
                             [KEY + ':hardware.identity'])

    def test_passing_fleet_never_contacts_opted_in_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'test-lab/alert-state.json'
            save_local_config(state.parent / CONFIG_NAME, 'local-test')
            with patch('c64u_browser.test_lab_auto_analysis.AIGateway') as gateway:
                self.invoke(*fleet('pass'), state, lambda *_: True)
            gateway.assert_not_called()

    def test_unsaved_failure_still_alerts_without_contacting_model(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'test-lab/alert-state.json'
            save_local_config(state.parent / CONFIG_NAME, 'local-test')
            notices = []
            with patch('c64u_browser.test_lab_auto_analysis.AIGateway') as gateway:
                self.invoke(*fleet('fail'), state,
                            lambda title, body: notices.append((title, body)) or True)
            self.assertEqual(len(notices), 1)
            self.assertNotIn('Local AI:', notices[0][1])
            gateway.assert_not_called()


if __name__ == '__main__':
    unittest.main()
