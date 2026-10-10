"""Explicit offline C2 presentation checks; a GTK display is required, no skips."""
import unittest
from unittest.mock import patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
import c1_gtk_check
from c64u_browser.file_service import FileLocation,PartialUpload
from c64u_browser.app_preferences import show_preferences
from c64u_browser.profiles import Preferences

class BackupUiRetirement(unittest.TestCase):
    setUp=c1_gtk_check.StorageGtk.setUp
    show=c1_gtk_check.StorageGtk.show

    def test_files_layout_and_no_backup_entry_points(self):
        app=self.app;files=app.tabs.get_nth_page(0)
        children=[];w=files.get_first_child()
        while w:children.append(w);w=w.get_next_sibling()
        self.assertEqual(2,len(children))
        self.assertIsInstance(children[1],Gtk.Paned)
        self.assertIs(app.partial_button,children[0].get_first_child())
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
        for tip in ('Copy','Paste','New folder…','New D64 disk on C64U…'):self.assertIn(tip,tips)

    def test_partial_upload_recovery_keeps_exact_target(self):
        app=self.app
        partial=PartialUpload(FileLocation.c64u('/USB1/c64u-part-owned'),'device','session')
        app.partial_upload=partial;app.partial_button.set_sensitive(True)
        with patch.object(app,'delete_dialog') as delete:
            app.partial_button.emit('clicked')
            delete.assert_called_once_with(False,[partial.location.path],self.client,partial=partial)

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
