"""SID consumer validation and captured-session admission, without devices."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from c64u_browser.picker_model import PickerSelection, PickerError
from c64u_browser.scheduler import DeviceSession
from c64u_browser.sid_jukebox import SidCatalogService, SidCatalogError
from c64u_browser.sid_jukebox_client import SidJukeboxClient
from tests.test_sid_format import sid_bytes


class SidPicker(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.session = DeviceSession('founders', 'one')
        self.reader = Mock(return_value=sid_bytes())
        self.catalog = SidCatalogService(Path(self.tmp.name)/'catalog.json',
            remote_reader=self.reader, session_provider=lambda:self.session).load()
        self.addCleanup(self.catalog.close)
        self.client = SidJukeboxClient(self.catalog, Mock())
        self.remote = PickerSelection('c64u','/SD/music.sid','music.sid','/SD',
                                       'founders','one','sid','file')

    def local(self, data):
        path = Path(self.tmp.name)/'music.sid';path.write_bytes(data)
        return PickerSelection('core-host',str(path),path.name,'','','','sid','file')

    def test_local_sid_and_invalid_content_use_existing_parser(self):
        result=self.client.add_selection(self.local(sid_bytes()),self.session).wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual('PSID',result.result.tune.metadata.format)
        result=self.client.add_selection(self.local(b'not a SID'),self.session).wait(5)
        self.assertEqual('failed',result.state)
        self.reader.assert_not_called()

    def test_remote_sid_read_only_and_invalid_content(self):
        result=self.client.add_selection(self.remote,self.session).wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual('founders',result.result.tune.source.device_id)
        self.assertEqual('/SD/music.sid',result.result.tune.source.path)
        self.reader.assert_called_once()
        self.reader.return_value=b'bad SID'
        self.assertEqual('failed',self.client.add_selection(self.remote,self.session).wait(5).state)

    def test_invalid_reference_never_submits(self):
        for selection in (None, replace(self.remote,filename='music.prg',path='/SD/music.prg'),
                replace(self.remote,category='games'),replace(self.remote,kind='dir'),
                replace(self.remote,storage_root='/USB0'),
                replace(self.remote,path='/Flash/music.sid',storage_root='/Flash'),
                replace(self.remote,path='/Temp/music.sid',storage_root='/Temp')):
            with self.subTest(selection=selection), self.assertRaises((SidCatalogError,PickerError)):
                self.client.add_selection(selection,self.session)
        self.reader.assert_not_called()
        self.assertEqual((),self.catalog.search())

    def test_stale_device_disconnect_reconnect(self):
        for session in (DeviceSession('other','one'),DeviceSession('founders','two'),DeviceSession('','')):
            with self.assertRaises(PickerError):self.client.add_selection(self.remote,session)
        self.reader.assert_not_called()

    def test_reconnect_between_consumer_check_and_catalog_binding(self):
        captured=self.session
        self.session=DeviceSession('founders','two')
        with self.assertRaises(SidCatalogError):self.client.add_selection(self.remote,captured)
        self.reader.assert_not_called()

    def test_relink_captures_tune_and_session_keeps_confirmation(self):
        tune=self.client.add_selection(self.local(sid_bytes()),self.session).wait(5).result.tune
        prepared=self.client.prepare_relink_selection(tune.id,self.remote,self.session).wait(5)
        self.assertEqual('succeeded',prepared.state)
        self.assertEqual(tune.id,prepared.result.tune_id)
        self.assertEqual('core-host',self.catalog.get(tune.id).source.scope)
        self.session=DeviceSession('founders','two')
        with self.assertRaises(SidCatalogError):self.client.execute_relink(prepared.result.plan_id)
        with self.assertRaises(SidCatalogError):
            self.client.prepare_relink_selection(tune.id,self.remote,DeviceSession('founders','one'))
