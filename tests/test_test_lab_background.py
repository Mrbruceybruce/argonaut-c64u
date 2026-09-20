import subprocess
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.test_lab_background import TIMER, set_enabled, status


def result(args, code=0, output=''):
    return subprocess.CompletedProcess(args, code, stdout=output, stderr='')


class BackgroundTestLabTests(unittest.TestCase):
    def test_status_distinguishes_off_stopped_and_ready(self):
        def runner(state):
            def run(args, **_kwargs):
                if args[2] == 'is-enabled':
                    return result(args, code=0 if state != 'disabled' else 1,
                                  output='enabled\n' if state != 'disabled' else '')
                return result(args, code=0 if state == 'ready' else 3,
                              output='active\n' if state == 'ready' else 'inactive\n')
            return run

        self.assertEqual(status(runner('disabled')).state, 'disabled')
        self.assertEqual(status(runner('stopped')).state, 'stopped')
        self.assertEqual(status(runner('ready')).state, 'ready')

    def test_enable_and_disable_are_verified(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                commands = []

                def runner(args, **_kwargs):
                    commands.append((args[2], args[-1], tuple(args[3:-1])))
                    if args[2] == 'is-enabled':
                        return result(args, code=0 if enabled else 1,
                                      output='enabled\n' if enabled else '')
                    return result(args, output=(
                        'active\n' if args[2] == 'is-active' else ''))

                current = set_enabled(enabled, runner)
                self.assertEqual(current.state,
                                 'ready' if enabled else 'disabled')
                self.assertEqual(commands[:2], [
                    ('daemon-reload', 'daemon-reload', ()),
                    ('enable' if enabled else 'disable', TIMER, ('--now',)),
                ])

    def test_failed_service_change_is_actionable(self):
        def runner(args, **_kwargs):
            return result(args, code=1 if args[2] == 'enable' else 0)

        with self.assertRaisesRegex(BrowserError, 'could not be enabled'):
            set_enabled(True, runner)


if __name__ == '__main__':
    unittest.main()
