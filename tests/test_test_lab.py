import json
import subprocess
import sys
import threading
import unittest

from c64u_browser.api import ConnectionFailure, UltimateClient
from c64u_browser.test_lab import Check, SkipCheck, run_checks, run_default_checks


class TestLabTests(unittest.TestCase):
    def test_offline_checks_pass_and_serialize(self):
        report = run_default_checks()
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(len(report['checks']), 10)
        self.assertEqual(json.loads(json.dumps(report))['schema'], 1)

    def test_simulated_checks_exercise_real_transports_without_leaking_fixtures(self):
        report = run_default_checks()
        simulated = [check for check in report['checks'] if check['id'].startswith('sim.')]
        self.assertEqual(len(simulated), 8)
        self.assertTrue(all(check['status'] == 'pass' for check in simulated))
        self.assertTrue(all(len(check['operations']) == 1 for check in simulated[:6]))
        self.assertEqual(len(simulated[6]['operations']), 2)
        self.assertEqual(len(simulated[7]['operations']), 5)
        self.assertEqual(simulated[2]['operations'][0]['error_kind'], 'authentication')
        self.assertEqual(simulated[5]['operations'][0]['error_kind'], 'authentication')
        self.assertEqual(simulated[6]['id'], 'sim.identity.wrong_device')
        self.assertEqual(simulated[7]['id'], 'sim.hardware.complete')
        self.assertNotIn('private', json.dumps(report))
        self.assertNotIn('fixture.invalid', json.dumps(report))

    def test_verdict_assertions_remain_active_in_optimized_python(self):
        process = subprocess.run([sys.executable, '-O', '-c',
            'from c64u_browser.test_lab import require; require(False, "must fail")'],
            capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('AssertionError', process.stderr)

    def test_failed_check_does_not_stop_following_checks(self):
        seen = []

        def failure():
            raise AssertionError('private details')

        report = run_checks((Check('bad', 'Bad', failure),
                             Check('next', 'Next', lambda: seen.append('ran'))))
        self.assertEqual([r['status'] for r in report['checks']], ['fail', 'pass'])
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['checks'][0]['error_kind'], 'AssertionError')
        self.assertNotIn('private details', json.dumps(report))
        self.assertEqual(seen, ['ran'])

    def test_duplicate_or_invalid_ids_are_rejected_before_checks_run(self):
        seen = []
        for ids in (('same', 'same'), ('valid', ''), ('valid', 'bad\nname')):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                run_checks(Check(key, 'Fixture', lambda: seen.append('ran'))
                           for key in ids)
        self.assertEqual(seen, [])

    def test_operation_events_are_attached_to_their_check(self):
        client = UltimateClient('c64u.local')

        def failed_operation():
            def fail_request(*args):
                raise ConnectionFailure('network', 'private address')
            client._request_json_impl = fail_request
            client._request_json('GET', '/v1/info?token=secret')

        report = run_checks((Check('operation', 'Operation', failed_operation),))
        result = report['checks'][0]
        self.assertEqual(result['error_kind'], 'network')
        self.assertEqual(result['operations'][0]['error_kind'], 'network')
        self.assertEqual(result['operations'][0]['target'], '/v1/info')
        self.assertNotIn('secret', json.dumps(report))

    def test_other_thread_operations_do_not_pollute_check(self):
        client = UltimateClient('c64u.local')
        client._request_json_impl = lambda *args: {'errors': []}

        def unrelated_operation():
            thread = threading.Thread(target=lambda: client._request_json('GET', '/v1/info'))
            thread.start()
            thread.join()

        report = run_checks((Check('quiet', 'Quiet', unrelated_operation),))
        self.assertEqual(report['checks'][0]['operations'], [])

    def test_skip_is_distinct_from_failure(self):
        report = run_checks((Check('unavailable', 'Unavailable',
                                   lambda: (_ for _ in ()).throw(SkipCheck('not_connected'))),))
        self.assertEqual(report['status'], 'skip')
        self.assertEqual(report['checks'][0]['status'], 'skip')
        self.assertEqual(report['checks'][0]['error_kind'], 'not_connected')


if __name__ == '__main__':
    unittest.main()
