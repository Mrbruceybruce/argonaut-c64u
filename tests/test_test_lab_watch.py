import io
import json
import unittest
from unittest.mock import patch

from c64u_browser.test_lab_watch import main, monitor


class HeadlessMonitorTests(unittest.TestCase):
    def test_runs_sequentially_and_waits_after_each_completed_run(self):
        output = io.StringIO()
        events = []
        results = iter([(0, {'status': 'pass'}), (1, {'status': 'fail'}),
                        (0, {'status': 'pass'})])

        def run():
            events.append('run')
            return next(results)

        def sleep(seconds):
            events.append(('sleep', seconds))

        code = monitor(300, 3, run, output, sleeper=sleep)
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(code, 1)
        self.assertEqual(events, ['run', ('sleep', 300), 'run', ('sleep', 300), 'run'])
        self.assertEqual([line['exit_code'] for line in lines], [0, 1, 0])
        self.assertEqual([line['run'] for line in lines], [1, 2, 3])

    def test_setup_error_stops_before_sleeping(self):
        output = io.StringIO()
        slept = []
        code = monitor(300, 0, lambda: (3, None), output,
                       sleeper=lambda seconds: slept.append(seconds))
        self.assertEqual(code, 3)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(slept, [])

    def test_password_is_read_once_reused_and_never_printed(self):
        output = io.StringIO()
        calls = []

        def fake_run(args, stdin, stdout, stderr):
            calls.append((args, stdin.readline()))
            stdout.write(json.dumps({'schema': 1, 'suite': 'hardware', 'status': 'pass'}) + '\n')
            return 0

        with patch('c64u_browser.test_lab_watch.run_once', side_effect=fake_run):
            code = main(['--runs', '2', '--interval-minutes', '5', '--password-stdin'],
                        stdin=io.StringIO('private-secret\n'), stdout=output,
                        sleeper=lambda _: None)
        self.assertEqual(code, 0)
        self.assertEqual([secret for _, secret in calls],
                         ['private-secret\n', 'private-secret\n'])
        self.assertTrue(all('--suite' in args and 'hardware' in args for args, _ in calls))
        self.assertNotIn('private-secret', output.getvalue())

    def test_device_id_is_forwarded_to_each_read_only_run(self):
        output = io.StringIO()
        seen = []

        def fake_run(args, stdin, stdout, stderr):
            seen.append(args)
            stdout.write(json.dumps({'schema': 1, 'status': 'pass'}) + '\n')
            return 0

        with patch('c64u_browser.test_lab_watch.run_once', side_effect=fake_run):
            code = main(['--runs', '2', '--interval-minutes', '5',
                         '--device-id', 'BRAVO'], stdout=output, sleeper=lambda _: None)
        self.assertEqual(code, 0)
        self.assertEqual([args[args.index('--device-id') + 1] for args in seen],
                         ['BRAVO', 'BRAVO'])
        self.assertNotIn('BRAVO', output.getvalue())

    def test_all_profiles_dispatches_to_fleet_runner(self):
        output = io.StringIO()
        seen = []

        def fake_fleet(args, stdin, stdout, stderr):
            seen.append(args)
            stdout.write(json.dumps({'schema': 1, 'suite': 'hardware_profiles',
                                     'status': 'pass', 'profiles': []}) + '\n')
            return 0

        with patch('c64u_browser.test_lab_watch.run_fleet', side_effect=fake_fleet), patch(
                'c64u_browser.test_lab_watch.run_once') as single:
            code = main(['--all-profiles', '--runs', '1'], stdout=output)
        self.assertEqual(code, 0)
        self.assertEqual(seen, [['--timeout', '10']])
        single.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['result']['suite'],
                         'hardware_profiles')

    def test_skip_is_reported_without_model_contact(self):
        output = io.StringIO()
        code = monitor(300, 1, lambda: (2, {'status': 'skip'}), output)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['result']['status'], 'skip')


if __name__ == '__main__':
    unittest.main()
