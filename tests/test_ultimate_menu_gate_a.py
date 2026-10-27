"""Gate A real GTK: deterministic synthetic device operations only."""
import unittest
from unittest.mock import patch
from ultimate_menu_fixture import MenuFixture, Gtk, children, descendants, allocated_frame
from test_configuration_dependencies import CATEGORIES, MODES, FLAGS, FIELDS, metadata
from c64u_browser.backups import read_backup, write_backup


class RealGtkMenu(MenuFixture, unittest.TestCase):
    def test_visibility_sensitivity_all_qualified_modes(self):
        for category in CATEGORIES:
            for mode in MODES + (('Sparkle',) if category == CATEGORIES[0] else ()):
                with self.subTest(category=category, mode=mode):
                    self.tab.revert()
                    self.client.metadata[category] = metadata(category, mode)
                    self.tab.reload()
                    for name in metadata(category):
                        expander = self.expander(category, name)
                        self.assertTrue(expander.get_visible())
                        expander.set_expanded(True)
                        allocated_frame(self.window, expander)
                        self.assertFalse(any(isinstance(w, (Gtk.ComboBoxText, Gtk.Entry)) for w in descendants(expander)))
                        self.assertTrue(any(isinstance(w, Gtk.Label) and 'blocked by Argonaut' in w.get_text() for w in descendants(expander)))
        self.no_writes()

    def test_led_fields_read_only_and_unrelated_draft_preserved(self):
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        before = dict(self.tab.pending)
        for category in CATEGORIES:
            for row in self.tab.all_settings[category]:
                self.tab.stage(category, row, '15' if row.name == 'Strip Intensity' else 'Rainbow')
                self.assertEqual(self.tab.pending, before)
        self.no_writes()

    def test_collapsed_combo_cannot_edit_and_expanded_can_focus(self):
        self.show_section('Wired Network Setup')
        expander = self.expander('Ethernet Settings', 'Use DHCP')
        combo = next(w for w in descendants(expander.get_child()) if isinstance(w, Gtk.ComboBoxText))
        self.assertFalse(combo.is_sensitive())
        self.assertFalse(combo.grab_focus())
        expander.set_expanded(True); allocated_frame(self.window, combo)
        self.assertTrue(combo.is_sensitive()); self.assertTrue(combo.grab_focus())
        focus = self.window.get_focus()
        self.assertTrue(focus is combo or focus.is_ancestor(combo))
        self.no_writes()

    def test_invalid_mixed_preview_refuses_all_and_retains_history(self):
        payload = {CATEGORIES[0]: {'LedStrip Auto SID Mode': 'Enabled'}, 'Other': {'Value': 'new'}}
        for title in ('Restore preview', 'Undo last apply preview', 'Native configuration preview'):
            dialog, checks = self.tab.backups.preview({'settings': payload}, self.tab.all_settings, title=title)
            allocated_frame(dialog)
            for check in checks:
                check.set_active(True)
            dialog.response(Gtk.ResponseType.OK)
            self.assertFalse(self.tab.pending); self.assertFalse(self.tab.drafts)
            self.no_writes()

    def test_stale_value_after_real_review_refuses(self):
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        pending = dict(self.tab.pending)
        dialog = self.reviewed()
        self.client.metadata['Other']['Value']['current'] = 'external'
        dialog.response(Gtk.ResponseType.OK)
        self.assertEqual(self.tab.pending, pending)
        self.assertIn('not sent', self.app.status.get_text())
        self.no_writes()

    def test_stale_queued_session_refuses(self):
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        queued = []
        self.app.run = lambda task, done: queued.append((task, done))
        self.reviewed().response(Gtk.ResponseType.OK)
        self.assertEqual(len(queued), 1)
        old = self.client
        self.core.reconnect(); self.client = self.core._client
        task, done = queued.pop(); done(task())
        self.assertEqual(old.writes, [])
        self.assertIn('not sent', self.app.status.get_text())
        self.no_writes()

    def test_led_ui_bypass_refuses_and_reload_gate_disables_editing(self):
        self.client.info['firmware_version'] = '1.1.0s2'
        key = (CATEGORIES[0], 'Strip Intensity')
        self.tab.pending[key] = 15; self.tab.drafts[key] = '15'
        payload = {CATEGORIES[0]: {'Strip Intensity': 15}}
        with patch.object(self.tab, 'admit_changes', return_value=payload), patch.object(self.client, 'read_configuration', side_effect=AssertionError('read')) as read, patch.object(self.client, 'read_about', side_effect=AssertionError('info')) as info:
            self.tab.apply_reviewed(dict(self.tab.pending))
        read.assert_not_called(); info.assert_not_called()
        self.assertIn('not sent', self.app.status.get_text()); self.no_writes()
        self.tab.require_fresh_settings()
        self.assertFalse(self.tab.rows.is_sensitive())
        self.assertFalse(self.tab.apply_button.is_sensitive())
        self.assertFalse(self.tab.flash_button.is_sensitive())
        self.assertIsNone(self.tab.apply()); self.no_writes()

    def test_valid_unrelated_edit_records_history(self):
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        self.no_writes()
        self.reviewed().response(Gtk.ResponseType.OK)
        self.assertEqual(self.client.writes, [{'Other': {'Value': 'new'}}])
        self.assertEqual(read_backup(self.history)['settings'], {'Other': {'Value': 'old'}})
        self.assertFalse(self.tab.pending)
        self.assertIn('Applied and verified', self.app.status.get_text())

    def test_existing_dhcp_dependencies_and_unrelated_edits(self):
        for category, section in (('Ethernet Settings', 'Wired Network Setup'), ('WiFi settings', 'WiFi Network Setup')):
            self.tab.revert(); self.show_section(section)
            self.assertFalse(self.expander(category, 'Static IP').is_sensitive())
            self.choose(category, 'Use DHCP', 'Disabled')
            self.assertTrue(self.expander(category, 'Static IP').is_sensitive())
            self.choose(category, 'Static IP', '192.0.2.2')
            self.reviewed().response(Gtk.ResponseType.OK)
            self.assertEqual(list(self.client.writes[-1][category]), ['Use DHCP', 'Static IP'])
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        self.reviewed().response(Gtk.ResponseType.OK)
        self.assertEqual(self.client.writes[-1], {'Other': {'Value': 'new'}})
        self.assertEqual(len(self.client.writes), 3)

    def test_cancel_review_and_actual_undo_preview_write_nothing(self):
        self.show_section('Additional Settings'); self.choose('Other', 'Value', 'new')
        self.reviewed().response(Gtk.ResponseType.CANCEL); self.no_writes()
        self.tab.revert()
        write_backup(self.history, {'format': 'argonaut-settings', 'version': 1, 'settings': {CATEGORIES[0]: {'LedStrip SID Select': 'UltiSID1-B'}}})
        before = self.history.read_bytes()
        self.tab.undo_apply()
        dialog = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Gtk.Dialog))
        allocated_frame(dialog)
        for check in descendants(dialog):
            if isinstance(check, Gtk.CheckButton): check.set_active(True)
        dialog.response(Gtk.ResponseType.OK)
        self.assertFalse(self.tab.pending); self.assertEqual(self.client.writes, [])
        self.assertEqual(self.history.read_bytes(), before)

    def test_actual_native_file_preview_refuses_invalid_batch(self):
        from types import SimpleNamespace
        from c64u_browser.flash_dialog import FlashFiles
        native = FlashFiles.__new__(FlashFiles)
        native.tab = self.tab; native.client = self.ops
        native.dialog = Gtk.Dialog(transient_for=self.window)
        native.folder = lambda: '/Flash/configs'
        native.listing = SimpleNamespace(get_selected_row=lambda: SimpleNamespace(name='synthetic.cfg'))
        native.run = lambda task, done: done(task())
        with patch('c64u_browser.flash_dialog.read_remote', return_value=b'[Keyboard Lighting]\nStrip Intensity=15\n') as read:
            native.preview()
        self.assertEqual(read.call_count, 1)
        dialog = next(w for w in Gtk.Window.get_toplevels() if isinstance(w, Gtk.Dialog) and w is not native.dialog)
        allocated_frame(dialog)
        checks = [w for w in descendants(dialog) if isinstance(w, Gtk.CheckButton)]
        self.assertEqual(len(checks), 1)
        for check in checks: check.set_active(True)
        dialog.response(Gtk.ResponseType.OK)
        self.assertFalse(self.tab.pending); self.no_writes()
