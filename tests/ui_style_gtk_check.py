"""Explicit offline UI-02A checks; requires an isolated GTK display, no skips."""
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from c64u_browser import ui_style
import test_preferences_ui


class StyleProviderTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Isolated GTK display required')
        self.display = Mock()
        self.display.is_closed.return_value = False
        self.add = patch.object(Gtk.StyleContext, 'add_provider_for_display').start()
        self.remove = patch.object(Gtk.StyleContext, 'remove_provider_for_display').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(ui_style._providers.pop, self.display, None)

    def test_once_per_display_and_distinct_displays(self):
        provider = ui_style.install_styles(self.display)
        self.assertIs(provider, ui_style.install_styles(self.display))
        self.add.assert_called_once_with(self.display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.display.connect.assert_called_once_with('closed', ui_style._display_closed)
        other = Mock();other.is_closed.return_value = False
        self.addCleanup(ui_style._providers.pop, other, None)
        self.assertIsNot(provider, ui_style.install_styles(other))
        self.assertEqual(self.add.call_count, 2)

    def test_close_releases_display_and_provider(self):
        provider = ui_style.install_styles(self.display)
        ui_style._display_closed(self.display, False)
        self.remove.assert_called_once_with(self.display, provider)
        self.assertNotIn(self.display, ui_style._providers)
        self.display.is_closed.return_value = True
        with self.assertRaises(ValueError):ui_style.install_styles(self.display)
        self.assertEqual(self.add.call_count, 1)

    def test_real_parser_reports_invalid_css_without_raw_contents(self):
        with patch.object(ui_style, 'APPLICATION_CSS', b'.private-sentinel { invalid-property: 1; }'), \
             patch.object(ui_style, 'diagnostic_event') as report:
            ui_style.install_styles(self.display)
        self.assertGreater(report.call_count, 0)
        for call in report.call_args_list:
            self.assertEqual(call.args, ('gtk', 'application_css', 'style_provider', 'error'))
            self.assertEqual(call.kwargs, {'error_kind': 'css-parse'})

    def test_registration_failure_can_retry(self):
        self.add.side_effect = RuntimeError('registration failed')
        with self.assertRaises(RuntimeError):ui_style.install_styles(self.display)
        self.assertNotIn(self.display, ui_style._providers)
        self.add.side_effect = None
        self.assertIsInstance(ui_style.install_styles(self.display), Gtk.CssProvider)

    def test_original_css_and_native_selection_rules(self):
        # Frozen UI-02 baseline, including error appearance: provider move only.
        baseline = (b'.argonaut-file-pane { border: 2px solid transparent; border-radius: 6px; padding: 4px; }\n'
                    b'.argonaut-file-pane-active { border-color: alpha(@theme_selected_bg_color, 0.55); }\n'
                    b'.argonaut-error-message { color: #c01c28; font-size: 1.083333em; }')
        self.assertEqual(ui_style.APPLICATION_CSS, baseline)
        with patch.object(ui_style, 'diagnostic_event') as report:
            provider = ui_style.install_styles(self.display)
        report.assert_not_called()
        self.assertIn('argonaut-file-pane-active', provider.to_string())
        self.assertNotIn('row:selected', provider.to_string())

    def test_error_recovery_preserves_label_properties(self):
        label = Gtk.Label(label='Unchanged text', selectable=True, sensitive=False)
        label.set_tooltip_text('Unchanged tooltip')
        label.update_property([Gtk.AccessibleProperty.LABEL], ['Error details'])
        label.add_css_class('heading')
        for failed in (True, True, False, False):
            ui_style.set_error(label, failed)
            for name in ('error', 'argonaut-error-message'):
                self.assertEqual(label.has_css_class(name), failed)
            self.assertTrue(label.has_css_class('heading'))
            self.assertEqual(label.get_text(), 'Unchanged text')
            self.assertEqual(label.get_tooltip_text(), 'Unchanged tooltip')
            self.assertFalse(label.get_sensitive())
            self.assertTrue(Gtk.test_accessible_has_property(label, Gtk.AccessibleProperty.LABEL))


class ApplicationStyleTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Isolated GTK display required')
        trap = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.fixture = test_preferences_ui.PreferencesUI()
        self.accessible = []
        original_update = Gtk.Button.update_property
        def update(widget, properties, values):
            self.accessible.append((widget, properties, values))
            return original_update(widget, properties, values)
        with patch.object(Gtk.Button, 'update_property', update):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.app = self.fixture.app
        self.fixture.pump()

    def test_repeated_activation_preserves_provider_and_header_properties(self):
        app = self.app;window = app.window;provider = app.file_pane_css
        buttons = (app.connection_button, app.settings_button, app.power_button)
        original = [(b.get_sensitive(), b.get_tooltip_text()) for b in buttons]
        with patch.object(Gtk.StyleContext, 'add_provider_for_display') as register:
            app.do_activate();app.do_activate()
            self.assertIs(ui_style.install_styles(window.get_display()), provider)
        register.assert_not_called()
        self.assertIs(app.window, window)
        self.assertIs(app.file_pane_css, provider)
        self.assertEqual(original, [(b.get_sensitive(), b.get_tooltip_text()) for b in buttons])
        self.assertTrue(any(w is app.power_button and p == [Gtk.AccessibleProperty.LABEL]
                            and v == ['Ultimate Power'] for w, p, v in self.accessible))
        self.assertTrue(Gtk.test_accessible_has_property(app.power_button, Gtk.AccessibleProperty.LABEL))
        self.assertEqual(app.power_button.get_child().get_pixel_size(), 24)

    def test_general_failure_then_recovery_uses_both_classes(self):
        from pathlib import Path
        from c64u_browser.app_preferences import show_preferences
        dialog = show_preferences(self.app)
        page = dialog.pages.get_nth_page(0)
        entries = [w for w in self.fixture.walk(page) if isinstance(w, Gtk.Entry)]
        entries[0].set_text(str(Path(self.fixture.temp.name)/'missing'))
        entries[0].emit('activate');self.fixture.pump()
        for cls in ('error', 'argonaut-error-message'):
            self.assertTrue(dialog.general_message.has_css_class(cls))
        entries[0].set_text('');entries[0].emit('activate');self.fixture.pump()
        for cls in ('error', 'argonaut-error-message'):
            self.assertFalse(dialog.general_message.has_css_class(cls))

    def test_local_filename_failure_recovery_preserves_action_guard(self):
        self.app.populate(self.app.llist, [('existing.d64', False, 174848)])
        self.app.new_d64()
        dialog = self.app.d64_create_prompt
        filename, disk_name, disk_id = self.app.d64_create_entries
        filename.set_text('existing.d64');disk_name.set_text('TEST')
        self.fixture.pump()
        labels = [w for w in self.fixture.walk(dialog) if isinstance(w, Gtk.Label)
                  and w.has_css_class('argonaut-error-message')]
        self.assertEqual(len(labels), 1)
        self.assertTrue(labels[0].has_css_class('error'))
        action = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        self.assertFalse(action.get_sensitive())
        filename.set_text('new.d64');self.fixture.pump()
        self.assertTrue(action.get_sensitive())
        self.assertFalse(labels[0].has_css_class('error'))
        self.assertFalse(labels[0].has_css_class('argonaut-error-message'))
        dialog.response(Gtk.ResponseType.CANCEL)
