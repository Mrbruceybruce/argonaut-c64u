"""Bounded explicit CI suites. No discovery and no network-isolation fallback."""
import ctypes
import argparse
import ast
import faulthandler
import importlib
import ipaddress
import pwd
import grp
import shutil
import uuid
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
            output.write(json.dumps(command) + '\n')
            output.flush()
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


CAPS = ('CapEff', 'CapPrm', 'CapInh', 'CapBnd', 'CapAmb')


def security_evidence():
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    return {'current': os.readlink('/proc/self/ns/net'), 'uid': os.getuid(),
            'euid': os.geteuid(), 'gid': os.getgid(), 'egid': os.getegid(),
            'capabilities': {k: status[k].strip() for k in CAPS + ('NoNewPrivs',)}}


def validate_security(evidence, uid, gid):
    if (uid == 0 or gid == 0 or evidence['uid'] != uid or evidence['euid'] != uid
            or evidence['gid'] != gid or evidence['egid'] != gid
            or any(int(evidence['capabilities'][k], 16) for k in CAPS)
            or evidence['capabilities']['NoNewPrivs'] != '1'):
        raise RuntimeError('Tests must run with expected nonroot UID/GID and zero capabilities')


def validate_network(links, routes):
    if (not isinstance(links, list) or len(links) != 1 or links[0]['ifname'] != 'lo'
            or 'UP' not in links[0]['flags']):
        raise RuntimeError('Expected only active loopback')
    addresses = links[0]['addr_info']
    if not addresses or any(not ipaddress.ip_address(a['local']).is_loopback for a in addresses):
        raise RuntimeError('Non-loopback or missing address')
    for family, rows in routes.items():
        if not isinstance(rows, list):
            raise ValueError('Malformed route evidence')
        allowed = ipaddress.ip_network('127.0.0.0/8' if family == '-4' else '::1/128')
        for route in rows:
            destination = ipaddress.ip_network(route['dst'], strict=False)
            if (destination.version != allowed.version or not destination.subnet_of(allowed)
                    or route.get('dev') != 'lo' or 'gateway' in route or 'multipath' in route):
                raise RuntimeError('Non-loopback route')


def verify_network(parent, uid=None, gid=None):
    evidence = security_evidence()
    if evidence['current'] == parent or not parent:
        raise RuntimeError('Network namespace did not change')
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    validate_security(evidence, uid, gid)
    links = json.loads(subprocess.check_output(['ip', '-j', 'address'], timeout=5))
    routes = {family: json.loads(subprocess.check_output(
        ['ip', family, '-j', 'route', 'show', 'table', 'all'], timeout=5)) for family in ('-4', '-6')}
    validate_network(links, routes)
    lookups = {}
    for family, address in (('-4', '192.0.2.1'), ('-6', '2001:db8::1')):
        lookup = subprocess.run(['ip', family, 'route', 'get', address],
                                capture_output=True, text=True, timeout=5)
        # This is a kernel route lookup, never a packet. Reject command errors too.
        if lookup.returncode != 2 or 'Network is unreachable' not in lookup.stderr:
            raise RuntimeError('External route lookup was not unreachable: ' + address)
        lookups[address] = lookup.stderr.strip()
    child = json.loads(subprocess.check_output(
        ['/usr/bin/python3', '-I', '-c',
         'import runpy,json; r=runpy.run_path(' + repr(str(Path(__file__).resolve())) +
         '); print(json.dumps(r["security_evidence"]()))'], timeout=5))
    validate_security(child, uid, gid)
    if child['current'] != evidence['current']:
        raise RuntimeError('Child network namespace changed')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(2)
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            peer, _ = listener.accept()
            with peer:
                client.sendall(b'ci'); peer.settimeout(2)
                if peer.recv(2) != b'ci':
                    raise RuntimeError('Loopback probe failed')
    return dict(evidence, parent=parent, links=links, routes=routes, child=child,
                route_lookups=lookups, loopback_tcp='pass', external_probe='none')


def tracked_snapshot(destination, root=ROOT):
    """Copy current tracked regular files, never .git, untracked files or symlinks."""
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    for name in filter(None, names):
        relative = Path(name)
        source = root / relative
        if (relative.is_absolute() or '..' in relative.parts or '.git' in relative.parts
                or any(part.is_symlink() for part in (source, *source.parents))
                or not source.is_file()):
            raise ValueError('Unsafe tracked snapshot entry: ' + name)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)


def docker_call(arguments, output, timeout=20):
    old = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    pending = None
    interruptible = False

    def interrupted(signum, frame):
        nonlocal pending, interruptible
        pending = pending or signum
        if interruptible:
            # Disarm before raising: even a signal during exception handling is deferred.
            interruptible = False
            raise InterruptedError('Docker client interrupted: ' + str(pending))

    try:
        for sig, handler in old.items():
            # Container cleanup deliberately ignores cancellation; preserve that policy.
            if handler != signal.SIG_IGN:
                signal.signal(sig, interrupted)
        with (output / 'docker-control.log').open('a') as log:
            log.write(json.dumps(['docker', *arguments]) + '\n')
            log.flush()
            # Defer signals until Popen returns and ownership of the child is recorded.
            proc = subprocess.Popen(['docker', *arguments], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            try:
                try:
                    interruptible = True
                    if pending is not None:
                        interrupted(pending, None)
                    stdout, stderr = proc.communicate(timeout=timeout)
                finally:
                    interruptible = False
            except BaseException as exc:
                proc.kill()
                stdout, stderr = proc.communicate()
                log.write(stdout + stderr + '\n' + repr(exc) + '\n')
                log.flush()
                raise
            log.write(stdout + stderr + '\n')
        # Log close/flush is also protected. A late cancellation must still fail.
        if pending is not None:
            raise InterruptedError('Docker client interrupted: ' + str(pending))
        if proc.returncode:
            raise RuntimeError('Docker command failed: ' + arguments[0])
        return stdout.strip()
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def cleanup_container(name, output, creation_unresolved=False):
    """Attempt all cleanup stages; absence must be proved by a successful daemon query."""
    errors = []
    if creation_unresolved:
        # No finite series of empty listings proves an interrupted create completed.
        # Reconcile late registration, but never promote this uncertainty to success.
        errors.append('Creation unresolved; daemon-side creation may still complete')
        for attempt in range(10):
            try:
                if docker_call(['ps', '-aq', '--filter', 'name=^/' + name + '$'], output):
                    docker_call(['rm', '--force', name], output)
            except Exception as exc:
                errors.append(str(exc))
            time.sleep(1)
    for arguments in (['stop', '--time', '10', name], ['rm', '--force', name]):
        present = True  # A failed query must not suppress the removal attempt.
        try:
            # A failed create may never have made a container. Query before each action.
            present = docker_call(['ps', '-aq', '--filter', 'name=^/' + name + '$'], output)
        except Exception as exc:
            errors.append(str(exc))
        if present:
            try:
                docker_call(arguments, output)
            except Exception as exc:
                errors.append(str(exc))
    try:
        if docker_call(['ps', '-aq', '--filter', 'name=^/' + name + '$'], output):
            errors.append('Container still exists')
    except Exception as exc:
        errors.append(str(exc))
    write_json(output / 'cleanup.json', {'name': name, 'ok': not errors, 'creation_unresolved': creation_unresolved, 'errors': errors})
    if errors:
        raise RuntimeError('Container cleanup failed: ' + '; '.join(errors))


def validate_runtime_ids(uid, gid):
    # Linux reserves (uid_t)-1; accept only nonroot numeric IDs, never text fields.
    if any(type(value) is not int or not 0 < value < 2**32 - 1 for value in (uid, gid)):
        raise ValueError('Docker requires valid nonroot UID/GID')


def write_container_identity(directory, uid, gid):
    """Generate private account databases; never copy host passwd/group entries."""
    validate_runtime_ids(uid, gid)
    directory.mkdir(mode=0o755)
    for name, content in {
        'passwd': f'root:x:0:0:root:/nonexistent:/usr/sbin/nologin\n'
                  f'argonaut-ci:x:{uid}:{gid}:CI:/nonexistent:/usr/sbin/nologin\n',
        'group': f'root:x:0:\nargonaut-ci:x:{gid}:\n',
    }.items():
        path = directory / name
        path.write_text(content)
        path.chmod(0o444)


def verify_account_identity(uid, gid, container=False):
    validate_runtime_ids(uid, gid)
    try:
        user, group = pwd.getpwuid(uid), grp.getgrgid(gid)
        if (user.pw_uid != uid or user.pw_gid != gid or group.gr_gid != gid
                or pwd.getpwnam(user.pw_name) != user
                or grp.getgrnam(group.gr_name) != group
                or (container and (user.pw_name != 'argonaut-ci' or group.gr_name != 'argonaut-ci'))):
            raise RuntimeError('Runtime passwd/group identity mismatch')
    except KeyError as exc:
        raise RuntimeError('Runtime UID/GID missing from passwd/group') from exc
    return {'uid': uid, 'gid': gid, 'user': user.pw_name, 'group': group.gr_name}


def verify_session_bus(Gio, GLib, uid):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    name = bus.get_unique_name()
    if bus.is_closed() or not name:
        raise RuntimeError('Private session D-Bus connection unavailable')
    reply = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                          'org.freedesktop.DBus', 'GetConnectionUnixUser',
                          GLib.Variant('(s)', (name,)), GLib.VariantType.new('(u)'),
                          Gio.DBusCallFlags.NONE, 5000, None)
    if reply.unpack() != (uid,):
        raise RuntimeError('Private session D-Bus UID mismatch')
    print('Session D-Bus authenticated UID', uid, flush=True)


def docker_suite(args, budget):
    uid, gid = os.getuid(), os.getgid()
    validate_runtime_ids(uid, gid)
    name = 'argonaut-ci-' + uuid.uuid4().hex
    output = args.output
    results = output / 'container-results'
    results.mkdir(mode=0o700)  # Never reuse writable suite results.
    write_json(output / 'container.json', {'name': name, 'uid': uid, 'gid': gid})
    with tempfile.TemporaryDirectory(prefix='argonaut-source-') as temporary:
        workspace = Path(temporary)
        workspace.chmod(0o755)
        snapshot = workspace / 'source'
        snapshot.mkdir(mode=0o755)
        identity = workspace / 'identity'
        write_container_identity(identity, uid, gid)
        tracked_snapshot(snapshot)
        command = ['create', '--name', name, '--label', 'argonaut.ci-job=' + os.environ.get('ARGONAUT_CI_JOB', name),
                   '--network', 'none', '--user', f'{uid}:{gid}', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges=true', '--init', '--pull', 'never',
                   '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,mode=1777',
                   '--mount', f'type=bind,src={snapshot},dst=/source,readonly',
                   '--mount', f'type=bind,src={results},dst=/results',
                   '--mount', f'type=bind,src={identity / "passwd"},dst=/etc/passwd,readonly',
                   '--mount', f'type=bind,src={identity / "group"},dst=/etc/group,readonly',
                   '--workdir', '/source',
                   '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'LANG=C.UTF-8',
                   args.docker_image, '/usr/bin/python3', '-u', '/source/tests/run_ci_tests.py',
                   '--inside', '--isolation', 'docker', '--parent-netns', os.readlink('/proc/self/ns/net'),
                   '--expected-uid', str(uid), '--expected-gid', str(gid),
                   '--suite', args.suite, '--output', '/results']
        if args.optimized:
            command.append('--optimized')
        completed = None
        creation_unresolved = False
        old = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        def interrupted(signum, frame):
            raise InterruptedError('Docker runner interrupted: ' + str(signum))
        try:
            for sig in old:
                signal.signal(sig, interrupted)
            image = json.loads(docker_call(['image', 'inspect', args.docker_image], output))
            write_json(output / 'image.json', image)
            # Use the recorded immutable image ID even if a tag changes subsequently.
            command[command.index(args.docker_image)] = image[0]['Id']
            creation_unresolved = True
            write_json(output / 'create-pending.json', {'name': name})
            cid = docker_call(command, output, timeout=30)
            if len(cid) != 64 or any(c not in '0123456789abcdef' for c in cid):
                raise RuntimeError('Malformed container ID')
            write_json(output / 'container.json', {'name': name, 'id': cid, 'uid': uid, 'gid': gid})
            (output / 'create-pending.json').unlink()
            creation_unresolved = False
            docker_call(['inspect', cid], output)
            completed = bounded(['docker', 'start', '--attach', cid], budget + 45,
                                output / 'docker.log')
        finally:
            for sig in old:
                signal.signal(sig, signal.SIG_IGN)
            try:
                cleanup_container(name, output, creation_unresolved=creation_unresolved)
            finally:
                for sig, handler in old.items():
                    signal.signal(sig, handler)
        summary = json.loads((results / 'summary.json').read_text())
        if completed['timeout'] or completed['returncode'] or summary.get('ok') is not True:
            return 1
        return 0


def preflight(kind):
    if kind == 'gtk-regression':
        print('Runtime identity', json.dumps(verify_account_identity(os.getuid(), os.getgid())), flush=True)
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
                     'audioresample', 'vorbisenc', 'webmmux',
                     'filesrc', 'matroskademux', 'filesink', 'vp8dec', 'vorbisdec', 'fakesink'):
            if Gst.ElementFactory.find(name) is None:
                raise RuntimeError('Missing GStreamer element: ' + name)
        GstPbutils.Discoverer.new(5 * Gst.SECOND)
    if kind == 'gtk-regression':
        from gi.repository import Gio, Gdk, GLib
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise RuntimeError('GTK display unavailable')
        verify_session_bus(Gio, GLib, os.getuid())
        import ctypes
        ctypes.CDLL('libXtst.so.6')
        window = Gtk.Window(); window.present(); window.destroy()
    return 0


def inside(args, data, report):
    out = args.output
    if args.isolation == 'docker':
        write_json(out / 'identity.json', verify_account_identity(args.expected_uid, args.expected_gid, container=True))
        shutil.copyfile('/usr/local/share/argonaut-ci/dependencies.txt', out / 'dependencies.txt')
    write_json(out / 'network.json', verify_network(args.parent_netns, args.expected_uid, args.expected_gid))
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
    parser.add_argument('--isolation', choices=['namespace', 'docker'], default='namespace')
    parser.add_argument('--docker-image', default='argonaut-ci:local')
    parser.add_argument('--expected-uid', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--expected-gid', type=int, help=argparse.SUPPRESS)
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
        if args.isolation == 'docker':
            budget = 120 if args.suite == 'offline-checks' else data['suites'][args.suite]['budget_seconds']
            code = docker_suite(args, budget)
            report.update(ok=code == 0, isolation='docker', isolation_or_suite_exit=code)
            write_json(args.output / 'summary.json', report)
            return code
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
