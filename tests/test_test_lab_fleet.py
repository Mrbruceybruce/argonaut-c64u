import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.profiles import Preferences, Profile
from c64u_browser.test_lab_fleet import main
from c64u_browser.test_lab_history import TestLabHistory, profile_scope_key


def report(status):
    return {'schema': 1, 'suite': 'hardware', 'status': status,
            'checks': [{'id': 'hardware.identity', 'title': 'Identity',
                        'status': status, 'error_kind': None,
                        'duration_ms': 0, 'operations': []}]}


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.development = patch.dict(
            os.environ, {'ARGONAUT_DEVELOPMENT': '1'})
        self.development.start()

    def tearDown(self):
        self.development.stop()

    def test_each_bound_development_profile_gets_its_own_report(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            first = Profile.new('First', 'first.invalid', device_id='ALPHA')
            second = Profile.new('Second', 'second.invalid', device_id='BRAVO')
            unbound = Profile.new('Unbound', 'unbound.invalid')
            preferences.profiles = [first, second, unbound]
            preferences.selected_id = first.id
            preferences.save()
            output = io.StringIO()
            seen = []

            def hardware(client, profile):
                seen.append(profile.id)
                return report('fail' if profile.id == second.id else 'pass')

            with patch('c64u_browser.test_lab_fleet.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_cli.run_hardware_checks', side_effect=hardware):
                code = main([], stdout=output)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result['status'], 'fail')
            self.assertEqual(set(seen), {first.id, second.id})
            self.assertEqual(len(result['profiles']), 2)
            self.assertEqual({item['key'] for item in result['profiles']},
                             {profile_scope_key(first.id)[:16], profile_scope_key(second.id)[:16]})
            self.assertEqual(TestLabHistory(path, first.id).latest('hardware')['status'], 'pass')
            self.assertEqual(TestLabHistory(path, second.id).latest('hardware')['status'], 'fail')
            for value in ('ALPHA', 'BRAVO', 'first.invalid', 'second.invalid',
                          first.id, second.id):
                self.assertNotIn(value, output.getvalue())

    def test_no_bound_profiles_skips_without_device_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            preferences.profiles = [Profile.new('Unbound', 'unbound.invalid')]
            preferences.save()
            output = io.StringIO()
            with patch('c64u_browser.test_lab_fleet.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_fleet.run_profile') as runner:
                code = main([], stdout=output)
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['profiles'], [])
            runner.assert_not_called()

    def test_password_is_read_once_and_setup_error_stops_fleet(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'argonaut-development' / 'config.json'
            preferences = Preferences(path)
            preferences.profiles = [Profile.new('First', 'first.invalid', device_id='ALPHA'),
                                    Profile.new('Second', 'second.invalid', device_id='BRAVO')]
            preferences.save()
            output = io.StringIO()
            secrets = []

            def fail_first(args, stdin, stdout, stderr):
                secrets.append(stdin.readline())
                return 3

            with patch('c64u_browser.test_lab_fleet.config_base', return_value=base), patch(
                    'c64u_browser.test_lab_fleet.run_profile', side_effect=fail_first):
                code = main(['--password-stdin'], stdin=io.StringIO('private-secret\n'),
                            stdout=output)
            self.assertEqual(code, 3)
            self.assertEqual(secrets, ['private-secret\n'])
            self.assertEqual(json.loads(output.getvalue())['status'], 'error')
            self.assertNotIn('private-secret', output.getvalue())


if __name__ == '__main__':
    unittest.main()
