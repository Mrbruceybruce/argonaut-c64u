"""Offline Drives selection and confirmation binding; fake Core transports only."""
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from c64u_browser.drives_selection import remote_selection, validate_selection
from c64u_browser.drives_tab import DrivesTab
from c64u_browser.picker_model import PickerMode, DRIVES, PickerError
from c64u_browser.scheduler import DeviceSession
from c64u_browser.api import BrowserError
from tests import test_core


class Dialog:
    def __init__(self,**kw):pass
    def add_button(self,*args):pass
    def get_content_area(self):return self
    def append(self,*args):pass
    def connect(self,signal,fn):self.callback=fn
    def present(self):pass
    def destroy(self):pass
    def respond(self,ok=True):self.callback(self,int(ok))


class DrivesPicker(unittest.TestCase):
    def setUp(self):
        self.fixture=test_core.CoreTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.client=self.fixture.created[-1]
        self.client.mount_disk=Mock()
        self.client.read_drives=Mock(return_value={})
        self.selection=remote_selection('/SD/game.d64',self.core.device_session())
        self.tab=DrivesTab.__new__(DrivesTab)
        self.tab.app=NS(core=self.core,busy=False,window=None,run=lambda task,done:done(task()))
        self.tab.client=self.core.device_operations;self.tab.loaded=True
        self.tab.message=Mock();self.tab.show=Mock();self.tab.chooser=None;self.tab.setting_path=False
        self.tab.cards={}
        for drive in ('a','b'):
            entry=Mock();entry.get_text.return_value=self.selection.path
            self.tab.cards[drive]={'selection':self.selection,'path':entry,
                'access':Mock(get_selected=Mock(return_value=0)),'controls':Mock(),'status':Mock()}
        fake=NS(Dialog=Dialog,Label=lambda **kw:None,ResponseType=NS(OK=1,CANCEL=0))
        patcher=patch('c64u_browser.drives_tab.Gtk',fake);patcher.start();self.addCleanup(patcher.stop)

    def test_picker_remote_only_and_cancel_no_actions(self):
        with patch('c64u_browser.drives_tab.FilePicker') as picker:
            self.tab.choose_image('b')
        kw=picker.call_args.kwargs
        self.assertEqual((PickerMode.OPEN_FILE,('c64u',),DRIVES,1),
                         (kw['mode'],kw['scopes'],kw['filter'],kw['limit']))
        callback=picker.call_args.args[1]
        callback(None);self.client.mount_disk.assert_not_called()
        callback((self.selection,))
        self.assertIs(self.selection,self.tab.cards['b']['selection'])
        self.client.mount_disk.assert_not_called()

    def test_supported_and_unsupported_sources(self):
        for ext in ('d64','G64','d71','g71','d81'):
            selection=remote_selection('/USB1/game.'+ext,self.core.device_session())
            self.tab.select_image(selection)
        for path in ('/SD/game.crt','/SD/game.prg','/Flash/game.d64','/Temp/game.d64','/SD/../game.d64'):
            with self.assertRaises(BrowserError):remote_selection(path,self.core.device_session())
        for selection in (replace(self.selection,storage_root='/USB0'),
                          replace(self.selection,scope='core-host')):
            with self.assertRaises(BrowserError):self.tab.select_image(selection)
        self.client.mount_disk.assert_not_called()

    def test_confirmation_cancel_and_captured_target(self):
        self.tab.mount('a').respond(False)
        self.client.mount_disk.assert_not_called()
        self.tab.cards['b']['access'].get_selected.return_value=1
        dialog=self.tab.mount('b')
        self.tab.cards['b']['path'].get_text.return_value='/USB0/other.d64'
        self.tab.cards['b']['selection']=remote_selection('/USB0/other.d64',self.core.device_session())
        self.tab.cards['b']['access'].get_selected.return_value=2
        dialog.respond()
        self.client.mount_disk.assert_called_once_with('b','/SD/game.d64','readwrite')

    def test_stale_before_receipt_and_confirmation(self):
        self.core.reconnect()
        with self.assertRaises(PickerError):self.tab.select_image(self.selection)
        self.assertIsNone(self.tab.mount('a'))
        self.client.mount_disk.assert_not_called()

    def test_stale_after_confirmation(self):
        dialog=self.tab.mount('a');self.core.reconnect();dialog.respond()
        self.client.mount_disk.assert_not_called()

    def test_stale_after_submission_before_worker(self):
        queued=[];self.tab.app.run=lambda task,done:queued.append(task)
        self.tab.mount('a').respond();self.assertEqual(1,len(queued))
        self.core.reconnect()
        self.assertIsInstance(queued[0](),Exception)
        self.client.mount_disk.assert_not_called()

    def test_core_disconnect_replacement_and_root_mismatch(self):
        for selection in (replace(self.selection,device_id='different'),
                          replace(self.selection,session_id='different'),
                          replace(self.selection,storage_root='/USB1')):
            with self.assertRaises((BrowserError,PickerError)):
                self.core.execute_drive_image(selection,'a')
        self.core.disconnect()
        with self.assertRaises((BrowserError,PickerError)):
            self.core.execute_drive_image(self.selection,'a')
        self.client.mount_disk.assert_not_called()

    def test_session_change_cannot_retarget_during_dispatch(self):
        def mounted(*args):
            with self.assertRaises(BrowserError):self.core.reconnect()
        self.client.mount_disk.side_effect=mounted
        self.core.execute_drive_image(self.selection,'a')
        self.client.mount_disk.assert_called_once_with('a','/SD/game.d64','readonly')
        self.client.read_drives.assert_called_once()

    def test_run_preserves_d64_drive_a_and_temporary_copy_route(self):
        with patch('c64u_browser.disk_run.mount_and_run') as run:
            self.tab.mount_run().respond(False);run.assert_not_called()
            self.tab.mount_run().respond()
            run.assert_called_once_with(self.client,'/SD/game.d64')
            for ext in ('g64','d71','g71','d81'):
                selection=remote_selection('/SD/game.'+ext,self.core.device_session())
                with self.assertRaises(BrowserError):self.core.execute_drive_image(selection,'a',run=True)
            with self.assertRaises(BrowserError):self.core.execute_drive_image(self.selection,'b',run=True)
            self.assertEqual(1,run.call_count)
        self.client.mount_disk.assert_not_called()
