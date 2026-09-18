import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.profiles import Preferences, Profile
from c64u_browser.ai_gateway import GatewayError
from c64u_browser.test_lab_cli import main
from c64u_browser.test_lab_history import TestLabHistory


def fixture_report(status):
    return {'schema': 1, 'suite': 'hardware', 'status': status,
            'checks': [{'id': 'hardware.identity', 'title': 'Identity',
                        'status': status, 'error_kind': None,
                        'duration_ms': 0.0, 'operations': []}]}


class HeadlessCliTests(unittest.TestCase):
    def setUp(self):
        self.development = patch.dict(
            os.environ, {'ARGONAUT_DEVELOPMENT': '1'})
        self.development.start()

    def tearDown(self):
        self.development.stop()

    def test_device_id_selects_only_matching_development_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            first = Profile.new('First', 'first.invalid', device_id='ALPHA')
            second = Profile.new('Second', 'second.invalid', device_id='BRAVO')
            preferences.profiles = [first, second]
            preferences.selected_id = first.id
            preferences.save()
            output = io.StringIO()
            seen = []

            def hardware(client, profile):
                seen.append((client.host, profile.id))
                return fixture_report('pass')

            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks', side_effect=hardware):
                code = main(['--suite', 'hardware', '--device-id', 'bravo'], stdout=output)
            self.assertEqual(code, 0)
            self.assertEqual(seen, [('second.invalid', second.id)])
            self.assertIsNone(TestLabHistory(path, first.id).latest('hardware'))
            self.assertEqual(TestLabHistory(path, second.id).latest('hardware')['status'], 'pass')
            self.assertNotIn('BRAVO', output.getvalue())
            self.assertNotIn('second.invalid', output.getvalue())

    def test_unknown_or_ambiguous_device_id_stops_without_device_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            first = Profile.new('First', 'first.invalid', device_id='ALPHA')
            second = Profile.new('Second', 'second.invalid', device_id='alpha')
            preferences.profiles = [first, second]
            preferences.selected_id = first.id
            preferences.save()
            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks') as hardware:
                for device_id in ('unknown', 'ALPHA'):
                    with self.subTest(device_id=device_id):
                        output, error = io.StringIO(), io.StringIO()
                        code = main(['--suite', 'hardware', '--device-id', device_id],
                                    stdout=output, stderr=error)
                        self.assertEqual(code, 3)
                        self.assertEqual(output.getvalue(), '')
                        self.assertNotIn(device_id, error.getvalue())
            hardware.assert_not_called()

    def test_ai_explains_failure_without_changing_verdict_or_saved_history(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            profile = Profile.new('Fixture', 'fixture.invalid', device_id='bound')
            preferences.profiles = [profile]
            preferences.selected_id = profile.id
            preferences.save()
            output = io.StringIO()
            evidence = []

            def adapter(failures):
                evidence.append(failures)
                return 'Check the cable.'

            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks',
                    return_value=fixture_report('fail')), patch(
                    'c64u_browser.test_lab_cli.AIGateway', return_value=adapter):
                code = main(['--suite', 'hardware', '--explain-failures',
                             '--ai-provider', 'ollama', '--ai-model', 'local-test'],
                            stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['status'], 'fail')
            self.assertEqual(result['analysis']['status'], 'analyzed')
            self.assertEqual(result['analysis']['diagnosis'], 'Check the cable.')
            self.assertEqual(evidence[0]['failures'][0]['id'], 'hardware.identity')
            self.assertNotIn('analysis', TestLabHistory(path, profile.id).latest('hardware'))

    def test_ai_error_does_not_change_failure_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            profile = Profile.new('Fixture', 'fixture.invalid', device_id='bound')
            preferences.profiles = [profile]
            preferences.selected_id = profile.id
            preferences.save()
            output = io.StringIO()

            def adapter(_):
                raise GatewayError('network', 'AI service could not be reached.')

            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks',
                    return_value=fixture_report('fail')), patch(
                    'c64u_browser.test_lab_cli.AIGateway', return_value=adapter):
                code = main(['--suite', 'hardware', '--explain-failures',
                             '--ai-provider', 'ollama', '--ai-model', 'local-test'],
                            stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['analysis'], {'schema': 1, 'status': 'error',
                                                   'error_kind': 'network', 'diagnosis': None})

    def test_invalid_ai_configuration_still_runs_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            profile = Profile.new('Fixture', 'fixture.invalid', device_id='bound')
            preferences.profiles = [profile]
            preferences.selected_id = profile.id
            preferences.save()
            output = io.StringIO()
            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks',
                    return_value=fixture_report('fail')) as checks, patch(
                    'c64u_browser.test_lab_cli.AIGateway') as gateway:
                code = main(['--suite', 'hardware', '--explain-failures',
                             '--ai-provider', 'ollama', '--ai-model', 'remote:cloud'],
                            stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            checks.assert_called_once()
            gateway.assert_not_called()
            self.assertEqual(result['analysis']['error_kind'], 'configuration')
            self.assertEqual(TestLabHistory(path, profile.id).latest('hardware')['status'], 'fail')

    def test_passing_run_does_not_call_ai(self):
        output = io.StringIO()
        with patch('c64u_browser.test_lab_cli.AIGateway') as gateway:
            code = main(['--suite', 'offline', '--explain-failures',
                         '--ai-provider', 'ollama', '--ai-model', 'local-test'],
                        stdout=output)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['analysis']['status'], 'no_failures')
        gateway.return_value.assert_not_called()

    def test_offline_mode_preserves_json_and_exit_zero(self):
        output = io.StringIO()
        code = main(['--suite', 'offline'], stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['suite'], 'offline')
        self.assertEqual(len(report['checks']), 15)

    def test_diagnosis_probe_is_an_expected_offline_failure_with_separate_ai(self):
        output = io.StringIO()
        with patch('c64u_browser.test_lab_cli.AIGateway',
                   return_value=lambda _: 'Inspect local FTP login.') as gateway, patch(
                   'socket.create_connection') as connect:
            code = main(['--suite', 'diagnosis_probe', '--explain-failures',
                         '--ai-provider', 'ollama', '--ai-model', 'local-test'],
                        stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result['suite'], 'diagnosis_probe')
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['analysis']['status'], 'analyzed')
        self.assertEqual(result['analysis']['diagnosis'],
                         'Inspect local FTP login.')
        self.assertNotIn('history_saved', result)
        connect.assert_not_called()
        gateway.assert_called_once()

    def test_hardware_uses_development_profile_and_stdin_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            profile = Profile.new('Fixture', 'fixture.invalid', device_id='bound')
            preferences.profiles = [profile]
            preferences.selected_id = profile.id
            preferences.save()
            output = io.StringIO()
            seen = []

            def hardware(client, selected):
                seen.append((client.password, selected.id, client.timeout))
                return fixture_report('pass')

            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks', side_effect=hardware):
                code = main(['--suite', 'hardware', '--password-stdin', '--timeout', '3'],
                            stdin=io.StringIO('private-secret\n'), stdout=output)
            report = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(seen, [('private-secret', profile.id, 3)])
            self.assertTrue(report['history_saved'])
            self.assertIsNone(report['comparison'])
            self.assertNotIn('private-secret', output.getvalue())
            self.assertEqual(TestLabHistory(path, profile.id).latest('hardware')['status'], 'pass')

    def test_no_development_profile_skips_without_using_stable_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            stable = Preferences(base / 'argonaut' / 'config.json')
            profile = Profile.new('Stable', 'fixture.invalid', device_id='bound')
            stable.profiles = [profile]
            stable.selected_id = profile.id
            stable.save()
            output = io.StringIO()
            with patch('c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'urllib.request.build_opener') as opener:
                code = main(['--suite', 'hardware'], stdout=output)
            report = json.loads(output.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(report['status'], 'skip')
            opener.assert_not_called()
            dev_path = base / 'argonaut-development' / 'config.json'
            self.assertIsNone(TestLabHistory(dev_path).latest('hardware'))

    def test_stable_developer_mode_uses_only_stable_profile_and_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
                os.environ, {'ARGONAUT_DEVELOPMENT': '0'}):
            base = Path(directory)
            path = base / 'argonaut' / 'config.json'
            preferences = Preferences(path)
            profile = Profile.new('Stable', 'stable.invalid', device_id='STABLE')
            preferences.profiles = [profile]
            preferences.selected_id = profile.id
            preferences.save()
            output = io.StringIO()
            with patch('c64u_browser.test_lab_cli.config_base',
                       return_value=base), patch(
                       'c64u_browser.test_lab_cli.run_hardware_checks',
                       return_value=fixture_report('pass')):
                code = main(['--suite', 'hardware'], stdout=output)
            self.assertEqual(code, 0)
            self.assertEqual(
                TestLabHistory(path, profile.id).latest('hardware')['status'],
                'pass')
            self.assertFalse((base / 'argonaut-development').exists())

    def test_invalid_password_is_not_echoed_or_sent(self):
        output, error = io.StringIO(), io.StringIO()
        with patch('c64u_browser.test_lab_cli.config_base') as base:
            code = main(['--suite', 'hardware', '--password-stdin'],
                stdin=io.StringIO('s' * 1100 + '\n'), stdout=output, stderr=error)
        self.assertEqual(code, 3)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn('s' * 100, error.getvalue())
        base.assert_not_called()


if __name__ == '__main__':
    unittest.main()
