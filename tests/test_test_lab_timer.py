import importlib.util
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'packaging/linux/test_lab_timer.py'
SPEC = importlib.util.spec_from_file_location('argonaut_test_lab_timer', SOURCE)
timer_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(timer_module)


class TestLabTimerTests(unittest.TestCase):
    def test_render_runs_read_only_fleet_and_separates_failed_verdict(self):
        with tempfile.TemporaryDirectory(prefix='Argonaut Test Lab ') as directory:
            root = Path(directory)
            service, timer = timer_module.render(root, '/usr/bin/python3',
                                                 root / 'config.json')
        self.assertIn(f'WorkingDirectory={root}', service)
        self.assertIn(f'ExecStart={Path("/usr/bin/python3").resolve()} '
                      '-m c64u_browser.test_lab_alert', service)
        self.assertIn(f'ConditionPathExists={root / "config.json"}', service)
        self.assertIn('SuccessExitStatus=2', service)
        self.assertNotIn('--explain-failures', service)
        self.assertNotIn('SuccessExitStatus=1', service)
        self.assertIn('OnActiveSec=5min', timer)
        self.assertIn('OnUnitActiveSec=30min', timer)
        self.assertIn('Unit=argonaut-test-lab-fleet.service', timer)

    def test_python_path_with_spaces_is_rejected(self):
        with self.assertRaises(ValueError):
            timer_module.render('/tmp/source', '/tmp/python with spaces', '/tmp/config')


if __name__ == '__main__':
    unittest.main()
