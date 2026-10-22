"""Synthetic contracts only: no Docker, package building/installing, GTK or devices."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import run
import verify

SHA = 'a' * 40
EPOCH = 1700000000


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as out:
        for name, kind, mode, uid, mtime, content in entries:
            member = tarfile.TarInfo(name)
            member.type, member.mode, member.uid, member.mtime = kind, mode, uid, mtime
            member.size = len(content) if kind == tarfile.REGTYPE else 0
            out.addfile(member, io.BytesIO(content))
    return stream.getvalue()


def entry(name, kind=tarfile.REGTYPE, mode=0o644, uid=0, mtime=EPOCH, content=b'hello'):
    return name, kind, mode, uid, mtime, content


def report():
    return {'schema': 1, 'suite': 'package', 'platform': 'linux', 'result': 'passed',
            'version': '1.10-dev2', 'build': SHA,
            'checks': [{'id': name, 'status': 'pass'} for name in verify.CONTRACT['self_test_ids']]}


class ArchiveTests(unittest.TestCase):
    def test_valid_tar(self):
        result = verify.tar_members(archive([entry('.', tarfile.DIRTYPE, 0o755), entry('file')]), EPOCH)
        self.assertEqual(result['file']['sha256'], verify.digest(b'hello'))

    def test_archive_rejections(self):
        for invalid in [entry('../escape'), entry('/absolute'), entry('a/../escape'),
                        entry('file', tarfile.SYMTYPE), entry('file', tarfile.LNKTYPE),
                        entry('file', tarfile.CHRTYPE), entry('file', uid=1000),
                        entry('file', mode=0o4755), entry('file', mode=0o666),
                        entry('file', mtime=EPOCH + 1)]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                verify.tar_members(archive([entry('.', tarfile.DIRTYPE, 0o755), invalid]), EPOCH)

    def test_duplicate_and_extra_directory(self):
        for entries in [[entry('file'), entry('file')],
                        [entry('extra', tarfile.DIRTYPE, 0o755), entry('file')]]:
            with self.assertRaises(ValueError):
                verify.tar_members(archive([entry('.', tarfile.DIRTYPE, 0o755), *entries]), EPOCH)

    def test_missing_parent_directory(self):
        with self.assertRaises(ValueError):
            verify.tar_members(archive([entry('dir/file')]), EPOCH)

    def test_ar_members(self):
        def member(name, data):
            header = f'{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n'.encode()
            return header + data + (b'\n' if len(data) % 2 else b'')
        valid = b'!<arch>\n' + member('debian-binary', b'2.0\n') + member('control.tar.xz', b'x') + member('data.tar.xz', b'y')
        self.assertEqual(len(verify.ar_members(valid)), 3)
        for bad in [b'', valid[:-1], valid + member('extra', b''),
                    valid.replace(b'data.tar.xz', b'evil.tar.xz'),
                    valid.replace(b'2.0\n', b'1.0\n')]:
            with self.assertRaises(ValueError):
                verify.ar_members(bad)

    def test_control_exact_identity(self):
        valid = '\n'.join(f'{k}: {v}' for k, v in verify.CONTRACT['control'].items()) + '\nInstalled-Size: 12\n'
        verify.check_control(valid)
        for key in ['Package', 'Version', 'Architecture', 'Depends', 'Recommends', 'Suggests']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify.check_control(valid.replace(verify.CONTRACT['control'][key], 'wrong'))
        for bad in [valid + 'Package: duplicate\n', valid + 'Pre-Depends: unknown\n',
                    valid.replace('Installed-Size: 12', 'Installed-Size: 0')]:
            with self.assertRaises(ValueError):
                verify.check_control(bad)

    def test_manifest_checksum_and_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / verify.CONTRACT['filename']; package.write_bytes(b'synthetic-deb')
            manifest = {'schema': 1, 'result': 'passed', 'source_sha': SHA,
                        'source_epoch': EPOCH, 'sha256': verify.digest(b'synthetic-deb'),
                        'control': {'control': {}}, 'payload': {'file': {}}}
            with patch.object(verify, 'read_archive', return_value=(manifest['control'], manifest['payload'])):
                verify.verify_package(package, manifest)
                for key, value in [('sha256', '0' * 64), ('source_sha', SHA + '-modified'),
                                   ('source_epoch', 0), ('payload', {}), ('result', 'failed')]:
                    bad = {**manifest, key: value}
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        verify.verify_package(package, bad)


    def test_final_archive_extra_control_payload_and_generated_content(self):
        control_text = '\n'.join(f'{k}: {v}' for k, v in verify.CONTRACT['control'].items()) + '\nInstalled-Size: 1\n'
        root = entry('.', tarfile.DIRTYPE, 0o755)
        good_control = archive([root, entry('control', content=control_text.encode())])
        good_data = archive([root, entry('file')])
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'test.deb'; package.write_bytes(b'synthetic-deb')
            contract = {**verify.CONTRACT, 'payload': ['file'], 'generated_sha256': {'file': verify.digest(b'hello')}}
            with patch.object(verify, 'CONTRACT', contract), patch.object(verify, 'ar_members'):
                for control, data, okay in [
                    (good_control, good_data, True),
                    (archive([root, entry('control', content=control_text.encode()), entry('postinst')]), good_data, False),
                    (good_control, archive([root, entry('file'), entry('extra')]), False),
                    (good_control, archive([root, entry('file', content=b'altered launcher')]), False)]:
                    with patch.object(verify.subprocess, 'check_output', side_effect=[control, data]):
                        if okay:
                            verify.read_archive(package, EPOCH)
                        else:
                            with self.assertRaises(ValueError):
                                verify.read_archive(package, EPOCH)


class ReportTests(unittest.TestCase):
    def test_complete_report(self):
        verify.check_report(report(), SHA)

    def test_identity_failures(self):
        for key, value in [('schema', 2), ('suite', 'unit'), ('result', 'failed'),
                           ('platform', 'win32'), ('version', '1.9'), ('build', SHA + '-modified'),
                           ('failure', {})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify.check_report({**report(), key: value}, SHA)

    def test_missing_duplicate_unknown_failed_zero_checks(self):
        original = report()
        for checks in [[], original['checks'][:-1], original['checks'] + [original['checks'][0]],
                       original['checks'] + [{'id': 'unknown', 'status': 'pass'}],
                       [{'id': c['id'], 'status': 'skip'} for c in original['checks']], None]:
            with self.subTest(checks=checks), self.assertRaises(ValueError):
                verify.check_report({**original, 'checks': checks}, SHA)

    def test_invalid_provenance(self):
        for sha, epoch in [('unknown', EPOCH), (SHA, 0), (SHA, True), (SHA, '1700000000')]:
            with self.assertRaises(ValueError):
                verify.identity(sha, epoch)


class InstalledCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.name = 'usr/share/doc/argonaut-c64u-development/BUILD-EVIDENCE.txt'
        self.path = self.root / self.name
        self.path.parent.mkdir(parents=True)
        self.content = b'synthetic build evidence\n'
        self.path.write_bytes(self.content)
        self.path.chmod(0o644)
        self.expected = {'sha256': verify.digest(self.content), 'mode': 0o644}
        self.manifest = {'payload': {self.name: self.expected}}
        paths = patch.object(run, 'Path', return_value=self.root)
        self.paths = paths.start()
        self.addCleanup(paths.stop)
        capture = patch.object(run, 'capture', return_value=(
            'install ok installed ' + verify.CONTRACT['version'] + ' all'))
        self.capture = capture.start()
        self.addCleanup(capture.stop)

    def reject(self, message):
        with self.assertRaises(ValueError) as error:
            run.installed_check(self.manifest)
        self.assertEqual(str(error.exception), message)
        self.capture.assert_not_called()

    def test_valid_payload_and_identity(self):
        run.installed_check(self.manifest)
        self.paths.assert_called_once_with('/')
        self.capture.assert_called_once_with([
            'dpkg-query', '-W', '-f=${Status} ${Version} ${Architecture}',
            verify.CONTRACT['control']['Package']])

    def test_missing(self):
        self.path.unlink()
        self.reject('installed missing: ' + self.name)

    def test_symlink_with_matching_bytes_and_mode(self):
        target = self.root / 'target'
        self.path.rename(target)
        self.path.symlink_to(target)
        self.reject('installed symlink: ' + self.name)

    def test_dangling_symlink(self):
        self.path.unlink()
        self.path.symlink_to(self.root / 'absent')
        self.reject('installed symlink: ' + self.name)

    def test_directory(self):
        self.path.unlink()
        self.path.mkdir()
        self.reject('installed not a regular file: ' + self.name)

    def test_sha256_mismatch(self):
        self.path.write_bytes(b'changed evidence\n')
        self.reject(f"installed SHA-256 mismatch: {self.name}: "
                    f"expected {self.expected['sha256']}, actual {verify.digest(self.path.read_bytes())}")

    def test_mode_mismatch_including_special_bits(self):
        for mode in (0o600, 0o755, 0o4644):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(mode)
                self.reject(f'installed mode mismatch: {self.name}: expected 0o0644, actual {mode:#06o}')

    def test_later_payload_entry_is_checked(self):
        name = 'usr/share/argonaut-development/later.py'
        self.manifest['payload'][name] = dict(self.expected)
        self.reject('installed missing: ' + name)

    def test_invalid_identity_still_fails(self):
        for status in ('', 'install ok installed wrong all',
                       'install ok installed ' + verify.CONTRACT['version'] + ' amd64'):
            with self.subTest(status=status):
                self.capture.return_value = status
                with self.assertRaisesRegex(ValueError, '^installed identity$'):
                    run.installed_check(self.manifest)


class OrchestrationTests(unittest.TestCase):
    def test_timeout_and_partial_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'child.log'
            with self.assertRaises(subprocess.TimeoutExpired):
                run.command([sys.executable, '-u', '-c', 'import time; print("started"); time.sleep(30)'], log, 0.2)
            self.assertIn('started', log.read_text())

    def test_failed_child(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run.command([sys.executable, '-c', 'raise SystemExit(2)'], Path(directory) / 'log')

    def test_container_isolation_flags(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'command') as command, \
                patch.object(run, 'capture', return_value=json.dumps([{'State': {'ExitCode': 0, 'OOMKilled': False, 'Running': False, 'Restarting': False, 'Status': 'exited'}}])):
            runner = run.Docker(Path(directory), 'synthetic')
            runner.container('test', 'sha256:test', 'smoke-child', [])
            args = command.call_args_list[0].args[0]
            for flag in ['--read-only', '--network', '--cap-drop', '--security-opt',
                         '--memory', '--memory-swap', '--pids-limit', '--cpus', '--init']:
                self.assertIn(flag, args)
            self.assertEqual(args[args.index('--network') + 1], 'none')
            self.assertEqual(args[args.index('--cap-drop') + 1], 'ALL')
            self.assertNotIn('--privileged', args)
            self.assertNotIn('--cap-add', args)
            self.assertFalse(list(Path(directory).glob('*.pending')))

    def test_failed_creation_retains_pending_and_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'command', side_effect=RuntimeError('create failure')):
            runner = run.Docker(Path(directory), 'synthetic')
            with self.assertRaises(RuntimeError):
                runner.container('test', 'image', 'smoke-child', [])
            self.assertTrue(list(Path(directory).glob('*.pending')))
            with patch.object(run, 'capture', return_value=''), patch.object(run.time, 'sleep'), self.assertRaises(ValueError):
                runner.cleanup()
            self.assertTrue(json.loads((Path(directory) / 'cleanup.json').read_text())['unresolved_creation'])

    def test_cleanup_success_and_remaining_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = run.Docker(Path(directory), 'synthetic')
            with patch.object(run, 'capture', return_value=''):
                runner.cleanup()
            with patch.object(run, 'capture', side_effect=['', 'container', '', '', '', '']), self.assertRaises(ValueError):
                runner.cleanup()

    def test_cleanup_removal_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'capture', side_effect=['id', '', '', '', '', '']), \
                patch.object(run, 'command', side_effect=RuntimeError('remove failed')):
            with self.assertRaises(ValueError):
                run.Docker(Path(directory), 'synthetic').cleanup()

    def test_container_oom_or_nonzero_rejected(self):
        for state in [{'ExitCode': 1, 'OOMKilled': False}, {'ExitCode': 0, 'OOMKilled': True}]:
            with tempfile.TemporaryDirectory() as directory, patch.object(run, 'command'), \
                    patch.object(run, 'capture', return_value=json.dumps([{'State': {**state, 'Running': False, 'Restarting': False, 'Status': 'exited'}}])), self.assertRaises(ValueError):
                run.Docker(Path(directory), 'synthetic').container('test', 'image', 'smoke-child', [])


    def test_snapshot_uses_immutable_archive_and_explicit_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; source.mkdir()
            def export(args, stdout, **kwargs):
                self.assertEqual(args[-4:], ['tar.umask=0022', 'archive', '--format=tar', SHA])
                stdout.write(archive([entry('tracked.txt')]))
            with patch.object(run, 'capture', side_effect=[SHA, '', str(EPOCH), '']), \
                    patch.object(run.subprocess, 'run', side_effect=export):
                evidence = run.snapshot(root, source, root, SHA)
            self.assertEqual((source / 'tracked.txt').stat().st_mode & 0o777, 0o644)
            self.assertEqual(evidence['source_sha'], SHA)
            self.assertEqual(list(source.iterdir()), [source / 'tracked.txt'])

    def test_snapshot_rejects_wrong_head_and_dirty_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for outputs in [['b' * 40], [SHA, 'tracked-change']]:
                with patch.object(run, 'capture', side_effect=outputs), self.assertRaises(ValueError):
                    run.snapshot(root, root / 'source', root, SHA)

    def test_missing_or_malformed_report_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            with self.assertRaises(FileNotFoundError):
                verify.check_report(json.loads(path.read_text()), SHA)
            path.write_text('{partial')
            with self.assertRaises(json.JSONDecodeError):
                verify.check_report(json.loads(path.read_text()), SHA)

    def test_interruption_cleans_child(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run.subprocess, 'Popen') as popen, \
                patch.object(run.os, 'killpg') as kill:
            process = popen.return_value
            process.pid = 12345
            process.wait.side_effect = [InterruptedError('synthetic signal'), 0, 0]
            with self.assertRaises(InterruptedError):
                run.command(['synthetic-child'], Path(directory) / 'log')
            self.assertEqual(kill.call_count, 2)


class CorrectionTests(unittest.TestCase):
    def test_image_receives_actual_host_ids(self):
        base = [{'RepoDigests': ['ubuntu@sha256:' + 'a' * 64]}]
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'command') as command, \
                patch.object(run, 'capture', side_effect=[json.dumps(base), '[{"Id": "image"}]']), \
                patch.object(run.os, 'getuid', return_value=1001), patch.object(run.os, 'getgid', return_value=1002):
            run.Docker(Path(directory), 'synthetic').image('runtime')
            args = command.call_args_list[1].args[0]
            self.assertIn('RUNTIME_UID=1001', args)
            self.assertIn('RUNTIME_GID=1002', args)

    def test_timeout_stops_daemon_and_preserves_error_and_evidence(self):
        active = json.dumps([{'State': {'Running': True, 'Restarting': False, 'Status': 'running'}}])
        stopped = json.dumps([{'State': {'Running': False, 'Restarting': False, 'Status': 'exited'}}])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); runner = run.Docker(out, 'synthetic')
            def command(args, *unused, **kwargs):
                if args[1] == 'start':
                    raise subprocess.TimeoutExpired(args, 300)
                if args[1] == 'stop':
                    raise subprocess.TimeoutExpired(args, 20)
            with patch.object(run, 'command', side_effect=command) as commands, \
                    patch.object(run, 'capture', side_effect=[active, active, stopped]), \
                    self.assertRaises(subprocess.TimeoutExpired):
                runner.container('runtime', 'image', 'smoke-child', [])
            self.assertTrue(runner.termination_verified)
            evidence = json.loads((out / 'runtime-termination.json').read_text())
            self.assertTrue(evidence['stopped']); self.assertTrue(evidence['errors'])
            self.assertEqual([c.args[0][1] for c in commands.call_args_list], ['create', 'start', 'stop', 'kill'])
            self.assertTrue((out / 'runtime-final.json').exists())

    def test_unknown_or_live_daemon_state_blocks_removal(self):
        for result, primary_type in [(json.dumps([{'State': {'Running': True}}]), KeyError),
                                     ('[]', IndexError)]:
            with tempfile.TemporaryDirectory() as directory, patch.object(run, 'command') as commands, \
                    patch.object(run, 'capture', return_value=result):
                out = Path(directory); runner = run.Docker(out, 'synthetic')
                with self.assertRaises(primary_type):
                    runner.smoke_and_remove('image', [])
                self.assertEqual(runner.secondary_errors[0]['step'], 'runtime-termination')
                self.assertIn('termination unverified', runner.secondary_errors[0]['message'])
                self.assertFalse(runner.termination_verified)
                self.assertEqual(json.loads((out / 'removal.json').read_text())['result'], 'skipped')
                self.assertEqual(sum(c.args[0][1] == 'create' for c in commands.call_args_list), 1)
                self.assertFalse(json.loads((out / 'runtime-termination.json').read_text())['stopped'])

    def test_failed_smoke_with_verified_stop_runs_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = run.Docker(Path(directory), 'synthetic')
            def container(suffix, *args, **kwargs):
                if suffix == 'runtime':
                    runner.termination_verified = True
                    raise ValueError('smoke failure')
            with patch.object(runner, 'container', side_effect=container) as call, self.assertRaisesRegex(ValueError, 'smoke failure'):
                runner.smoke_and_remove('image', [])
            self.assertEqual([c.args[0] for c in call.call_args_list], ['runtime', 'remove'])

    def test_cleanup_inspection_failure_still_persists_errors(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(run, 'capture', side_effect=RuntimeError('daemon unavailable')):
            out = Path(directory)
            with self.assertRaises(ValueError):
                run.Docker(out, 'synthetic').cleanup()
            evidence = json.loads((out / 'cleanup.json').read_text())
            self.assertEqual(evidence['remaining'], 'unverified')
            self.assertTrue(evidence['errors'])

    def test_preflight_incremental_success_and_failures(self):
        for failure in [None, 'identity', 'typelibs', 'dbus', 'gtk', 'factories']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                gi = MagicMock(__version__='synthetic')
                modules = {name: MagicMock() for name in ['Gio', 'GLib', 'Gtk', 'Gst', 'GstPbutils', 'Secret']}
                glib, gtk, gst, gio = (modules[n] for n in ['GLib', 'Gtk', 'Gst', 'Gio'])
                glib.MAJOR_VERSION, glib.MINOR_VERSION, glib.MICRO_VERSION = 2, 80, 0
                gtk.get_major_version.return_value = 4
                gtk.get_minor_version.return_value = 14
                gtk.get_micro_version.return_value = 0
                gtk.init_check.return_value = failure != 'gtk'
                gst.version_string.return_value = 'synthetic Gst'
                gst.ElementFactory.find.side_effect = lambda name: None if failure == 'factories' else object()
                bus = gio.bus_get_sync.return_value
                bus.get_unique_name.return_value = ':1.0'
                bus.call_sync.return_value.unpack.return_value = (999 if failure == 'dbus' else 1001,)
                def imports(name):
                    if name == 'gi': return gi
                    short = name.rsplit('.', 1)[1]
                    if failure == 'typelibs' and short == 'GstPbutils': raise ImportError('missing GstPbutils')
                    return modules[short]
                user = SimpleNamespace(pw_name='runtime', pw_uid=1001, pw_gid=1002)
                group = SimpleNamespace(gr_name='runtime', gr_gid=1002)
                with patch.object(run.importlib, 'import_module', side_effect=imports), \
                        patch.object(run.os, 'getuid', return_value=1001), patch.object(run.os, 'geteuid', return_value=1001), \
                        patch.object(run.os, 'getgid', return_value=1002), patch.object(run.os, 'getegid', return_value=1002), \
                        patch.object(run.pwd, 'getpwuid', side_effect=KeyError('missing UID') if failure == 'identity' else None, return_value=user), \
                        patch.object(run.pwd, 'getpwnam', return_value=user), \
                        patch.object(run.grp, 'getgrgid', return_value=group), patch.object(run.grp, 'getgrnam', return_value=group):
                    if failure:
                        with self.assertRaises((ValueError, KeyError, ImportError)):
                            run.preflight(Path(directory))
                    else:
                        run.preflight(Path(directory))
                evidence = json.loads((Path(directory) / 'preflight.json').read_text())
                self.assertEqual(evidence['identity']['uid'], 1001)
                if failure:
                    self.assertEqual(evidence['errors'][-1]['step'], failure)
                else:
                    self.assertEqual(evidence['errors'], [])
                    self.assertEqual(evidence['dbus']['authenticated_uid'], 1001)
                if failure == 'typelibs': self.assertFalse(evidence['typelibs']['GstPbutils']['loaded'])
                if failure == 'gtk': self.assertFalse(evidence['gtk']['initialized'])
                if failure in (None, 'factories'):
                    self.assertEqual(set(evidence['factories']), set(verify.CONTRACT['media_factories']))
                    self.assertEqual(evidence['gstreamer'], 'synthetic Gst')


class StatusEvidenceTests(unittest.TestCase):
    def check_status(self, operation, primary, secondary_steps, cleanup_error=None):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            runner = run.Docker(out, 'synthetic')
            args = SimpleNamespace(output=out, job='synthetic', phase='build',
                                   source=out, sha=SHA)
            def image(target):
                (out / 'base-image.json').write_text('[{"RepoDigests": []}]')
                return 'synthetic-image'
            with patch.object(run, 'Docker', return_value=runner), \
                    patch.object(run.os, 'getuid', return_value=1001), \
                    patch.object(run, 'command'), patch.object(run, 'snapshot', return_value={}), \
                    patch.object(runner, 'image', side_effect=image), \
                    patch.object(runner, 'container', side_effect=lambda *a, **k: operation(runner)), \
                    patch.object(runner, 'cleanup', side_effect=cleanup_error):
                try:
                    run.host(args)
                except BaseException as error:
                    self.assertIs(error, primary)
                    frames = []
                    tb = error.__traceback__
                    while tb:
                        frames.append(tb.tb_frame.f_code.co_name)
                        tb = tb.tb_next
                    if cleanup_error is not primary:
                        self.assertIn('fail', frames)
                else:
                    self.fail('failure must propagate')
            status = json.loads((out / 'status.json').read_text())
            self.assertEqual(status['result'], 'failed')
            self.assertEqual(status['error'], type(primary).__name__ + ': ' + str(primary))
            self.assertEqual(status['primary_error']['type'], type(primary).__name__)
            self.assertEqual(status['primary_error']['message'], str(primary))
            self.assertIn(type(primary).__name__, status['primary_error']['traceback'])
            self.assertEqual([e['step'] for e in status['secondary_errors']], secondary_steps)
            for error in status['secondary_errors']:
                self.assertIn(error['message'], error['traceback'])
            return status

    def test_primary_failure_then_cleanup_failure(self):
        primary = ValueError('build failed')
        def fail(runner):
            raise primary
        self.check_status(fail, primary, ['cleanup'], RuntimeError('global cleanup failed'))

    def test_timeout_then_termination_and_cleanup_failure(self):
        primary = subprocess.TimeoutExpired(['docker', 'start'], 300)
        container = run.Docker.container
        def fail(runner):
            with patch.object(run, 'command', side_effect=[None, primary]), \
                    patch.object(runner, 'stop_and_verify', return_value=False):
                container(runner, 'build', 'image', 'build-child', [])
        status = self.check_status(fail, primary, ['build-termination', 'cleanup'],
                                   RuntimeError('global cleanup failed'))
        self.assertIn('termination unverified', status['secondary_errors'][0]['message'])

    def test_smoke_then_removal_and_cleanup_failure(self):
        primary = ValueError('smoke failed')
        def fail(runner):
            def container(suffix, *args, **kwargs):
                runner.termination_verified = True
                if suffix == 'runtime':
                    raise primary
                raise RuntimeError('removal failed')
            with patch.object(runner, 'container', side_effect=container):
                runner.smoke_and_remove('image', [])
        status = self.check_status(fail, primary, ['removal', 'cleanup'],
                                   RuntimeError('global cleanup failed'))
        self.assertEqual(status['secondary_errors'][0]['message'], 'removal failed')

    def test_cleanup_only_failure(self):
        primary = RuntimeError('cleanup alone failed')
        status = self.check_status(lambda runner: None, primary, [], primary)
        self.assertEqual(status['primary_error']['step'], 'cleanup')

    def test_removal_only_failure(self):
        primary = RuntimeError('removal alone failed')
        def fail(runner):
            def container(suffix, *args, **kwargs):
                runner.termination_verified = True
                if suffix == 'remove':
                    raise primary
            with patch.object(runner, 'container', side_effect=container):
                runner.smoke_and_remove('image', [])
        self.check_status(fail, primary, [])


if __name__ == '__main__':
    unittest.main()
