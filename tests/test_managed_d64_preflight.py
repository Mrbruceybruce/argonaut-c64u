"""Offline managed D64 preflight: no execution capabilities or physical devices."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import BrowserError, Entry, ConnectionFailure
from c64u_browser.jobs import JobCancelled
from c64u_browser.managed_library import parse_manifest
from c64u_browser.managed_d64_preflight import ManagedD64Preflight
from tests.test_managed_library import manifest, game, ID, GAME

ROOT='/USB0/ARGONAUT_LIBRARY'
FILE=ROOT+'/games/canonical.d64'
DATA=(Path(__file__).parent/'fixtures/vice-1541-authentic.d64').read_bytes()


def document(**changes):
    return manifest(revision=1,games=[game(path='games/canonical.d64',format='D64',
        size=len(DATA),sha256=hashlib.sha256(DATA).hexdigest())],**changes)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        from tests.test_core import CoreTests
        fixture=CoreTests();fixture.setUp();self.addCleanup(fixture.tearDown)
        self.core=fixture.core;self.profile=fixture.profile
        self.core.connect(self.profile)
        self.client=fixture.created[-1]
        self.now=[100.0]
        self.core.managed_d64_preflight.close()
        self.service=self.core.managed_d64_preflight=ManagedD64Preflight(self.core,clock=lambda:self.now[0],ttl=10)
        self.payloads={ROOT+'/manifest.json':document(),FILE:DATA}
        self.library=parse_manifest(document(),self.core.device_session().device_id,ROOT)
        self.core.configure_game_library(ROOT,identity=self.library.identity)
        self.tree={ROOT:[Entry('manifest.json','file',len(document()))]+[
            Entry(n,'dir',None) for n in ('games','metadata','artwork')],
            ROOT+'/games':[Entry('canonical.d64','file',len(DATA))]}
        self.calls=[]
        def listing(path):
            self.calls.append(('LIST',path))
            return path,self.tree[path]
        self.client.list_directory=Mock(side_effect=listing)
        def read(client,path,maximum,check=None):
            self.calls.append(('READ',path));check()
            return self.payloads[path]
        self.read=patch('c64u_browser.managed_d64_preflight.read_remote_game',side_effect=read).start()
        self.addCleanup(patch.stopall)
        self.core.preferences.save=Mock(side_effect=AssertionError('Preference write forbidden'))
        for name in ('run_crt','run_crt_data','mount_disk','machine_action','run_prg','write_memory','open_dma'):
            setattr(self.client,name,Mock(side_effect=AssertionError('Device command forbidden')))
        self.selected=self.service.selection(self.library,GAME,self.core.device_session())

    def prepare(self):return self.service.prepare(self.selected).wait(5)

    def failed(self):
        result=self.prepare();self.assertEqual('failed',result.state,result)
        self.assertIsNone(result.result)
        return result

    def test_canonical_selection_preview_and_single_use(self):
        before=self.core.preferences.game_library_location.copy()
        result=self.prepare();self.assertEqual('succeeded',result.state,result.error)
        plan=result.result
        self.assertEqual(self.selected,plan.selection)
        self.assertEqual((ROOT,FILE,'D64',len(DATA),hashlib.sha256(DATA).hexdigest(),'dma-run-img'),
            (plan.library_path,plan.game_path,plan.format,plan.verified_size,plan.verified_sha256,plan.method))
        self.assertEqual(self.core.device_session(),plan.selection.session)
        self.assertEqual(self.library.identity,plan.selection.library)
        self.assertEqual(1,plan.selection.revision)
        self.assertEqual(hashlib.sha256(document()).hexdigest(),plan.selection.manifest_sha256)
        self.assertIn('reset',plan.warning)
        with self.assertRaises(FrozenInstanceError):plan.selection.game.path='games/other.d64'
        with self.assertRaises(FrozenInstanceError):plan.expires_at=999
        self.assertEqual(plan,self.service.consume_plan(plan.plan_id))
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)
        self.assertEqual(before,self.core.preferences.game_library_location)
        self.core.preferences.save.assert_not_called()
        self.assertFalse(self.core.game_library.path.exists())
        self.assertTrue(all(path.startswith(ROOT+'/') or path==ROOT for _,path in self.calls))
        for name in ('run_crt','run_crt_data','mount_disk','machine_action','run_prg','write_memory','open_dma'):
            getattr(self.client,name).assert_not_called()
        self.assertFalse(hasattr(self.service,'execute_launch'))

    def test_busy_admission_permanently_retires_token(self):
        plan=self.prepare().result
        with self.core._session_admission():
            with self.assertRaises(BrowserError) as failure:
                self.service.consume_plan(plan.plan_id)
            self.assertEqual('admission_busy',failure.exception.code)
        self.assertNotIn(plan.plan_id,self.service._plans)
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)

    def test_concurrent_consumers_claim_only_once(self):
        plan=self.prepare().result
        start=Barrier(2)
        def consume():
            start.wait(timeout=5)
            try:return self.service.consume_plan(plan.plan_id)
            except BrowserError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(consume) for _ in range(2)]
            results=[future.result(timeout=5) for future in futures]
        self.assertEqual(1,results.count(plan))
        self.assertEqual(1,results.count(None))
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)

    def test_failed_validation_permanently_retires_token(self):
        plan=self.prepare().result
        preference=self.core.preferences.game_library_location
        self.core.preferences.game_library_location=None
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)
        self.core.preferences.game_library_location=preference
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)

    def test_cancellation_at_final_publication_admission(self):
        entered=Event();release=Event();admission=self.core._session_admission
        calls=[]
        @contextmanager
        def controlled_admission():
            with admission():
                calls.append(True)
                if len(calls)==2:
                    entered.set()
                    if not release.wait(5):raise AssertionError('Publication release missing')
                yield
        with patch.object(self.core,'_session_admission',controlled_admission):
            job=self.service.prepare(self.selected)
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(job.request_cancel())
            finally:release.set()
            result=job.wait(5)
        self.assertEqual(2,len(calls))
        self.assertEqual('cancelled',result.state)
        self.assertIsNone(result.result)
        self.assertEqual({},self.service._plans)
        self.assertEqual(2,self.calls.count(('READ',ROOT+'/manifest.json')))

    def test_bounded_storage_evicts_oldest_plan(self):
        self.service._limit=2
        plans=[self.prepare().result for _ in range(3)]
        self.assertEqual([p.plan_id for p in plans[1:]],list(self.service._plans))
        with self.assertRaises(BrowserError):self.service.consume_plan(plans[0].plan_id)
        for plan in plans[1:]:self.assertEqual(plan,self.service.consume_plan(plan.plan_id))

    def test_default_five_minute_expiry(self):
        self.service.close()
        self.service=self.core.managed_d64_preflight=ManagedD64Preflight(self.core,clock=lambda:self.now[0])
        self.selected=self.service.selection(self.library,GAME,self.core.device_session())
        first=self.prepare().result;second=self.prepare().result
        self.assertEqual(300,first.expires_at-first.created_at)
        self.now[0]=first.expires_at-0.001
        self.assertEqual(first,self.service.consume_plan(first.plan_id))
        self.now[0]=second.expires_at
        with self.assertRaises(BrowserError):self.service.consume_plan(second.plan_id)
        self.assertEqual({},self.service._plans)

    def test_close_is_explicitly_idempotent(self):
        plan=self.prepare().result
        with patch.object(self.service,'_unsubscribe',wraps=self.service._unsubscribe) as unsubscribe:
            self.service.close();epoch=self.service._epoch
            self.service.close()
            unsubscribe.assert_called_once_with()
        self.assertEqual(epoch,self.service._epoch)
        self.assertEqual({},self.service._plans)
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)
        with self.assertRaises(BrowserError):self.service.prepare(self.selected)

    def test_changed_manifest_without_revision_increment(self):
        self.payloads[ROOT+'/manifest.json']=document()+b' '
        self.failed();self.assertNotIn(('READ',FILE),self.calls)

    def test_changed_library_and_game_fields(self):
        changes=[('library_id','22222222-2222-4222-8222-222222222222'),('revision',2),
                 ('id',ID),('path','games/other.d64'),('size',len(DATA)-1),('sha256','0'*64)]
        for key,value in changes:
            with self.subTest(key=key):
                doc=json.loads(document())
                (doc if key in ('library_id','revision') else doc['games'][0])[key]=value
                self.payloads[ROOT+'/manifest.json']=json.dumps(doc).encode()
                self.failed()
        doc=json.loads(document());doc['games']=[]
        self.payloads[ROOT+'/manifest.json']=json.dumps(doc).encode();self.failed()

    def test_wrong_device_session_and_no_preference_no_reads(self):
        for selected in (replace(self.selected,session=replace(self.selected.session,device_id='other')),
                         replace(self.selected,session=replace(self.selected.session,session_id='old'))):
            with self.assertRaises(BrowserError):self.service.prepare(selected)
        self.core.preferences.game_library_location=None
        with self.assertRaises(BrowserError):self.service.prepare(self.selected)
        self.assertEqual([],self.calls)

    def test_changed_bytes_size_and_missing_file(self):
        for data in (DATA[:-1],bytes([DATA[0]^1])+DATA[1:]):
            self.payloads[FILE]=data;self.failed()
        self.tree[ROOT+'/games']=[];self.failed()

    def test_matching_hash_does_not_accept_malformed_disk(self):
        data=b'\0'*len(DATA)
        doc=json.loads(document());doc['games'][0]['sha256']=hashlib.sha256(data).hexdigest()
        self.payloads[ROOT+'/manifest.json']=json.dumps(doc).encode();self.payloads[FILE]=data
        library=parse_manifest(self.payloads[ROOT+'/manifest.json'],self.selected.session.device_id,ROOT)
        self.selected=self.service.selection(library,GAME,self.core.device_session())
        self.failed()

    def test_redirects_and_transport_failures(self):
        original=self.client.list_directory.side_effect
        for target in (ROOT,ROOT+'/games'):
            self.client.list_directory.side_effect=lambda path:('/USB9',[]) if path==target else original(path)
            self.failed()
        for kind in ('network','authentication','ftp'):
            self.client.list_directory.side_effect=ConnectionFailure(kind,'unavailable')
            self.failed()

    def test_cancellation_during_game_read(self):
        entered=Event();release=Event();original=self.read.side_effect
        def read(client,path,maximum,check=None):
            if path==FILE:
                entered.set()
                if not release.wait(3):raise AssertionError('Test release missing')
            return original(client,path,maximum,check)
        self.read.side_effect=read
        job=self.service.prepare(self.selected)
        try:
            self.assertTrue(entered.wait(3));job.request_cancel()
        finally:release.set()
        self.assertEqual('cancelled',job.wait(5).state)
        self.assertEqual({},self.service._plans)

    def test_changes_during_read_and_manifest_revalidation(self):
        original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.payloads[ROOT+'/manifest.json']=document()+b' '
            return data
        self.read.side_effect=read;self.failed()

    def test_reconnect_and_preference_change_during_preparation(self):
        original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.core.connect(self.profile)
            return data
        self.read.side_effect=read
        self.failed();self.assertEqual({},self.service._plans)

    def test_preference_change_during_preparation(self):
        original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.core.preferences.game_library_location=None
            return data
        self.read.side_effect=read
        self.failed();self.assertEqual({},self.service._plans)

    def test_game_path_casing_and_directory_size_rejected(self):
        for entry in (Entry('CANONICAL.D64','file',len(DATA)),
                      Entry('canonical.d64','file',len(DATA)+1),
                      Entry('canonical.d64','dir',len(DATA))):
            self.tree[ROOT+'/games']=[entry]
            self.failed()
        self.assertNotIn(('READ',FILE),self.calls)

    def test_preference_change_and_restore_invalidates_selection_and_plan(self):
        plan=self.prepare().result
        before=self.core.preferences.game_library_location.copy()
        self.core.preferences.save=Mock()
        self.core.configure_game_library('')
        self.core.configure_game_library(ROOT,identity=self.library.identity)
        self.assertEqual(before,self.core.preferences.game_library_location)
        with self.assertRaises(BrowserError):self.service.prepare(self.selected)
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)

    def test_reconnect_invalidates_selection_and_plan(self):
        plan=self.prepare().result
        self.core.connect(self.profile)
        with self.assertRaises(BrowserError):self.service.prepare(self.selected)
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)

    def test_expiry_discard_and_close(self):
        plan=self.prepare().result
        self.now[0]=plan.expires_at
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)
        plan=self.prepare().result
        self.assertTrue(self.service.discard_plan(plan.plan_id))
        with self.assertRaises(BrowserError):self.service.consume_plan(plan.plan_id)
        self.service.close()
        with self.assertRaises(BrowserError):self.service.prepare(self.selected)


class WireTests(unittest.TestCase):
    def test_real_ftp_preflight_cleanup_and_read_only_commands(self):
        from tests.test_ftp_reads import ReadMigrationTests
        from c64u_ftp_server import FakeC64UFtp
        tree={b'/':b'type=dir; USB0\r\n',b'/USB0':b'type=dir; ARGONAUT_LIBRARY\r\n',
              ROOT.encode():b'type=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\ntype=file;size='+str(len(document())).encode()+b'; manifest.json\r\n',
              (ROOT+'/games').encode():b'type=file;size='+str(len(DATA)).encode()+b'; canonical.d64\r\n'}
        with FakeC64UFtp(directories=tree,files={(ROOT+'/manifest.json').encode():document(),FILE.encode():DATA}) as server:
            core,profile=ReadMigrationTests.core(self,server)
            core.connect(profile,remote_folder='/USB0')
            library=parse_manifest(document(),core.device_session().device_id,ROOT)
            core.configure_game_library(ROOT,identity=library.identity)
            core.preferences.save=Mock(side_effect=AssertionError('No preference writes'))
            service=core.managed_d64_preflight
            selected=service.selection(library,GAME,core.device_session())
            before=server.connections
            with patch('c64u_browser.disk_run.socket.create_connection',side_effect=AssertionError('No DMA')), \
                 patch.object(core._client,'_request_json',side_effect=AssertionError('No REST')):
                result=service.prepare(selected).wait(5)
                self.assertEqual('succeeded',result.state,result.error)
                self.assertEqual(before+1,server.connections)
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertEqual(result.result,service.consume_plan(result.result.plan_id))
                server.replies[b'SIZE']=b'550 Missing\r\n'
                failed=service.prepare(selected).wait(5)
                self.assertEqual('failed',failed.state)
                self.assertEqual(0,core._ftp_manager.active_count)
            self.assertLessEqual(set(server.verbs),{b'USER',b'PASS',b'FEAT',b'TYPE',b'PASV',b'CWD',b'PWD',b'MLSD',b'LIST',b'SIZE',b'RETR',b'QUIT'})
            core.preferences.save.assert_not_called()
            self.assertFalse(core.game_library.path.exists())
            core.close()

    def test_session_replacement_during_real_ftp_transfer_cleans_lease(self):
        from tests.test_ftp_reads import ReadMigrationTests
        from c64u_ftp_server import FakeC64UFtp
        entered=Event();release=Event()
        def readback(path,data):
            if path==FILE.encode():
                entered.set()
                if not release.wait(5):raise AssertionError('Transfer release missing')
            return data
        tree={b'/':b'type=dir; USB0\r\n',b'/USB0':b'type=dir; ARGONAUT_LIBRARY\r\n',
              ROOT.encode():b'type=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\ntype=file; manifest.json\r\n',
              (ROOT+'/games').encode():b'type=file;size='+str(len(DATA)).encode()+b'; canonical.d64\r\n'}
        with FakeC64UFtp(directories=tree,files={(ROOT+'/manifest.json').encode():document(),FILE.encode():DATA},
                         readback_data=readback) as server:
            core,profile=ReadMigrationTests.core(self,server)
            core.connect(profile,remote_folder='/USB0')
            old_session=core.device_session()
            library=parse_manifest(document(),old_session.device_id,ROOT)
            core.configure_game_library(ROOT,identity=library.identity)
            core.preferences.save=Mock(side_effect=AssertionError('No preference writes'))
            service=core.managed_d64_preflight
            selected=service.selection(library,GAME,old_session)
            job=service.prepare(selected)
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(1,core._ftp_manager.active_count)
                # Replace the verified session without competing for its old FTP lease.
                core.connect(profile,initial_browse=False)
                self.assertNotEqual(old_session,core.device_session())
            finally:release.set()
            result=job.wait(5)
            self.assertEqual('failed',result.state)
            self.assertIsNone(result.result)
            self.assertEqual({},service._plans)
            self.assertEqual(0,core._ftp_manager.active_count)
            core.preferences.save.assert_not_called()
            self.assertLessEqual(set(server.verbs),{b'USER',b'PASS',b'FEAT',b'TYPE',b'PASV',b'CWD',b'PWD',b'MLSD',b'LIST',b'SIZE',b'RETR',b'QUIT'})
