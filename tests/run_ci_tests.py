"""Bounded explicit CI suites. No discovery and no network-isolation fallback."""
import ctypes
import argparse
import ast
import faulthandler
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tests/ci_suites.json'
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT)]


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def inventory(root=ROOT):
    """Source-only inventory; never imports deferred modules."""
    result = {}
    for path in sorted((root / 'tests').glob('test_*.py')):
        classes = {}
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [n.name for n in ast.walk(node)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and n.name.startswith('test')]
            testcase = any((isinstance(base, ast.Name) and base.id.endswith('TestCase'))
                           or (isinstance(base, ast.Attribute) and base.attr.endswith('TestCase'))
                           for base in node.bases)
            if methods or testcase:
                direct = [n.name for n in node.body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and n.name.startswith('test')]
                if (node not in tree.body or methods != direct
                        or len(methods) != len(set(methods)) or node.name in classes):
                    raise ValueError('Unsupported test class definition: ' + path.stem + '.' + node.name)
                classes[node.name] = len(methods)
        result[path.stem] = classes
    return result


def audit(data, root=ROOT):
    validate_identities(data['offline_checks'], data['offline_checks'])
    found = inventory(root)
    selected = {}
    for name, suite in data['suites'].items():
        if not suite['selectors'] or not 0 < suite['budget_seconds'] <= 600:
            raise ValueError('Empty suite or invalid budget: ' + name)
        for row in suite['selectors']:
            selector = row['selector']
            module, cls = selector.split('.')
            if selector in selected or cls not in found.get(module, {}):
                raise ValueError('Duplicate or missing selector: ' + selector)
            if row['tests'] != found[module][cls] or not row['audit']:
                raise ValueError('Changed test count or missing audit: ' + selector)
            if not 0 < row.get('timeout_seconds', 120) <= 180:
                raise ValueError('Invalid timeout: ' + selector)
            selected[selector] = row
    deferred = data['deferred_modules']
    selected_modules = {s.split('.')[0] for s in selected}
    if set(deferred) != set(found) - selected_modules or not all(deferred.values()):
        raise ValueError('Module inventory drift: review manifest')
    omitted = {m + '.' + c for m in selected_modules for c in found[m]
               if m + '.' + c not in selected}
    if set(data['deferred_classes']) != omitted or not all(data['deferred_classes'].values()):
        raise ValueError('Class inventory drift: review manifest')
    scripts = {p.name for p in (root / 'tests').glob('*_gtk_check.py')}
    if set(data['deferred_gtk_scripts']) != scripts or not all(data['deferred_gtk_scripts'].values()):
        raise ValueError('GTK script inventory drift: review manifest')
    return {'modules': len(found), 'selected_modules': len(selected_modules),
            'selected_classes': len(selected), 'selected_tests': sum(r['tests'] for r in selected.values()),
            'deferred_modules': deferred, 'deferred_classes': data['deferred_classes'],
            'deferred_gtk_scripts': data['deferred_gtk_scripts'],
            'deferred_module_count': len(deferred), 'deferred_class_count': len(omitted),
            'deferred_test_methods': sum(sum(found[m].values()) for m in deferred) + sum(found[s.split('.')[0]][s.split('.')[1]] for s in omitted),
            'count_basis': 'Source-defined test methods; no imports or inherited-method expansion for deferred tests',
            'deferred_gtk_script_count': len(scripts)}


def request_tracebacks(pgid):
    """Signal only group members that have installed a SIGUSR1 handler (also wrappers)."""
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
            if os.getpgid(pid) != pgid:
                continue
            status = dict(line.split(':', 1) for line in (entry / 'status').read_text().splitlines() if ':' in line)
            if int(status['SigCgt'].strip(), 16) & (1 << (signal.SIGUSR1 - 1)):
                os.kill(pid, signal.SIGUSR1)
        except (ProcessLookupError, FileNotFoundError, PermissionError):
            pass


def bounded(command, seconds, log, env=None, supervisor=False):
    """Supervisors own/reap nested groups; outer shutdown allows their cleanup to finish."""
    # Adopt orphaned grandchildren so group cleanup does not leave zombies to init.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot enable child subreaper')
    started = time.monotonic()
    proc = None
    pending_signal = None
    def interrupted(signum, frame):
        nonlocal pending_signal
        pending_signal = signum
        if proc is not None:
            raise InterruptedError('Runner interrupted by signal ' + str(signum))
    old = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    timed_out = False
    try:
        with Path(log).open('w') as output:
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            if pending_signal is not None:
                raise InterruptedError('Interrupted during launch')
            try:
                proc.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        # Repeated TERM/INT must not interrupt cleanup or prevent reaping.
        for sig in old:
            signal.signal(sig, signal.SIG_IGN)
        try:
            if proc is not None:
                def kill_group(sig):
                    try:
                        os.killpg(proc.pid, sig)
                    except ProcessLookupError:
                        pass
                if supervisor and proc.poll() is None:
                    proc.terminate()  # Its bounded() finally cleans every active class group.
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                request_tracebacks(proc.pid)
                time.sleep(.2)
                kill_group(signal.SIGTERM)
                time.sleep(.1)
                kill_group(signal.SIGKILL)
                proc.wait()
                # All adopted descendants in this group have received KILL.
                while True:
                    try:
                        os.waitpid(-proc.pid, 0)
                    except ChildProcessError:
                        break
        finally:
            for sig, handler in old.items():
                signal.signal(sig, handler)
    return {'returncode': proc.returncode, 'timeout': timed_out,
            'seconds': round(time.monotonic() - started, 3)}


def validate_identities(actual, expected):
    if (not expected or any(not isinstance(key, str) or not key for key in expected)
            or len(expected) != len(set(expected)) or len(actual) != len(set(actual))
            or set(actual) != set(expected)):
        raise ValueError('Offline check identities missing, duplicate or unexpected')


def offline_child(output, expected, load=None):
    report = {'schema': 1, 'suite': 'offline', 'status': 'incomplete',
              'complete': False, 'ok': False, 'checks': [], 'events': []}
    write_json(output, report)  # Persist even when importing checks hangs.
    try:
        if load is None:
            from c64u_browser.test_lab import DEFAULT_CHECKS, run_checks, operation_origin
            from c64u_browser.simulated_c64u import SIMULATED_CHECKS
            checks, run_one, origin = DEFAULT_CHECKS + SIMULATED_CHECKS, run_checks, operation_origin
        else:
            checks, run_one, origin = load()
        validate_identities([check.id for check in checks], expected)
        with origin('simulation'):
            for check in checks:
                report['events'].append({'id': check.id, 'status': 'started'})
                write_json(output, report)
                result = run_one((check,))
                rows = result['checks']
                validate_identities([row['id'] for row in rows], [check.id])
                report['checks'].extend(rows)
                report['events'].append({'id': check.id, 'status': rows[0]['status']})
                write_json(output, report)
        validate_identities([row['id'] for row in report['checks']], expected)
        ok = all(row['status'] == 'pass' for row in report['checks'])
        report.update(complete=True, ok=ok, status='pass' if ok else 'fail')
    except BaseException:
        report.update(error=traceback.format_exc(), status='fail')
        traceback.print_exc()
    finally:
        write_json(output, report)
    return 0 if report['ok'] else 1


def child(selector, output):
    faulthandler.enable()
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    faulthandler.dump_traceback_later(30, repeat=True)
    report = {'selector': selector, 'events': [], 'complete': False}
    write_json(output, report)
    class Result(unittest.TextTestResult):
        def event(self, test, status, detail=''):
            test_started = getattr(self, 'started_tests', {}).get(test.id(), started)
            report['events'].append({'id': test.id(), 'status': status, 'detail': detail,
                                     'elapsed_seconds': round(time.monotonic() - started, 3),
                                     'duration_seconds': round(time.monotonic() - test_started, 3)})
            write_json(output, report)
        def startTest(self, test):
            super().startTest(test)
            if not hasattr(self, 'started_tests'):
                self.started_tests = {}
            self.started_tests[test.id()] = time.monotonic()
            self.event(test, 'started')
        def addSuccess(self, test):
            super().addSuccess(test); self.event(test, 'pass')
        def addFailure(self, test, err):
            super().addFailure(test, err); self.event(test, 'failure', self._exc_info_to_string(err, test))
        def addError(self, test, err):
            super().addError(test, err); self.event(test, 'error', self._exc_info_to_string(err, test))
        def addSkip(self, test, reason):
            super().addSkip(test, reason); self.event(test, 'skip', reason)
        def addExpectedFailure(self, test, err):
            super().addExpectedFailure(test, err); self.event(test, 'expected-failure', self._exc_info_to_string(err, test))
        def addUnexpectedSuccess(self, test):
            super().addUnexpectedSuccess(test); self.event(test, 'unexpected-success')
        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err:
                self.event(subtest, 'subtest-failure', self._exc_info_to_string(err, test))
    started = time.monotonic()
    try:
        module, name = selector.split('.')
        cls = getattr(importlib.import_module(module), name)
        if not isinstance(cls, type) or not issubclass(cls, unittest.TestCase):
            raise ValueError('Selector is not a TestCase class')
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
        ok = (result.testsRun > 0 and result.wasSuccessful() and not result.skipped
              and not result.expectedFailures)
        report.update(complete=True, tests=result.testsRun, skips=len(result.skipped),
                      failures=len(result.failures), errors=len(result.errors), ok=ok)
    except BaseException:
        report.update(ok=False, error=traceback.format_exc())
        traceback.print_exc()
    finally:
        write_json(output, report)
        faulthandler.cancel_dump_traceback_later()
    return 0 if report.get('ok') else 1


def verify_network(parent):
    current = os.readlink('/proc/self/ns/net')
    if current == parent or not parent:
        raise RuntimeError('Network namespace did not change')
    security = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if os.getuid() == 0 or any(int(security[k].strip(), 16) for k in ('CapEff', 'CapPrm', 'CapInh', 'CapBnd', 'CapAmb')) or security['NoNewPrivs'].strip() != '1':
        raise RuntimeError('Tests must run unprivileged with all capabilities dropped')
    links = json.loads(subprocess.check_output(['ip', '-j', 'address'], timeout=5))
    if len(links) != 1 or links[0]['ifname'] != 'lo' or 'UP' not in links[0]['flags']:
        raise RuntimeError('Expected only active loopback')
    import ipaddress
    for address in links[0]['addr_info']:
        if not ipaddress.ip_address(address['local']).is_loopback:
            raise RuntimeError('Non-loopback address')
    routes = {}
    for family in ('-4', '-6'):
        routes[family] = json.loads(subprocess.check_output(
            ['ip', family, '-j', 'route', 'show', 'table', 'all'], timeout=5))
        if any(r.get('dev') != 'lo' or r.get('dst') == 'default' for r in routes[family]):
            raise RuntimeError('Non-loopback route')
    # Actual local TCP traffic; no external probe or device packet is sent.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(2)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                client.sendall(b'ci'); peer.settimeout(2)
                if peer.recv(2) != b'ci':
                    raise RuntimeError('Loopback probe failed')
    return {'parent': parent, 'current': current, 'links': links, 'routes': routes,
            'loopback_tcp': 'pass', 'external_probe': 'none', 'uid': os.getuid(),
            'capabilities': {k: security[k].strip() for k in ('CapEff', 'CapPrm', 'CapInh', 'CapBnd', 'CapAmb', 'NoNewPrivs')}}


def preflight(kind):
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Secret', '1')
    from gi.repository import Gtk, Secret
    print('Python', sys.version, 'GI', gi.__version__, 'GTK', Gtk.get_major_version(), Gtk.get_minor_version(), flush=True)
    if kind == 'media-regression':
        gi.require_version('Gst', '1.0'); gi.require_version('GstPbutils', '1.0')
        from gi.repository import Gst, GstPbutils
        Gst.init(None)
        print(Gst.version_string(), flush=True)
        for name in ('appsrc', 'queue', 'videoconvert', 'vp8enc', 'audioconvert',
                     'audioresample', 'vorbisenc', 'webmmux', 'splitmuxsink',
                     'filesrc', 'matroskademux', 'splitmuxsrc', 'filesink'):
            if Gst.ElementFactory.find(name) is None:
                raise RuntimeError('Missing GStreamer element: ' + name)
        GstPbutils.Discoverer.new(5 * Gst.SECOND)
    if kind == 'gtk-regression':
        from gi.repository import Gio, Gdk
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise RuntimeError('GTK display unavailable')
        Gio.bus_get_sync(Gio.BusType.SESSION, None)
        import ctypes
        ctypes.CDLL('libXtst.so.6')
        window = Gtk.Window(); window.present(); window.destroy()
    return 0


def inside(args, data, report):
    out = args.output
    write_json(out / 'network.json', verify_network(args.parent_netns))
    suite = data['suites'].get(args.suite)
    budget = 120 if args.suite == 'offline-checks' else suite['budget_seconds']
    deadline = time.monotonic() + budget
    with tempfile.TemporaryDirectory(prefix='argonaut-ci-') as temporary:
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONUNBUFFERED': '1',
               'PYTHONNOUSERSITE': '1', 'GDK_BACKEND': 'x11', 'GSK_RENDERER': 'cairo',
               'NO_AT_BRIDGE': '1'}
        for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_RUNTIME_DIR'):
            path = Path(temporary) / key.lower(); path.mkdir(mode=0o700); env[key] = str(path)
        python = ['/usr/bin/python3'] + (['-O'] if args.optimized else []) + ['-u', str(Path(__file__).resolve())]
        prefix = ['xvfb-run', '-a', '-s', '-screen 0 1280x1024x24 -nolisten tcp', 'dbus-run-session', '--'] if args.suite == 'gtk-regression' else []
        report['preflight'] = bounded(prefix + python + ['--preflight', args.suite], min(30, budget), out / 'preflight.log', env)
        write_json(out / 'summary.json', report)
        if report['preflight']['returncode'] or report['preflight']['timeout']:
            return 1
        if args.suite == 'offline-checks':
            target = out / 'test-lab-report.json'
            target.unlink(missing_ok=True)
            report['offline'] = bounded(python + ['--offline-child', '--output', str(target)], max(.01, deadline-time.monotonic()), out / 'offline.log', env)
            report['ok'] = report['offline']['returncode'] == 0 and not report['offline']['timeout']
        else:
            report['classes'] = []
            for row in suite['selectors']:
                selector = row['selector']; remaining = deadline - time.monotonic()
                if remaining <= 0:
                    report['classes'].append({'selector': selector, 'ok': False, 'not_run': 'suite budget exhausted'})
                else:
                    target = out / (selector + '.json')
                    target.unlink(missing_ok=True)
                    result = bounded(prefix + python + ['--child', selector, '--output', str(target)], min(row.get('timeout_seconds', 120), remaining), out / (selector + '.log'), env)
                    details = json.loads(target.read_text()) if target.exists() else {}
                    result.update({key: details.get(key) for key in ('tests', 'skips', 'failures', 'errors', 'complete')})
                    result.update(selector=selector, ok=result['returncode'] == 0 and not result['timeout'] and details.get('ok', False) and details.get('tests') == row['tests'])
                    report['classes'].append(result)
                write_json(out / 'summary.json', report)
            report['ok'] = bool(report['classes']) and all(r['ok'] for r in report['classes'])
        write_json(out / 'summary.json', report)
        return 0 if report['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['offline-checks', 'python-unit', 'python-regression', 'media-regression', 'gtk-regression'])
    parser.add_argument('--optimized', action='store_true')
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'ci-results')
    parser.add_argument('--offline-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--child', help=argparse.SUPPRESS)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--parent-netns', help=argparse.SUPPRESS)
    parser.add_argument('--preflight', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.offline_child:
        faulthandler.enable()
        faulthandler.register(signal.SIGUSR1, all_threads=True)
        faulthandler.dump_traceback_later(30, repeat=True)
        try:
            return offline_child(args.output, json.loads(MANIFEST.read_text())['offline_checks'])
        finally:
            faulthandler.cancel_dump_traceback_later()
    if args.child:
        return child(args.child, args.output)
    if args.preflight:
        return preflight(args.preflight)
    args.output = args.output.resolve(); args.output.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'suite': args.suite, 'optimized': args.optimized}
    try:
        data = json.loads(MANIFEST.read_text())
        coverage = audit(data); write_json(args.output / 'coverage.json', coverage)
        if args.audit:
            print(json.dumps(coverage, indent=2)); return 0
        if not args.suite or (args.optimized and args.suite not in ('python-unit', 'python-regression')):
            raise ValueError('Choose a suite; optimization is only for Python suites')
        if args.inside:
            return inside(args, data, report)
        # No sudo, sysctl change, privileged container, or host-network fallback.
        command = ['unshare', '--user', '--map-current-user', '--keep-caps', '--net', '--',
                   'sh', '-ec', 'ip link set lo up; exec setpriv --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all "$@"', 'ci',
                   '/usr/bin/python3', '-u', str(Path(__file__).resolve()), '--inside',
                   '--parent-netns', os.readlink('/proc/self/ns/net'), '--suite', args.suite,
                   '--output', str(args.output)] + (['--optimized'] if args.optimized else [])
        write_json(args.output / 'summary.json', report)
        budget = 120 if args.suite == 'offline-checks' else data['suites'][args.suite]['budget_seconds']
        completed = bounded(command, budget + 45, args.output / 'namespace.log', supervisor=True)
        code = 1 if completed['timeout'] else completed['returncode']
        if code:
            report = json.loads((args.output / 'summary.json').read_text())
            report.update(ok=False, isolation_or_suite_exit=code)
            write_json(args.output / 'summary.json', report)
        return code
    except BaseException:
        report['error'] = traceback.format_exc(); write_json(args.output / 'summary.json', report)
        traceback.print_exc(); return 1


if __name__ == '__main__':
    sys.exit(main())
