import unittest

from c64u_browser.settings_safety import warning_for, warnings_for


class SettingsSafetyTests(unittest.TestCase):
    def test_supercpu_detect_is_high_risk(self):
        warning = warning_for('U64 Specific Settings',
                              'SuperCPU Detect (D0BC)')
        self.assertIn('unresponsive', warning)
        self.assertIn('power cycle', warning)

    def test_unrelated_and_similar_settings_are_not_marked(self):
        self.assertIsNone(warning_for('U64 Specific Settings', 'CPU Speed'))
        self.assertIsNone(warning_for('Other', 'SuperCPU Detect (D0BC)'))

    def test_warnings_are_stable_and_deduplicated(self):
        key = ('U64 Specific Settings', 'SuperCPU Detect (D0BC)')
        warnings = warnings_for([('Other', 'Setting'), key, key])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings, warnings_for([key]))


if __name__ == '__main__':
    unittest.main()
