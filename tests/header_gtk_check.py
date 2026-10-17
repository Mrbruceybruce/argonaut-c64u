"""UI-02B.1 real GTK routes and allocations; disposable display, no devices."""
from concurrent.futures import Future
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from c64u_browser.core import CoreError
from c64u_browser.gui import Browser
from c64u_browser.header import begin_connection, end_connection
from c64u_browser.jobs import CoreJob
from c64u_browser.profiles import Profile
import test_core
import test_preferences_ui
import c0_gtk_input


class HeaderGtk(unittest.TestCase):
    def settle(self, *_):
        window = getattr(self, 'window', None)
        if window is None or not window.get_visible():
            context = GLib.MainContext.default()
            for _ in range(10000):
                if not context.pending():return
                context.iteration(False)
            self.fail('Event queue did not drain')
        loop = GLib.MainLoop()
        frames = []; expired = []
        def tick(*_):
            frames.append(True)
            if len(frames) == 2:loop.quit();return False
            return True
        def timeout():expired.append(True);loop.quit();return False
        tick_id = window.add_tick_callback(tick)
        deadline = GLib.timeout_add(3000, timeout)
        try:loop.run()
        finally:
            if expired:window.remove_tick_callback(tick_id)
            else:GLib.source_remove(deadline)
        self.assertFalse(expired, 'GTK frame deadline expired')
        # Frame ticks precede idle delivery; drain queued worker completions too.
        self.f.drain_events()

    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Isolated display required')
        trap = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f = test_preferences_ui.PreferencesUI()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app = self.f.app;self.window = self.app.window;self.h = self.app.header_view
        self.app.preferences.app_options['remember_folders'] = False
        self.app.preferences.app_options['remember_window'] = False
        self.app.core._client_factory = test_core.FakeClient
        self.app.recovery.next_check = float('inf')
        self.settle()
        self.original_run = self.app.run
        self.app.run = lambda task, done: done(task()) or True
        self.a = Profile.new('Device A', '192.0.2.10', device_id='ABC123')
        self.b = Profile.new('Device B', '192.0.2.11', device_id='ABC123')
        self.c = Profile.new('Editor C', '192.0.2.12', device_id='ABC123')
        self.app.preferences.profiles = [self.a, self.b, self.c]
        self.select(self.a)

    def select(self, profile):
        self.app.preferences.selected_id = profile.id if profile else None
        self.app.update_connection_header()

    def connect(self):
        self.app.connection_button.emit('clicked')
        self.app.recovery.next_check = float('inf')
        self.assertEqual(self.app.active_profile.id, self.a.id)
        self.assertEqual(self.app.connection_button.get_label(), 'Disconnect')

    def test_connect_disconnect_real_callbacks_without_persistence(self):
        with patch.object(self.app.core, '_save_profile', side_effect=AssertionError('Profile save')), \
             patch.object(self.app.preferences, 'save', side_effect=AssertionError('Preferences write')), \
             patch.object(self.app.core._credentials, 'set', side_effect=AssertionError('Credential write')):
            self.assertEqual(self.h.primary.get_label(), 'Connect')
            self.connect()
            self.h.primary.emit('clicked')
            self.assertIsNone(self.app.active_profile)
            self.assertFalse(self.app.core.device_session().session_id)
            self.assertIsNone(self.app.recovery.profile)
            self.assertEqual(self.h.primary.get_label(), 'Connect')

    def test_missing_and_unbound_open_device_details(self):
        for profile in (None, Profile.new('Unbound', '192.0.2.20')):
            if profile:self.app.preferences.profiles.append(profile)
            self.select(profile)
            self.assertEqual(self.h.primary.get_label(), 'Connect…')
            from c64u_browser.package_self_test import _connection_header_valid
            self.assertTrue(_connection_header_valid(self.app))
            with patch.object(self.app.core, 'connect_selected') as connect:
                self.h.primary.emit('clicked');self.settle()
                self.assertEqual(self.app.preferences_dialog.pages.get_current_page(), 1)
                connect.assert_not_called()
            self.app.preferences_dialog.response(Gtk.ResponseType.CLOSE);self.settle()

    def test_disconnect_then_connect_uses_saved_b_not_editor_c(self):
        self.connect();old = self.app.core.device_session()
        self.select(self.b)
        self.app.open_connections();self.settle()
        self.app.connection_dialog.saved.set_active_id(self.c.id)
        self.assertEqual(self.app.core.selected_profile().id, self.b.id)
        self.app.preferences_dialog.response(Gtk.ResponseType.CLOSE);self.settle()
        with patch.object(self.app.core, '_save_profile', side_effect=AssertionError('Profile save')), \
             patch.object(self.app.core._credentials, 'set', side_effect=AssertionError('Credential write')):
            self.h.primary.emit('clicked')
            self.assertIsNone(self.app.active_profile)
            self.h.primary.emit('clicked')
        self.assertEqual(self.app.core.active_profile.id, self.b.id)
        self.assertNotEqual(self.app.core.device_session().session_id, old.session_id)
        self.app.recovery.next_check = float('inf')

    def test_exactly_three_header_actions_without_reconnect_menu(self):
        children = [];child = self.h.actions.get_first_child()
        while child:
            children.append(child);child = child.get_next_sibling()
        self.assertEqual(children, [self.h.primary, self.app.settings_button, self.app.power_button])
        self.assertFalse(any(isinstance(w, Gtk.MenuButton) for w in self.f.walk(self.app.connection_header)))
        self.assertFalse(hasattr(self.app, 'connection_menu'))
        self.assertFalse(hasattr(self.app, 'reconnect_button'))

    def test_automatic_recovery_keeps_active_device_despite_saved_selection(self):
        self.connect();old = self.app.core.device_session()
        self.select(self.b)
        self.app.recovery.lost('Synthetic offline state')
        self.app.recovery.next_check = 0
        future = Future()
        with patch.object(self.app.pool, 'submit', return_value=future) as submit:
            self.app.recovery.tick()
            self.assertEqual(self.h.primary.get_label(), 'Disconnect')
            self.assertFalse(self.h.primary.get_sensitive())
            future.set_result(submit.call_args.args[0]())
            self.settle()
        self.assertEqual(self.app.core.active_profile.id, self.a.id)
        self.assertEqual(self.app.core.selected_profile().id, self.b.id)
        self.assertNotEqual(self.app.core.device_session().session_id, old.session_id)
        self.assertFalse(self.app.recovery.offline)
        self.assertTrue(self.h.primary.get_sensitive())
        self.assertIn('Selected for next connection: Device B', self.h.metadata.get_text())
        self.app.recovery.next_check = float('inf')

    def test_pending_labels_duplicate_clicks_and_completion(self):
        for connected, label in ((False, 'Connecting…'), (True, 'Reconnecting…')):
            queued = []
            self.app.run = lambda task, done: queued.append((task, done)) or True
            if connected:self.app.reconnect_device()
            else:self.h.primary.emit('clicked')
            self.assertEqual(self.h.primary.get_label(), label)
            self.assertFalse(self.h.primary.get_sensitive())
            self.h.primary.emit('clicked');self.h.primary.emit('clicked')
            self.assertEqual(len(queued), 1)
            task, done = queued.pop();done(task())
            self.assertEqual(self.h.primary.get_label(), 'Disconnect')
            self.assertTrue(self.h.primary.get_sensitive())
            self.app.recovery.next_check = float('inf')

    def test_busy_and_health_checks_do_not_claim_connection_attempt(self):
        self.connect()
        for kind in ('busy', 'health', 'reserved'):
            self.app.busy = kind == 'busy'
            self.app.recovery.inflight = kind == 'health'
            token = self.app.foreground.reserve() if kind == 'reserved' else None
            self.app.update_connection_header()
            self.assertEqual(self.h.primary.get_label(), 'Disconnect')
            self.assertFalse(self.h.primary.get_sensitive())
            with patch.object(self.app, 'disconnect_device') as disconnect, patch.object(self.app, 'reconnect_device') as reconnect:
                self.h.primary.emit('clicked');self.h.primary.emit('clicked')
                disconnect.assert_not_called();reconnect.assert_not_called()
            if token:self.app.foreground.release(token)
        self.app.busy = False;self.app.recovery.inflight = False;self.app.update_connection_header()
        self.assertTrue(self.h.primary.get_sensitive())

    def test_offline_disconnect_stops_recovery_and_keeps_diagnostics(self):
        self.connect();self.app.recovery.lost('Identity mismatch: expected A, received another device.')
        self.app.recovery.paused = True;self.app.update_connection_header()
        self.assertEqual(self.h.primary.get_label(), 'Disconnect')
        self.assertIn('retries paused', self.h.title.get_text())
        self.assertIn('Identity mismatch', self.h.notice.get_text())
        self.assertFalse(self.h.notice.has_css_class('dim-label'))
        self.h.primary.emit('clicked')
        self.assertIsNone(self.app.recovery.profile)
        self.assertFalse(self.h.notice.get_visible())

    def test_authentication_and_identity_failures_clear_pending_and_pause(self):
        self.connect()
        for code in ('authentication', 'identity'):
            with patch.object(self.app.core, 'reconnect', side_effect=CoreError(code, 'Safe '+code+' refusal')):
                self.app.reconnect_device()
            self.assertIsNone(self.h.phase)
            self.assertTrue(self.app.recovery.paused)
            self.assertEqual(self.h.primary.get_label(), 'Disconnect')
            self.assertIn('Safe '+code+' refusal', self.h.notice.get_text())
            self.assertFalse(self.app.core.device_session().session_id)

    def test_disconnected_failure_and_submission_refusal(self):
        with patch.object(self.app.core, 'connect_selected', side_effect=CoreError('authentication', 'Safe refusal')):
            self.h.primary.emit('clicked')
        self.assertEqual(self.h.primary.get_label(), 'Connect')
        self.assertEqual(self.app.status.get_text(), 'Safe refusal')
        for result in (False, RuntimeError('Executor closed')):
            self.app.run = Mock(return_value=False) if result is False else Mock(side_effect=result)
            self.h.primary.emit('clicked')
            self.assertIsNone(self.h.phase);self.assertFalse(self.app.recovery.inflight)
            self.assertTrue(self.h.primary.get_sensitive())

    def test_stale_phase_end_and_shutdown_are_inert(self):
        old = begin_connection(self.app, 'Connecting…')
        new = begin_connection(self.app, 'Reconnecting…')
        end_connection(self.app, old)
        self.assertEqual(self.h.primary.get_label(), 'Reconnecting…')
        self.h.close();before = self.h.title.get_text()
        end_connection(self.app, new);self.app.update_connection_header()
        self.assertEqual(self.h.title.get_text(), before)
        self.assertFalse(self.h.primary.get_sensitive())
        with patch.object(self.app, 'reconnect_device') as reconnect:
            self.h.primary.emit('clicked');reconnect.assert_not_called()

    def test_foreground_admission_release_and_failure_refresh(self):
        self.app.run = self.original_run
        job = CoreJob('file.synthetic', lambda _:None)
        self.app.run_file_job(lambda:job, Mock())
        self.assertEqual(self.h.primary.get_label(), 'Connect')
        self.assertFalse(self.h.primary.get_sensitive())
        job.run();self.settle()
        self.assertTrue(self.h.primary.get_sensitive())
        self.app.run_file_job(lambda:False, Mock())
        self.assertTrue(self.h.primary.get_sensitive())

    def test_ordinary_worker_refresh_preserves_contextual_label(self):
        self.app.run = self.original_run
        future = Future()
        with patch.object(self.app.pool, 'submit', return_value=future):
            self.app.run(lambda:None, Mock())
            self.assertEqual(self.h.primary.get_label(), 'Connect')
            self.assertFalse(self.h.primary.get_sensitive())
            future.set_result(None);self.settle()
        self.assertTrue(self.h.primary.get_sensitive())

    def test_auto_connect_failure_clears_pending(self):
        self.a.auto_connect = True
        self.app.run = self.original_run
        future = Future()
        with patch.object(self.app.pool, 'submit', return_value=future):
            self.app.auto_connect()
            self.assertEqual(self.h.primary.get_label(), 'Connecting…')
            future.set_result(CoreError('authentication', 'Safe failure'));self.settle()
        self.assertIsNone(self.h.phase);self.assertEqual(self.h.primary.get_label(), 'Connect')
        self.assertEqual(self.app.status.get_text(), 'Safe failure')
        self.a.auto_connect = False

    def test_auto_connect_cannot_replace_an_explicit_attempt(self):
        self.a.auto_connect = True
        queued = []
        self.app.run = lambda task, done:queued.append((task, done)) or True
        self.h.primary.emit('clicked')
        token = self.h.token
        self.app.auto_connect()
        self.assertIs(self.h.token, token)
        self.assertEqual(len(queued), 1)
        task, done = queued.pop();done(CoreError('authentication', 'Refused'))
        self.a.auto_connect = False

    def test_device_details_connect_marks_only_connect_submissions(self):
        self.app.open_connections();self.settle();dialog = self.app.connection_dialog
        queued = [];self.app.run = lambda task, done:queued.append((task, done)) or True
        dialog.connect()
        self.assertEqual(self.h.primary.get_label(), 'Connecting…')
        task, done = queued.pop();done(CoreError('authentication', 'Refused'))
        self.assertIsNone(self.h.phase)
        dialog.test()
        self.assertIsNone(self.h.phase)
        task, done = queued.pop();done('Test result')
        self.app.preferences_dialog.response(Gtk.ResponseType.CLOSE)

    def test_recovery_tick_refresh_and_late_generation(self):
        self.connect();self.app.recovery.next_check = 0;future = Future()
        with patch.object(self.app.pool, 'submit', return_value=future):
            self.app.recovery.tick()
            self.assertFalse(self.h.primary.get_sensitive())
            self.assertEqual(self.h.primary.get_label(), 'Disconnect')
            self.app.disconnect_device()
            future.set_result(None);self.settle()
        self.assertEqual(self.h.primary.get_label(), 'Connect')
        self.assertTrue(self.h.primary.get_sensitive());self.assertIsNone(self.app.active_profile)

    def test_keyboard_settings_and_power(self):
        patcher = patch('c0_gtk_input.pump', self.settle);patcher.start();self.addCleanup(patcher.stop)
        input = c0_gtk_input.Input(self.window);self.addCleanup(input.close)
        self.h.primary.grab_focus();input.press('Tab')
        self.assertIs(self.window.get_focus(), self.app.settings_button)
        input.press('space');self.settle()
        self.assertIsNotNone(self.app.preferences_dialog)
        self.app.preferences_dialog.response(Gtk.ResponseType.CLOSE);self.settle()
        # The isolated X server has no window manager to return native input
        # focus from a destroyed modal to its parent. Reacquire that target.
        input = c0_gtk_input.Input(self.window);self.addCleanup(input.close)
        self.app.settings_button.grab_focus();input.press('Tab')
        self.assertIs(self.window.get_focus(), self.app.power_button)
        input.press('space');self.settle()
        self.assertIsNotNone(self.app.ultimate_power.dialog)
        self.assertEqual(self.app.power_button.get_child().get_pixel_size(), 24)
        self.assertIn('Ultimate Power', self.app.power_button.get_tooltip_text())
        self.app.ultimate_power.dialog.response(Gtk.ResponseType.CLOSE)

    def test_repeated_activation_and_appearance_keep_header_and_provider(self):
        provider = self.app.file_pane_css;settings = Gtk.Settings.get_default()
        old = settings.get_property('gtk-application-prefer-dark-theme')
        self.addCleanup(settings.set_property, 'gtk-application-prefer-dark-theme', old)
        name = settings.get_property('gtk-theme-name');self.h.primary.grab_focus()
        with patch.object(Gtk.StyleContext, 'add_provider_for_display') as add:
            for dark in (True, False):
                settings.set_property('gtk-application-prefer-dark-theme', dark)
                self.app.do_activate();self.settle()
                self.assertIs(self.app.header_view, self.h)
                self.assertIs(self.app.file_pane_css, provider)
                self.assertIs(self.window.get_focus(), self.h.primary)
            add.assert_not_called()
        self.assertEqual(settings.get_property('gtk-theme-name'), name)

    def test_responsive_full_window_and_narrow_header(self):
        self.a.name = 'Long device name ' * 16
        self.a.host = 'long-endpoint-' * 8 + '.invalid'
        self.app.update_connection_header()
        self.assertIn(self.a.name, self.h.title.get_tooltip_text())
        self.assertIn(self.a.host, self.h.metadata.get_tooltip_text())
        actions = [self.h.primary, self.app.settings_button, self.app.power_button]
        def contained():
            valid, bounds = self.h.actions.compute_bounds(self.app.connection_header)
            self.assertTrue(valid)
            self.assertGreaterEqual(bounds.get_x(), 0)
            self.assertLessEqual(bounds.get_x() + bounds.get_width(), self.app.connection_header.get_width())
            self.assertGreater(self.h.title.get_width(), 0)
            for button in actions:
                bounds = button.get_allocation()
                self.assertGreater(bounds.width, 0)
                self.assertLessEqual(bounds.x + bounds.width, self.h.actions.get_width())
                self.assertTrue(button.get_mapped())
            self.assertIs(self.h.actions.get_last_child(), self.app.power_button)
        for width in (1200, 1, 3840):
            self.window.set_default_size(width, 850);self.settle();contained()
            self.assertGreaterEqual(self.window.get_width(), self.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum)
        header = self.app.connection_header;self.app.controls.remove(header)
        narrow = Gtk.Window();narrow.set_child(header);self.addCleanup(narrow.destroy)
        self.window = narrow
        for width in (360, 480, 640):
            narrow.set_default_size(width, 200);narrow.present();self.settle();contained()
            self.assertGreaterEqual(narrow.get_width(), header.measure(Gtk.Orientation.HORIZONTAL, -1).minimum)
