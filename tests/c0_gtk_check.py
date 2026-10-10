"""Explicit offline C0 checks; X11/XTest display and memory GSettings required.

Run with ARGONAUT_UI_TESTS=1 GDK_BACKEND=x11 GSETTINGS_BACKEND=memory.
Missing prerequisites fail rather than silently skipping event coverage.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio
from c64u_browser.api import Entry
from c64u_browser.file_selection import ClickPolicy
from c0_gtk_input import Input, pump
import test_preferences_ui


class Policy(unittest.TestCase):
    def test_missing_schema_and_key_fallback(self):
        for source in (None, Mock(lookup=Mock(return_value=None)),
                       Mock(lookup=Mock(return_value=Mock(has_key=Mock(return_value=False))))):
            with patch.object(Gio.SettingsSchemaSource, 'get_default', return_value=source):
                policy = ClickPolicy()
                self.assertEqual('double', policy.value)
                self.assertIsNone(policy.settings)
                policy.close()

    def test_invalid_unreadable_and_live_changes(self):
        settings = Mock()
        with patch.object(Gio.Settings, 'new_full', return_value=settings), patch.object(
                Gio.SettingsSchemaSource, 'get_default', return_value=Mock()):
            settings.get_string.return_value = 'invalid'
            policy = ClickPolicy(); self.addCleanup(policy.close)
            self.assertEqual('double', policy.value)
            listener = Mock(); policy.listeners.append(listener)
            settings.get_string.return_value = 'single'
            settings.connect.call_args.args[1]()
            self.assertEqual('single', policy.value);listener.assert_called_once()
            settings.get_string.side_effect = RuntimeError('unreadable')
            policy.changed();self.assertEqual('double', policy.value)
            settings.set_string.assert_not_called()

    def test_real_gsettings_live_notification_in_memory_only(self):
        self.assertEqual('memory', os.environ.get('GSETTINGS_BACKEND'))
        policy = ClickPolicy();self.addCleanup(policy.close)
        self.assertIsNotNone(policy.settings, 'This explicit test requires the Nautilus schema')
        original = policy.settings.get_string('click-policy')
        self.addCleanup(policy.settings.set_string, 'click-policy', original)
        policy.settings.set_string('click-policy', 'single');pump()
        self.assertEqual('single', policy.value)
        policy.settings.set_string('click-policy', 'double');pump()
        self.assertEqual('double', policy.value)


class Selection(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Offline GTK display required')
        trap = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.fixture = test_preferences_ui.PreferencesUI()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.app = self.fixture.app
        self.base = Path(self.fixture.temp.name)/'files';self.base.mkdir()
        for name in ('a', 'b', 'c'):(self.base/name).write_text(name)
        (self.base/'folder').mkdir();(self.base/'folder'/'a').write_text('child')
        self.app.local = self.base;self.app.refresh_local()
        self.client = Mock(storage_roots=['/USB1', '/SD', '/Flash', '/Temp'])
        self.entries = [Entry('folder','dir',None), Entry('a','file',1), Entry('b','file',1), Entry('c','file',1)]
        self.client.list_directory.side_effect = lambda path:(path,self.entries)
        self.app.client = self.client;self.app.show_remote(('/USB1',self.entries))
        self.policy('double')
        self.input = Input(self.app.window);self.addCleanup(self.input.close)
        self.assertFalse(self.app.llist.get_activate_on_single_click())

    def policy(self, value):
        self.app.file_click_policy.value = value
        for callback in self.app.file_click_policy.listeners:callback()

    def row(self, name, local=True):
        listing = self.app.llist if local else self.app.rlist
        row = listing.get_first_child()
        while row:
            if row.item[0] == name:return row
            row = row.get_next_sibling()
        self.fail('Missing row '+name)

    def selected(self, local=True):
        return [r.item[0] for r in (self.app.llist if local else self.app.rlist).get_selected_rows()]

    def test_default_click_selects_double_activates(self):
        with patch.object(self.app, 'activate_row') as activate:
            self.input.click(self.row('a'))
            self.assertEqual(['a'],self.selected());activate.assert_not_called()
            pump(.5)
            self.input.click(self.row('b'),twice=True)
            self.assertEqual(['b'],self.selected())
            activate.assert_called_once_with(True,self.row('b'))

    def test_single_click_once_and_modifier_native_selection(self):
        self.policy('single')
        with patch.object(self.app, 'activate_row') as activate:
            self.input.click(self.row('a'),twice=True)
            activate.assert_called_once_with(True,self.row('a'))
            activate.reset_mock()
            self.input.click(self.row('c'),modifier='Control_L')
            self.assertEqual(['a','c'],self.selected());activate.assert_not_called()
            self.input.click(self.row('c'),modifier='Control_L')
            self.assertEqual(['a'],self.selected());activate.assert_not_called()
            self.input.click(self.row('c'),modifier='Shift_L')
            self.assertEqual(['a','b','c'],self.selected());activate.assert_not_called()
            pump(.5);self.input.click(self.row('b'))
            self.assertEqual(['b'],self.selected());activate.assert_called_once()

    def test_double_mode_ctrl_shift_and_parent_ctrl_a(self):
        with patch.object(self.app, 'activate_row') as activate:
            self.input.click(self.row('a'))
            self.input.click(self.row('c'),modifier='Control_L')
            self.assertEqual(['a','c'],self.selected())
            self.input.click(self.row('c'),modifier='Shift_L')
            self.assertEqual(['a','b','c'],self.selected())
            self.input.press('a','Control_L')
            self.assertEqual(['folder','a','b','c'],self.selected())
            self.assertFalse(self.row('..').get_selectable());self.assertTrue(self.row('..').get_activatable())
            activate.assert_not_called()

    def test_empty_background_and_independent_panes(self):
        for value in ('double','single'):
            self.policy(value)
            with patch.object(self.app,'activate_row') as activate:
                self.input.click(self.row('a'));self.input.click(self.row('b',False))
                self.assertEqual(['a'],self.selected());self.assertEqual(['b'],self.selected(False))
                self.input.click(self.app.rlist,y=self.app.rlist.get_height()-10,modifier='Control_L')
                self.assertEqual(['b'],self.selected(False))
                self.input.click(self.app.rlist,y=self.app.rlist.get_height()-10)
                self.assertEqual([],self.selected(False));self.assertEqual(['a'],self.selected())
                self.assertLessEqual(activate.call_count,2 if value=='single' else 0)

    def test_arrows_enter_path_text_focus_and_native_theme(self):
        with patch.object(self.app,'activate_row') as activate:
            self.input.click(self.row('a'));self.input.press('Down');self.input.press('Return')
            activate.assert_called_once_with(True,self.row('b'))
        self.app.rpath.grab_focus();pump()
        self.assertFalse(self.app.active_file_pane)
        self.input.press('a','Control_L')
        self.assertEqual((0,len(self.app.rpath.get_text())),self.app.rpath.get_selection_bounds())
        self.assertEqual([],self.selected(False));self.assertEqual(['b'],self.selected())
        self.app.lpath.grab_focus();pump();self.assertTrue(self.app.active_file_pane)
        self.assertTrue(self.app.file_pane_boxes[False].get_sensitive())
        css = self.app.file_pane_css.to_string()
        self.assertNotIn('row:selected',css);self.assertNotIn('#5e5c64',css)
        self.assertIn('argonaut-file-pane-active',css)

    def test_refresh_retains_survivors_navigation_does_not_resurrect(self):
        self.app.select_names(self.app.llist,('a','b'))
        (self.base/'b').unlink();self.app.refresh_local()
        self.assertEqual(['a'],self.selected())
        self.app.navigate(True,str(self.base/'folder'));self.assertEqual([],self.selected())
        self.app.navigate(True,str(self.base));self.assertEqual([],self.selected())
        self.app.select_names(self.app.rlist,('a','b'))
        self.app.show_remote(('/USB1',self.entries[:2]));self.assertEqual(['a'],self.selected(False))
        self.app.show_remote(('/SD',self.entries));self.assertEqual([],self.selected(False))
        self.app.select_names(self.app.rlist,('a',))
        self.app.client = Mock();self.app.show_remote(('/SD',self.entries))
        self.assertEqual([],self.selected(False))

    def test_directory_and_parent_activation(self):
        for policy in ('double','single'):
            self.policy(policy)
            self.input.click(self.row('folder'),twice=policy=='double');pump()
            self.assertEqual(self.base/'folder',self.app.local)
            self.assertEqual([],self.selected())
            pump(.5)
            self.input.click(self.row('..'),twice=policy=='double');pump(.5)
            self.assertEqual(self.base,self.app.local);self.assertEqual([],self.selected())

    def test_right_click_preserves_group_or_selects_one_no_activation(self):
        self.policy('single');self.app.select_names(self.app.llist,('a','b'))
        with patch.object(self.app,'menu') as menu,patch.object(self.app,'activate_row') as activate:
            self.input.click(self.row('a'),button=3);self.assertEqual(['a','b'],self.selected())
            menu.assert_called_once();menu.reset_mock()
            self.input.click(self.row('c'),button=3);self.assertEqual(['c'],self.selected())
            self.input.click(self.app.llist,button=3,y=self.app.llist.get_height()-10)
            self.assertEqual([],self.selected());self.assertIsNone(menu.call_args.args[2])
            activate.assert_not_called()

    def test_real_context_menu_opens_without_activation(self):
        with patch.object(self.app,'activate_row') as activate:
            self.input.click(self.row('a'),button=3)
            self.assertTrue(self.app.popover.get_visible());activate.assert_not_called()
            self.input.press('Escape');pump();self.assertFalse(self.app.popover.get_visible())

    def test_drag_preserves_group_copy_target_without_activation(self):
        for mode in ('single','double'):
            pump(.6)
            self.policy(mode);self.app.select_names(self.app.llist,('a','b'))
            with patch.object(self.app,'activate_row') as activate,patch.object(self.app,'start_copy') as copy:
                self.input.move(self.row('a'));self.input.button(True)
                self.input.move(self.row('a'),x=100)
                self.input.move(self.row('a'),x=115)
                self.assertIsNotNone(self.app.drag_payload)
                self.assertEqual(['a','b'],self.app.drag_payload[3])
                self.input.move(self.app.rlist,x=100,y=self.app.rlist.get_height()-15)
                pump(.1)
                self.input.move(self.app.rlist,x=110,y=self.app.rlist.get_height()-15)
                self.input.button(False);pump(.2)
                copy.assert_called_once_with(True,self.base,['a','b'],False,'/USB1',self.client)
                activate.assert_not_called();self.assertEqual(['a','b'],self.selected())

    def test_keyboard_copy_captures_source_and_paste_destination(self):
        self.input.click(self.row('a'));self.input.press('c','Control_L')
        self.assertEqual((True,self.base,('a',),None),self.app.file_clipboard)
        self.app.select_names(self.app.llist,('b',))
        self.input.click(self.row('c',False))
        with patch.object(self.app,'start_copy') as copy:
            self.input.press('v','Control_L')
            copy.assert_called_once_with(True,self.base,('a',),False,'/USB1',self.client)

    def test_stale_release_live_policy_and_replaced_listing(self):
        self.policy('single')
        with patch.object(self.app,'activate_row') as activate:
            self.input.move(self.row('a'));self.input.button(True)
            self.policy('double');self.input.button(False);activate.assert_not_called()
            self.policy('single');pump(.5)
            self.input.move(self.row('b'));self.input.button(True)
            self.app.refresh_local();self.input.button(False);activate.assert_not_called()
            self.input.click(self.row('c'));activate.assert_called_once_with(True,self.row('c'))

    def test_flash_temp_real_keys_refuse_operations_and_file_activation(self):
        self.policy('single')
        for root in ('/Flash','/Temp'):
            self.app.show_remote((root,[Entry('file.d64','file',1)]));pump()
            with patch.object(self.app,'open_disk_image') as image,patch.object(self.app,'start_copy') as copy,patch.object(self.app,'delete_dialog') as delete:
                self.input.click(self.row('file.d64',False))
                self.input.press('Delete');self.input.press('c','Control_L');self.input.press('v','Control_L')
                image.assert_not_called();copy.assert_not_called();delete.assert_not_called()

    def test_unselected_and_same_pane_drag_never_activates_or_copies(self):
        self.policy('single');self.app.select_names(self.app.llist,('a','b'))
        with patch.object(self.app,'activate_row') as activate,patch.object(self.app,'start_copy') as copy:
            self.input.move(self.row('c'));self.input.button(True)
            self.input.move(self.row('c'),x=100);self.input.move(self.row('c'),x=115)
            self.assertIsNotNone(self.app.drag_payload)
            self.assertEqual(['c'],self.app.drag_payload[3])
            self.input.move(self.app.llist,x=120,y=self.app.llist.get_height()-15)
            self.input.move(self.app.llist,x=135,y=self.app.llist.get_height()-15)
            self.input.button(False);pump(.3)
            self.assertEqual(['c'],self.selected());activate.assert_not_called();copy.assert_not_called()

    def test_background_drag_does_not_clear_selection(self):
        self.app.select_names(self.app.llist,('a','b'))
        with patch.object(self.app,'activate_row') as activate:
            y = self.app.llist.get_height()-20
            self.input.move(self.app.llist,x=20,y=y);self.input.button(True)
            self.input.move(self.app.llist,x=150,y=y);self.input.button(False)
            self.assertEqual(['a','b'],self.selected());activate.assert_not_called()

    def test_delete_key_requests_confirmation_for_captured_selection(self):
        self.input.click(self.row('a'));self.input.click(self.row('b'),modifier='Control_L')
        with patch.object(self.app,'delete_dialog') as confirm,patch.object(self.app.core.files,'execute_delete') as execute:
            self.input.press('Delete')
            confirm.assert_called_once_with(True,[self.base/'a',self.base/'b'],self.client)
            self.app.select_names(self.app.llist,('c',))
            self.assertEqual([self.base/'a',self.base/'b'],confirm.call_args.args[1])
            execute.assert_not_called()

    def test_pointer_motion_does_not_change_pane_focus(self):
        self.app.lpath.grab_focus();pump()
        focus = self.app.window.get_focus()
        self.input.move(self.row('b',False))
        self.assertTrue(self.app.active_file_pane)
        self.assertIs(focus,self.app.window.get_focus())
        remote_button = self.app.remote_file_actions[0]
        remote_button.grab_focus();pump()
        self.assertFalse(self.app.active_file_pane)
        self.assertIs(remote_button,self.app.window.get_focus())

    def begin_activation_press(self, mode, row):
        self.policy(mode)
        if mode == 'double':
            self.input.click(row)
        else:
            self.input.move(row)
        # No wait between the first click and the second press in double mode.
        self.input.button(True)

    def test_rapid_click_then_drag_does_not_navigate_or_open_disk(self):
        (self.base/'disk.d64').write_bytes(b'offline fixture; must not be opened')
        self.app.refresh_local();pump()
        for name in ('folder','disk.d64'):
            with self.subTest(name=name), patch.object(self.app,'activate_row',wraps=self.app.activate_row) as activate, patch.object(self.app,'navigate') as navigate, patch.object(self.app,'open_disk_image') as viewer, patch.object(self.app,'start_copy') as copy:
                self.begin_activation_press('double',self.row(name))
                at_second_press = activate.call_count
                self.input.move(self.row(name),x=100);self.input.move(self.row(name),x=115)
                self.assertIsNotNone(self.app.drag_payload)
                self.assertEqual((True,self.base,[name]),self.app.drag_payload[1:])
                self.assertEqual(0,at_second_press)
                activate.assert_not_called();navigate.assert_not_called();viewer.assert_not_called()
                self.assertEqual(self.base,self.app.local)
                self.input.press('Escape');self.input.button(False);pump(.2)
                activate.assert_not_called();copy.assert_not_called()
            pump(.5)  # Separate cases, never the select-then-drag sequence.

    def test_completed_clicks_activate_only_on_release_once(self):
        for mode in ('double','single'):
            with self.subTest(mode=mode),patch.object(self.app,'activate_row') as activate:
                self.begin_activation_press(mode,self.row('a'))
                activate.assert_not_called()
                self.input.button(False)
                # Input.button drains GTK's event/idle work; no timeout is awaited.
                activate.assert_called_once_with(True,self.row('a'))
                pump(.1);activate.assert_called_once()
            pump(.5)

    def test_single_press_then_drag_has_no_activation(self):
        with patch.object(self.app,'activate_row') as activate,patch.object(self.app,'start_copy') as copy:
            self.begin_activation_press('single',self.row('a'))
            activate.assert_not_called()
            self.input.move(self.row('a'),x=100);self.input.move(self.row('a'),x=115)
            self.assertIsNotNone(self.app.drag_payload)
            self.assertEqual((True,self.base,['a']),self.app.drag_payload[1:])
            self.input.press('Escape');self.input.button(False)
            activate.assert_not_called();copy.assert_not_called()

    def test_pending_gesture_cancelled_before_release(self):
        for mode in ('double','single'):
            for cancel in ('escape','gesture'):
                with self.subTest(mode=mode,cancel=cancel),patch.object(self.app,'activate_row') as activate:
                    self.begin_activation_press(mode,self.row('a'))
                    activate.assert_not_called()
                    if cancel == 'escape':self.input.press('Escape')
                    else:self.app.llist.file_activation.click.reset()
                    self.input.button(False);activate.assert_not_called()
                pump(.5)

    def test_pending_rebuilt_row_never_activates_replacement(self):
        for mode in ('double','single'):
            with self.subTest(mode=mode),patch.object(self.app,'activate_row') as activate:
                original = self.row('a')
                self.begin_activation_press(mode,original)
                self.app.refresh_local();pump()
                self.assertIsNot(original,self.row('a'))
                self.input.button(False);activate.assert_not_called()
            pump(.5)

    def test_pending_remote_client_root_change_discards_activation(self):
        for mode in ('double','single'):
            with self.subTest(mode=mode),patch.object(self.app,'activate_row') as activate:
                original = self.row('a',False)
                self.begin_activation_press(mode,original)
                self.app.client = Mock(storage_roots=['/SD'])
                self.app.show_remote(('/SD',self.entries));pump()
                self.assertIsNot(original,self.row('a',False))
                self.input.button(False);activate.assert_not_called()
            pump(.5)

    def test_modifier_double_clicks_and_changed_release_row_do_not_activate(self):
        for mode in ('double','single'):
            self.policy(mode)
            with self.subTest(mode=mode),patch.object(self.app,'activate_row') as activate:
                self.input.click(self.row('a'),modifier='Control_L',twice=True)
                self.input.click(self.row('c'),modifier='Shift_L',twice=True)
                activate.assert_not_called()
                pump(.5)
                self.begin_activation_press(mode,self.row('a'))
                self.input.move(self.row('b'))
                self.input.press('Escape');self.input.button(False)
                activate.assert_not_called()
            pump(.5)

    def test_enter_activation_is_synchronous_without_pointer_idle(self):
        from c64u_browser import file_selection
        self.input.click(self.row('a'))
        with patch.object(self.app,'activate_row') as activate,patch.object(file_selection.GLib,'idle_add',wraps=file_selection.GLib.idle_add) as idle:
            self.input.key('Return',True)
            activate.assert_called_once_with(True,self.row('a'))
            idle.assert_not_called()
            self.input.key('Return',False)
