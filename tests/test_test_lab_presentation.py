import json
import unittest

from c64u_browser.test_lab import run_default_checks
from c64u_browser.test_lab_presentation import (
    check_details, comparison_changes, comparison_summary, summary,
)


class PresentationTests(unittest.TestCase):
    def test_summary_and_operation_details(self):
        report = run_default_checks()
        self.assertEqual(summary(report), '14 passed · 0 failed · 0 skipped · 14 total')
        check = next(c for c in report['checks'] if c['id'] == 'sim.rest.authentication')
        text = check_details(check)
        self.assertIn('REST GET /v1/info · error', text)
        self.assertIn('authentication', text)
        self.assertNotIn('fixture.invalid', text)
        self.assertNotIn('private', json.dumps(report))

    def test_failure_category_is_visible_without_exception_message(self):
        check = {'title': 'Broken', 'id': 'broken', 'status': 'fail',
                 'duration_ms': 1.0, 'error_kind': 'AssertionError', 'operations': []}
        text = check_details(check)
        self.assertIn('Failure category: AssertionError', text)
        self.assertIn('No C64U operations', text)
        self.assertEqual(comparison_summary(None),
                         'First saved run; no previous run to compare.')

    def test_saved_regression_names_changed_checks(self):
        current = {'checks': [
            {'id': 'hardware.identity', 'title': 'Bound C64U identity and firmware'},
            {'id': 'hardware.storage', 'title': 'Read-only FTP root listing'}]}
        comparison = {'new_failures': ['hardware.storage'],
                      'resolved': ['hardware.identity'], 'added': [], 'removed': []}
        self.assertEqual(comparison_changes(comparison, current),
                         'New failures: Read-only FTP root listing · '
                         'Resolved: Bound C64U identity and firmware')
        current['checks'][1]['title'] = 42
        self.assertIn('New failures: hardware.storage',
                      comparison_changes(comparison, current))


if __name__ == '__main__':
    unittest.main()
