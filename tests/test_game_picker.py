"""Offline selection contract and service-admission regressions."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
from c64u_browser.game_library import GameLibraryService, GameLibraryError, GameSource
from c64u_browser.game_library_client import GameLibraryClient
from c64u_browser.picker_model import PickerSelection, PickerError
from c64u_browser.scheduler import DeviceSession
from tests.test_game_library import crt_bytes


class GamePickerTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.session=DeviceSession('founders','one')
        self.reader=Mock(return_value=crt_bytes())
        self.service=GameLibraryService(self.root/'catalog.json',
            session_provider=lambda:self.session, remote_reader=self.reader,
            bulk_remote_reader=lambda *args:self.reader()).load()
        self.addCleanup(self.service.close)
        self.launcher=Mock();self.client=GameLibraryClient(self.service,self.launcher)
        self.remote=PickerSelection('c64u','/SD/a.crt','a.crt','/SD','founders','one','games','file')

    def local(self,name='a.crt',data=None):
        path=self.root/name;path.write_bytes(crt_bytes() if data is None else data)
        return PickerSelection('core-host',str(path),name,'','','','games','file')

    def test_local_order_establishes_duplicate_reference(self):
        selections=(self.local('z.crt'),self.local('a.crt'))
        sources,_=self.client.picker_sources(selections,self.session)
        self.assertEqual([s.path for s in selections],[s.path for s in sources])
        results=[self.client.add_selection(s,self.session).wait(5) for s in selections]
        self.assertEqual(['succeeded']*2,[s.state for s in results])
        self.assertEqual('content',results[1].result.duplicate_kind)
        self.assertEqual(selections[0].path,self.service.list()[0].source.path)
        self.launcher.assert_not_called();self.reader.assert_not_called()

    def test_remote_single_validates_and_catalogs_without_launch(self):
        result=self.client.add_selection(self.remote,self.session).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual('/SD',result.result.record.source.volume)
        self.assertEqual([],self.launcher.mock_calls)

    def test_local_limit_and_remote_bounds_preserved(self):
        local=self.local()
        selections=tuple(replace(local,path=str(self.root/f'{i}.crt'),filename=f'{i}.crt') for i in range(65))
        self.client.picker_sources(selections[:64],self.session)
        with self.assertRaises(GameLibraryError):self.client.picker_sources(selections,self.session)
        remote=tuple(replace(self.remote,path=f'/SD/{i}.crt',filename=f'{i}.crt') for i in range(65))
        self.client.picker_sources(remote,self.session)
        self.service.bulk_max_candidates=64
        result=self.client.scan_selections(remote,self.session).wait(5)
        self.assertEqual('scan-limit',result.error.code)
        self.reader.assert_not_called()

    def test_remote_multiple_keeps_preview_order_and_duplicates(self):
        selections=(replace(self.remote,path='/SD/z.crt',filename='z.crt'),self.remote)
        result=self.client.scan_selections(selections,self.session).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual(['/SD/a.crt','/SD/z.crt'],[c.source.path for c in result.result.candidates])
        self.assertEqual(['new-valid','duplicate-scan-content'],[c.classification for c in result.result.candidates])
        self.assertEqual((),self.service.list())

    def test_disconnect_reconnect_and_device_change_rejected(self):
        for session in (DeviceSession('',''),DeviceSession('founders','two'),DeviceSession('other','one')):
            with self.subTest(session=session),self.assertRaises(PickerError):
                self.client.add_selection(self.remote,session)
        self.reader.assert_not_called()

    def test_admission_rejects_change_after_consumer_validation(self):
        old=self.session;self.session=DeviceSession('founders','two')
        for call in (lambda:self.client.add_selection(self.remote,old),
                     lambda:self.client.scan_selections((self.remote,),old)):
            with self.assertRaises(GameLibraryError):call()
        self.reader.assert_not_called()

    def test_root_scope_kind_filter_traversal_and_duplicates_rejected(self):
        for item in (replace(self.remote,storage_root='/USB0'),
                     replace(self.remote,path='/Flash/a.crt',storage_root='/Flash'),
                     replace(self.remote,path='/Temp/a.crt',storage_root='/Temp'),
                     replace(self.remote,path='/SD/../a.crt'),
                     replace(self.remote,kind='dir'),replace(self.remote,category='sid'),
                     replace(self.remote,filename='different.crt'),
                     replace(self.remote,path='/SD/a.sid',filename='a.sid')):
            with self.subTest(item=item),self.assertRaises((GameLibraryError,PickerError)):
                self.client.picker_sources((item,),self.session)
        for items in ((),(self.remote,self.remote),(self.remote,self.local()),
                      (self.remote,replace(self.remote,path='/USB0/a.crt',storage_root='/USB0'))):
            with self.assertRaises(GameLibraryError):self.client.picker_sources(items,self.session)

    def test_invalid_content_uses_existing_validator(self):
        result=self.client.add_selection(self.local(data=b'not a CRT'),self.session).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual((),self.service.list())

    def test_relink_captures_record_and_refuses_changed_record(self):
        original=self.client.add_selection(self.local(),self.session).wait(5).result.record
        other=self.client.add_selection(self.local('other.crt',crt_bytes(b'y'*32)),self.session).wait(5).result.record
        self.client.select(other.id)
        result=self.client.prepare_relink_selection(original,self.local('replacement.crt'),self.session).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual(original.id,result.result.record_id)
        self.assertTrue(result.result.content_matches)
        self.service.edit_title(original.id,'changed')
        with self.assertRaises(GameLibraryError):
            self.client.prepare_relink_selection(original,self.local('replacement.crt'),self.session)

    def test_remote_relink_admission_rejects_reconnect(self):
        record=self.client.add_selection(self.remote,self.session).wait(5).result.record
        old=self.session;self.session=DeviceSession('founders','two');self.reader.reset_mock()
        with self.assertRaises(GameLibraryError):self.client.prepare_relink_selection(record,self.remote,old)
        self.reader.assert_not_called()

    def test_reconnect_during_read_cannot_catalog_replacement_content(self):
        def read(source):
            self.session=DeviceSession('founders','two')
            return crt_bytes()
        self.reader.side_effect=read
        result=self.client.add_selection(self.remote,self.session).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.assertEqual((),self.service.list())

    def test_reconnect_after_admission_fails_worker_preflight(self):
        binding=self.service._binding
        def bind(source,**kwargs):
            result=binding(source,**kwargs)
            self.session=DeviceSession('founders','two')
            return result
        self.service._binding=bind
        result=self.client.add_selection(self.remote,self.session).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.reader.assert_not_called()
        self.assertEqual((),self.service.list())


class GamePublicationTests(TestCase):
    """Real Core guard and scheduler; only fake transports and temporary catalog."""
    def setUp(self):
        from tests.test_core import CoreTests
        self.fixture=CoreTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.service=self.core.game_library.load()
        self.service._remote_reader=lambda source:crt_bytes()
        self.client=GameLibraryClient(self.service,Mock())
        session=self.core.device_session()
        self.selected=PickerSelection('c64u','/SD/a.crt','a.crt','/SD',
            session.device_id,session.session_id,'games','file')

    def add(self):
        result=self.client.add_selection(self.selected,self.core.device_session()).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        return result.result.record

    def preview(self):
        record=self.add()
        target=replace(self.selected,path='/SD/b.crt',filename='b.crt')
        result=self.client.prepare_relink_selection(record,target,self.core.device_session()).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        return record,result.result

    def reconnect_after_validation(self):
        inspect=self.service._inspection_from_data
        def changed(*args):
            result=inspect(*args)
            self.core.connect(self.fixture.profile)
            return result
        self.service._inspection_from_data=changed

    def test_add_late_reconnect_leaves_catalog_absent(self):
        self.reconnect_after_validation()
        result=self.client.add_selection(self.selected,self.core.device_session()).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.assertEqual((),self.service.list())
        self.assertFalse(self.service.path.exists())

    def test_relink_late_reconnect_preserves_catalog_bytes(self):
        record,preview=self.preview();before=self.service.path.read_bytes()
        self.reconnect_after_validation()
        result=self.client.execute_relink(preview.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.assertEqual(record,self.service.get(record.id))
        self.assertEqual(before,self.service.path.read_bytes())

    def guard_write(self):
        from c64u_browser.core import CoreError
        save=self.service._save_locked
        self.writes=0
        def guarded_save():
            session=self.core.device_session()
            self.assertTrue(self.core._session_gate.locked())
            for change in (lambda:self.core.connect(self.fixture.profile),self.core.disconnect):
                with self.assertRaises(CoreError) as error:change()
                self.assertEqual('admission_busy',error.exception.code)
                self.assertEqual(session,self.core.device_session())
            save();self.writes+=1
        self.service._save_locked=guarded_save

    def test_normal_add_holds_existing_guard_through_disk_write(self):
        self.guard_write();record=self.add()
        self.assertEqual(1,self.writes)
        self.assertEqual(self.selected.path,record.source.path)
        self.assertFalse(self.core._session_gate.locked())
        self.core.disconnect()

    def test_normal_relink_holds_existing_guard_through_disk_write(self):
        record,preview=self.preview();self.guard_write()
        result=self.client.execute_relink(preview.plan_id).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual('/SD/b.crt',self.service.get(record.id).source.path)
        self.assertEqual(1,self.writes)
        self.assertFalse(self.core._session_gate.locked())

    def test_publication_refuses_busy_guard_without_writing(self):
        with self.core._session_admission():
            result=self.client.add_selection(self.selected,self.core.device_session()).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('admission_busy',result.error.code)
        self.assertEqual((),self.service.list())
        self.assertFalse(self.service.path.exists())

    def test_validated_source_replacement_is_refused(self):
        inspect=self.service._inspection_from_data
        def replaced(*args):
            result=inspect(*args)
            return replace(result,source=GameSource.c64u(self.selected.device_id,'/USB0/a.crt'))
        self.service._inspection_from_data=replaced
        result=self.client.add_selection(self.selected,self.core.device_session()).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('source',result.error.code)
        self.assertEqual((),self.service.list())
        self.assertFalse(self.core._session_gate.locked())
