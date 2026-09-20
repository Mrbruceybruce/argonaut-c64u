import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from c64u_browser.app_preferences import defaults
from c64u_browser.test_lab_access import (
    UNITS, enabled, initialize_stable_automation, stop_background,
)


class Preferences:
    def __init__(self, mode):
        self.app_options = defaults()
        self.app_options['developer_mode'] = mode


class TestLabAccessTests(unittest.TestCase):
    def test_development_build_or_stable_opt_in_enables_test_lab(self):
        with patch.dict('os.environ', {'ARGONAUT_DEVELOPMENT': '1'}):
            self.assertTrue(enabled(Preferences(False)))
        with patch.dict('os.environ', {'ARGONAUT_DEVELOPMENT': '0'}):
            self.assertFalse(enabled(Preferences(False)))
            self.assertTrue(enabled(Preferences(True)))

    def test_turning_off_stops_all_linux_timers(self):
        commands = []

        def runner(args, **_kwargs):
            commands.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')

        self.assertTrue(stop_background(runner, 'linux'))
        self.assertEqual([args[-1] for args in commands], list(UNITS))
        self.assertTrue(all(args[2:5] == ['disable', '--now', timer]
                            for args, timer in zip(commands, UNITS)))

    def test_non_linux_does_not_call_system_service_manager(self):
        called = []
        self.assertTrue(stop_background(lambda *args, **kwargs: called.append(args),
                                        'darwin'))
        self.assertEqual(called, [])

    def test_first_stable_opt_in_clears_legacy_generic_enablements_once(self):
        commands = []
        def runner(args, **_kwargs):
            commands.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')
        with tempfile.TemporaryDirectory() as folder, patch.dict(
                'os.environ', {'ARGONAUT_DEVELOPMENT': '0'}):
            marker = Path(folder) / 'test-lab/marker'
            self.assertTrue(initialize_stable_automation(
                marker, runner, 'linux'))
            self.assertEqual(marker.read_text(), 'stable-service-opt-in-v1\n')
            if os.name != 'nt':
                self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            self.assertFalse(initialize_stable_automation(
                marker, runner, 'linux'))
        self.assertEqual([args[-1] for args in commands], list(UNITS))

    def test_stable_initialization_never_touches_development_or_non_linux(self):
        called = []
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'marker'
            with patch.dict('os.environ', {'ARGONAUT_DEVELOPMENT': '1'}):
                self.assertFalse(initialize_stable_automation(
                    marker, lambda *args, **kwargs: called.append(args), 'linux'))
            with patch.dict('os.environ', {'ARGONAUT_DEVELOPMENT': '0'}):
                self.assertFalse(initialize_stable_automation(
                    marker, lambda *args, **kwargs: called.append(args), 'darwin'))
        self.assertEqual(called, [])


if __name__ == '__main__':
    unittest.main()
