"""Explicit offline GTK/XTest picker checks; no device or consumer integration."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import Mock
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from c64u_browser.file_picker import FilePicker
from c64u_browser.picker_model import PickerMode, PickerEntry as E
from c0_gtk_input import Input, pump


class Host:
    def __init__(self):
        self.window = Gtk.Window()
        self.session = NS(device_id='founders', session_id='session-1')
        self.listeners = []
        self.calls = []
        self.pending = []
        self.defer = False
        self.admit = True
        self.core = NS(device_session=lambda: self.session, add_listener=self.listen,
                       list_directory=self.list_directory)

    def listen(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def list_directory(self, path):
        self.calls.append(path)
        entries = [E(n, 'dir') for n in ('USB0', 'SD', 'Flash', 'Temp')] if path == '/' else [E('music.sid', 'file')]
        return NS(state='succeeded', result=(path, entries), error=None,
                  device_id=self.session.device_id, session_id=self.session.session_id)

    def run(self, task, done):
        if not self.admit:return False
        done(task())
        return True

    def run_file_job(self, factory, done, failed):
        if not self.admit:return False
        snapshot = factory()
        if self.defer:self.pending.append(lambda: done(snapshot))
        else:done(snapshot)
        return True


class PickerGtk(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ('a.sid', 'b.sid', 'c.sid', 'hidden.prg'):
            (Path(self.tmp.name) / name).write_bytes(b'offline fixture')
        (Path(self.tmp.name) / 'folder').mkdir()
        self.host = Host()
        self.results = Mock()
        self.picker = FilePicker(self.host, self.results, mode=PickerMode.OPEN_FILES,
                                 limit=3, local_path=self.tmp.name)
        self.picker.policy.value = 'double'
        pump()
        self.input = Input(self.picker.dialog)

    def tearDown(self):
        self.input.close()
        self.picker.response(None, Gtk.ResponseType.CANCEL)
        self.host.window.destroy()
        pump()

    def row(self, name):
        row = self.picker.listing.get_first_child()
        while row:
            if row.item[0] == name:return row
            row = row.get_next_sibling()
        self.fail('Missing row: ' + name)

    def test_cancel_once_no_selection_and_unsubscribe(self):
        self.picker.response(None, Gtk.ResponseType.CANCEL)
        self.picker.response(None, Gtk.ResponseType.CANCEL)
        self.results.assert_called_once_with(None)
        self.assertFalse(self.host.listeners)

    def test_escape_cancels_without_returning_selection(self):
        self.input.click(self.row('a.sid'))
        self.input.press('Escape')
        self.results.assert_called_once_with(None)

    def test_explicit_single_file_and_folder_modes(self):
        for mode in (PickerMode.OPEN_FILE, PickerMode.OPEN_FOLDER):
            self.input.close()
            self.picker.response(None, Gtk.ResponseType.CANCEL)
            self.results.reset_mock()
            self.picker = FilePicker(self.host, self.results, mode=mode,
                                     scopes=('core-host',), local_path=self.tmp.name)
            pump();self.input = Input(self.picker.dialog)
            self.assertEqual(Gtk.SelectionMode.SINGLE, self.picker.listing.get_selection_mode())
            if mode == PickerMode.OPEN_FILE:
                self.picker.listing.select_row(self.row('a.sid'))
                expected = str(Path(self.tmp.name) / 'a.sid')
            else:
                self.assertEqual(['folder'], [e.name for e in self.picker.model.entries])
                expected = self.tmp.name
            self.picker.response(None, Gtk.ResponseType.ACCEPT)
            self.results.assert_called_once()
            self.assertEqual(expected, self.results.call_args.args[0][0].path)

    def test_native_ctrl_shift_and_select_all_excludes_parent(self):
        self.input.click(self.row('a.sid'))
        self.assertEqual(('a.sid',), self.picker.names())
        self.input.click(self.row('c.sid'), modifier='Control_L')
        self.assertEqual(('a.sid', 'c.sid'), self.picker.names())
        self.input.click(self.row('a.sid'))
        self.input.click(self.row('c.sid'), modifier='Shift_L')
        self.assertEqual(('a.sid', 'b.sid', 'c.sid'), self.picker.names())
        self.input.press('a', modifier='Control_L')
        self.assertNotIn('..', self.picker.names())
        self.results.assert_not_called()

    def test_double_click_returns_once(self):
        self.input.click(self.row('a.sid'), twice=True)
        self.results.assert_called_once()
        self.assertEqual('a.sid', self.results.call_args.args[0][0].filename)

    def test_keyboard_navigation_enter_directory(self):
        self.row('folder').grab_focus();pump()
        self.input.press('Return')
        self.assertEqual(str(Path(self.tmp.name) / 'folder'), self.picker.model.loaded.path)
        self.assertFalse(self.picker.names())
        self.results.assert_not_called()
        self.row('..').grab_focus();pump();self.input.press('Return')
        self.assertEqual(self.tmp.name, self.picker.model.loaded.path)

    def test_single_click_and_modifier_safety(self):
        self.picker.policy.value = 'single'
        self.input.click(self.row('a.sid'), modifier='Control_L')
        self.input.click(self.row('c.sid'), modifier='Shift_L')
        self.results.assert_not_called()
        self.input.click(self.row('b.sid'))
        self.results.assert_called_once()
        self.assertEqual('b.sid', self.results.call_args.args[0][0].filename)

    def test_pointer_motion_cannot_activate(self):
        self.picker.policy.value = 'single'
        row = self.row('a.sid')
        self.input.move(row);self.input.button(True)
        self.input.move(row, x=160);self.input.button(False)
        self.results.assert_not_called()
        self.assertEqual(self.tmp.name, self.picker.model.loaded.path)

    def test_arrow_navigation_and_enter_select(self):
        self.row('a.sid').grab_focus();pump()
        self.input.press('Down')
        self.assertEqual(('b.sid',), self.picker.names())
        self.input.press('Return')
        self.results.assert_called_once()
        self.assertEqual('b.sid', self.results.call_args.args[0][0].filename)

    def test_session_checked_at_accept_before_event_delivery(self):
        self.picker.navigate('c64u', '/USB0');pump()
        self.picker.listing.select_row(self.row('music.sid'))
        self.host.session = NS(device_id='founders', session_id='new')
        self.picker.response(None, Gtk.ResponseType.ACCEPT)
        self.results.assert_not_called()
        self.assertFalse(self.picker.names())
        self.assertIsNone(self.picker.listing.get_first_child())

    def test_unavailable_root_and_bound_snapshot_mismatch(self):
        for snapshot in (
                NS(state='failed', error=NS(message='Storage unavailable'), result=None),
                NS(state='succeeded', error=None, result=('/SD', []),
                   device_id='founders', session_id='wrong'),
                NS(state='succeeded', error=None, result=('/', []),
                   device_id='founders', session_id='session-1')):
            self.host.core.list_directory = lambda path: snapshot
            self.picker.navigate('c64u', '/SD')
            self.assertIsNone(self.picker.model.loaded)
            self.assertFalse(self.picker.select.get_sensitive())
            self.assertNotEqual('This folder is empty.', self.picker.status.get_text())

    def test_remote_selection_and_flash_browse_only(self):
        self.picker.navigate('c64u', '/Flash');pump()
        self.picker.listing.select_row(self.row('music.sid'))
        self.assertFalse(self.picker.select.get_sensitive())
        self.picker.response(None, Gtk.ResponseType.ACCEPT)
        self.results.assert_not_called()
        self.picker.navigate('c64u', '/USB0');pump()
        self.picker.listing.select_row(self.row('music.sid'))
        self.picker.response(None, Gtk.ResponseType.ACCEPT)
        self.assertEqual('session-1', self.results.call_args.args[0][0].session_id)
        self.assertEqual(['/Flash', '/USB0'], self.host.calls)

    def test_reconnect_clears_pending_and_selected_rows(self):
        self.picker.navigate('c64u', '/USB0');pump()
        self.picker.listing.select_row(self.row('music.sid'))
        self.host.session = NS(device_id='founders', session_id='session-2')
        self.host.listeners[0](None);pump()
        self.assertIsNone(self.picker.model.loaded)
        self.assertFalse(self.picker.select.get_sensitive())
        self.assertFalse(self.picker.names())
        self.picker.response(None, Gtk.ResponseType.ACCEPT)
        self.results.assert_not_called()

    def test_stale_completion_and_cancel(self):
        self.host.defer = True
        self.picker.navigate('c64u', '/USB0')
        self.picker.navigate('core-host', self.tmp.name)
        self.host.pending.pop()()
        self.assertEqual('core-host', self.picker.model.loaded.scope)
        self.picker.navigate('c64u', '/SD')
        self.picker.response(None, Gtk.ResponseType.CANCEL)
        self.host.pending.pop()()
        self.results.assert_called_once_with(None)

    def test_admission_refusal_never_submits(self):
        self.host.admit = False
        self.picker.navigate('c64u', '/USB0')
        self.assertFalse(self.host.calls)
        self.assertFalse(self.picker.select.get_sensitive())
        self.assertIn('operation', self.picker.status.get_text())

    def test_no_mutation_controls_and_filter(self):
        labels = []
        def visit(widget):
            if isinstance(widget, Gtk.Button):labels.append(widget.get_label())
            child = widget.get_first_child()
            while child:visit(child);child = child.get_next_sibling()
        visit(self.picker.dialog)
        self.assertEqual({'Cancel', 'Select', 'This Computer', 'C64 Ultimate', 'Parent folder', 'Refresh'}, set(labels))
        self.assertNotIn('hidden.prg', [e.name for e in self.picker.model.entries])
        self.assertFalse(self.row('..').get_selectable())


if __name__ == '__main__':
    unittest.main()
