"""R2 production CLI tests: saved authority, private credentials, JSON and drains."""
from contextlib import redirect_stdout, redirect_stderr, nullcontext
from dataclasses import replace
import getpass
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings

import test_ftp_reads as reads
from test_fresh_folder import server
from c64u_browser.__main__ import main
from c64u_browser.api import BrowserError, ConnectionFailure, Entry
from c64u_browser.fresh_folder_cli import resolve_profile, private_password, drain
from c64u_browser.jobs import CoreJob
from c64u_browser.profiles import Profile


class FreshFolderCliTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core

    def setup_core(self, ftp):
        core, profile = self.core(ftp)
        core.preferences.profiles = [profile]; core.preferences.selected_id = profile.id
        source = core.preferences.path.parent/'source'; source.write_bytes(b'abc')
        return core, profile, source

    def invoke(self, argv, core=None):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['c64u_browser'] + argv), redirect_stdout(out), redirect_stderr(err):
            with patch('c64u_browser.fresh_folder_cli.ArgonautCore', return_value=core) as factory:
                with patch.object(core, 'load', return_value=core) if core else nullcontext():
                    code = main()
        record = json.loads(out.getvalue())
        self.assertEqual(1, len(out.getvalue().splitlines()))
        self.assertEqual(1, record['schema_version']); self.assertEqual('file.fresh-folder-upload', record['operation'])
        self.assertNotIn('PRIVATE', out.getvalue() + err.getvalue())
        if record['error']:self.assertFalse(record['error']['retryable'])
        return code, record, err.getvalue(), factory

    def test_selected_profile_success_and_no_writes(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp)
            with patch.object(core.preferences, 'save', side_effect=AssertionError('profile write')), \
                 patch.object(core._credentials, 'set', side_effect=AssertionError('credential write')), \
                 patch.object(core, 'connect', wraps=core.connect) as connect, \
                 patch('c64u_browser.transfers.connect', side_effect=AssertionError('raw transport')), \
                 patch('c64u_browser.core.CoreDeviceOperations.open_ftp', side_effect=AssertionError('raw facade')):
                code, record, _, _ = self.invoke(['put-new', str(source), '/USB1/parent'], core)
            self.assertEqual(0, code); self.assertEqual('succeeded', record['state'])
            self.assertEqual('published', record['result']['disposition']); self.assertTrue(record['result']['verified'])
            self.assertEqual(profile.id, record['result']['profile_id'])
            self.assertEqual(dict(entered_password='', require_bound=True, bind_identity=False, persist=False, remember=False), connect.call_args.kwargs)
            self.assertEqual(profile.id, core.preferences.selected_id)
            self.assertEqual(3, ftp.connections)  # connect + preparation + execution
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_exact_profile_id_case_sensitive_not_name_host_or_device(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); profile.id = 'Exact-ID'; core.preferences.selected_id = None
            for selector in ('exact-id', profile.name, profile.host, profile.device_id):
                with self.subTest(selector=selector), self.assertRaises(BrowserError):resolve_profile(core, [selector])
            code, record, _, _ = self.invoke(['--profile-id', profile.id, 'put-new', str(source), '/USB1'], core)
            self.assertEqual(0, code); self.assertEqual(profile.id, record['result']['profile_id'])
            self.assertIsNone(core.preferences.selected_id)

    def test_missing_selection_has_no_first_profile_fallback(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); core.preferences.selected_id = None
            code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual(0, ftp.connections)
            self.assertIsNone(record['result']['mutation'])

    def test_invalid_missing_ambiguous_and_unbound_profiles(self):
        for mode in ('empty', 'control', 'long', 'missing', 'duplicate', 'dangling', 'unbound', 'corrupt'):
            with self.subTest(mode=mode), server() as ftp:
                core, profile, source = self.setup_core(ftp); selector = profile.id
                if mode == 'empty':selector = ''
                if mode == 'control':selector = 'a\nb'
                if mode == 'long':selector = 'a'*121
                if mode == 'missing':selector = 'missing'
                if mode == 'duplicate':core.preferences.profiles.append(replace(profile))
                if mode == 'dangling':core.preferences.selected_id = 'missing'
                if mode == 'unbound':profile.device_id = ''; profile.device_mac = ''
                if mode == 'corrupt':core.preferences_error = 'PRIVATE'
                code, record, _, _ = self.invoke(['--profile-id', selector, 'put-new', str(source), '/USB1'], core)
                self.assertEqual(1, code); self.assertEqual(0, ftp.connections)

    def test_real_corrupt_preferences_load_refused(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp); core.preferences.path.write_text('{broken')
            core.load()
            self.assertIsNotNone(core.preferences_error)
            code, _, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual('{broken', core.preferences.path.read_text())
            self.assertEqual(0, ftp.connections)

    def test_identity_mismatch_sanitized_before_ftp(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); profile.device_id = 'OTHER'
            code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual('identity', record['error']['code'])
            self.assertEqual(0, ftp.connections)

    def test_mac_fallback_bound_authority(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); profile.device_id = ''; profile.device_mac = '00:11:22:33:44:55'
            code, _, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(0, code)

    def test_unsupported_explicit_defaults_and_syntax(self):
        for options in (['--host', '127.0.0.1'], ['--port', '21'], ['--timeout', '10'], ['--encoding', 'utf-8'],
                        ['--port=21'], ['--timeout=10'], ['--unknown'], ['--profile-id', 'a', '--profile-id', 'b']):
            with self.subTest(options=options):
                code, record, _, factory = self.invoke(options + ['put-new', 'source', '/USB1'])
                self.assertEqual(2, code); factory.assert_not_called()
                self.assertEqual('syntax', record['error']['code'])
        for arguments in (['put-new'], ['put-new', 'source'], ['put-new', 'a', 'b', 'c'], ['--port', 'x', 'put-new']):
            with self.subTest(arguments=arguments):
                code, _, _, factory = self.invoke(arguments)
                self.assertEqual(2, code); factory.assert_not_called()

    def test_profile_id_bound_inclusive_120(self):
        with server() as ftp:
            core, profile, _ = self.setup_core(ftp); profile.id = 'a'*120; core.preferences.selected_id = profile.id
            self.assertIs(profile, resolve_profile(core, [profile.id]))

    def test_private_entered_credential_not_persisted_or_printed(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); events = []; core.scheduler_events = events
            with patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value='PRIVATE'), \
                 patch.object(core.preferences, 'save', side_effect=AssertionError('write')), \
                 patch.object(core._credentials, 'set', side_effect=AssertionError('write')):
                code, record, err, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
            self.assertEqual(0, code); self.assertEqual('PRIVATE', core._client.password)
            self.assertEqual({}, core._session_passwords); self.assertEqual({}, core._credentials.values)
            self.assertNotIn('PRIVATE', json.dumps([job.snapshot().as_dict() for job in core.scheduler._jobs.values()]))
            self.assertEqual([b'anonymous']*3, [p for v,p in ftp.commands if v == b'USER'])

    def test_credential_resolution_existing_session_then_remembered(self):
        for session, remembered, expected in (('session', 'stored', 'session'), ('', 'stored', 'stored'), ('', '', '')):
            with self.subTest(session=session, remembered=remembered), server() as ftp:
                core, profile, source = self.setup_core(ftp)
                core._session_passwords[profile.id] = session; core._credentials.values[profile.id] = remembered
                with patch('c64u_browser.fresh_folder_cli.getpass.getpass', side_effect=AssertionError('new prompt')):
                    code, _, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
                self.assertEqual(0, code); self.assertEqual(expected, core._client.password)

    def test_empty_entered_password_uses_existing_fallback(self):
        with server() as ftp:
            core, profile, source = self.setup_core(ftp); core._credentials.values[profile.id] = 'PRIVATE'
            with patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value=''):
                code, _, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
            self.assertEqual(0, code); self.assertEqual('PRIVATE', core._client.password)

    def test_password_bounds_and_control_characters(self):
        for value in ('a'*1025, 'line\nbreak', 'bad\x00'):
            with self.subTest(value=repr(value[:10])), server() as ftp:
                core, _, source = self.setup_core(ftp)
                with patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value=value):
                    code, _, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
                self.assertEqual(1, code); self.assertEqual(0, ftp.connections)
        with patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value='a'*1024):
            self.assertEqual(1024, len(private_password()))

    def test_password_eof_and_interrupt_cancel(self):
        for exc in (EOFError, KeyboardInterrupt):
            with self.subTest(exc=exc), server() as ftp:
                core, _, source = self.setup_core(ftp)
                with patch('c64u_browser.fresh_folder_cli.getpass.getpass', side_effect=exc):
                    code, record, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
                self.assertEqual(130, code); self.assertEqual('cancelled', record['state']); self.assertEqual(0, ftp.connections)

    def test_no_private_input_fallback(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp)
            def fallback(*a, **k):
                warnings.warn('PRIVATE', getpass.GetPassWarning)
                self.fail('Echoing fallback must not continue')
            with patch('c64u_browser.fresh_folder_cli.getpass.getpass', side_effect=fallback):
                code, _, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual(0, ftp.connections)

    def test_failure_json_preserves_directory_and_upload(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp); ftp.replies[b'STOR'] = b'550 PRIVATE\r\n'
            code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual('created', record['result']['directory_disposition'])
            self.assertEqual('no-candidate', record['result']['upload_state'])
            self.assertEqual(550, record['result']['upload']['stor']['preliminary_reply'])

    def test_ctrl_c_drains_and_repeated_interrupt_retains_created(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp); original = CoreJob.wait; interrupted = [False]
            def wait(job, timeout=None):
                if job.operation == 'file.fresh-folder-upload' and not interrupted[0]:
                    interrupted[0] = True
                    # Wait until MKD is acknowledged in the worker before delivery.
                    marked.wait(2)
                    signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
                    signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
                    release.set()
                return original(job, timeout)
            import threading
            marked = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
            def hook(v,p):
                if v == b'MKD':marked.set(); release.wait(3)
            ftp.mutation_hook = hook
            with patch.object(CoreJob, 'wait', wait):code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertTrue(interrupted[0]); self.assertEqual(130, code)
            self.assertEqual('directory-created-upload-not-started', record['result']['disposition'])
            self.assertNotIn(b'STOR', ftp.verbs); self.assertEqual(0, core._ftp_manager.active_count)

    def test_drain_keyboard_interrupt_wait_loop(self):
        job = Mock(); job.wait.side_effect = [KeyboardInterrupt(), KeyboardInterrupt(), 'terminal']
        self.assertEqual('terminal', drain(job, [False])); self.assertGreaterEqual(job.request_cancel.call_count, 2)

    def test_cli_late_success_exit_zero(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp)
            def hook(v,p):
                if v == b'RNTO':signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            ftp.mutation_hook = hook
            code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(0, code); self.assertEqual('published', record['result']['disposition'])

    def test_core_close_cleanup_failure_keeps_published(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp); original = core.close
            def close():original(); raise OSError('PRIVATE')
            with patch.object(core, 'close', side_effect=close):
                code, record, _, _ = self.invoke(['put-new', str(source), '/USB1'], core)
            self.assertEqual(1, code); self.assertEqual('published-local-cleanup-failed', record['result']['disposition'])
            self.assertTrue(record['result']['verified'])

    def test_legacy_info_ls_browse_get_routes_unchanged(self):
        for command in ('info', 'ls', 'browse', 'get'):
            with self.subTest(command=command):
                client = Mock(); client.info.return_value = {'ok': True}; client.list_directory.return_value = ('/USB1', [Entry('a','file',3)])
                argv = ['c64u_browser', '--host', 'example.invalid', '--password', '--port', '123', '--timeout', '7', '--encoding', 'latin-1', command, '/USB1']
                if command == 'get':argv.append('local')
                with patch('sys.argv', argv), patch('c64u_browser.__main__.UltimateClient', return_value=client) as factory, \
                     patch('c64u_browser.__main__.getpass.getpass', return_value='legacy'), patch('builtins.input', return_value='q'), \
                     patch('c64u_browser.__main__.download', return_value={'path':'local'}) as download, \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(0, main())
                factory.assert_called_once_with('example.invalid', 'legacy', 123, 7, 'latin-1')
                self.assertEqual(command == 'get', download.called)

    def test_legacy_required_host_and_profile_rejection(self):
        for argv in (['info'], ['--profile-id', 'a', '--host', 'example.invalid', 'ls']):
            with self.subTest(argv=argv), patch('sys.argv', ['c64u_browser']+argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(2, caught.exception.code)

    def assert_legacy_syntax(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['c64u_browser'] + argv), redirect_stdout(out), redirect_stderr(err), \
             patch('c64u_browser.fresh_folder_cli.run') as run, \
             patch('c64u_browser.__main__.UltimateClient') as client, \
             self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(2, caught.exception.code)
        self.assertEqual('', out.getvalue())
        self.assertIn('error:', err.getvalue())
        run.assert_not_called(); client.assert_not_called()

    def test_put_new_as_legacy_get_source_missing_destination(self):
        self.assert_legacy_syntax(['--host', 'example.invalid', 'get', 'put-new'])

    def test_put_new_as_other_legacy_positionals(self):
        for command in ('info', 'ls', 'browse', 'get'):
            for operands in (['put-new'], ['source', 'put-new']):
                with self.subTest(command=command, operands=operands):
                    # Missing host is a legacy error, regardless of operand text.
                    self.assert_legacy_syntax([command] + operands)
        self.assert_legacy_syntax(['--host', 'example.invalid', '--', 'get', 'put-new'])

    def test_put_new_as_option_value_is_not_command(self):
        for option in ('--host', '--profile-id', '--port', '--timeout', '--encoding', '--hos', '--profile-i'):
            for arguments in ([option, 'put-new', 'get', 'source'], [option + '=put-new', 'get', 'source'],
                              [option, 'put-new']):
                with self.subTest(arguments=arguments):
                    self.assert_legacy_syntax(arguments)
        self.assert_legacy_syntax(['--unknown', 'get', 'put-new'])

    def test_genuine_put_new_malformed_routing(self):
        for arguments in (['--', 'put-new'], ['--profile-i', 'id', 'put-new'],
                          ['--profile-id=put-new', 'put-new'], ['--password', 'put-new'],
                          ['--port', 'bad', 'put-new'], ['--encoding', 'bad', 'put-new'],
                          ['--host', '--password', 'put-new'], ['put-new', '--port', 'bad'],
                          ['--unknown', 'put-new']):
            with self.subTest(arguments=arguments):
                code, record, _, factory = self.invoke(arguments)
                self.assertEqual(2, code); self.assertEqual('syntax', record['error']['code'])
                factory.assert_not_called()

    def test_genuine_put_new_valid_command_dispatch(self):
        for arguments in (['put-new', 'source', '/USB1'], ['--', 'put-new', 'source', '/USB1'],
                          ['--profile-i', 'put-new', 'put-new', 'source', '/USB1'],
                          ['--profile-id=put-new', 'put-new', 'source', '/USB1'],
                          ['--password', 'put-new', 'source', '/USB1']):
            with self.subTest(arguments=arguments), patch('sys.argv', ['c64u_browser'] + arguments), \
                 patch('c64u_browser.fresh_folder_cli.run', return_value=0) as run, \
                 patch('c64u_browser.__main__.UltimateClient') as client:
                self.assertEqual(0, main())
                run.assert_called_once(); client.assert_not_called()
                self.assertEqual('put-new', run.call_args.args[0].command)

    def test_help_remains_help(self):
        out = io.StringIO()
        with patch('sys.argv', ['c64u_browser', '--help']), redirect_stdout(out), self.assertRaises(SystemExit) as caught:main()
        self.assertEqual(0, caught.exception.code); self.assertIn('--profile-id', out.getvalue())

    def test_prompt_signal_interrupt_cancels_before_connection(self):
        with server() as ftp:
            core, _, source = self.setup_core(ftp)
            def prompt(*args, **kwargs):signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            with patch('c64u_browser.fresh_folder_cli.getpass.getpass', side_effect=prompt):
                code, record, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
            self.assertEqual(130, code); self.assertEqual(0, ftp.connections)

    def test_diagnostics_and_job_events_exclude_credentials_and_peer_prose(self):
        from c64u_browser.test_lab import _EventCollector
        from c64u_browser.diagnostics import LOGGER
        # Unlike Test Lab's thread-local collector, collect the Core worker too.
        class Collector(_EventCollector):
            def emit(self, record):
                event = getattr(record, 'operation_event', None)
                if event is not None:self.events.append(dict(event))
        with server() as ftp:
            core, _, source = self.setup_core(ftp); collector = Collector(); jobs = []
            original = core.scheduler.submit
            def submit(job, binding):job.add_listener(jobs.append); return original(job, binding)
            ftp.replies[b'STOR'] = b'550 PRIVATE prose\r\n'
            LOGGER.addHandler(collector)
            try:
                with patch.object(core.scheduler, 'submit', side_effect=submit), \
                     patch('c64u_browser.fresh_folder_cli.getpass.getpass', return_value='PRIVATE password'):
                    code, _, _, _ = self.invoke(['--password', 'put-new', str(source), '/USB1'], core)
            finally:LOGGER.removeHandler(collector)
            self.assertEqual(1, code); self.assertTrue(jobs)
            self.assertNotIn('PRIVATE', json.dumps([event.as_dict() for event in jobs]))
            self.assertNotIn('PRIVATE', json.dumps(collector.events))
