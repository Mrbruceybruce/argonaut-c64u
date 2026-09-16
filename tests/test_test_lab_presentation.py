import json
import unittest

from c64u_browser.test_lab import run_default_checks
from c64u_browser.test_lab_presentation import check_details, comparison_summary, summary


class PresentationTests(unittest.TestCase):
    def test_summary_and_operation_details(self):
        report = run_default_checks()
        self.assertEqual(summary(report), '10 passed · 0 failed · 0 skipped · 10 total')
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


if __name__ == '__main__':
    unittest.main()
