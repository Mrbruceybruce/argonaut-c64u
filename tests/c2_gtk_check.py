"""Explicit offline C2 presentation checks; a GTK display is required, no skips."""
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
import c1_gtk_check
from c64u_browser.app_preferences import show_preferences
from c64u_browser.profiles import Preferences

class BackupUiRetirement(unittest.TestCase):
    def setUp(self):
        c1_gtk_check.StorageGtk.setUp(self)
        from test_core import FakeClient, FakeCredentials
        from c64u_browser.profiles import Profile
        self.app.core._client_factory = FakeClient
        self.app.core._credentials = FakeCredentials()
        self.app.recovery.next_check = float('inf')
        self.profile = Profile.new('Offline fixture', '192.0.2.20', device_id='ABC123')
        self.app.core.connect(self.profile)
        self.session = self.app.core.device_session()
        self.assertTrue(self.session.session_id)
        self.client = self.app.core._client
        from unittest.mock import Mock
        from c64u_browser.api import Entry
        self.client.list_directory = Mock(side_effect=lambda path: (path, [
            Entry('folder', 'dir', None), Entry('file.d64', 'file', 3)]))
        self.app.client = self.client
        self.show('/USB1')

    def test_bound_picker_selection_rejects_replaced_session(self):
        from c64u_browser.drives_selection import remote_selection, validate_selection
        from c64u_browser.picker_model import PickerError
        selection = remote_selection('/USB1/file.d64', self.session)
        self.assertEqual(selection, validate_selection(selection, self.app.core.device_session()))
        self.app.core.connect(self.profile)
        self.assertNotEqual(self.session, self.app.core.device_session())
        with self.assertRaises(PickerError):
            validate_selection(selection, self.app.core.device_session())

    show=c1_gtk_check.StorageGtk.show

    def test_files_layout_and_no_backup_entry_points(self):
        app=self.app;files=app.tabs.get_nth_page(0)
        children=[];w=files.get_first_child()
        while w:children.append(w);w=w.get_next_sibling()
        self.assertEqual(1,len(children))
        self.assertIsInstance(children[0],Gtk.Paned)
        self.assertFalse(hasattr(app,'partial_button'))
        labels=[w.get_label() for w in self.fixture.walk(app.window) if isinstance(w,Gtk.Button)]
        self.assertNotIn('Back up USB/SD…',labels);self.assertNotIn('Restore USB/SD…',labels)
        for name in ('backup_usb','restore_usb','restore_preview','usb_report','usb_backup_button','usb_restore_button'):
            self.assertFalse(hasattr(app,name),name)
        titles=[app.tabs.get_tab_label_text(app.tabs.get_nth_page(i)) for i in range(app.tabs.get_n_pages())]
        self.assertFalse(any('Backup' in title for title in titles))
        for width,height in ((900,650),(1200,850)):
            app.window.set_default_size(width,height);self.fixture.pump()
            self.assertGreater(app.llist.get_width(),0);self.assertGreater(app.rlist.get_width(),0)
            self.assertTrue(app.tabs.child_focus(Gtk.DirectionType.TAB_FORWARD))
        self.assertFalse(app.cancel_button.get_visible())

    def test_copy_paste_upload_download_and_context_actions(self):
        app=self.app
        app.populate(app.llist,[('local.d64',False,3)])
        app.llist.select_row(app.llist.get_row_at_index(1))
        with patch.object(app,'start_copy') as copy:
            app.copy_selection(True);app.paste_files(False)
            copy.assert_called_once_with(True,app.local,('local.d64',),False,'/USB1',self.client)
        app.rlist.select_row(app.rlist.get_row_at_index(2))
        with patch.object(app,'start_copy') as copy:
            app.copy_selection(False);app.paste_files(True)
            copy.assert_called_once_with(False,'/USB1',('file.d64',),True,app.local,self.client)
        app.menu(app.rlist,False,app.rlist.get_row_at_index(2),0,0)
        labels=[w.get_label() for w in self.fixture.walk(app.popover) if isinstance(w,Gtk.Button)]
        for label in ('Copy','Paste','Rename…','Delete…','Open disk image','Mount…'):self.assertIn(label,labels)
        app.popover.popdown();self.fixture.pump()
        tips=[w.get_tooltip_text() for w in self.fixture.walk(app.tabs.get_nth_page(0)) if isinstance(w,Gtk.Button)]
        for tip in ('Copy','Paste','New folder…','New D64 disk on C64 Ultimate…'):self.assertIn(tip,tips)

    def test_hidden_legacy_root_survives_settings_changes_and_defaults(self):
        app=self.app;sentinel='/missing/legacy-backups'
        app.preferences.usb_backup_root=sentinel;app.preferences.save()
        dialog=show_preferences(app);self.fixture.pump()
        general=dialog.pages.get_nth_page(0)
        labels=[w.get_text() for w in self.fixture.walk(general) if isinstance(w,Gtk.Label)]
        self.assertNotIn('USB/SD backup root',labels)
        check=next(w for w in self.fixture.walk(general) if isinstance(w,Gtk.CheckButton))
        check.set_active(not check.get_active());self.fixture.pump()
        restore=next(w for w in self.fixture.walk(general) if isinstance(w,Gtk.Button) and w.get_label()=='Restore defaults…')
        restore.emit('clicked');dialog.restore_prompt.response(Gtk.ResponseType.OK);self.fixture.pump()
        dialog.response(Gtk.ResponseType.CLOSE);self.fixture.pump()
        self.assertEqual(sentinel,app.preferences.usb_backup_root)
        self.assertEqual(sentinel,Preferences(app.preferences.path).load().usb_backup_root)
