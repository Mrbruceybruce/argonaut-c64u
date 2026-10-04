"""R5 boundary and failure attribution; all transport contact is loopback."""
import ast
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import getpass
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as fixtures
from test_core import INFO, FakeCredentials
from c64u_browser.__main__ import main
from c64u_browser.api import UltimateClient, BrowserError, ConnectionFailure
from c64u_browser.core import ArgonautCore, CoreError
from c64u_browser.hardware_checks import run_core_hardware_checks
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.profiles import Preferences, Profile
from c64u_browser.scheduler import JobBinding
from c64u_browser.transfers import download


class HeadlessReadsTests(unittest.TestCase):
    core = fixtures.ReadMigrationTests.core

    def setup_core(self, server):
        core, profile = self.core(server)
        core.preferences.profiles = [profile]
        core.preferences.selected_id = profile.id
        core.preferences.save()
        return core, profile

    def invoke(self, args, core=None):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['c64u_browser'] + args), redirect_stdout(out), redirect_stderr(err), \
             patch('c64u_browser.headless_reads_cli.ArgonautCore', return_value=core), \
             patch('ftplib.FTP', side_effect=AssertionError('raw FTP forbidden')):
            try:code = main()
            except SystemExit as exc:code = exc.code
        return code, out.getvalue(), err.getvalue()

    def target(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        return Path(temp.name) / 'result'

    def test_no_browse_commits_normal_binding_without_ftp(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile = self.setup_core(server)
            with patch.object(core._ftp_manager, 'lease', side_effect=AssertionError('eager FTP')):
                result = core.connect(profile, initial_browse=False, require_bound=True)
            self.assertEqual(('', ()), (result.remote_path, result.entries))
            session = core.device_session()
            self.assertEqual(session.session_id, core._client._ftp_reads.binding.core_session_id)
            self.assertEqual(0, server.connections)
            snapshot = core.list_directory('/USB1').wait(5)
            self.assertEqual('succeeded', snapshot.state)
            self.assertEqual('/USB1', snapshot.result[0])
            self.assertEqual(session, core.device_session())
            self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))

    def test_unbrowsed_folder_conflict_is_pre_network(self):
        core = ArgonautCore();self.addCleanup(core.close)
        with patch.object(core, '_new_client') as factory, self.assertRaises(CoreError):
            core.connect(Profile.new('x', 'fixture.invalid'), initial_browse=False, remote_folder='/')
        factory.assert_not_called()

    def test_ls_default_path_order_and_one_lease(self):
        rows = b'type=file;size=2; z\r\ntype=dir; folder\r\ntype=file;size=1; A\r\n'
        with FakeC64UFtp(directories={b'/':rows}) as server:
            core, profile = self.setup_core(server)
            code, out, err = self.invoke(['--profile-id', profile.id, 'ls'], core)
            self.assertEqual((0, ''), (code, err))
            result = json.loads(out)
            self.assertEqual('/', result['path'])
            self.assertEqual(['folder', 'A', 'z'], [e['name'] for e in result['entries']])
            self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))

    def test_get_exact_empty_and_binary_bytes_hash_and_cleanup(self):
        for data in (b'', bytes(range(256))*513):
            with self.subTest(length=len(data)), FakeC64UFtp(files={b'/USB1/a':data}) as server:
                core, profile = self.setup_core(server)
                target = self.target()
                code, out, err = self.invoke(['--profile-id='+profile.id, 'get', '/USB1/a', str(target)], core)
                self.assertEqual(0, code, err)
                result = json.loads(out)
                self.assertEqual(data, target.read_bytes())
                self.assertEqual(len(data), result['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), result['sha256'])
                self.assertEqual([target], list(target.parent.iterdir()))
                self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))
                self.assertEqual([b'SIZE', b'RETR', b'SIZE'], [v for v in server.verbs if v in (b'SIZE', b'RETR')])

    def test_get_refuses_existing_without_acquiring_ftp(self):
        with FakeC64UFtp() as server:
            core, profile = self.setup_core(server)
            target = self.target();target.write_bytes(b'keep')
            code, out, _ = self.invoke(['--profile-id', profile.id, 'get', '/USB1/a', str(target)], core)
            self.assertEqual((1, ''), (code, out))
            self.assertEqual(b'keep', target.read_bytes())
            self.assertEqual(0, server.connections)

    def test_parser_authority_legacy_options_and_poisoned_values(self):
        secret = 'PRIVATE_PASSWORD_MARKER'
        cases = [['ls'], ['get', '/USB1/a', 'local'], ['--profile-id', 'x', '--profile-id', 'x', 'ls'],
                 ['--profile-id', 'x', 'ls', '/', 'extra'], ['--profile-id', 'x', 'get', '/USB1/a'],
                 ['--profile-id', 'x', 'get'], ['--password='+secret, 'ls'],
                 ['--unknown='+secret, 'ls'], ['--profile-id', '--', 'ls'], ['--p', secret, 'ls']]
        for command in ('ls', 'get'):
            operands = [command] + (['/USB1/a', 'local'] if command == 'get' else [])
            for option, value in (('--host', secret), ('--port', '21'), ('--timeout', '10'), ('--encoding', 'utf-8')):
                cases += [['--profile-id', 'x', option, value]+operands,
                          ['--profile-id=x', option+'='+value]+operands]
        for args in cases:
            with self.subTest(args=args):
                code, out, err = self.invoke(args)
                self.assertEqual((2, ''), (code, out))
                self.assertNotIn(secret, err)

    def test_option_aware_routing_values_abbreviations_delimiter_and_operands(self):
        # Option values and later operands never choose put-new's JSON route.
        for name in ('info', 'ls', 'get', 'browse', 'put-new'):
            for option in ('--profile-id', '--profile-i', '--host', '--hos', '--port', '--timeout', '--encoding'):
                for prefix in ([option, name], [option+'='+name]):
                    with self.subTest(prefix=prefix):
                        code, out, _ = self.invoke(prefix+['get', '/USB1/a'])
                        self.assertEqual((2, ''), (code, out))
        for args in (['--profile-id=x', '--', 'get', 'put-new'], ['ls', 'put-new'], ['get', 'a', 'put-new']):
            self.assertEqual((2, ''), self.invoke(args)[:2])
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile = self.setup_core(server)
            self.assertEqual(0, self.invoke(['--profile-i='+profile.id, '--', 'ls', '/USB1'], core)[0])

    def test_browse_absent_help_and_deliberate_exit_two(self):
        self.assertNotRegex(self.invoke(['--help'])[1], r'\bbrowse\b')
        for args in (['browse'], ['--host', 'fixture.invalid', 'browse'], ['--', 'browse']):
            code, out, _ = self.invoke(args)
            self.assertEqual((2, ''), (code, out))

    def test_unknown_unbound_ambiguous_corrupt_profiles_fail_before_ftp(self):
        for fault in ('unknown', 'unbound', 'ambiguous', 'corrupt'):
            with self.subTest(fault=fault), FakeC64UFtp() as server:
                core, profile = self.setup_core(server)
                selector = profile.id
                if fault == 'unknown':selector = 'absent'
                elif fault == 'unbound':
                    core.preferences.profiles = [replace(profile, device_id='', device_mac='')]
                    core.preferences.save()
                elif fault == 'ambiguous':
                    data = json.loads(core.preferences.path.read_text())
                    data['profiles'].append(data['profiles'][0])
                    core.preferences.path.write_text(json.dumps(data))
                else:core.preferences.path.write_text('{ broken')
                code, out, _ = self.invoke(['--profile-id', selector, 'ls'], core)
                self.assertEqual((1, ''), (code, out))
                self.assertEqual(0, server.connections)

    def test_identity_mismatch_prevents_reads_and_redacts_peer(self):
        with FakeC64UFtp() as server:
            core, profile = self.setup_core(server)
            core.preferences.profiles = [replace(profile, device_id='PRIVATE_WRONG_ID')]
            core.preferences.save()
            code, out, err = self.invoke(['--profile-id', profile.id, 'ls'], core)
            self.assertEqual((1, ''), (code, out))
            self.assertIn('identity', err)
            self.assertNotIn('PRIVATE_WRONG_ID', err)
            self.assertEqual(0, server.connections)

    def test_private_stored_empty_and_entered_password_no_implicit_prompt(self):
        for entered, stored in ((None, 'STORED_PRIVATE'), ('', 'STORED_PRIVATE'), ('ENTERED_PRIVATE', 'STORED_PRIVATE'), (None, '')):
            with self.subTest(entered=entered), FakeC64UFtp(directories=fixtures.ROOT) as server:
                core, profile = self.setup_core(server)
                core._credentials.set(profile.id, stored)
                args = ['--profile-id', profile.id, 'ls'] + ([] if entered is None else ['--password'])
                with patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value=entered) as prompt:
                    code, out, err = self.invoke(args, core)
                self.assertEqual(0, code, err)
                self.assertEqual(entered is not None, prompt.called)
                password = stored if entered in (None, '') else entered
                self.assertIn((b'PASS', password.encode()), server.commands)
                self.assertNotIn('PRIVATE', out+err)
                self.assertNotIn('PRIVATE', core.preferences.path.read_text())

    def test_private_prompt_refusal_eof_and_interrupt(self):
        for failure, expected in ((getpass.GetPassWarning('PRIVATE'), 1), (EOFError(), 130), (KeyboardInterrupt(), 130)):
            with self.subTest(failure=type(failure)), FakeC64UFtp() as server:
                core, profile = self.setup_core(server)
                with patch('c64u_browser.fresh_folder_cli.getpass.getpass', side_effect=failure):
                    code, out, err = self.invoke(['--profile-id', profile.id, '--password', 'ls'], core)
                self.assertEqual((expected, ''), (code, out))
                self.assertNotIn('PRIVATE', err)
                self.assertEqual(0, server.connections)

    def test_ftp_failure_releases_lease_and_rest_session_survives(self):
        for reply in (b'530 PRIVATE_PASSWORD_MARKER\r\n', b'550 PRIVATE_PASSWORD_MARKER\r\n'):
            with self.subTest(reply=reply), FakeC64UFtp(replies={b'MLSD': reply}) as server:
                core, profile = self.setup_core(server)
                core.connect(profile, initial_browse=False)
                session = core.device_session()
                result = core.list_directory('/').wait(5)
                self.assertEqual('failed', result.state)
                self.assertNotIn('PRIVATE', str(result))
                self.assertEqual(session, core.device_session())
                self.assertEqual(INFO['info'], core.check_health()['info'])
                self.assertEqual(0, core._ftp_manager.active_count)

    def test_queued_read_refuses_changed_session_without_replay(self):
        with FakeC64UFtp() as server:
            core, profile = self.setup_core(server)
            core.connect(profile, initial_browse=False)
            ready, release = threading.Event(), threading.Event()
            def hold(job):ready.set();release.wait(5)
            blocker = core.scheduler.submit(CoreJob('hold', hold), JobBinding.device(core.device_session()))
            self.assertTrue(ready.wait(2))
            job = core.list_directory('/')
            core.connect(profile, initial_browse=False)
            release.set();blocker.wait(5)
            result = job.wait(5)
            self.assertEqual(('failed', 'session'), (result.state, result.error.code))
            self.assertEqual(0, server.connections)

    def test_download_cancel_and_changed_session_clean_staging(self):
        for fault in ('cancel', 'session'):
            with self.subTest(fault=fault), FakeC64UFtp(files={b'/USB1/a':b'abc'*1000}) as server:
                core, profile = self.setup_core(server)
                core.connect(profile, initial_browse=False)
                target = self.target()
                def progress(count):
                    if fault == 'cancel':raise JobCancelled()
                    core.connect(profile, initial_browse=False)
                result = core.download('/USB1/a', target, progress).wait(5)
                self.assertEqual('cancelled' if fault == 'cancel' else 'failed', result.state)
                self.assertEqual([], list(target.parent.iterdir()))
                self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))

    def test_cli_cancel_drains_and_late_publication_stays_successful(self):
        from c64u_browser.fresh_folder_cli import drain as real_drain
        from c64u_browser.platform_support import publish_new
        from c64u_browser import headless_reads_cli
        for late in (False, True):
            with self.subTest(late=late), FakeC64UFtp(files={b'/USB1/a':b'abc'}) as server:
                core, profile = self.setup_core(server)
                target = self.target()
                if late:
                    def publish(source, destination):
                        publish_new(source, destination)
                        import signal
                        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
                    context = patch('c64u_browser.transfers.publish_new', side_effect=publish)
                else:
                    def drain(job, cancelled):
                        cancelled[0] = True
                        return real_drain(job, cancelled)
                    context = patch.object(headless_reads_cli, 'drain', side_effect=drain)
                with context:
                    code, out, err = self.invoke(['--profile-id',profile.id,'get','/USB1/a',str(target)], core)
                self.assertEqual(0 if late else 130, code, err)
                if late:
                    self.assertEqual(3, json.loads(out)['bytes'])
                    self.assertEqual(b'abc', target.read_bytes())
                else:
                    self.assertEqual('', out)
                    self.assertEqual([], list(target.parent.iterdir()))
                self.assertEqual(0, core._ftp_manager.active_count)

    def test_cli_cleanup_failure_withholds_success_and_preserves_published_file(self):
        with FakeC64UFtp(files={b'/USB1/a':b'abc'}) as server:
            core, profile = self.setup_core(server)
            target = self.target()
            original = core.close
            def close():original();raise OSError('PRIVATE_CLEANUP_DETAIL')
            with patch.object(core, 'close', side_effect=close):
                code, out, err = self.invoke(['--profile-id',profile.id,'get','/USB1/a',str(target)], core)
            self.assertEqual((1,''), (code,out))
            self.assertNotIn('PRIVATE', err)
            self.assertIn('inspect the local destination', err)
            self.assertEqual(b'abc', target.read_bytes())

    def test_cli_authentication_failure_has_safe_category_and_no_success_json(self):
        with FakeC64UFtp(replies={b'PASS':b'530 PRIVATE_PASSWORD_MARKER\r\n'}) as server:
            core, profile = self.setup_core(server)
            events = []
            core.add_listener(lambda event:events.append(str(event)))
            code, out, err = self.invoke(['--profile-id',profile.id,'ls'], core)
            self.assertEqual((1,''), (code,out))
            self.assertIn('authentication', err)
            self.assertNotIn('PRIVATE', err+str(events))
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_info_rest_only_success_failure_defaults_and_no_core(self):
        responses = {'version': {'version':'v1'}, 'info':{'product':'C64 Ultimate'}}
        for failure in (False, True):
            out, err = io.StringIO(), io.StringIO()
            with patch('sys.argv', ['c64u_browser', '--host', 'fixture.invalid', 'info', 'ls', 'get']), \
                 patch.object(UltimateClient, 'read_about', side_effect=ConnectionFailure('network', 'Unavailable') if failure else lambda route:responses[route]), \
                 patch('c64u_browser.core.ArgonautCore.connect', side_effect=AssertionError('Core')), \
                 patch('socket.socket', side_effect=AssertionError('network acquisition')), \
                 patch('ftplib.FTP', side_effect=AssertionError('FTP')), redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(1 if failure else 0, main())
            if failure:self.assertEqual('', out.getvalue())
            else:self.assertEqual(responses, json.loads(out.getvalue()))

    def test_retired_symbols_and_migrated_paths_have_no_raw_access(self):
        root = Path(__file__).resolve().parents[1]/'c64u_browser'
        self.assertFalse(hasattr(Profile, 'client'))
        self.assertFalse(hasattr(UltimateClient, '_list_directory'))
        for name in ('headless_reads_cli.py', 'test_lab_cli.py', 'hardware_checks.py'):
            tree = ast.parse((root/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, ('open_ftp', 'device_operations', '_client', '_ftp_reads'))
                if isinstance(node, ast.ImportFrom):self.assertNotEqual('ftplib', node.module)
        tree = ast.parse((root/'transfers.py').read_text())
        body = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_download')
        self.assertFalse(any(isinstance(n, ast.Name) and n.id == 'connect' for n in ast.walk(body)))
        with self.assertRaises(BrowserError):download(UltimateClient('fixture.invalid'), '/USB1/a', self.target())
        self.assertTrue(hasattr(__import__('c64u_browser.transfers', fromlist=['connect']), 'connect'))


class HardwareOwnershipTests(unittest.TestCase):
    def setup_core(self, server, *, mismatch=False, rest_failure=False, timeout=None):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        preferences = Preferences(base/'argonaut-development'/'config.json')
        profile = replace(Profile.new('fixture', '127.0.0.1', device_id='ABC123'), ftp_port=server.port)
        preferences.profiles = [profile];preferences.selected_id = profile.id;preferences.save()
        calls, clients = [], []
        def rest(method, path, payload=None):
            calls.append((path, threading.get_ident(), server.connections))
            if rest_failure:raise ConnectionFailure('network', 'PRIVATE_REST_DETAIL')
            if path == '/v1/info':return dict(INFO['info'], unique_id='OTHER_PRIVATE' if mismatch else 'ABC123')
            if path == '/v1/version':return dict(INFO['version'])
            if path == '/v1/drives':return {'drives':[{'a':{'enabled':True}}]}
            raise AssertionError(path)
        def factory(host, password, **kwargs):
            client = UltimateClient(host, password, **kwargs)
            client._request_json_impl = rest
            clients.append(client)
            return client
        core = ArgonautCore(preferences=preferences, client_factory=factory,
                            credentials=FakeCredentials(), network_timeout=timeout)
        self.addCleanup(core.close)
        return core, profile, base, calls, clients

    def run_report(self, core, profile):
        with patch('c64u_browser.network_identity.peer_mac', return_value=''), \
             patch('ftplib.FTP', side_effect=AssertionError('raw FTP')):
            return run_core_hardware_checks(core, profile, 'PRIVATE_PASSWORD')

    def test_hardware_success_synchronous_collector_and_lazy_ftp(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, _, calls, _ = self.setup_core(server)
            report = self.run_report(core, profile)
            self.assertEqual(['pass']*4, [c['status'] for c in report['checks']])
            self.assertEqual(['hardware.identity','hardware.drives','hardware.storage','hardware.version_stability'], [c['id'] for c in report['checks']])
            self.assertEqual(['/v1/version','/v1/info','/v1/drives','/v1/version'], [c[0] for c in calls])
            self.assertTrue(all(c[1] == threading.get_ident() for c in calls))
            self.assertEqual([0, 0, 0, 1], [c[2] for c in calls])
            self.assertTrue(report['checks'][2]['operations'])
            self.assertNotIn('PRIVATE', json.dumps(report))
            self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))

    def test_hardware_ftp_failure_is_storage_and_later_rest_runs(self):
        for verb, reply, kind in ((b'PASS', b'530 PRIVATE\r\n', 'authentication'),
                                  (b'MLSD', b'550 PRIVATE\r\n', 'ftp')):
            with self.subTest(verb=verb), FakeC64UFtp(replies={verb:reply}) as server:
                core, profile, _, calls, _ = self.setup_core(server)
                report = self.run_report(core, profile)
                self.assertEqual(['pass','pass','fail','pass'], [c['status'] for c in report['checks']])
                self.assertEqual(kind, report['checks'][2]['error_kind'])
                self.assertEqual('fail', report['status'])
                self.assertEqual('/v1/version', calls[-1][0])
                self.assertNotIn('PRIVATE', json.dumps(report))
                self.assertEqual(0, core._ftp_manager.active_count)
                self.assertTrue(core.device_session().session_id)

    def test_hardware_refused_ftp_identity_passes_and_cli_exit_history(self):
        from c64u_browser.test_lab_cli import main as lab
        from c64u_browser.test_lab_history import TestLabHistory
        import os
        # A bound but non-listening loopback socket reliably refuses connections.
        with socket.socket() as closed, FakeC64UFtp() as server:
            closed.bind(('127.0.0.1', 0))
            core, profile, base, _, _ = self.setup_core(server, timeout=2)
            profile.ftp_port = closed.getsockname()[1];core.preferences.save()
            output, errors = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}), \
                 patch('c64u_browser.test_lab_cli.config_base', return_value=base), \
                 patch('c64u_browser.test_lab_cli.ArgonautCore', return_value=core), \
                 patch('c64u_browser.network_identity.peer_mac', return_value=''):
                code = lab(['--suite','hardware','--password-stdin','--timeout','2'],
                    stdin=io.StringIO('PRIVATE_PASSWORD\n'), stdout=output, stderr=errors)
            self.assertEqual(1, code)
            report = json.loads(output.getvalue())
            self.assertEqual(['pass','pass','fail','pass'], [c['status'] for c in report['checks']])
            self.assertEqual('network', report['checks'][2]['error_kind'])
            self.assertTrue(report['history_saved'])
            history = TestLabHistory(core.preferences.path, profile.id).latest('hardware')
            self.assertNotIn('PRIVATE', json.dumps(history)+output.getvalue()+errors.getvalue())
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_hardware_rest_identity_failures_remain_identity_and_no_ftp(self):
        for mismatch in (True, False):
            with self.subTest(mismatch=mismatch), FakeC64UFtp() as server:
                core, profile, _, _, _ = self.setup_core(server, mismatch=mismatch, rest_failure=not mismatch)
                report = self.run_report(core, profile)
                self.assertEqual(['fail','skip','skip','skip'], [c['status'] for c in report['checks']])
                self.assertEqual('identity' if mismatch else 'network', report['checks'][0]['error_kind'])
                self.assertEqual(['identity_prerequisite']*3, [c['error_kind'] for c in report['checks'][1:]])
                self.assertNotIn('PRIVATE', json.dumps(report))
                self.assertEqual(0, server.connections)

    def test_hardware_missing_unbound_profile_skips_without_network(self):
        with FakeC64UFtp() as server:
            core, profile, _, _, _ = self.setup_core(server)
            for p, kind in ((None,'not_connected'), (replace(profile, device_id=''),'identity_unbound')):
                with patch.object(core, 'connect', side_effect=AssertionError('connect')):
                    report = self.run_report(core, p)
                self.assertEqual(['skip']*4, [c['status'] for c in report['checks']])
                self.assertEqual(kind, report['checks'][0]['error_kind'])

    def test_timeout_sets_rest_and_all_ftp_limits_while_omission_preserves_defaults(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, _, _, clients = self.setup_core(server, timeout=3)
            self.assertEqual('pass', self.run_report(core, profile)['status'])
            self.assertEqual(3, clients[0].timeout)
            policy = core._ftp_manager._policy
            self.assertEqual([3]*5, [getattr(policy,k) for k in ('control_connect','control_reply','data_connect','data_idle','final_reply')])
            default = ArgonautCore();self.addCleanup(default.close)
            self.assertEqual(4, default._ftp_manager._policy.data_connect)

    def test_diagnostic_storage_waits_for_same_fifo_lane_and_rechecks_session(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, _, _, _ = self.setup_core(server)
            with patch('c64u_browser.network_identity.peer_mac', return_value=''):
                core.connect(profile, initial_browse=False)
            session = core.device_session()
            entered, release, submitted = threading.Event(), threading.Event(), threading.Event()
            def hold(job):entered.set();release.wait(5)
            blocker = core.scheduler.submit(CoreJob('hold', hold), JobBinding.device(session))
            self.assertTrue(entered.wait(2))
            errors = []
            original = core.scheduler.submit
            def submit(job, binding):
                result = original(job, binding)
                if job.operation == 'diagnostic.reservation':submitted.set()
                return result
            def diagnostic():
                try:core.diagnostic_listing(session)
                except Exception as exc:errors.append(exc)
            with patch.object(core.scheduler, 'submit', side_effect=submit):
                thread = threading.Thread(target=diagnostic);thread.start()
                self.assertTrue(submitted.wait(2))
                self.assertEqual(0, server.connections)
                with patch('c64u_browser.network_identity.peer_mac', return_value=''):
                    core.connect(profile, initial_browse=False)
                release.set();blocker.wait(5);thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(1, len(errors))
            self.assertEqual('session', errors[0].code)
            self.assertEqual(0, server.connections)

    def test_diagnostic_session_error_uses_kind_and_reservation_releases_after_failure(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, _, _, _ = self.setup_core(server)
            with patch.object(core, 'diagnostic_listing', side_effect=CoreError('session', 'PRIVATE')):
                report = self.run_report(core, profile)
            self.assertEqual(['pass','pass','fail','pass'], [c['status'] for c in report['checks']])
            self.assertEqual('session', report['checks'][2]['error_kind'])
            self.assertNotIn('PRIVATE', json.dumps(report))
            with self.assertRaises(RuntimeError):
                with core.scheduler.inline(JobBinding.device(core.device_session())):
                    raise RuntimeError('collector failure')
            result = core.list_directory('/').wait(5)
            self.assertEqual('succeeded', result.state)
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_cancelled_diagnostic_reservation_never_executes_unserialized_read(self):
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, _, _, _ = self.setup_core(server)
            with patch('c64u_browser.network_identity.peer_mac', return_value=''):
                core.connect(profile, initial_browse=False)
            entered, release, submitted = threading.Event(), threading.Event(), threading.Event()
            def hold(job):entered.set();release.wait(5)
            binding = JobBinding.device(core.device_session())
            blocker = core.scheduler.submit(CoreJob('hold', hold), binding)
            self.assertTrue(entered.wait(2))
            original = core.scheduler.submit
            def submit(job, binding):
                result = original(job, binding)
                if job.operation == 'diagnostic.reservation':
                    job.request_cancel();submitted.set()
                return result
            errors = []
            def diagnostic():
                try:core.diagnostic_listing(core.device_session())
                except Exception as exc:errors.append(exc)
            with patch.object(core.scheduler, 'submit', side_effect=submit):
                thread = threading.Thread(target=diagnostic);thread.start()
                self.assertTrue(submitted.wait(2))
                release.set();blocker.wait(5);thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(1, len(errors))
            self.assertIsInstance(errors[0], JobCancelled)
            self.assertEqual(0, server.connections)
            self.assertEqual('succeeded', core.list_directory('/').wait(5).state)

    def test_fleet_uses_same_managed_runner_and_closes_each_core(self):
        from c64u_browser.test_lab_fleet import main as fleet
        import os
        with FakeC64UFtp(directories=fixtures.ROOT) as server:
            core, profile, base, _, _ = self.setup_core(server)
            output = io.StringIO()
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}), \
                 patch('c64u_browser.test_lab_fleet.config_base', return_value=base), \
                 patch('c64u_browser.test_lab_cli.config_base', return_value=base), \
                 patch('c64u_browser.test_lab_cli.ArgonautCore', return_value=core), \
                 patch.object(core, 'close', wraps=core.close) as close, \
                 patch('c64u_browser.network_identity.peer_mac', return_value=''):
                code = fleet([], stdout=output)
            self.assertEqual(0, code)
            self.assertEqual('pass', json.loads(output.getvalue())['status'])
            self.assertEqual((1, 0), (server.connections, core._ftp_manager.active_count))
            close.assert_called_once()
