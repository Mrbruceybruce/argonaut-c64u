"""Offline native GTK hardware/inspection lifecycle contracts."""
from concurrent.futures import Future
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from c64u_browser.connection_dialog import ConnectionDialog
from c64u_browser.compatibility import inspect, InspectionStatus
from c64u_browser.credentials import SessionCredentials
from c64u_browser.profiles import Profile
import test_core
from test_uc1_compatibility import INFO, VERSION
from gtk_layout_fixture import allocated_frame


class HardwarePresentation(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.connect', 'socket.socket.sendto', 'ftplib.FTP'):
            guard = patch(name, side_effect=AssertionError('Device access forbidden'))
            guard.start(); self.addCleanup(guard.stop)
        self.assertTrue(Gtk.init_check(), 'Isolated X11/Xvfb display required')
        self.fixture = test_core.CoreTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core = self.fixture.core
        self.original_listeners = tuple(self.core._listeners)
        self.core._credentials = SessionCredentials('Development')
        self.profile = self.fixture.profile
        self.fixture.prefs.profiles = [self.profile]
        self.fixture.prefs.selected_id = self.profile.id
        self.core.discovery_networks = Mock(return_value=())
        self.core.inspect_profile = Mock(return_value=self.result())
        self.futures = []
        def submit(task):
            future = Future(); self.futures.append((task, future)); return future
        self.app = SimpleNamespace(core=self.core, busy=False, pool=Mock(submit=Mock(side_effect=submit)))
        def button(box, label, action):
            widget = Gtk.Button(label=label)
            widget.connect('clicked', lambda *_: action()); box.append(widget); return widget
        self.app.button = button
        self.windows = []
        self.d = self.construct()
        self.addCleanup(self.cleanup_windows)

    def construct(self):
        window = Gtk.Window(title='Offline Device Details')
        window.set_default_size(740, 680)
        self.windows.append(window)
        with patch.object(ConnectionDialog, '_background', lambda owner, task, done: done(task())):
            dialog = ConnectionDialog(self.app, window=window)
        window.set_child(dialog.page)
        window.present(); self.pump()
        return dialog

    def cleanup_windows(self):
        for window in self.windows:window.destroy()
        self.pump()

    @staticmethod
    def pump():
        context = GLib.MainContext.default()
        for _ in range(1000):
            if not context.pending():break
            context.iteration(False)

    @staticmethod
    def result():
        client = Mock(read_configuration=Mock(side_effect=[
            {'categories': ['Private category A', 'Private category B']},
            {'Private category A': {}}, {'Private category B': {}}]))
        return inspect(client, {'version': VERSION, 'info': INFO})

    def finish(self, result=None):
        task, future = self.futures[-1]
        future.set_result(task() if result is None else result)
        self.pump()

    def test_expansion_is_local_and_resets_after_destruction(self):
        d = self.d
        self.assertFalse(d.hardware_expander.get_expanded())
        for expanded in (True, False, True):
            d.hardware_expander.set_expanded(expanded); self.pump()
            self.assertEqual(expanded, d.hardware_expander.get_expanded())
        d.fields['notes'].set_text('Unsaved hardware note')
        self.assertTrue(d.hardware_expander.get_expanded())
        self.assertFalse(d.close_requested())  # A parent may still offer Keep editing.
        self.assertFalse(d._closed)
        self.assertTrue(d.hardware_expander.get_expanded())
        self.core.inspect_profile.assert_not_called()
        self.assertEqual([], self.futures)
        d.window.destroy(); self.pump()
        self.assertTrue(d._closed)
        reopened = self.construct()
        self.assertFalse(reopened.hardware_expander.get_expanded())
        self.assertEqual(len(self.original_listeners) + 1, len(self.core._listeners))

    def test_saved_and_draft_target_use_editor_not_active(self):
        self.core._active_profile = Profile.new('Unrelated active', '192.0.2.99')
        self.assertIn('Saved profile:', self.d.inspection_target.get_text())
        self.d.password.set_text('typed-only')
        self.d.inspect_compatibility(); self.finish()
        target, password = self.core.inspect_profile.call_args.args
        self.assertEqual(self.profile.host, target.host)
        self.assertEqual(self.profile.device_id, target.device_id)
        self.assertEqual('typed-only', password)
        self.d.fields['host'].set_text('192.0.2.22')
        self.assertIn('Unsaved endpoint', self.d.inspection_target.get_text())
        self.assertIn('192.0.2.22:80', self.d.inspection_target.get_text())
        self.d.inspect_compatibility(); self.finish()
        target, password = self.core.inspect_profile.call_args.args
        self.assertEqual('192.0.2.22', target.host)
        self.assertEqual(self.profile.device_id, target.device_id)
        self.assertEqual({}, self.core._session_passwords)
        self.assertIsNone(self.core._client)
        self.assertFalse(self.fixture.prefs.path.exists())

    def test_new_valid_draft_and_invalid_endpoint(self):
        self.d.new()
        self.assertFalse(self.d.inspect_button.get_sensitive())
        self.d.inspect_compatibility(); self.assertEqual([], self.futures)
        self.assertIn('valid hostname', self.d.inspection_target.get_text())
        self.d.fields['host'].set_text('192.0.2.23')
        self.assertTrue(self.d.inspect_button.get_sensitive())
        self.assertIn('Unsaved endpoint', self.d.inspection_target.get_text())
        self.d.fields['http'].set_text('bad')
        self.assertFalse(self.d.inspect_button.get_sensitive())
        self.d.fields['http'].set_text('8080')
        self.d.inspect_compatibility(); self.finish()
        target = self.core.inspect_profile.call_args.args[0]
        self.assertEqual(('192.0.2.23', 8080, ''), (target.host, target.http_port, target.device_id))

    def test_duplicates_edits_and_late_callback(self):
        self.d.inspect_compatibility(); self.d.inspect_compatibility()
        self.assertEqual(1, len(self.futures))
        self.assertFalse(self.d.inspect_button.get_sensitive())
        self.d.fields['host'].set_text('192.0.2.24')
        self.d.password.set_text('replacement')
        self.assertIn('still running', self.d.compatibility_status.get_text())
        self.d.inspect_compatibility(); self.assertEqual(1, len(self.futures))
        self.finish()
        self.assertEqual('Not inspected', self.d.compatibility_status.get_text())
        self.assertTrue(self.d.inspect_button.get_sensitive())
        self.d.inspect_compatibility(); self.finish()
        self.assertIn('REST interface recognized', self.d.compatibility_status.get_text())

    def test_profile_switch_while_running(self):
        second = replace(self.profile, id='second', host='192.0.2.25')
        self.fixture.prefs.profiles.append(second); self.d.reload()
        self.d.inspect_compatibility()
        self.d.saved.set_active_id(second.id)
        self.finish()
        self.assertEqual('Not inspected', self.d.compatibility_status.get_text())
        self.d.inspect_compatibility(); self.finish()
        self.assertEqual('192.0.2.25', self.core.inspect_profile.call_args.args[0].host)

    def test_session_events_clear_pending_and_completed_results(self):
        self.d.inspect_compatibility()
        self.core._session_id = 'replacement'
        self.core._emit('reconnected'); self.pump()
        self.finish()
        self.assertEqual('Not inspected', self.d.compatibility_status.get_text())
        self.d.inspect_compatibility(); self.finish()
        self.core._session_id = 'replacement-again'
        self.core._emit('disconnected'); self.pump()
        self.assertEqual('Not inspected', self.d.compatibility_status.get_text())
        self.assertEqual(2, len(self.futures))

    def test_actual_closure_retires_callbacks_and_listener(self):
        self.d.inspect_compatibility()
        self.d.window.destroy(); self.pump()
        self.assertTrue(self.d._closed)
        self.assertEqual(self.original_listeners, tuple(self.core._listeners))
        with patch.object(self.d, 'compact_compatibility') as render:
            self.finish(); render.assert_not_called()
        self.d.inspect_compatibility(); self.assertEqual(1, len(self.futures))

    def test_compact_counts_no_category_list_and_no_secret(self):
        self.d.inspect_compatibility(); self.finish()
        text = self.d.compatibility_status.get_text()
        self.assertIn('categories discovered: 2', text)
        self.assertIn('inspected successfully: 2', text)
        self.assertIn('Requests attempted: 2', text)
        self.assertNotIn('Private category', text)
        self.assertIn('does not grant operational qualification', text)
        self.assertIn('Ultimate Menu', text)

    def test_failures_and_uninspected_counts(self):
        from c64u_browser.api import ConnectionFailure
        for kind, state in (('unsupported_api', InspectionStatus.UNSUPPORTED),
                            ('authentication', InspectionStatus.AUTHENTICATION),
                            ('network', InspectionStatus.COMMUNICATION),
                            ('malformed', InspectionStatus.INVALID), ('future', InspectionStatus.UNKNOWN)):
            client = Mock(read_configuration=Mock(side_effect=[
                {'categories': ['A', 'B', 'C', 'D', 'E']}, {'A': {}},
                ConnectionFailure(kind, 'secret'), {'C': {}}, {'D': {}}]))
            result = inspect(client, {'version': VERSION, 'info': INFO})
            text = self.d.compact_compatibility(result)
            self.assertIn(state.value, text)
            self.assertNotIn('secret', text)
            self.assertIn('Requests attempted: ' + ('2' if kind == 'authentication' else '4'), text)
            self.assertIn('inspected successfully: ' + ('1' if kind == 'authentication' else '3'), text)

    def test_password_change_alone_rejects_result(self):
        self.d.inspect_compatibility()
        self.d.password.set_text('changed-password')
        self.finish()
        self.assertEqual('Not inspected', self.d.compatibility_status.get_text())
        self.assertTrue(self.d.inspect_button.get_sensitive())

    def test_submission_failure_restores_availability(self):
        self.app.pool.submit.side_effect = RuntimeError('private worker details')
        self.d.inspect_compatibility()
        self.assertFalse(self.d._inspection_inflight)
        self.assertTrue(self.d.inspect_button.get_sensitive())
        self.assertEqual('Inspection: Unknown', self.d.compatibility_status.get_text())

    def test_native_keyboard_focus(self):
        d = self.d
        self.assertTrue(d.hardware_expander.grab_focus())
        self.assertTrue(d.hardware_expander.activate())
        self.pump(); self.assertTrue(d.hardware_expander.get_expanded())
        self.assertTrue(d.inspect_button.grab_focus())
        self.assertTrue(d.page.child_focus(Gtk.DirectionType.TAB_FORWARD))
        self.assertFalse(d.inspect_button.has_focus())
        self.assertEqual([], self.futures)

    def test_narrow_enlarged_text_and_light_dark(self):
        settings = Gtk.Settings.get_default()
        font = settings.get_property('gtk-font-name')
        dark = settings.get_property('gtk-application-prefer-dark-theme')
        try:
            self.d.hardware_expander.set_expanded(True)
            self.d.inspect_compatibility(); self.finish()
            self.d.window.set_default_size(520, 480)
            for mode in (False, True):
                settings.set_property('gtk-application-prefer-dark-theme', mode)
                settings.set_property('gtk-font-name', 'Sans 18')
                allocated_frame(self.d.window, self.d.page, self.d.compatibility_status)
                allocated_frame(self.d.window, self.d.page, self.d.compatibility_status)
                self.assertLessEqual(self.d.compatibility_status.get_width(), self.d.page.get_width())
                adjustment = self.d.page.get_vadjustment()
                self.assertGreater(adjustment.get_upper(), adjustment.get_page_size())
                self.assertGreater(self.d.compatibility_status.get_layout().get_line_count(), 7)
        finally:
            settings.set_property('gtk-font-name', font)
            settings.set_property('gtk-application-prefer-dark-theme', dark)


class SettingsHardware(unittest.TestCase):
    def test_settings_reuse_close_prompt_and_reopen(self):
        import test_preferences_ui
        from c64u_browser.app_preferences import show_preferences
        fixture = test_preferences_ui.PreferencesUI(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        app = fixture.app
        app.core.discovery_networks = Mock(return_value=())
        app.core.inspect_profile = Mock(side_effect=AssertionError('No automatic inspection'))
        app.preferences.profiles = [Profile.new('Selected', '192.0.2.20')]
        app.preferences.selected_id = app.preferences.profiles[0].id
        dialog = show_preferences(app, page=1); fixture.pump()
        self.assertEqual(4, dialog.pages.get_n_pages())
        self.assertEqual(['General', 'Device details', 'About', 'Game Library'],
            [dialog.pages.get_tab_label_text(dialog.pages.get_nth_page(i)) for i in range(4)])
        hardware = dialog.connections.hardware_expander
        self.assertFalse(hardware.get_expanded())
        hardware.set_expanded(True)
        self.assertIs(dialog, show_preferences(app, page=2))
        self.assertIs(dialog, show_preferences(app, page=1))
        self.assertTrue(hardware.get_expanded())
        dialog.connections.fields['notes'].set_text('Unfinished edit')
        dialog.close(); fixture.pump()
        dialog.unsaved_prompt.response(Gtk.ResponseType.CANCEL); fixture.pump()
        self.assertFalse(dialog.connections._closed)
        self.assertTrue(hardware.get_expanded())
        dialog.close(); fixture.pump()
        dialog.unsaved_prompt.response(Gtk.ResponseType.REJECT); fixture.pump()
        self.assertTrue(dialog.connections._closed)
        reopened = show_preferences(app, page=1); fixture.pump()
        self.assertFalse(reopened.connections.hardware_expander.get_expanded())
        app.core.inspect_profile.assert_not_called()
