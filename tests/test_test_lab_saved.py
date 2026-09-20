from pathlib import Path
import tempfile
import unittest

from c64u_browser.profiles import Preferences, Profile
from c64u_browser.test_lab_history import TestLabHistory
from c64u_browser.test_lab_saved import (
    preferred_record, saved_comparison, saved_hardware_results, saved_run_label,
    saved_status, saved_suite_result,
)


def report(status):
    return {'schema': 1, 'suite': 'hardware', 'status': status,
            'checks': [{'id': 'hardware.identity', 'status': status}]}


def suite_report(status):
    return {'schema': 1, 'suite': 'bridge', 'status': status,
            'checks': [{'id': 'bridge.end_to_end', 'status': status}]}


class SavedHardwareTests(unittest.TestCase):
    def test_unscoped_bridge_history_can_reopen_latest_automatic_result(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / 'config.json')
            history = TestLabHistory(preferences.path)
            history.save(suite_report('pass'))
            history.save(suite_report('fail'))
            record = saved_suite_result(preferences, 'bridge')
            self.assertEqual(record['recent']['status'], 'fail')
            self.assertEqual(record['verified']['status'], 'fail')
            self.assertEqual(record['previous_verified']['status'], 'pass')
            self.assertEqual(
                saved_comparison(record, record['recent'])['new_failures'],
                ['bridge.end_to_end'])

    def test_failing_device_is_selected_and_skip_keeps_last_verified_failure_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / 'argonaut-development/config.json')
            first = Profile.new('First C64U', 'first.invalid', device_id='FIRST')
            second = Profile.new('Second C64U', 'second.invalid', device_id='SECOND')
            unbound = Profile.new('Unbound', 'unbound.invalid')
            preferences.profiles = [first, second, unbound]
            preferences.selected_id = first.id
            TestLabHistory(preferences.path, first.id).save(report('pass'))
            second_history = TestLabHistory(preferences.path, second.id)
            second_history.save(report('fail'))
            second_history.save(report('skip'))
            records = saved_hardware_results(preferences)
            self.assertEqual(len(records), 2)
            self.assertEqual(preferred_record(records, first.id), 1)
            self.assertEqual(saved_status(records[0]), 'Pass')
            self.assertEqual(saved_status(records[1]), 'Skipped · last verified fail')
            self.assertEqual(records[1]['recent']['status'], 'skip')

    def test_selected_profile_is_preferred_when_none_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / 'config.json')
            first = Profile.new('First', 'first.invalid', device_id='FIRST')
            second = Profile.new('Second', 'second.invalid', device_id='SECOND')
            preferences.profiles = [first, second]
            records = saved_hardware_results(preferences)
            self.assertEqual(preferred_record(records, second.id), 1)
            self.assertEqual(saved_status(records[0]), 'No saved run')

    def test_saved_view_compares_verified_runs_but_not_a_later_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / 'config.json')
            first = Profile.new('First', 'first.invalid', device_id='FIRST')
            second = Profile.new('Second', 'second.invalid', device_id='SECOND')
            preferences.profiles = [first, second]
            history = TestLabHistory(preferences.path, first.id)
            history.save(report('pass'))
            history.save(report('fail'))
            history.save(report('skip'))
            records = saved_hardware_results(preferences)
            self.assertEqual(records[0]['previous_verified']['status'], 'pass')
            self.assertEqual(saved_comparison(records[0], records[0]['verified'])
                             ['new_failures'], ['hardware.identity'])
            self.assertIsNone(saved_comparison(records[0], records[0]['recent']))
            self.assertIsNone(records[1]['previous_verified'])

    def test_older_saved_run_uses_its_own_prior_verified_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory) / 'config.json')
            profile = Profile.new('First', 'first.invalid', device_id='FIRST')
            preferences.profiles = [profile]
            history = TestLabHistory(preferences.path, profile.id)
            history.save(report('pass'))
            history.save(report('fail'))
            history.save(report('pass'))
            record = saved_hardware_results(preferences)[0]
            self.assertEqual(len(record['runs']), 3)
            newest, middle, oldest = (item['report'] for item in record['runs'])
            self.assertEqual(saved_comparison(record, newest)['resolved'],
                             ['hardware.identity'])
            self.assertEqual(saved_comparison(record, middle)['new_failures'],
                             ['hardware.identity'])
            self.assertIsNone(saved_comparison(record, oldest))
            self.assertIn('— Pass', saved_run_label(record['runs'][0], 0))


if __name__ == '__main__':
    unittest.main()
