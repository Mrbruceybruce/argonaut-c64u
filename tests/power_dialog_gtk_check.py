"""Offline power-dialog layout and cancellation checks on an isolated display."""
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Pango
import header_gtk_check
import test_preferences_ui
import c0_gtk_input


class PowerDialogLayout(unittest.TestCase):
    def settle(self, *_):
        # A cancellation destroys the dialog during event delivery. Anchor frame
        # waits to the fixture window, which survives all tested responses.
        current = self.window
        self.window = self.app.window
        try:header_gtk_check.HeaderGtk.settle(self)
        finally:self.window = current

    def setUp(self):
        trap = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f = test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app = self.f.app;self.window = self.app.window
        self.power = self.app.ultimate_power
        self.power.bind(NS(host='exact-device.example:80'))
        self.target = NS(host='exact-device.example:80', session=object())
        for name in ('prepare_machine_command', 'discard_machine_command', 'execute_machine_command'):
            mock = Mock(return_value=self.target if name == 'prepare_machine_command' else None)
            p = patch.object(self.app.core, name, mock);p.start();self.addCleanup(p.stop)
        self.dispatch = self.app.core.execute_machine_command
        self.run = patch.object(self.app, 'run', side_effect=AssertionError('No dispatch allowed'))
        self.run.start();self.addCleanup(self.run.stop)
        self.settle()

    def open(self, action=None):
        dialog = self.power.command(action) if action else self.power.show()
        self.window = dialog;self.settle()
        self.addCleanup(dialog.destroy)
        self.dispatch.assert_not_called()
        return dialog

    def content(self, dialog):
        return next(w for w in self.f.walk(dialog.get_content_area())
                    if isinstance(w, Gtk.Box) and w.get_margin_top() == 20)

    def layout(self, dialog, response):
        box = self.content(dialog)
        self.assertEqual(box.get_spacing(), 12)
        for side in ('top', 'start', 'end'):
            self.assertEqual(getattr(box, 'get_margin_' + side)(), 20)
        self.assertEqual(box.get_margin_bottom(), 16)
        footer = dialog.get_widget_for_response(response).get_parent()
        self.assertEqual(footer.get_spacing(), 8)
        self.assertEqual(footer.get_halign(), Gtk.Align.END)
        for side in ('bottom', 'start', 'end'):
            self.assertEqual(getattr(footer, 'get_margin_' + side)(), 20)
        return box

    def confirmation(self, action):
        dialog = self.open(action)
        box = self.layout(dialog, Gtk.ResponseType.CANCEL)
        labels = [w for w in self.f.walk(box) if isinstance(w, Gtk.Label)]
        self.assertEqual([w.get_text() for w in labels], [
            action.title()+' C64 on exact-device.example:80?',
            'The running program will stop and unsaved work may be lost.'])
        for label in labels:
            self.assertTrue(label.get_wrap())
            self.assertEqual(label.get_wrap_mode(), Pango.WrapMode.WORD_CHAR)
            self.assertEqual(label.get_ellipsize(), Pango.EllipsizeMode.NONE)
        cancel = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
        self.assertIs(dialog.get_default_widget(), cancel)
        self.assertIs(dialog.get_focus(), cancel)
        self.assertEqual(cancel.get_label(), 'Cancel')
        self.assertEqual(dialog.get_widget_for_response(Gtk.ResponseType.OK).get_label(), action.title()+' C64')
        return dialog

    def test_power_content_actions_and_footer(self):
        dialog = self.open();self.layout(dialog, Gtk.ResponseType.CLOSE)
        self.assertEqual(self.power.actions.get_spacing(), 8)
        self.assertTrue(self.power.actions.get_homogeneous())
        self.assertEqual(self.power.actions.get_halign(), Gtk.Align.START)
        a = self.power.actions.get_first_child();b = a.get_next_sibling()
        self.assertEqual(a.get_width(), b.get_width())
        a.grab_focus();self.power.actions.child_focus(Gtk.DirectionType.TAB_FORWARD)
        self.assertIs(dialog.get_focus(), b)
        self.assertEqual([a.get_label(), b.get_label()], ['Reset C64…', 'Reboot C64…'])
        dialog.response(Gtk.ResponseType.CLOSE);self.dispatch.assert_not_called()

    def test_reset_confirmation_layout(self):
        self.confirmation('reset').response(Gtk.ResponseType.CANCEL)

    def test_reboot_confirmation_layout(self):
        self.confirmation('reboot').response(Gtk.ResponseType.CANCEL)

    def test_cancel_consumes_authority_once(self):
        dialog = self.confirmation('reset')
        dialog.response(Gtk.ResponseType.CANCEL);dialog.response(Gtk.ResponseType.OK)
        self.app.core.discard_machine_command.assert_called_once_with(self.target)
        self.dispatch.assert_not_called()

    def test_escape_cancels_both_confirmations(self):
        for action in ('reset', 'reboot'):
            dialog = self.confirmation(action)
            with patch('c0_gtk_input.pump', self.settle):
                input = c0_gtk_input.Input(dialog)
                try:input.press('Escape')
                finally:input.close()
            self.f.drain_events()
            self.assertFalse(dialog.get_visible())
            self.dispatch.assert_not_called()
        self.assertEqual(self.app.core.discard_machine_command.call_count, 2)

    def test_window_close_cancels_both_confirmations(self):
        for action in ('reset', 'reboot'):
            dialog = self.confirmation(action);dialog.close();self.f.drain_events()
            self.assertFalse(dialog.get_visible());self.dispatch.assert_not_called()
        self.assertEqual(self.app.core.discard_machine_command.call_count, 2)

    def test_enter_uses_safe_default(self):
        dialog = self.confirmation('reboot')
        with patch('c0_gtk_input.pump', self.settle):
            input = c0_gtk_input.Input(dialog)
            try:input.press('Return')
            finally:input.close()
        self.assertFalse(dialog.get_visible());self.dispatch.assert_not_called()
        self.app.core.discard_machine_command.assert_called_once_with(self.target)

    def test_narrow_and_normal_layout_in_both_appearances(self):
        settings = Gtk.Settings.get_default()
        old = settings.get_property('gtk-application-prefer-dark-theme')
        self.addCleanup(settings.set_property, 'gtk-application-prefer-dark-theme', old)
        for action in (None, 'reset', 'reboot'):
            dialog = self.open(action)
            for dark in (False, True):
                settings.set_property('gtk-application-prefer-dark-theme', dark)
                for width in (320, 480):
                    dialog.set_default_size(width, -1);self.settle()
                    for widget in self.f.walk(self.content(dialog)):
                        if isinstance(widget, (Gtk.Label, Gtk.Button)):
                            valid, bounds = widget.compute_bounds(dialog)
                            self.assertTrue(valid)
                            self.assertGreaterEqual(bounds.get_x(), 0)
                            self.assertLessEqual(bounds.get_x()+bounds.get_width(), dialog.get_width())
                            self.assertLessEqual(bounds.get_y()+bounds.get_height(), dialog.get_height())
                            if isinstance(widget, Gtk.Label):
                                self.assertLessEqual(widget.get_layout().get_pixel_size()[1], widget.get_height())
                    response = Gtk.ResponseType.CANCEL if action else Gtk.ResponseType.CLOSE
                    self.assertTrue(dialog.get_widget_for_response(response).get_mapped())
            dialog.response(Gtk.ResponseType.CANCEL if action else Gtk.ResponseType.CLOSE)
            self.dispatch.assert_not_called()
