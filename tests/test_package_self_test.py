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


class DebianSelfTestChecks(unittest.TestCase):
    def setUp(self):
        import hashlib
        from c64u_browser.package_self_test import _check_debian_package
        self.check=_check_debian_package
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'assets').mkdir()
        for name in ('foreground.py','operation_status.py','assets/commodore-c-equals.svg','assets/COMMODORE-ATTRIBUTION.txt'):
            (self.root/name).write_text('fixture')
        self.notes=self.root/'RELEASE-NOTES.md';self.notes.write_text('# Argonaut Development — 1.10\n')
        self.data={'package_format':'deb','package_version':'1.10~dev2','version':'1.10-dev2',
                   'development':True,'release_notes_sha256':hashlib.sha256(self.notes.read_bytes()).hexdigest()}
    def test_missing_notes_and_each_resource_fail(self):
        for name in ('RELEASE-NOTES.md','foreground.py','operation_status.py','assets/commodore-c-equals.svg','assets/COMMODORE-ATTRIBUTION.txt'):
            path=self.root/name;content=path.read_bytes();path.unlink()
            with self.assertRaises(PackageSelfTestFailure):self.check(self.data,[],self.root,self.root)
            path.write_bytes(content)
    def test_incorrect_channel_notes_fail_even_with_matching_digest(self):
        import hashlib
        self.notes.write_text('# Argonaut 0.1.0')
        self.data['release_notes_sha256']=hashlib.sha256(self.notes.read_bytes()).hexdigest()
        with self.assertRaises(PackageSelfTestFailure):self.check(self.data,[],self.root,self.root)
    def test_metadata_mismatch_and_old_development_line_fail(self):
        for value in ('1.10~dev1','1.9'):
            self.data['package_version']=value
            with self.assertRaises(PackageSelfTestFailure):self.check(self.data,[],self.root,self.root)
        self.data.update(package_version='1.9-dev',version='1.9-dev')
        with self.assertRaises(PackageSelfTestFailure):self.check(self.data,[],self.root,self.root)
    def test_other_platform_contracts_are_unchanged(self):
        checks=[];self.check({'version':'historical','development':True},checks,self.root,self.root)
        self.assertEqual([],checks)


if __name__ == '__main__':
    unittest.main()
