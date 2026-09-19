from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class TestingChecklistTests(unittest.TestCase):
    def test_versioned_ods_keeps_controls_and_uses_current_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'checklist.ods'
            subprocess.run([
                sys.executable, str(ROOT / 'packaging/build_testing_checklist.py'),
                '--version', '9.8-test.7', '--commit', 'abc123',
                '--output', str(output),
            ], check=True)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist()[0], 'mimetype')
                content = archive.read('content.xml').decode('utf-8')
            self.assertIn('Argonaut 9.8-test.7 testing checklist', content)
            self.assertIn('source commit abc123', content)
            self.assertIn('New D64 disk on C64U…', content)
            self.assertIn('Save image as…', content)
            self.assertIn('Save and return the completed ODS', content)
            self.assertIn(
                'Argonaut-9.8-test.7-testing-results-PLATFORM-TESTER.ods', content)
            self.assertIn('table:content-validation-name="val1"', content)
            self.assertIn('COUNTIF', content)
            self.assertNotIn('1.7-disk.14', content)


if __name__ == '__main__':
    unittest.main()
