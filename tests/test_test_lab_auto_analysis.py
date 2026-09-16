import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from c64u_browser.ai_gateway import GatewayError
from c64u_browser.test_lab_auto_analysis import (
    Diagnosis, alert_excerpt, diagnose_saved_fleet, load_local_config,
    save_local_config, saved_diagnosis,
)
from c64u_browser.test_lab_history import profile_scope_key


class LocalAISettingTests(unittest.TestCase):
    def test_missing_and_disabled_settings_never_enable_model(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test-lab/local-ai.json'
            self.assertIsNone(load_local_config(path))
            save_local_config(path, 'downloaded-model')
            self.assertEqual(load_local_config(path).provider, 'ollama')
            self.assertEqual(load_local_config(path).model, 'downloaded-model')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            save_local_config(path)
            self.assertIsNone(load_local_config(path))

    def test_cloud_model_and_cloud_provider_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'local-ai.json'
            with self.assertRaises(GatewayError):
                save_local_config(path, 'remote:cloud')
            self.assertFalse(path.exists())
            path.write_text(json.dumps({'schema': 1, 'enabled': True,
                                        'provider': 'openai',
                                        'model': 'cloud-model'}), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_local_config(path)

    def test_saved_view_matches_profile_and_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config, cache = base / 'local-ai.json', base / 'latest-local-ai.json'
            save_local_config(config, 'downloaded-model')
            profile_id = 'fixture-profile'
            key = profile_scope_key(profile_id)[:16]
            report = {'schema': 1, 'suite': 'hardware', 'status': 'fail',
                      'history_saved': True, 'checks': [
                          {'id': 'hardware.identity', 'status': 'fail',
                           'error_kind': 'network', 'operations': []}]}
            fleet = {'schema': 1, 'profiles': [
                {'key': key, 'exit_code': 1, 'result': report}]}
            adapter = Mock(return_value='Inspect the network link.')
            diagnose_saved_fleet(json.dumps(fleet), config, cache,
                                 gateway_factory=lambda _: adapter)
            self.assertEqual(saved_diagnosis(cache, profile_id, report),
                             'Inspect the network link.')
            self.assertIsNone(saved_diagnosis(cache, 'different-profile', report))
            changed = json.loads(json.dumps(report))
            changed['checks'][0]['error_kind'] = 'authentication'
            self.assertIsNone(saved_diagnosis(cache, profile_id, changed))
            save_local_config(config, 'different-downloaded-model')
            diagnose_saved_fleet(json.dumps(fleet), config, cache,
                                 gateway_factory=lambda _: adapter)
            self.assertEqual(adapter.call_count, 2)

    def test_untrusted_model_markup_is_plain_notification_text(self):
        diagnosis = Diagnosis('a' * 64, (
            {'key': 'b' * 16, 'diagnosis': '<a href="bad">Check cable</a>'},), False)
        self.assertEqual(alert_excerpt(diagnosis),
                         '&lt;a href="bad"&gt;Check cable&lt;/a&gt;')


if __name__ == '__main__':
    unittest.main()
