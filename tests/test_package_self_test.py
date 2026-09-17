import ast
import json
from pathlib import Path
import tempfile
import unittest

from c64u_browser.package_self_test import (
    PackageSelfTestFailure, _require, _write_report,
)


class PackageSelfTestTests(unittest.TestCase):
    def test_verdicts_do_not_depend_on_python_assertions(self):
        source = Path(__file__).resolve().parents[1] / 'c64u_browser/package_self_test.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))

    def test_named_failure_writes_structured_report(self):
        checks = []
        with self.assertRaises(PackageSelfTestFailure) as caught:
            _require(False, 'runtime.fixture', 'Fixture failed.', checks)
        checks.append({'id': caught.exception.check_id, 'status': 'fail'})
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            _write_report(report, {'version': 'test', 'build': 'fixture'},
                          'failed', checks, caught.exception)
            value = json.loads(report.read_text(encoding='utf-8'))
        self.assertEqual(value['result'], 'failed')
        self.assertEqual(value['failure']['check_id'], 'runtime.fixture')
        self.assertEqual(value['failure']['error_kind'], 'verification')
        self.assertNotIn('Fixture failed.', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
