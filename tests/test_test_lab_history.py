import json
import os
from pathlib import Path
import tempfile
import unittest

from c64u_browser.test_lab import run_default_checks
from c64u_browser.test_lab_history import (MAX_RUNS, TestLabHistory,
                                           compare_reports, run_with_history)
from c64u_browser.test_lab_presentation import comparison_summary


def report(*statuses):
    checks = [{'id': key, 'status': status} for key, status in statuses]
    verdicts = {status for _, status in statuses}
    overall = 'fail' if 'fail' in verdicts else 'skip' if verdicts == {'skip'} else 'pass'
    return {'schema': 1, 'status': overall, 'checks': checks}


class HistoryTests(unittest.TestCase):
    def test_comparison_uses_verdicts_and_stable_ids(self):
        old = report(('one', 'pass'), ('two', 'fail'), ('removed', 'pass'))
        new = report(('one', 'fail'), ('two', 'pass'), ('added', 'pass'))
        result = compare_reports(old, new)
        self.assertEqual(result, {'new_failures': ['one'], 'resolved': ['two'],
                                  'added': ['added'], 'removed': ['removed']})
        self.assertEqual(comparison_summary(result),
                         '1 new failures · 1 resolved · 1 added · 1 removed')
        self.assertEqual(old['checks'][0]['status'], 'pass')
        self.assertEqual(new['checks'][0]['status'], 'fail')

    def test_first_run_and_damaged_latest_file(self):
        with tempfile.TemporaryDirectory() as directory:
            history = TestLabHistory(Path(directory) / 'argonaut-development' / 'config.json')
            self.assertIsNone(history.latest())
            first = run_with_history(Path(directory) / 'argonaut-development' / 'config.json',
                                     run_default_checks)
            self.assertTrue(first['saved'])
            self.assertIsNone(first['comparison'])
            self.assertEqual(history.latest()['status'], 'pass')
            (history.path / 'zzzz-invalid.json').write_text('{broken')
            self.assertEqual(history.latest()['status'], 'pass')
            damaged = report(('same', 'pass'), ('same', 'fail'))
            (history.path / 'zzzz-duplicate.json').write_text(json.dumps(damaged))
            self.assertEqual(history.latest()['status'], 'pass')
            second = run_with_history(Path(directory) / 'argonaut-development' / 'config.json',
                                      run_default_checks)
            self.assertEqual(second['comparison']['new_failures'], [])
            runs = history.recent_runs('offline')
            self.assertEqual(len(runs), 2)
            self.assertTrue(all(item['saved_at'] is not None for item in runs))
            self.assertEqual([item['report']['status'] for item in runs],
                             ['pass', 'pass'])

    def test_duplicate_or_inconsistent_report_cannot_mask_a_failure(self):
        valid = report(('one', 'fail'))
        duplicate = report(('one', 'pass'), ('one', 'fail'))
        with self.assertRaises(ValueError):
            compare_reports(duplicate, valid)
        with self.assertRaises(ValueError):
            compare_reports(valid, duplicate)
        inconsistent = report(('one', 'fail'))
        inconsistent['status'] = 'pass'
        with self.assertRaises(ValueError):
            compare_reports(valid, inconsistent)

    def test_private_atomic_files_and_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            history = TestLabHistory(Path(directory) / 'config.json')
            for _ in range(MAX_RUNS + 2):
                history.save(report(('one', 'pass')))
            files = list(history.path.glob('*.json'))
            self.assertEqual(len(files), MAX_RUNS)
            self.assertEqual(len(history.recent_runs()), MAX_RUNS)
            self.assertFalse(list(history.path.glob('.run-*')))
            self.assertEqual(json.loads(files[0].read_text())['schema'], 1)
            if os.name != 'nt':
                self.assertEqual(history.path.stat().st_mode & 0o777, 0o700)
                self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in files))

    def test_comparison_uses_previous_run_from_same_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            history = TestLabHistory(path)
            offline = report(('offline', 'pass'))
            offline['suite'] = 'offline'
            hardware = report(('hardware', 'fail'))
            hardware['suite'] = 'hardware'
            history.save(offline)
            history.save(hardware)
            current = run_with_history(path, lambda: offline)
            self.assertEqual(current['comparison']['added'], [])
            self.assertEqual(current['comparison']['removed'], [])

    def test_hardware_baselines_are_separate_for_each_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            first = report(('hardware.identity', 'pass'))
            first['suite'] = 'hardware'
            second = report(('hardware.identity', 'fail'))
            second['suite'] = 'hardware'
            a = run_with_history(path, lambda: first, profile_id='profile-a')
            b = run_with_history(path, lambda: second, profile_id='profile-b')
            a_again = run_with_history(path, lambda: second, profile_id='profile-a')
            self.assertIsNone(a['comparison'])
            self.assertIsNone(b['comparison'])
            self.assertEqual(a_again['comparison']['new_failures'], ['hardware.identity'])
            self.assertEqual(TestLabHistory(path, 'profile-a').latest('hardware')['status'], 'fail')
            self.assertEqual(TestLabHistory(path, 'profile-b').latest('hardware')['status'], 'fail')
            self.assertNotEqual(TestLabHistory(path, 'profile-a').path,
                                TestLabHistory(path, 'profile-b').path)
            self.assertNotIn('profile-a', str(TestLabHistory(path, 'profile-a').path))
            self.assertIsNone(TestLabHistory(path).latest('hardware'))

    def test_most_recent_includes_skip_without_replacing_verified_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            history = TestLabHistory(Path(directory) / 'config.json', 'profile-a')
            passed = report(('hardware.identity', 'pass'))
            passed['suite'] = 'hardware'
            failed = report(('hardware.identity', 'fail'))
            failed['suite'] = 'hardware'
            skipped = report(('hardware.identity', 'skip'))
            skipped['suite'] = 'hardware'
            history.save(passed)
            history.save(failed)
            history.save(skipped)
            self.assertEqual(history.most_recent('hardware')['status'], 'skip')
            self.assertEqual(history.latest('hardware')['status'], 'fail')
            pair = history.verified_pair('hardware')
            self.assertEqual([item['status'] for item in pair], ['fail', 'pass'])
            (history.path / 'zzzz-broken.json').write_text('{broken')
            self.assertEqual(history.most_recent('hardware')['status'], 'skip')
            self.assertEqual([item['status'] for item in history.verified_pair('hardware')],
                             ['fail', 'pass'])


if __name__ == '__main__':
    unittest.main()
