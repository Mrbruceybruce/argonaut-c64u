from pathlib import Path
import tempfile
import unittest

from c64u_browser.profiles import Preferences, Profile
from c64u_browser.test_lab_history import TestLabHistory
from c64u_browser.test_lab_saved import (preferred_record, saved_hardware_results,
                                         saved_status)


def report(status):
    return {'schema': 1, 'suite': 'hardware', 'status': status,
            'checks': [{'id': 'hardware.identity', 'status': status}]}


class SavedHardwareTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
