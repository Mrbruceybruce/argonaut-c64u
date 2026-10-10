"""Focused C4 presentation checks; isolated X11/XTest display, no device access."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
import c1_gtk_check
from c0_gtk_input import Input, pump
from c64u_browser.file_service import FileLocation, PartialUpload


class FilesPolish(unittest.TestCase):
    setUp = c1_gtk_check.StorageGtk.setUp
    show = c1_gtk_check.StorageGtk.show

    def labels(self, widget):
        return [w.get_text() for w in self.fixture.walk(widget) if isinstance(w, Gtk.Label)]

    def test_bounded_names_sizes_and_accessibility(self):
        app = self.app
        name = 'long filename ' * 15 + '.d64'
        app.populate(app.llist, [(name, False, 174848), ('short', False, 2)])
        row = app.llist.get_row_at_index(1)
        content = row.get_child()
        label = content.get_first_child().get_next_sibling()
        size = content.get_last_child()
        self.assertEqual(name, row.item[0])
        self.assertEqual(name, label.get_text())
        self.assertEqual(name, label.get_tooltip_text())
        self.assertEqual('174,848 bytes', size.get_text())
        self.assertTrue(Gtk.test_accessible_has_property(row, Gtk.AccessibleProperty.LABEL))
        for width, height in ((900, 650), (1200, 850), (1600, 1000)):
            app.window.set_default_size(width, height);self.fixture.pump()
            self.assertLessEqual(app.llist.get_width(), app.llist.get_parent().get_width())
            self.assertGreater(label.get_width(), 0)
            self.assertGreater(size.get_width(), 0)
            self.assertEqual(content.get_last_child().get_allocation().x + size.get_width(),
                             app.llist.get_row_at_index(2).get_child().get_last_child().get_allocation().x +
                             app.llist.get_row_at_index(2).get_child().get_last_child().get_width())
        for widget, text in ((app.lpath, 'This Computer path'), (app.rpath, 'C64 Ultimate path'),
                             (app.llist, 'This Computer files'), (app.rlist, 'C64 Ultimate files')):
            self.assertTrue(Gtk.test_accessible_has_property(widget, Gtk.AccessibleProperty.LABEL), text)

    def test_keyboard_menu_preserves_group_escape_restores_focus(self):
        app = self.app
        app.populate(app.llist, [('a', False, 1), ('b', False, 2)])
        a, b = app.llist.get_row_at_index(1), app.llist.get_row_at_index(2)
        a.grab_focus();app.llist.select_row(a);app.llist.select_row(b)
        inp = Input(app.window);self.addCleanup(inp.close)
        with patch.object(app, 'activate_row') as activate, patch.object(app, 'start_copy') as copy:
            for modifier, key in ((None, 'Menu'), ('Shift_L', 'F10')):
                if modifier:inp.key(modifier, True)
                inp.key(key, True);inp.key(key, False)
                if modifier:inp.key(modifier, False)
                pump()
                self.assertTrue(app.popover.get_visible())
                self.assertEqual([a, b], app.llist.get_selected_rows())
                self.assertIn('Delete selected…', self.labels(app.popover))
                inp.key('Escape', True);inp.key('Escape', False);pump()
                self.assertFalse(app.popover.get_visible())
                self.assertIs(app.window.get_focus(), a)
            activate.assert_not_called();copy.assert_not_called()

    def test_menu_action_does_not_steal_dialog_focus(self):
        app = self.app
        app.populate(app.llist, [('a', False, 1)])
        row = app.llist.get_row_at_index(1)
        row.grab_focus();app.llist.select_row(row)
        inp = Input(app.window);self.addCleanup(inp.close)
        inp.key('Menu', True);inp.key('Menu', False);pump()
        dialog = Gtk.Dialog(transient_for=app.window, modal=True)
        entry = Gtk.Entry();dialog.get_content_area().append(entry)
        self.addCleanup(dialog.destroy)
        def rename(*_):
            dialog.present();entry.grab_focus()
        with patch.object(app, 'rename_item', side_effect=rename):
            button = next(w for w in self.fixture.walk(app.popover)
                          if isinstance(w, Gtk.Button) and w.get_label() == 'Rename…')
            button.emit('clicked');pump(.3)
        self.assertTrue(entry.has_focus() or entry.get_focus_child() is not None)
        self.assertEqual([row], app.llist.get_selected_rows())

    def test_keyboard_menu_does_not_select_unselected_focus(self):
        app = self.app
        row = app.rlist.get_row_at_index(2)
        row.grab_focus();app.rlist.unselect_all()
        app.keyboard_file_menu(False);self.fixture.pump()
        self.assertEqual([], app.rlist.get_selected_rows())
        self.assertIn('New folder…', self.labels(app.popover))
        self.assertNotIn('Delete…', self.labels(app.popover))
        app.popover.popdown();self.fixture.pump()
        for root in ('/Flash', '/Temp'):
            self.show(root)
            app.rlist.select_row(app.rlist.get_row_at_index(2))
            app.keyboard_file_menu(False)
            self.assertFalse(app.popover.get_visible())

    def test_recovery_visibility_session_and_captured_target(self):
        app = self.app
        self.assertFalse(app.partial_button.get_visible())
        partial = PartialUpload(FileLocation.c64u('/USB1/partial'), 'device', 'session')
        app.partial_upload = partial
        with patch.object(app.core, 'device_session', return_value=SimpleNamespace(
                device_id='device', session_id='session')):
            app.update_partial_recovery()
            self.assertTrue(app.partial_button.get_visible())
            with patch.object(app, 'delete_dialog') as delete:
                app.partial_button.emit('clicked')
                delete.assert_called_once_with(False, ['/USB1/partial'], self.client, partial=partial)
            app.busy = True;app.update_partial_recovery()
            self.assertFalse(app.partial_button.get_sensitive())
            app.busy = False
        app.update_partial_recovery()
        self.assertFalse(app.partial_button.get_visible())
        self.assertIs(partial, app.partial_upload)
        app.partial_upload = None;app.update_partial_recovery()
        self.assertFalse(app.partial_button.get_visible())

    def test_disconnected_no_roots_and_empty_folder_are_distinct(self):
        app = self.app
        app.client = None;app.drive_bars[False].refresh()
        self.assertTrue(any('Connect to a C64 Ultimate' in t for t in self.labels(app.drive_bars[False].box)))
        app.client = self.client;self.client.storage_roots = []
        app.drive_bars[False].refresh()
        self.assertIn('No storage locations found. Use Refresh to check again.', self.labels(app.drive_bars[False].box))
        self.client.storage_roots = ['/SD'];app.show_remote(('/SD', []))
        self.assertNotIn('No storage locations found. Use Refresh to check again.', self.labels(app.drive_bars[False].box))
        self.assertEqual('..', app.rlist.get_row_at_index(0).item[0])
        self.assertIsNone(app.rlist.get_row_at_index(1))
        self.assertIn('C64 Ultimate', app.file_pane_labels[False].get_text())
        self.assertIn('This Computer', app.file_pane_labels[True].get_text())
        tips = [w.get_tooltip_text() for w in self.fixture.walk(app.tabs.get_nth_page(0)) if isinstance(w, Gtk.Button)]
        self.assertIn('New D64 disk on C64 Ultimate…', tips)
