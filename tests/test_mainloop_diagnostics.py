import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from c64u_browser.mainloop_diagnostics import (
    MAX_BYTES, MAX_FRAMES, MAX_THREADS, Watchdog, observed,
    start_diagnostics, write_report, code_location,
)


SECURE_DIRECTORIES = (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
                      and os.open in os.supports_dir_fd
                      and os.mkdir in os.supports_dir_fd and hasattr(os, 'fchmod'))


class MainloopDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.reports = []
        self.monitor = Watchdog(self.reports.append, 'a' * 40, clock=lambda: self.now)
        self.addCleanup(self.monitor.close)

    def test_opt_in_requires_mode_and_exact_flag(self):
        for development in ('0', '1'):
            for mode in (False, True):
                for flag in (None, '0', 'true', '1'):
                    prefs = SimpleNamespace(app_options={'developer_mode': mode}, path='unused')
                    env = {} if flag is None else {'ARGONAUT_MAINLOOP_DIAGNOSTICS': flag}
                    with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': development}), patch(
                            'c64u_browser.mainloop_diagnostics.Watchdog') as factory:
                        result = start_diagnostics(prefs, Mock(), Mock(), environ=env)
                        expected = (development == '1' or mode) and flag == '1'
                        self.assertEqual(factory.called, expected)
                        self.assertEqual(result is not None, expected)

    def test_healthy_heartbeats_and_single_sustained_stall(self):
        for tick in range(20):
            self.now = tick
            self.assertTrue(self.monitor.heartbeat())
            self.assertFalse(self.monitor.check())
        self.now += 4.999
        self.assertFalse(self.monitor.check())
        self.now = 24
        self.assertTrue(self.monitor.check())
        self.monitor.heartbeat()
        self.now += 100
        self.assertFalse(self.monitor.check())
        self.assertEqual(len(self.reports), 1)

    def test_nested_phase_and_exception_preserve_behavior(self):
        owner = SimpleNamespace(mainloop_diagnostics=self.monitor)
        @observed('stream-tick')
        def fail(app):
            self.assertEqual(self.monitor.current_phase, 'stream-tick')
            raise ValueError('private-content')
        with self.monitor.phase('navigation', {'stream': True, 'password': 'private'}):
            with self.assertRaisesRegex(ValueError, 'private-content'):
                fail(owner)
            self.assertEqual(self.monitor.current_phase, 'navigation')
            self.assertEqual(self.monitor.state, {'stream': True})
        self.assertEqual(self.monitor.current_phase, 'idle')

    def test_stack_capture_redacts_content_and_prioritizes_main(self):
        secret = 'credential-user-content-do-not-log'
        frame = sys._getframe()
        self.monitor.frames = lambda: {i: frame for i in range(MAX_THREADS + 10)} | {
            self.monitor.main_thread: frame}
        self.monitor.build = 'a' * 40
        self.now = 5
        with self.monitor.phase(secret, {'stream': True, 'audio': secret, secret: secret}):
            self.monitor.check()
        report = self.reports[0]
        self.assertEqual(report['phase'], 'idle')
        self.assertEqual(report['state_at_phase_entry'], {'stream': True})
        self.assertEqual(report['threads']['items'][0]['thread'], self.monitor.main_thread)
        self.assertEqual(len(report['threads']['items']), MAX_THREADS)
        self.assertTrue(report['threads']['threads_truncated'])
        encoded = json.dumps(report)
        for value in (secret, __file__, 'test_stack_capture_redacts_content'):
            self.assertNotIn(value, encoded)
        self.assertTrue(all(len(t['stack']) <= MAX_FRAMES for t in report['threads']['items']))

    def test_deep_stacks_bounded_and_application_location_retained(self):
        def descend(depth):
            if depth:
                return descend(depth - 1)
            return self.monitor._stacks()
        result = descend(MAX_FRAMES + 3)
        main = next(t for t in result['items'] if t['thread'] == self.monitor.main_thread)
        self.assertEqual(len(main['stack']), MAX_FRAMES)
        self.assertTrue(main['frames_truncated'])
        self.assertEqual(main['stack'][0]['file'], 'mainloop_diagnostics.py')

    def test_real_worker_cleanup_and_source_removed_once(self):
        add, remove = Mock(return_value=42), Mock()
        self.monitor.start(add, remove)
        self.assertTrue(self.monitor.worker.is_alive())
        self.monitor.close()
        self.monitor.close()
        self.assertFalse(self.monitor.worker.is_alive())
        remove.assert_called_once_with(42)
        self.assertFalse(self.monitor.heartbeat())
        self.now = 10
        self.assertFalse(self.monitor.check())
        self.assertEqual(self.reports, [])

    def test_fake_worker_detects_stall_without_sleep(self):
        captured = {}
        def factory(**kwargs):
            captured.update(kwargs)
            return Mock(ident=None)
        self.monitor.thread_factory = factory
        self.monitor.start(Mock(return_value=1), Mock())
        self.now = 5
        # Drive exactly the worker loop using an injected wait, no wall-clock stall.
        with patch.object(self.monitor.stopped, 'wait', return_value=False):
            captured['target']()
        self.assertEqual(len(self.reports), 1)
        self.assertTrue(captured['daemon'])

    def test_failures_are_contained_and_failed_start_removes_timer(self):
        self.monitor.sink = Mock(side_effect=OSError('secret'))
        self.now = 5
        self.assertTrue(self.monitor.check())
        self.assertFalse(self.monitor.check())
        prefs = SimpleNamespace(app_options={'developer_mode': True}, path='unused')
        remove = Mock()
        with patch('threading.Thread.start', side_effect=RuntimeError('private')):
            self.assertIsNone(start_diagnostics(prefs, Mock(return_value=3), remove,
                environ={'ARGONAUT_MAINLOOP_DIAGNOSTICS': '1'}))
        remove.assert_called_once_with(3)

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_file_retention_size_permissions_and_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs = Path(folder).resolve() / 'config.json'
            self.now = 5
            self.monitor.check()
            report = self.reports[0]
            report['threads']['items'] *= 1000
            write_report(prefs, report)
            path = Path(folder).resolve() / 'diagnostics/mainloop-stall.json'
            self.assertLessEqual(path.stat().st_size, MAX_BYTES)
            self.assertTrue(json.loads(path.read_text())['threads']['threads_truncated'])
            report['threads']['items'] = []
            write_report(prefs, report)
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertEqual(list(path.parent.iterdir()), [path])
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_report_does_not_follow_file_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'diagnostics').mkdir()
            target = root / 'private'
            target.write_text('preserve')
            (root / 'diagnostics/mainloop-stall.json').symlink_to(target)
            with self.assertRaises(OSError):
                write_report(root / 'config.json', {'threads': {'items': []}})
            self.assertEqual(target.read_text(), 'preserve')

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_directory_symlinks_leave_targets_untouched(self):
        for component in ('diagnostics', 'parent'):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as folder:
                root = Path(folder).resolve()
                target = root / 'target'
                target.mkdir(mode=0o755)
                existing = target / 'mainloop-stall.json'
                existing.write_text('preserve')
                existing.chmod(0o644)
                before = (target.stat().st_mode, existing.stat().st_mode)
                (root / component).symlink_to(target, target_is_directory=True)
                prefs = root / 'config.json' if component == 'diagnostics' else root / 'parent/config.json'
                with self.assertRaises(OSError):
                    write_report(prefs, {'threads': {'items': []}})
                self.assertEqual(existing.read_text(), 'preserve')
                self.assertEqual((target.stat().st_mode, existing.stat().st_mode), before)
                self.assertEqual(list(target.iterdir()), [existing])

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_directory_non_directory_and_dangling_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            directory = root / 'diagnostics'
            directory.write_text('preserve')
            before = directory.stat().st_mode
            with self.assertRaises(OSError):
                write_report(root / 'config.json', {'threads': {'items': []}})
            self.assertEqual(directory.read_text(), 'preserve')
            self.assertEqual(directory.stat().st_mode, before)
            directory.unlink()
            directory.symlink_to(root / 'missing', target_is_directory=True)
            with self.assertRaises(OSError):
                write_report(root / 'config.json', {'threads': {'items': []}})
            self.assertFalse((root / 'missing').exists())

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_safe_nested_directory_creation_and_permission_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            prefs = Path(folder).resolve() / 'nested/settings/config.json'
            report = {'threads': {'items': []}}
            write_report(prefs, report)
            directory = prefs.parent / 'diagnostics'
            path = directory / 'mainloop-stall.json'
            directory.chmod(0o755)
            path.chmod(0o644)
            write_report(prefs, report)
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    @unittest.skipUnless(SECURE_DIRECTORIES, 'Requires secure directory operations')
    def test_directory_replaced_before_open_does_not_redirect_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            directory = root / 'diagnostics'
            directory.mkdir()
            target = root / 'target'
            target.mkdir(mode=0o755)
            original_open = os.open
            def replace_then_open(path, flags, *args, **kwargs):
                if path == 'diagnostics':
                    directory.rmdir()
                    directory.symlink_to(target, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)
            with patch('os.open', side_effect=replace_then_open) as mocked_open:
                with patch.object(os, 'supports_dir_fd', os.supports_dir_fd | {mocked_open}):
                    with self.assertRaises(OSError):
                        write_report(root / 'config.json', {'threads': {'items': []}})
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertEqual(list(target.iterdir()), [])

    def test_unsupported_secure_operations_are_contained_once(self):
        with tempfile.TemporaryDirectory() as folder:
            self.monitor.sink = lambda report: write_report(Path(folder).resolve() / 'config.json', report)
            self.now = 5
            with patch.object(os, 'supports_dir_fd', set()):
                self.assertTrue(self.monitor.check())
                self.assertFalse(self.monitor.check())
            self.assertEqual(list(Path(folder).resolve().iterdir()), [])

    def test_disabled_callbacks_passthrough(self):
        owner = SimpleNamespace(mainloop_diagnostics=None)
        callback = Mock(return_value='result')
        self.assertEqual(observed('navigation')(callback)(owner, 7), 'result')
        callback.assert_called_once_with(owner, 7)

    def test_navigation_with_synthetic_stream_and_stalled_audio(self):
        # Real callback methods, fake widgets/device/media; no application launch.
        from c64u_browser.gui import Browser
        from c64u_browser.streams_tab import StreamsTab
        app = SimpleNamespace(mainloop_diagnostics=self.monitor,
                              preferences=SimpleNamespace(app_options={}),
                              settings_tab=Mock(), drives_tab=Mock())
        tab = StreamsTab.__new__(StreamsTab)
        app.streams_tab = tab
        tab.app = app
        receiver = Mock(frames=0)
        receiver.take.return_value = (None, b'')
        tab.session = SimpleNamespace(receiver=receiver, stopping=threading.Event(),
                                      thread=Mock(), message='private-content')
        tab.session.thread.is_alive.return_value = True
        tab.recorder = None
        tab.output = Mock()
        tab.picture = Mock()
        tab.record_button = Mock()
        tab.status = Mock()
        tab.record_chooser = None
        for i in range(10):
            self.now = i
            Browser.on_switch_page(app, None, None, 1)
            self.assertTrue(StreamsTab.tick(tab))
            self.monitor.heartbeat()
            self.assertFalse(self.monitor.check())
        self.assertEqual(app.settings_tab.load_if_needed.call_count, 10)
        def stall(samples):
            self.now += 5
            self.monitor.check()
        tab.output.push.side_effect = stall
        self.assertTrue(StreamsTab.tick(tab))
        report = self.reports[0]
        self.assertEqual(report['phase'], 'stream-tick')
        self.assertEqual(report['state_at_phase_entry'], {
            'stream': True, 'audio': True, 'replay': False,
            'recording': False, 'replay_exporting': False})
        self.assertTrue(any(frame['file'] == 'streams_tab.py' for thread in
                            report['threads']['items'] for frame in thread['stack']))
        self.assertNotIn('private-content', json.dumps(report))

    def test_stalled_navigation_identifies_navigation_phase(self):
        from c64u_browser.gui import Browser
        def stall():
            self.now = 5
            self.monitor.check()
        app = SimpleNamespace(mainloop_diagnostics=self.monitor,
                              settings_tab=SimpleNamespace(load_if_needed=stall))
        Browser.on_switch_page(app, None, None, 1)
        self.assertEqual(self.reports[0]['phase'], 'navigation')

    def test_build_metadata_accepts_only_full_commit_hash(self):
        for value in ('private-content', 'abc123', None, 123):
            self.assertEqual(Watchdog(Mock(), value).build, 'unknown')
        self.assertEqual(self.monitor.build, 'a' * 40)

    def test_frozen_source_locations_use_only_fixed_labels(self):
        self.assertEqual(code_location('/build/private/c64u_browser/streams_tab.py'), 'streams_tab.py')
        self.assertEqual(code_location(r'C:\build\c64u_browser\streaming.py'), 'streaming.py')
        self.assertEqual(code_location('/home/private/customer-file.py'), '<external>')
        self.assertEqual(code_location('/home/c64u_browser/credential.py'), '<external>')
