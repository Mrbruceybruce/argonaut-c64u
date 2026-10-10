"""Explicit offline GTK C1 checks; display required, no skips."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk
from c64u_browser.api import Entry, BrowserError
from c64u_browser.storage import root_presentation
import test_preferences_ui


class StorageGtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(),'Offline GTK display required')
        trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.fixture=test_preferences_ui.PreferencesUI()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown);self.app=self.fixture.app
        self.client=Mock(storage_roots=['/SD','/USB1','/Flash','/Temp'])
        self.client.list_directory.side_effect=lambda path:(path,[Entry(n,'dir',None) for n in ('SD','USB1','Flash','Temp')] if path=='/' else [Entry('folder','dir',None),Entry('file.d64','file',3)])
        self.app.client=self.client
        self.show('/USB1')

    def show(self,path):
        self.app.show_remote(self.client.list_directory(path))
        self.fixture.pump()

    def test_roots_icons_description_and_usb_action_restoration(self):
        theme=Gtk.IconTheme.get_for_display(self.app.window.get_display())
        for root in ('/SD','/USB1','/Flash','/Temp'):
            self.show(root)
            self.assertTrue(theme.has_icon(root_presentation(root)[1]))
            expected=root not in ('/Flash','/Temp')
            for button in self.app.remote_file_actions:self.assertEqual(expected,button.get_sensitive())
            self.assertEqual(not expected,self.app.storage_description.get_visible())
        self.show('/USB1')
        self.assertTrue(all(b.get_sensitive() for b in self.app.remote_file_actions))
        self.assertFalse(self.app.cancel_button.get_visible())

    def test_paste_drop_keyboard_context_and_direct_handlers_refuse(self):
        app=self.app
        for root in ('/Flash','/Temp'):
            self.show(root)
            app.file_clipboard=(True,app.local,('a',),None)
            app.drag_payload=('token',True,app.local,['a'])
            app.rlist.select_row(app.rlist.get_row_at_index(2))
            with patch.object(app,'start_copy') as copy,patch.object(app,'prompt') as prompt,patch.object(app,'delete_dialog') as delete:
                app.paste_files(False)
                self.assertFalse(app.dropped(app.rlist,False,'token',0,0))
                app.file_key(False,Gdk.KEY_Delete,Gdk.ModifierType(0))
                app.file_key(False,Gdk.KEY_v,Gdk.ModifierType.CONTROL_MASK)
                app.new_folder(False);app.rename_item(False,'file.d64')
                app.new_remote_d64();app.open_disk_image(False,'file.d64')
                app.menu(app.rlist,False,app.rlist.get_row_at_index(2),0,0)
                copy.assert_not_called();prompt.assert_not_called();delete.assert_not_called()
            self.assertFalse(hasattr(app,'popover'))

    def test_navigation_history_parent_and_inaccessible_root_preserve_listing(self):
        app=self.app
        app.navigate(False,'/Temp');self.fixture.pump()
        app.navigate(False,'/Temp/folder');self.fixture.pump()
        self.assertEqual('/Temp/folder',app.remote)
        app.history_move(False,-1);self.fixture.pump();self.assertEqual('/Temp',app.remote)
        app.activate_row(False,app.rlist.get_row_at_index(0));self.fixture.pump()
        self.assertEqual('/Temp',app.remote)
        original=self.client.list_directory.side_effect
        def unavailable(path):
            if path=='/Temp':raise BrowserError('Temp storage unavailable')
            return original(path)
        self.client.list_directory.side_effect=unavailable
        app.refresh_remote();self.fixture.pump()
        self.assertIn('unavailable',app.status_label.get_text())
        self.assertEqual('/Temp',app.rpath.get_text())
        self.assertIsNotNone(app.rlist.get_row_at_index(2))
        app.navigate(False,'/Temp/../Flash');self.fixture.pump()
        self.assertEqual('/Temp',app.remote)

    def test_keyboard_focus_resize_and_browsing_never_activates_a_file(self):
        app=self.app;self.show('/Flash')
        app.rpath.grab_focus();self.fixture.pump()
        self.assertTrue(app.rpath.has_focus() or app.rpath.is_focus() or app.rpath.get_focus_child() is not None)
        with patch.object(app,'open_disk_image') as launch:
            app.activate_row(False,app.rlist.get_row_at_index(2));launch.assert_not_called()
        for width in (900,1200):
            app.window.set_default_size(width,850);self.fixture.pump()
            self.assertGreater(app.rpath.get_width(),0)
            self.assertGreater(app.storage_description.get_height(),0)
        app.rpath.set_text('/Flash/html');app.rpath.emit('activate');self.fixture.pump()
        self.assertEqual('/Flash/html',app.remote)
        app.lpath.grab_focus();self.fixture.pump()

    def test_usb_copy_drop_and_delayed_folder_keep_original_target(self):
        app=self.app
        app.file_clipboard=(True,app.local,('source',),None)
        with patch.object(app,'start_copy') as copy:
            app.paste_files(False);self.assertEqual('/USB1',copy.call_args.args[4])
            app.drag_payload=('token',True,app.local,['source'])
            self.assertTrue(app.dropped(app.rlist,False,'token',0,10000))
            self.assertEqual('/USB1',copy.call_args.args[4])
            self.assertFalse(app.dropped(app.rlist,False,'external-uri',0,0))
            app.drag_payload=('same',False,'/USB1',['source'])
            self.assertFalse(app.dropped(app.rlist,False,'same',0,0))
        with patch.object(app,'prompt') as prompt:
            app.new_folder(False)
            callback=prompt.call_args.args[2]
        self.show('/Temp')
        with patch.object(app,'run_file_job') as launch,patch.object(app.core.files,'create_folder') as create:
            callback('reviewed')
            launch.call_args.args[0]()
            self.assertEqual('/USB1',create.call_args.args[0].path)
            self.assertEqual('reviewed',create.call_args.args[1])

    def test_disappeared_root_refreshes_buttons_and_reports_unavailable(self):
        app=self.app
        self.show('/Temp')
        self.client.list_directory.side_effect=lambda path:('/',[Entry('USB1','dir',None)])
        app.refresh_remote();self.fixture.pump()
        self.assertEqual(['/USB1'],self.client.storage_roots)
        self.assertIn('unavailable',app.status_label.get_text())
        self.assertEqual('/Temp',app.remote)  # Last listing is not replaced by an empty success.
