"""Synthetic runner contracts; no application imports or network access."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_ci_tests as runner


class RunnerTests(unittest.TestCase):
    def test_missing_duplicate_and_drift_selectors_rejected(self):
        data = json.loads(runner.MANIFEST.read_text())
        runner.audit(data)
        rows = data['suites']['python-unit']['selectors']
        rows.append(dict(rows[0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            runner.audit(data)
        rows.pop(); rows[0]['selector'] = 'test_sid_format.Missing'
        with self.assertRaisesRegex(ValueError, 'missing selector'):
            runner.audit(data)
        rows[0]['selector'] = 'test_sid_format.SidFormatTests'
        data['deferred_modules'].pop(next(iter(data['deferred_modules'])))
        with self.assertRaisesRegex(ValueError, 'inventory drift'):
            runner.audit(data)

    def synthetic(self, source, seconds=5, selector='fixture.Case'):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'fixture.py').write_text(source)
            output = root / 'result.json'
            env = dict(os.environ, PYTHONPATH=str(root))
            result = runner.bounded([sys.executable, '-u', str(Path(runner.__file__)),
                                     '--child', selector, '--output', str(output)],
                                    seconds, root / 'output.log', env)
            detail = json.loads(output.read_text()) if output.exists() else {}
            log = (root / 'output.log').read_text()
            return result, detail, log

    def test_success_and_verbose_ids(self):
        result, detail, log = self.synthetic('import unittest\nclass Case(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        self.assertEqual(0, result['returncode']); self.assertTrue(detail['ok'])
        self.assertEqual('fixture.Case.test_ok', detail['events'][0]['id'])
        self.assertIn('test_ok', log)

    def test_failure_error_skip_zero_and_missing_fail(self):
        for body in ('self.fail("failure")', 'raise RuntimeError("error")',
                     'self.skipTest("skip")', 'with self.subTest(x=1): self.fail("subtest")'):
            with self.subTest(body=body):
                result, detail, _ = self.synthetic('import unittest\nclass Case(unittest.TestCase):\n def test_case(self):\n  ' + body + '\n')
                self.assertNotEqual(0, result['returncode']); self.assertFalse(detail['ok'])
        for source, selector in [('import unittest\nclass Case(unittest.TestCase): pass\n', 'fixture.Case'),
                                 ('', 'fixture.Missing')]:
            result, detail, _ = self.synthetic(source, selector=selector)
            self.assertNotEqual(0, result['returncode']); self.assertFalse(detail['ok'])

    def test_setup_error_and_expected_failure_fail(self):
        for source in ('import unittest\nclass Case(unittest.TestCase):\n @classmethod\n def setUpClass(cls): raise RuntimeError("setup")\n def test_ok(self): pass\n',
                       'import unittest\nclass Case(unittest.TestCase):\n @unittest.expectedFailure\n def test_ok(self): self.fail("expected")\n'):
            result, detail, _ = self.synthetic(source)
            self.assertNotEqual(0, result['returncode']); self.assertFalse(detail['ok'])

    def test_timeout_retains_partial_traceback_and_kills_descendant(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'pid'
            source = ('import unittest, subprocess, sys, time\nfrom pathlib import Path\n'
                      'class Case(unittest.TestCase):\n def test_hang(self):\n'
                      '  p=subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"])\n'
                      f'  Path({str(marker)!r}).write_text(str(p.pid))\n'
                      '  time.sleep(60)\n')
            result, detail, log = self.synthetic(source, seconds=1)
            self.assertTrue(result['timeout']); self.assertFalse(detail['complete'])
            self.assertEqual('started', detail['events'][0]['status'])
            self.assertIn('test_hang', log); self.assertIn('Current thread', log)
            pid = int(marker.read_text())
            status = Path(f'/proc/{pid}/stat')
            # A reparented zombie is dead, though the host's init may reap it later.
            self.assertTrue(not status.exists() or status.read_text().split()[2] == 'Z')

    def test_success_also_cleans_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'pid'
            result, detail, _ = self.synthetic('import unittest, subprocess, sys\nfrom pathlib import Path\nclass Case(unittest.TestCase):\n def test_ok(self):\n  p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\n  Path(' + repr(str(marker)) + ').write_text(str(p.pid))\n')
            self.assertTrue(detail['ok']); self.assertFalse(result['timeout'])
            path = Path('/proc') / marker.read_text() / 'stat'
            self.assertTrue(not path.exists() or path.read_text().split()[2] == 'Z')

    def test_namespace_identity_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'did not change'):
            runner.verify_network(os.readlink('/proc/self/ns/net'))
        with patch.object(runner.subprocess, 'check_output', return_value=b'[{"ifname":"eth0","flags":["UP"]}]'), patch.object(runner.Path, 'read_text', return_value='CapEff: 0\nCapPrm: 0\nCapInh: 0\nCapBnd: 0\nCapAmb: 0\nNoNewPrivs: 1'), patch.object(runner.os, 'getuid', return_value=1000):
            with self.assertRaisesRegex(RuntimeError, 'only active loopback'):
                runner.verify_network('different')

    def test_async_and_unsupported_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'tests').mkdir()
            module = root / 'tests/test_sample.py'
            base = 'import unittest\nclass Plain(unittest.TestCase):\n def test_ok(self): pass\n'
            data = {'suites': {'unit': {'budget_seconds': 10, 'selectors': [
                {'selector': 'test_sample.Plain', 'tests': 1, 'audit': 'synthetic'}]}},
                'deferred_modules': {}, 'deferred_classes': {}, 'deferred_gtk_scripts': {},
                'offline_checks': ['one']}
            module.write_text(base + 'class Async(unittest.IsolatedAsyncioTestCase):\n async def test_async(self): pass\n')
            self.assertEqual(1, runner.inventory(root)['test_sample']['Async'])
            with self.assertRaisesRegex(ValueError, 'Class inventory drift'):
                runner.audit(data, root)
            data['deferred_classes']['test_sample.Async'] = 'not selected'
            runner.audit(data, root)
            for extra in ('if True:\n class Hidden(unittest.TestCase):\n  async def test_hidden(self): pass\n',
                          'class Hidden(unittest.TestCase):\n if True:\n  def test_hidden(self): pass\n',
                          'class Plain(unittest.TestCase):\n def test_again(self): pass\n'):
                module.write_text(base + extra)
                with self.assertRaisesRegex(ValueError, 'Unsupported test class'):
                    runner.audit(data, root)
            module.write_text(base + 'class Inherited(unittest.TestCase): pass\n')
            with self.assertRaisesRegex(ValueError, 'Class inventory drift'):
                runner.audit(dict(data, deferred_classes={}), root)

    def test_offline_identity_contract(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        expected = ['one', 'two']
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'offline.json'
            def run_one(checks):
                return {'checks': [{'id': checks[0].id, 'status': 'pass'}]}
            for actual in (['one'], ['one', 'one'], ['one', 'two', 'extra']):
                called = []
                def load():
                    return ([SimpleNamespace(id=key) for key in actual],
                            lambda checks: called.append(checks), lambda _: nullcontext())
                self.assertEqual(1, runner.offline_child(output, expected, load))
                self.assertFalse(called)
                self.assertFalse(json.loads(output.read_text())['complete'])
            checks = [SimpleNamespace(id=key) for key in expected]
            for rows in ([], [{'id': 'one', 'status': 'pass'}] * 2,
                         [{'id': 'other', 'status': 'pass'}]):
                self.assertEqual(1, runner.offline_child(output, expected,
                    lambda: (checks, lambda _: {'checks': rows}, lambda _: nullcontext())))
            self.assertEqual(0, runner.offline_child(output, expected,
                lambda: (checks, run_one, lambda _: nullcontext())))
            detail = json.loads(output.read_text())
            self.assertTrue(detail['complete']); self.assertEqual(2, len(detail['checks']))
            for status in ('skip', 'fail'):
                self.assertEqual(1, runner.offline_child(output, expected,
                    lambda: (checks, lambda c: {'checks': [{'id': c[0].id, 'status': status}]},
                             lambda _: nullcontext())))
            with self.assertRaises(ValueError):
                runner.validate_identities(expected, ['one', 'one'])

    def test_offline_partial_report_survives_hang(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'offline.json'
            source = ('import run_ci_tests as r, time\nfrom types import SimpleNamespace\n'
                      'from contextlib import nullcontext\n'
                      'def run(checks):\n'
                      ' if checks[0].id == "two": time.sleep(60)\n'
                      ' return {"checks": [{"id": checks[0].id, "status": "pass"}]}\n'
                      'def load():\n'
                      f' assert not r.json.loads(r.Path({str(output)!r}).read_text())["complete"]\n'
                      ' return [SimpleNamespace(id=k) for k in ("one","two")], run, lambda _: nullcontext()\n'
                      f'r.offline_child(r.Path({str(output)!r}), ["one","two"], load)\n')
            env = dict(os.environ, PYTHONPATH=str(Path(runner.__file__).parent))
            result = runner.bounded([sys.executable, '-c', source], 1, root / 'log', env)
            self.assertTrue(result['timeout'])
            detail = json.loads(output.read_text())
            self.assertFalse(detail['complete']); self.assertFalse(detail['ok'])
            self.assertEqual([{'id': 'one', 'status': 'pass'}], detail['checks'])
            self.assertEqual({'id': 'two', 'status': 'started'}, detail['events'][-1])

    def test_outer_timeout_reaps_nested_groups_and_preserves_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); marker = root / 'pids'; output = root / 'result.json'
            (root / 'fixture.py').write_text(
                'import unittest, subprocess, sys, time, os\nfrom pathlib import Path\n'
                'class Case(unittest.TestCase):\n def test_hang(self):\n'
                '  p=subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"])\n'
                f'  Path({str(marker)!r}).write_text(str(os.getpid())+" "+str(p.pid))\n'
                '  time.sleep(60)\n')
            inner_log = root / 'inner.log'
            command = [sys.executable, '-u', str(Path(runner.__file__)), '--child',
                       'fixture.Case', '--output', str(output)]
            source = ('import run_ci_tests as r\n'
                      f'r.bounded({command!r}, 60, {str(inner_log)!r})\n')
            env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(Path(runner.__file__).parent)]))
            result = runner.bounded([sys.executable, '-c', source], 1.5,
                                    root / 'outer.log', env, supervisor=True)
            self.assertTrue(result['timeout'])
            self.assertLess(result['seconds'], 8)
            self.assertFalse(json.loads(output.read_text())['complete'])
            self.assertIn('Current thread', inner_log.read_text())
            for pid in marker.read_text().split():
                self.assertFalse(Path('/proc', pid).exists(), 'unreaped process ' + pid)


if __name__ == '__main__':
    unittest.main()
