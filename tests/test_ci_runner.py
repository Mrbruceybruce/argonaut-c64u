"""Synthetic runner contracts; no application imports or network access."""
import json
import subprocess
from types import SimpleNamespace
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
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
        with patch.object(runner.subprocess, 'check_output', return_value=b'[{"ifname":"eth0","flags":["UP"]}]'), patch.object(runner.Path, 'read_text', return_value='CapEff: 0\nCapPrm: 0\nCapInh: 0\nCapBnd: 0\nCapAmb: 0\nNoNewPrivs: 1'), patch.object(runner.os, 'getuid', return_value=1000), patch.object(runner.os, 'geteuid', return_value=1000), patch.object(runner.os, 'getgid', return_value=1000), patch.object(runner.os, 'getegid', return_value=1000):
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


    def evidence(self):
        return {'current': 'net:[2]', 'uid': 1000, 'euid': 1000, 'gid': 1000,
                'egid': 1000, 'capabilities': dict.fromkeys(runner.CAPS, '0') | {'NoNewPrivs': '1'}}

    def test_security_rejects_wrong_identity_and_every_capability(self):
        runner.validate_security(self.evidence(), 1000, 1000)
        for key in ('uid', 'euid', 'gid', 'egid', *runner.CAPS, 'NoNewPrivs'):
            row = self.evidence()
            if key in row:
                row[key] = 0
            else:
                row['capabilities'][key] = '0' if key == 'NoNewPrivs' else '1'
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                runner.validate_security(row, 1000, 1000)
        for row in ({}, dict(self.evidence(), capabilities={})):
            with self.assertRaises((KeyError, ValueError, TypeError)):
                runner.validate_security(row, 1000, 1000)

    def test_interfaces_routes_and_malformed_evidence_fail_closed(self):
        links = [{'ifname': 'lo', 'flags': ['UP'], 'addr_info': [{'local': '127.0.0.1'}]}]
        routes = {'-4': [{'dev': 'lo', 'dst': '127.0.0.0/8'}], '-6': []}
        runner.validate_network(links, routes)  # IPv6 loopback need not be configured.
        for bad in ([], {}, links + [{'ifname': 'eth0'}],
                    [dict(links[0], flags=[])], [dict(links[0], addr_info=[])],
                    [dict(links[0], addr_info=[{'local': '192.0.2.1'}])]):
            with self.subTest(links=bad), self.assertRaises((RuntimeError, ValueError, KeyError, TypeError)):
                runner.validate_network(bad, routes)
        for family, destination in (('-4', 'default'), ('-4', '192.0.2.0/24'),
                                    ('-4', '0.0.0.0/0'), ('-6', '2001:db8::/32'), ('-6', '::/0')):
            with self.subTest(destination=destination), self.assertRaises((RuntimeError, ValueError)):
                runner.validate_network(links, {family: [{'dev': 'lo', 'dst': destination}]})
        for row in ({'dev': 'eth0', 'dst': '127.0.0.1'}, {'dev': 'lo'},
                    {'dev': 'lo', 'dst': '127.0.0.1', 'gateway': '127.0.0.2'},
                    {'dev': 'lo', 'dst': '::1', 'multipath': []}):
            with self.assertRaises((RuntimeError, ValueError, KeyError)):
                runner.validate_network(links, {'-4': [row]})
        with self.assertRaises(ValueError):
            runner.validate_network(links, {'-4': {}})

    def test_child_restrictions_and_route_lookup_gate(self):
        links = [{'ifname': 'lo', 'flags': ['UP'], 'addr_info': [{'local': '127.0.0.1'}]}]
        for failure in ('child-ns', 'child-uid', 'child-caps', 'malformed', 'route', 'command'):
            child = self.evidence()
            if failure == 'child-ns': child['current'] = 'net:[3]'
            if failure == 'child-uid': child['uid'] = 0
            if failure == 'child-caps': child['capabilities']['CapAmb'] = '1'
            outputs = [json.dumps(links), '[]', '[]', '{' if failure == 'malformed' else json.dumps(child)]
            lookup = SimpleNamespace(returncode=0 if failure == 'route' else 2,
                                     stderr='bad command' if failure == 'command' else 'RTNETLINK answers: Network is unreachable')
            with patch.object(runner, 'security_evidence', return_value=self.evidence()), \
                 patch.object(runner.subprocess, 'check_output', side_effect=outputs), \
                 patch.object(runner.subprocess, 'run', return_value=lookup), \
                 patch.object(runner.socket, 'socket') as socket_mock:
                with self.subTest(failure=failure), self.assertRaises((RuntimeError, ValueError)):
                    runner.verify_network('net:[1]', 1000, 1000)
                socket_mock.assert_not_called()

    def test_valid_network_evidence_and_local_tcp(self):
        links = [{'ifname': 'lo', 'flags': ['UP'], 'addr_info': [{'local': '127.0.0.1'}]}]
        outputs = [json.dumps(links), '[{"dev":"lo","dst":"127.0.0.0/8"}]', '[]', json.dumps(self.evidence())]
        lookup = SimpleNamespace(returncode=2, stderr='RTNETLINK answers: Network is unreachable')
        with patch.object(runner, 'security_evidence', return_value=self.evidence()), \
             patch.object(runner.subprocess, 'check_output', side_effect=outputs), \
             patch.object(runner.subprocess, 'run', return_value=lookup) as route_get, \
             patch.object(runner.socket, 'socket') as listener, \
             patch.object(runner.socket, 'create_connection') as connect:
            server = listener.return_value.__enter__.return_value
            peer = unittest.mock.MagicMock()
            server.accept.return_value = (peer, ('127.0.0.1', 1))
            server.getsockname.return_value = ('127.0.0.1', 1234)
            peer.recv.return_value = b'ci'
            evidence = runner.verify_network('net:[1]', 1000, 1000)
            self.assertEqual('pass', evidence['loopback_tcp'])
            self.assertEqual(self.evidence(), evidence['child'])
            connect.assert_called_once_with(('127.0.0.1', 1234), timeout=2)
            self.assertEqual(2, route_get.call_count)

    def test_snapshot_excludes_untracked_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); src = root / 'src'; dst = root / 'dst'
            src.mkdir(); dst.mkdir()
            (src / 'tracked').write_text('current edit')
            (src / 'secret').write_text('untracked')
            with patch.object(runner.subprocess, 'check_output', return_value=b'tracked\0'):
                runner.tracked_snapshot(dst, src)
            self.assertEqual(['tracked'], [p.name for p in dst.iterdir()])
            self.assertEqual('current edit', (dst / 'tracked').read_text())
            (src / 'link').symlink_to(src / 'secret')
            for name in (b'link\0', b'../secret\0', b'.git/config\0'):
                with patch.object(runner.subprocess, 'check_output', return_value=name):
                    with self.assertRaises(ValueError): runner.tracked_snapshot(dst, src)

    def test_docker_launch_contract_and_failure_paths(self):
        for mode in ('success', 'rejected', 'missing', 'malformed-id', 'timeout', 'interrupted', 'suite-failure', 'missing-report', 'cleanup-failure'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                out = Path(folder)
                args = SimpleNamespace(output=out, docker_image='argonaut-ci:local', suite='offline-checks', optimized=False)
                calls = []
                def control(command, output, timeout=20):
                    calls.append(command)
                    if command[0] == 'image':
                        if mode == 'missing': raise FileNotFoundError('docker')
                        return '[{"Id":"sha256:dependency-image"}]'
                    if command[0] == 'create':
                        if mode == 'rejected': raise RuntimeError('launch rejected')
                        return 'bad' if mode == 'malformed-id' else 'a' * 64
                    return '{}'
                def execute(command, seconds, log):
                    (out / 'container-results/partial.json').write_text('{"started":true}')
                    if mode != 'missing-report':
                        runner.write_json(out / 'container-results/summary.json', {'ok': mode != 'suite-failure'})
                    if mode == 'interrupted': raise InterruptedError('signal')
                    return {'timeout': mode == 'timeout', 'returncode': 0}
                with patch.object(runner.os, 'getuid', return_value=1000), \
                     patch.object(runner.os, 'getgid', return_value=1000), \
                     patch.object(runner, 'tracked_snapshot'), \
                     patch.object(runner, 'docker_call', side_effect=control), \
                     patch.object(runner, 'bounded', side_effect=execute) as launch, \
                     patch.object(runner, 'cleanup_container', side_effect=RuntimeError('cleanup') if mode == 'cleanup-failure' else None) as cleanup:
                    if mode in ('success', 'timeout', 'suite-failure'):
                        self.assertEqual(0 if mode == 'success' else 1, runner.docker_suite(args, 120))
                    else:
                        with self.assertRaises((RuntimeError, FileNotFoundError, InterruptedError)):
                            runner.docker_suite(args, 120)
                    cleanup.assert_called_once()
                    if mode in ('missing', 'rejected', 'malformed-id'): launch.assert_not_called()
                    if mode == 'success':
                        create = next(c for c in calls if c[0] == 'create')
                        for option, value in (('--network', 'none'), ('--user', '1000:1000'),
                                              ('--cap-drop', 'ALL'), ('--security-opt', 'no-new-privileges=true')):
                            self.assertEqual(value, create[create.index(option) + 1])
                        self.assertIn('--init', create); self.assertIn('--read-only', create)
                        self.assertIn('sha256:dependency-image', create)
                        mounts = [create[i+1] for i, v in enumerate(create) if v == '--mount']
                        self.assertEqual(2, len(mounts)); self.assertTrue(mounts[0].endswith(',dst=/source,readonly'))
                        self.assertTrue(mounts[1].endswith(',dst=/results'))
                        self.assertNotIn('--privileged', create); self.assertNotIn('--device', create)
                        self.assertEqual(os.readlink('/proc/self/ns/net'), create[create.index('--parent-netns')+1])
                    if launch.called:
                        self.assertTrue((out / 'container-results/partial.json').exists())

    def test_cleanup_attempts_removal_and_requires_positive_absence(self):
        for failure in (None, 'stop', 'rm', 'query', 'remaining'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                calls = []; queries = []
                def control(command, output):
                    calls.append(command[0])
                    if command[0] == 'ps':
                        queries.append(True)
                        if failure == 'query': raise RuntimeError('daemon unavailable')
                        return 'a' * 64 if len(queries) < 3 or failure == 'remaining' else ''
                    if command[0] == failure: raise RuntimeError(failure)
                    return ''
                with patch.object(runner, 'docker_call', side_effect=control):
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                            runner.cleanup_container('argonaut-ci-test', Path(folder))
                    else:
                        runner.cleanup_container('argonaut-ci-test', Path(folder))
                self.assertIn('rm', calls)
                self.assertEqual(3, len(queries))
                self.assertEqual(failure is None, json.loads((Path(folder) / 'cleanup.json').read_text())['ok'])

    def test_docker_control_rejects_nonzero_and_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            real_popen = subprocess.Popen
            for mode in ('failure', 'timeout'):
                (out / 'docker-control.log').unlink(missing_ok=True)
                source = ('import sys,time; print("partial stdout",flush=True); '
                          'print("partial stderr",file=sys.stderr,flush=True); '
                          + ('time.sleep(60)' if mode == 'timeout' else 'sys.exit(1)'))
                def launch(command, **kwargs):
                    self.assertIn('["docker", "create"]', (out / 'docker-control.log').read_text())
                    return real_popen([sys.executable, '-c', source], **kwargs)
                with patch.object(runner.subprocess, 'Popen', side_effect=launch):
                    with self.assertRaises(subprocess.TimeoutExpired if mode == 'timeout' else RuntimeError):
                        runner.docker_call(['create'], out, timeout=.3)
                log = (out / 'docker-control.log').read_text()
                self.assertIn('partial stdout', log); self.assertIn('partial stderr', log)

    def test_docker_call_real_repeated_signals_reap_and_preserve_diagnostics(self):
        # Each isolated harness uses real OS signals and a real piped client. Hooks
        # make delivery deterministic at ownership, termination, drain and log I/O.
        for first in (signal.SIGTERM, signal.SIGINT):
            for phase in ('launch', 'wait', 'log'):
                with self.subTest(first=first, phase=phase), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    source = r"""
import os, signal, subprocess, sys, time
from pathlib import Path
from unittest.mock import patch
import run_ci_tests as r
root = Path(sys.argv[1]); first = int(sys.argv[2]); phase = sys.argv[3]
real_popen = subprocess.Popen; real_open = Path.open
clients = []; stages = []; cancelled = False

def raising(sig, frame):
    raise InterruptedError('outer signal')
for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, raising)

def send(stage, repeat=False):
    stages.append(stage)
    os.kill(os.getpid(), first)
    if repeat:
        os.kill(os.getpid(), signal.SIGINT if first == signal.SIGTERM else signal.SIGTERM)

class Log:
    def __init__(self, stream): self.stream = stream
    def __enter__(self): return self
    def write(self, text):
        if 'partial stdout' in text: send('write', True)
        return self.stream.write(text)
    def flush(self):
        if clients: send('flush', True)
        return self.stream.flush()
    def __exit__(self, *args):
        if clients: send('close', True)
        return self.stream.__exit__(*args)

def open_log(path, *args, **kwargs):
    stream = real_open(path, *args, **kwargs)
    return Log(stream) if path.name == 'docker-control.log' else stream

def launch(command, **kwargs):
    code = ('import sys,time; from pathlib import Path; '
            'print("partial stdout",flush=True); '
            'print("partial stderr",file=sys.stderr,flush=True); '
            f'Path({str(root / "ready")!r}).touch(); '
            + ('pass' if phase == 'log' else 'time.sleep(60)'))
    child = real_popen([sys.executable, '-c', code], **kwargs)
    clients.append(child)
    deadline = time.monotonic() + 5
    while not (root / 'ready').exists():
        if time.monotonic() > deadline: raise RuntimeError('client not ready')
        time.sleep(.005)
    kill = child.kill; communicate = child.communicate
    def protected_kill():
        send('kill', True)
        return kill()
    def protected_communicate(*args, **kwargs):
        if kwargs.get('timeout') is not None:
            if phase == 'wait': send('wait')
        else:
            send('drain', True)
        result = communicate(*args, **kwargs)
        if not kwargs: send('reaped', True)
        return result
    child.kill = protected_kill; child.communicate = protected_communicate
    if phase == 'launch': send('launch', True)
    return child

try:
    with patch.object(r.subprocess, 'Popen', side_effect=launch), patch.object(Path, 'open', open_log):
        try: r.docker_call(['create'], root, timeout=5)
        except InterruptedError: cancelled = True
    if not cancelled: raise RuntimeError('cancellation reported success')
    if any(signal.getsignal(sig) is not raising for sig in (signal.SIGTERM, signal.SIGINT)):
        raise RuntimeError('handlers not restored')
    child = clients[0]
    if child.returncode is None: raise RuntimeError('client not reaped')
    try: os.waitpid(child.pid, os.WNOHANG)
    except ChildProcessError: pass
    else: raise RuntimeError('child still owned')
    log = (root / 'docker-control.log').read_text()
    for expected in ('["docker", "create"]', 'partial stdout', 'partial stderr'):
        if expected not in log: raise RuntimeError('missing diagnostic: ' + expected)
    required = {'write', 'close'} if phase == 'log' else {'kill', 'drain', 'reaped', 'write', 'flush', 'close'}
    if not required.issubset(stages): raise RuntimeError('missing stages: ' + repr(stages))
    if phase != 'log' and 'InterruptedError' not in log: raise RuntimeError('missing interruption diagnostic')
finally:
    # A failing predecessor must not leave this regression's synthetic client alive.
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, signal.SIG_IGN)
    for child in clients:
        if child.poll() is None: os.kill(child.pid, signal.SIGKILL)
        child.wait()
"""
                    env = dict(os.environ, PYTHONPATH=str(Path(runner.__file__).parent),
                               PYTHONDONTWRITEBYTECODE='1')
                    command = [sys.executable] + (['-O'] if sys.flags.optimize else [])
                    result = subprocess.run(command + ['-c', source, str(root), str(first), phase],
                                            env=env, capture_output=True, text=True, timeout=15)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_delayed_creation_reconciles_but_never_claims_certainty(self):
        for arrival in (4, 100):
            with self.subTest(arrival=arrival), tempfile.TemporaryDirectory() as folder:
                queries = []; removed = []
                def control(command, output):
                    if command[0] == 'ps':
                        queries.append(True)
                        return 'a' * 64 if len(queries) >= arrival and not removed else ''
                    if command[0] == 'rm': removed.append(True)
                    return ''
                with patch.object(runner, 'docker_call', side_effect=control), patch.object(runner.time, 'sleep') as sleep:
                    with self.assertRaisesRegex(RuntimeError, 'Creation unresolved'):
                        runner.cleanup_container('unique-name', Path(folder), creation_unresolved=True)
                self.assertEqual(10, sleep.call_count)
                self.assertEqual(arrival == 4, bool(removed))
                report = json.loads((Path(folder) / 'cleanup.json').read_text())
                self.assertFalse(report['ok']); self.assertTrue(report['creation_unresolved'])

    def test_create_timeout_and_interruption_keep_pending_marker(self):
        for exception in (subprocess.TimeoutExpired('docker', 30), InterruptedError('signal')):
            with tempfile.TemporaryDirectory() as folder:
                out = Path(folder)
                args = SimpleNamespace(output=out, docker_image='image', suite='offline-checks', optimized=False)
                def control(command, output, timeout=20):
                    if command[0] == 'image': return '[{"Id":"sha256:image"}]'
                    self.assertTrue((out / 'create-pending.json').exists())
                    raise exception
                with patch.object(runner.os, 'getuid', return_value=1000), patch.object(runner.os, 'getgid', return_value=1000), patch.object(runner, 'tracked_snapshot'), patch.object(runner, 'docker_call', side_effect=control), patch.object(runner, 'cleanup_container') as cleanup:
                    with self.assertRaises(type(exception)): runner.docker_suite(args, 120)
                self.assertTrue(cleanup.call_args.kwargs['creation_unresolved'])
                self.assertTrue((out / 'create-pending.json').exists())

    def test_real_signals_through_shell_supervisor_and_child_cleanup(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=sig), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); marker = root / 'pids'; cleaning = root / 'cleaning'
                leaf = ('import os,signal,time; from pathlib import Path; '
                        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                        'signal.signal(signal.SIGINT,signal.SIG_IGN); '
                        f'Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)')
                inner = ('import run_ci_tests as r; '
                         f'r.bounded({[sys.executable, "-c", leaf]!r},60,{str(root / "inner.log")!r})')
                # An actual shell exec chain, with a nested process group supervised by bounded().
                command = ['/bin/sh', '-c', 'exec "$@"', 'ci', sys.executable, '-c', inner]
                source = ('import run_ci_tests as r, signal, time; from pathlib import Path\n'
                          'original=r.request_tracebacks\n'
                          'def trace(pid):\n'
                          f' Path({str(cleaning)!r}).touch(); time.sleep(.3); original(pid)\n'
                          'r.request_tracebacks=trace\n'
                          'try:\n'
                          f' r.bounded({command!r},60,{str(root / "outer.log")!r},supervisor=True)\n'
                          'except InterruptedError: raise SystemExit(9)\n')
                env = dict(os.environ, PYTHONPATH=str(Path(runner.__file__).parent), PYTHONDONTWRITEBYTECODE='1')
                with (root / 'supervisor.log').open('w') as log:
                    proc = subprocess.Popen([sys.executable, '-c', source], env=env, stdout=log, stderr=log)
                    try:
                        deadline = time.monotonic() + 8
                        while not marker.exists() and proc.poll() is None and time.monotonic() < deadline: time.sleep(.01)
                        self.assertTrue(marker.exists(), (root / 'supervisor.log').read_text())
                        proc.send_signal(sig)
                        while not cleaning.exists() and proc.poll() is None and time.monotonic() < deadline: time.sleep(.01)
                        self.assertTrue(cleaning.exists())
                        proc.send_signal(sig)  # Cleanup must survive a repeated cancellation.
                        self.assertEqual(9, proc.wait(timeout=8))
                        self.assertFalse(Path('/proc', marker.read_text()).exists())
                    finally:
                        if proc.poll() is None: proc.kill(); proc.wait()


if __name__ == '__main__':
    unittest.main()
