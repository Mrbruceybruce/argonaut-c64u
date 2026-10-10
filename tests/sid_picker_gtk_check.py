"""Offline selection wiring checks; existing validation is covered separately."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from c64u_browser.sid_jukebox_tab import SidJukeboxTab
from c64u_browser.picker_model import PickerMode, PickerSelection, SID
from c64u_browser.scheduler import DeviceSession


class SidPickerWiring(unittest.TestCase):
    def setUp(self):
        self.tab=SidJukeboxTab.__new__(SidJukeboxTab)
        self.tab.chooser=None
        self.tab.app=NS(core=NS(device_session=lambda:DeviceSession('device','session')))
        self.tab.client=Mock();self.tab._show=Mock();self.tab.refresh=Mock()
        self.tab._run_job=Mock();self.tab._relink_prepared=Mock()
        self.selection=PickerSelection('c64u','/SD/a.sid','a.sid','/SD','device','session','sid','file')
        self.patch=patch('c64u_browser.sid_jukebox_tab.FilePicker')
        self.picker=self.patch.start();self.addCleanup(self.patch.stop)

    def test_remote_picker_does_not_read_files_state(self):
        self.tab.add_c64u()
        args=self.picker.call_args
        self.assertEqual(PickerMode.OPEN_FILE,args.kwargs['mode'])
        self.assertEqual(SID,args.kwargs['filter'])
        self.assertEqual(('c64u','core-host'),args.kwargs['scopes'])
        args.args[1]((self.selection,))
        self.tab._run_job.call_args.args[0]()
        self.tab.client.add_selection.assert_called_once_with(self.selection,DeviceSession('device','session'))

    def test_local_picker_and_cancel_no_submission(self):
        self.tab.add_local()
        self.assertEqual(('core-host','c64u'),self.picker.call_args.kwargs['scopes'])
        self.picker.call_args.args[1](None)
        self.assertIsNone(self.tab.chooser)
        self.tab._run_job.assert_not_called()
        self.tab.add_local();self.picker.call_args.args[1](())
        self.tab._run_job.assert_not_called()

    def test_reference_retained_until_admission_and_relink_target_captured(self):
        self.tab.client.selected.return_value=NS(id='original',source=NS(scope='c64u'))
        self.tab.relink()
        self.tab.client.selected.return_value=NS(id='different')
        self.picker.call_args.args[1]((self.selection,))
        self.tab.app.core.device_session=lambda:DeviceSession('device','new-session')
        self.tab._run_job.call_args.args[0]()
        self.tab.client.prepare_relink_selection.assert_called_once_with(
            'original',self.selection,DeviceSession('device','new-session'))
        self.assertIs(self.tab._relink_prepared,self.tab._run_job.call_args.args[1])


class SidPickerLiveGtk(unittest.TestCase):
    def test_actual_picker_adds_validated_local_sid_without_playback(self):
        from pathlib import Path
        from gi.repository import Gtk
        from tests.test_sid_format import sid_bytes
        from c64u_browser.sid_jukebox import SidCatalogService
        from c64u_browser.sid_jukebox_client import SidJukeboxClient
        import test_preferences_ui
        fixture=test_preferences_ui.PreferencesUI()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        trap=patch('socket.socket.connect',side_effect=AssertionError('Device contact forbidden'))
        trap.start();self.addCleanup(trap.stop)
        folder=Path(fixture.temp.name)/'sid-input';folder.mkdir()
        (folder/'tune.sid').write_bytes(sid_bytes())
        (folder/'invalid.prg').write_bytes(b'invalid')
        app=fixture.app;app.local=folder
        catalog=SidCatalogService(Path(fixture.temp.name)/'picker-catalog.json').load()
        self.addCleanup(catalog.close)
        playback=Mock()
        tab=app.sid_jukebox_tab;tab.client=SidJukeboxClient(catalog,playback)
        tab.add_local();picker=tab.chooser
        self.addCleanup(lambda:picker.response(None,Gtk.ResponseType.CANCEL))
        for _ in range(10):
            fixture.pump()
            if picker.model.loaded:break
        self.assertIsNotNone(picker.model.loaded)
        self.assertEqual(['tune.sid'],[e.name for e in picker.model.entries])
        row=picker.listing.get_first_child()
        while row.item[0]!='tune.sid':row=row.get_next_sibling()
        picker.listing.select_row(row)
        picker.response(None,Gtk.ResponseType.ACCEPT)
        for _ in range(10):
            fixture.pump()
            if catalog.search() and not tab.job_busy:break
        self.assertIsNone(tab.chooser)
        self.assertEqual('PSID',catalog.search()[0].metadata.format)
        self.assertFalse(tab.job_busy)
        playback.prepare_library.assert_not_called()
        playback.execute.assert_not_called()
