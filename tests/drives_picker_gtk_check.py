"""Real GTK Drives picker handoff on an offline display; no device transport."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.drives_tab import DrivesTab
from c64u_browser.picker_model import PickerEntry
from picker_gtk_check import Host
from c0_gtk_input import Input, pump


class DrivesPickerGtk(unittest.TestCase):
    def setUp(self):
        self.host=Host();self.host.busy=False
        def button(box,label,fn):
            widget=Gtk.Button(label=label);widget.connect('clicked',lambda _:fn());box.append(widget)
            return widget
        self.host.button=button
        self.host.core.execute_drive_image=Mock(return_value={})
        self.host.core.list_directory=lambda path:NS(state='succeeded',error=None,
            result=(path,[PickerEntry('SD','dir')] if path=='/' else [PickerEntry('game.d64','file')]),
            device_id=self.host.session.device_id,session_id=self.host.session.session_id)
        self.tab=DrivesTab(self.host)
        self.host.window.set_child(self.tab.box);self.host.window.present()
        self.tab.bind(NS(host='offline'))
        self.tab.show({'a':{'enabled':True},'b':{'enabled':True}})
        self.picker=None;self.input=None
        pump()

    def tearDown(self):
        if self.input:self.input.close()
        if self.picker:self.picker.response(None,Gtk.ResponseType.CANCEL)
        self.host.window.destroy();pump()

    def test_real_remote_picker_selection_never_mounts_and_cancel_retains(self):
        self.tab.choose_image('b');self.picker=self.tab.chooser
        self.assertEqual(('c64u',),self.picker.model.scopes)
        self.picker.navigate('c64u','/SD');pump()
        self.input=Input(self.picker.dialog)
        row=self.picker.listing.get_first_child().get_next_sibling()
        self.input.click(row,twice=True)
        self.assertIsNone(self.tab.chooser)
        selection=self.tab.cards['b']['selection']
        self.assertEqual('/SD/game.d64',selection.path)
        self.assertEqual(self.host.session.session_id,selection.session_id)
        self.host.core.execute_drive_image.assert_not_called()
        self.input.close();self.input=None
        self.tab.choose_image('b');self.picker=self.tab.chooser
        self.picker.response(None,Gtk.ResponseType.CANCEL)
        self.assertIs(selection,self.tab.cards['b']['selection'])
        self.host.core.execute_drive_image.assert_not_called()

    def test_manual_path_uses_same_gate_and_confirmation_captures_access(self):
        card=self.tab.cards['a']
        card['path'].set_text('/Flash/game.d64')
        self.assertIsNone(card['selection'])
        self.assertIsNone(self.tab.mount('a'))
        card['path'].set_text('/SD/game.d64');card['access'].set_selected(1)
        selection=card['selection'];dialog=self.tab.mount('a');pump()
        card['path'].set_text('/USB1/other.d64');card['access'].set_selected(0)
        dialog.response(Gtk.ResponseType.OK);pump()
        self.host.core.execute_drive_image.assert_called_once_with(selection,'a','readwrite')

    def test_reconnect_confirmation_refuses_even_with_same_facade(self):
        self.tab.cards['a']['path'].set_text('/SD/game.d64')
        dialog=self.tab.mount('a');pump()
        self.host.session=NS(device_id='founders',session_id='new')
        dialog.response(Gtk.ResponseType.OK);pump()
        self.host.core.execute_drive_image.assert_not_called()
        self.assertIn('changed',self.tab.message.get_text())
