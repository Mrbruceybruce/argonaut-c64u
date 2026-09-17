from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError
from c64u_browser.service_migration import (
    LEGACY_UNITS, migrate_legacy_services,
)


def result(args, code=0, output=''):
    return subprocess.CompletedProcess(args, code, output, '')


class ServiceMigrationTests(unittest.TestCase):
    def test_stable_app_never_touches_development_services(self):
        called = []
        with tempfile.TemporaryDirectory() as folder, patch.dict(
                'os.environ', {'ARGONAUT_DEVELOPMENT': '0'}):
            self.assertFalse(migrate_legacy_services(
                Path(folder) / 'marker',
                lambda *args, **kwargs: called.append(args)))
        self.assertEqual(called, [])

    def test_enabled_legacy_units_move_to_scoped_names_once(self):
        commands = []
        enabled_legacy = {LEGACY_UNITS[0][0], LEGACY_UNITS[2][0]}

        def runner(args, **_kwargs):
            commands.append(args[2:])
            if args[2] == 'is-enabled':
                return result(args, 0 if args[-1] in enabled_legacy else 1)
            if args[2] == 'cat':
                return result(args, output=(
                    'ExecStart=/usr/bin/argonaut-development-test\n'
                    if args[-1] in enabled_legacy else ''))
            return result(args)

        with tempfile.TemporaryDirectory() as folder, patch.dict(
                'os.environ', {'ARGONAUT_DEVELOPMENT': '1'}):
            marker = Path(folder) / 'marker'
            self.assertTrue(migrate_legacy_services(marker, runner))
            self.assertTrue(marker.is_file())
            self.assertFalse(migrate_legacy_services(marker, runner))
        self.assertIn(['disable', '--now', LEGACY_UNITS[0][0]], commands)
        self.assertIn(['disable', '--now', LEGACY_UNITS[2][0]], commands)
        self.assertIn(['daemon-reload'], commands)
        self.assertIn(['enable', '--now', LEGACY_UNITS[0][1]], commands)
        self.assertIn(['enable', '--now', LEGACY_UNITS[2][1]], commands)

    def test_restore_failure_is_actionable(self):
        old, new = LEGACY_UNITS[0]

        def runner(args, **_kwargs):
            if args[2] == 'is-enabled':
                return result(args, 0 if args[-1] == old else 1)
            if args[2] == 'cat':
                return result(args, output=(
                    'ExecStart=/usr/bin/argonaut-development-ai-bridge\n'
                    if args[-1] == old else ''))
            if args[2] == 'enable' and args[-1] == new:
                return result(args, 1)
            return result(args)

        with tempfile.TemporaryDirectory() as folder, patch.dict(
                'os.environ', {'ARGONAUT_DEVELOPMENT': '1'}):
            with self.assertRaisesRegex(BrowserError, 'could not be restored'):
                migrate_legacy_services(Path(folder) / 'marker', runner)

    def test_stable_units_are_never_mistaken_for_legacy_development_units(self):
        commands = []

        def runner(args, **_kwargs):
            commands.append(args[2:])
            if args[2] == 'is-enabled':
                return result(args)
            if args[2] == 'cat':
                return result(args, output='ExecStart=/usr/bin/argonaut-ai-bridge\n')
            return result(args)

        with tempfile.TemporaryDirectory() as folder, patch.dict(
                'os.environ', {'ARGONAUT_DEVELOPMENT': '1'}):
            marker = Path(folder) / 'marker'
            self.assertFalse(migrate_legacy_services(marker, runner))
            self.assertTrue(marker.is_file())
        self.assertFalse(any(command[0] == 'disable' for command in commands))


if __name__ == '__main__':
    unittest.main()
