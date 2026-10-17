"""Regression for invalid Settings teardown followed by real Files input."""
import unittest
from unittest.mock import patch
import test_preferences_ui
import c0_gtk_check


class SettingsCleanup(unittest.TestCase):
    def test_invalid_settings_cleanup_preserves_other_windows_and_files_input(self):
        from c64u_browser.app_preferences import show_preferences
        fixture=test_preferences_ui.PreferencesUI()
        with patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')):
            fixture.setUp()
            other=fixture.Gtk.Window(title='Unrelated test window')
            self.addCleanup(other.destroy)
            other.present()
            try:
                dialog=show_preferences(fixture.app)
                general=dialog.pages.get_nth_page(0)
                entry=next(w for w in fixture.walk(general) if isinstance(w,fixture.Gtk.Entry))
                entry.set_text(fixture.temp.name+'/missing')
                dialog.response(fixture.Gtk.ResponseType.CLOSE)
                fixture.drain_events()
                self.assertIs(fixture.app.preferences_dialog,dialog)
                self.assertTrue(dialog.get_visible())
                self.assertIn('Choose an existing folder',dialog.general_message.get_text())
            finally:
                try:fixture.tearDown()
                finally:fixture.doCleanups()
            try:
                self.assertFalse(dialog.get_visible())
                self.assertTrue(other.get_visible())
                self.assertIn(other,fixture.Gtk.Window.list_toplevels())
            finally:other.destroy()
            # Execute the real next fixtures and XTest interactions, not callbacks.
            suite=unittest.TestSuite(c0_gtk_check.Selection(name) for name in (
                'test_default_click_selects_double_activates',
                'test_arrows_enter_path_text_focus_and_native_theme'))
            result=unittest.TestResult();suite.run(result)
            self.assertEqual(result.testsRun,2)
            self.assertEqual(result.skipped,[])
            self.assertTrue(result.wasSuccessful(),result.failures+result.errors)
