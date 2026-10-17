"""Offline managed execution: actual DMA framing over controlled local transports."""
import hashlib
import json
from dataclasses import replace
from threading import Barrier, Event
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import JobBinding
from c64u_browser.managed_d64_execution import ManagedD64ExecutionError
from tests import test_managed_d64_preflight as fixtures
from tests.test_managed_d64_preflight import ROOT, FILE, DATA, document, GAME


class DmaSocket:
    def __init__(self, failure=None, hook=lambda data:None):
        self.messages=[];self.closed=False;self.failure=failure;self.hook=hook
        self.replies=[b'\x01',b'\x02',b'OK']
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def sendall(self,data):
        self.messages.append(data);self.hook(data)
        if data.startswith(b'\x0b\xff') and self.failure=='partial':raise OSError('partial send')
    def recv(self,n):
        if len(self.messages)==1 and self.failure=='authentication':return b'\x00'
        if len(self.messages)>1 and self.failure=='lost':return b''
        return self.replies.pop(0)


class ExecutionTests(unittest.TestCase):
    setUp=fixtures.PreflightTests.setUp
    prepare=fixtures.PreflightTests.prepare

    def plan(self):
        result=self.prepare();self.assertEqual('succeeded',result.state,result.error)
        return result.result

    def execute(self,plan,sock=None):
        sock=sock or DmaSocket()
        with patch('c64u_browser.disk_run.socket.create_connection',return_value=sock) as connect:
            result=self.core.execute_managed_d64(plan.plan_id).wait(5)
        return result,sock,connect

    def reject(self,plan):
        result,sock,connect=self.execute(plan)
        self.assertEqual('rejected',result.result.outcome)
        self.assertEqual('failed',result.state)
        connect.assert_not_called()
        self.assertEqual([],sock.messages)
        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)

    def test_success_exact_bytes_once_and_replay(self):
        plan=self.plan();before=self.core.preferences.game_library_location.copy()
        result,sock,connect=self.execute(plan)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual('accepted',result.result.outcome)
        self.assertFalse(result.result.playable_verified)
        self.assertEqual(b'\x0b\xff'+len(DATA).to_bytes(3,'little')+DATA,sock.messages[1])
        self.assertEqual(3,len(sock.messages));connect.assert_called_once()
        self.assertTrue(sock.closed)
        self.core.preferences.save.assert_not_called()
        self.assertEqual(before,self.core.preferences.game_library_location)
        self.assertFalse(self.core.game_library.path.exists())
        with self.assertRaises(ManagedD64ExecutionError) as exc:self.core.execute_managed_d64(plan.plan_id)
        self.assertEqual('rejected',exc.exception.result.outcome)

    def test_busy_admission_burns_token(self):
        plan=self.plan()
        with self.core._session_admission():
            with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)
        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)

    def test_expired_and_invalidated(self):
        plan=self.plan();self.now[0]=plan.expires_at
        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)
        plan=self.plan();self.service.invalidate()
        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)

    def test_wrong_device_session_preference(self):
        for field in ('device_id','session_id','preference'):
            plan=self.plan()
            with self.subTest(field=field):
                if field=='preference':
                    with patch.object(self.core.preferences,'game_library_location',None):
                        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)
                else:
                    session=replace(self.core.device_session(),**{field:'wrong'})
                    with patch.object(self.core,'device_session',return_value=session):
                        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)

    def test_changed_uuid_revision_record_and_same_revision_digest(self):
        original=document()
        for key,value in [('library_id','22222222-2222-4222-8222-222222222222'),('revision',2),('title','changed'),('id','33333333-3333-4333-8333-333333333333'),('path','games/other.d64'),('size',len(DATA)-1),('sha256','0'*64),('digest',None)]:
            self.payloads[ROOT+'/manifest.json']=original
            plan=self.plan();doc=json.loads(original)
            if key=='digest':changed=original+b' '
            else:
                (doc if key in ('library_id','revision') else doc['games'][0])[key]=value
                changed=json.dumps(doc).encode()
            self.payloads[ROOT+'/manifest.json']=changed
            with self.subTest(key=key):self.reject(plan)

    def test_same_size_changed_bytes(self):
        plan=self.plan();self.payloads[FILE]=bytes([DATA[0]^1])+DATA[1:];self.reject(plan)

    def test_missing_file(self):
        plan=self.plan();self.tree[ROOT+'/games']=[];self.reject(plan)

    def test_redirected_path(self):
        plan=self.plan();self.client.list_directory.side_effect=lambda path:('/USB9',[]);self.reject(plan)

    def test_malformed_matching_hash_rejected(self):
        # Inject matching evidence to isolate execution's structural validator:
        # execution must not trust even an internally retained plan's hash alone.
        from c64u_browser.managed_library import parse_manifest
        plan=self.plan();data=b'\0'*len(DATA);doc=json.loads(document())
        doc['games'][0]['sha256']=hashlib.sha256(data).hexdigest()
        self.payloads[FILE]=data;self.payloads[ROOT+'/manifest.json']=json.dumps(doc).encode()
        library=parse_manifest(self.payloads[ROOT+'/manifest.json'],self.selected.session.device_id,ROOT)
        selected=replace(plan.selection,game=library.games[0],manifest_sha256=library.manifest_sha256)
        plan=replace(plan,selection=selected)
        self.service._plans[plan.plan_id]=plan
        self.reject(plan)
        self.assertIn(('READ',FILE),self.calls)

    def test_ftp_network_authentication_failure(self):
        original=self.client.list_directory.side_effect
        for kind in ('network','authentication','ftp'):
            self.client.list_directory.side_effect=original;plan=self.plan()
            self.client.list_directory.side_effect=ConnectionFailure(kind,'FTP failure')
            with self.subTest(kind=kind):self.reject(plan)

    def test_manifest_changes_after_execution_read(self):
        plan=self.plan();original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.payloads[ROOT+'/manifest.json']=document()+b' '
            return data
        self.read.side_effect=read;self.reject(plan)

    def test_reconnect_during_execution_read(self):
        plan=self.plan();original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.core.connect(self.profile)
            return data
        self.read.side_effect=read;self.reject(plan)

    def test_dma_connect_failure_is_rejected(self):
        plan=self.plan()
        with patch('c64u_browser.disk_run.socket.create_connection',side_effect=OSError('refused')) as connect:
            result=self.core.execute_managed_d64(plan.plan_id).wait(5)
        self.assertEqual('rejected',result.result.outcome);connect.assert_called_once()

    def test_dma_authentication_rejection_before_run(self):
        result,sock,_=self.execute(self.plan(),DmaSocket('authentication'))
        self.assertEqual('rejected',result.result.outcome)
        self.assertEqual(1,len(sock.messages));self.assertTrue(sock.closed)

    def test_partial_send_and_lost_response_uncertain_no_retry(self):
        for mode in ('partial','lost'):
            with self.subTest(mode=mode):
                result,sock,connect=self.execute(self.plan(),DmaSocket(mode))
                self.assertEqual('failed',result.state)
                self.assertEqual('uncertain',result.result.outcome)
                self.assertEqual(1,sum(m.startswith(b'\x0b\xff') for m in sock.messages))
                self.assertTrue(sock.closed);connect.assert_called_once()

    def cancel_at(self,header,failure=None):
        plan=self.plan();entered=Event();release=Event()
        def hook(data):
            if data.startswith(header):
                entered.set()
                if not release.wait(5):raise AssertionError('release missing')
        sock=DmaSocket(failure,hook)
        with patch('c64u_browser.disk_run.socket.create_connection',return_value=sock):
            job=self.core.execute_managed_d64(plan.plan_id)
            try:
                self.assertTrue(entered.wait(5));job.request_cancel()
            finally:release.set()
            result=job.wait(5)
        self.assertTrue(sock.closed)
        return result,sock

    def test_cancel_after_auth_before_run(self):
        result,sock=self.cancel_at(b'\x1f\xff')
        self.assertEqual('cancelled',result.state)
        self.assertEqual('rejected',result.result.outcome)
        self.assertEqual(1,len(sock.messages))

    def test_cancel_after_submission_preserves_accepted(self):
        result,sock=self.cancel_at(b'\x0b\xff')
        self.assertEqual('succeeded',result.state)
        self.assertEqual('accepted',result.result.outcome)
        self.assertTrue(result.result.cancellation_requested)

    def test_cancel_after_submission_lost_response_uncertain(self):
        result,sock=self.cancel_at(b'\x0b\xff','lost')
        self.assertEqual('uncertain',result.result.outcome)
        self.assertTrue(result.result.cancellation_requested)

    def test_scheduler_busy_rejects_and_burns_token(self):
        plan=self.plan();entered=Event();release=Event()
        def task(job):
            entered.set();self.assertTrue(release.wait(5))
        busy=self.core.scheduler.submit(CoreJob('file-job',task),JobBinding.device(self.core.device_session()))
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)
        finally:release.set();busy.wait(5)
        with self.assertRaises(ManagedD64ExecutionError):self.core.execute_managed_d64(plan.plan_id)

    def test_concurrent_same_token_dispatches_once(self):
        plan=self.plan();barrier=Barrier(2);sock=DmaSocket()
        def launch():
            barrier.wait(5)
            try:return self.core.execute_managed_d64(plan.plan_id).wait(5).result.outcome
            except ManagedD64ExecutionError:return 'rejected'
        with patch('c64u_browser.disk_run.socket.create_connection',return_value=sock):
            with ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(launch) for _ in range(2)]
                results=[f.result(5) for f in futures]
        self.assertCountEqual(['accepted','rejected'],results)
        self.assertEqual(1,sum(m.startswith(b'\x0b\xff') for m in sock.messages))

    def test_session_gate_held_through_dispatch(self):
        def hook(data):
            with self.assertRaises(BrowserError):self.core.connect(self.profile)
        result,_,_=self.execute(self.plan(),DmaSocket(hook=hook))
        self.assertEqual('accepted',result.result.outcome)

    def test_expiry_during_authentication_never_submits(self):
        plan=self.plan()
        def hook(data):self.now[0]=plan.expires_at
        result,sock,_=self.execute(plan,DmaSocket(hook=hook))
        self.assertEqual('rejected',result.result.outcome)
        self.assertEqual(1,len(sock.messages))

    def test_preference_change_during_read(self):
        plan=self.plan();original=self.read.side_effect
        def read(client,path,maximum,check=None):
            data=original(client,path,maximum,check)
            if path==FILE:self.core.preferences.game_library_location=None
            return data
        self.read.side_effect=read;self.reject(plan)

    def test_cancel_during_read_never_connects_dma(self):
        plan=self.plan();entered=Event();release=Event();original=self.read.side_effect
        def read(client,path,maximum,check=None):
            if path==FILE:
                entered.set()
                if not release.wait(5):raise AssertionError('release missing')
            return original(client,path,maximum,check)
        self.read.side_effect=read
        with patch('c64u_browser.disk_run.socket.create_connection') as connect:
            job=self.core.execute_managed_d64(plan.plan_id)
            try:
                self.assertTrue(entered.wait(5));job.request_cancel()
            finally:release.set()
            result=job.wait(5)
        self.assertEqual('cancelled',result.state)
        self.assertEqual('rejected',result.result.outcome);connect.assert_not_called()


class WireExecutionTests(unittest.TestCase):
    def test_real_ftp_and_dma_exact_bytes_cleanup_no_mutations(self):
        import socket
        from threading import Thread
        from tests.test_ftp_reads import ReadMigrationTests
        from c64u_ftp_server import FakeC64UFtp
        from c64u_browser.disk_run import receive_exact
        from c64u_browser.managed_library import parse_manifest
        tree={b'/':b'type=dir; USB0\r\n',b'/USB0':b'type=dir; ARGONAUT_LIBRARY\r\n',
              ROOT.encode():b'type=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\ntype=file; manifest.json\r\n',
              (ROOT+'/games').encode():b'type=file;size='+str(len(DATA)).encode()+b'; canonical.d64\r\n'}
        files={(ROOT+'/manifest.json').encode():document(),FILE.encode():DATA}
        received=[];errors=[];done=Event()
        with FakeC64UFtp(directories=tree,files=files.copy()) as ftp, socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(5)
            core,profile=ReadMigrationTests.core(self,ftp)
            core.connect(profile,initial_browse=False)
            library=parse_manifest(document(),core.device_session().device_id,ROOT)
            core.configure_game_library(ROOT,identity=library.identity)
            before=core.preferences.path.read_bytes()
            selection=core.managed_d64_preflight.selection(library,GAME,core.device_session())
            plan=core.managed_d64_preflight.prepare(selection).wait(5).result
            failure_plan=core.managed_d64_preflight.prepare(selection).wait(5).result
            def server():
                try:
                    conn,_=listener.accept()
                    with conn:
                        conn.settimeout(5)
                        auth=receive_exact(conn,4)
                        self.assertEqual(b'\x1f\xff',auth[:2])
                        receive_exact(conn,int.from_bytes(auth[2:],'little'));conn.sendall(b'\x01')
                        header=receive_exact(conn,5)
                        self.assertEqual(b'\x0b\xff',header[:2])
                        received.append(receive_exact(conn,int.from_bytes(header[2:],'little')))
                        self.assertEqual(b'\x0e\xff\0\0',receive_exact(conn,4))
                        conn.sendall(b'\x02OK')
                except BaseException as exc:errors.append(exc)
                finally:done.set()
            worker=Thread(target=server,daemon=True);worker.start()
            original=socket.create_connection
            def local_dma(address,timeout):
                self.assertEqual(0,core._ftp_manager.active_count)
                return original(listener.getsockname(),timeout=timeout)
            with patch('c64u_browser.disk_run.socket.create_connection',side_effect=local_dma) as connect, \
                 patch.object(core._client,'_request_json',side_effect=AssertionError('No REST runner')):
                result=core.execute_managed_d64(plan.plan_id).wait(5)
            self.assertTrue(done.wait(5));worker.join(5)
            self.assertEqual([],errors)
            self.assertEqual('accepted',result.result.outcome,result.error)
            self.assertEqual([DATA],received);connect.assert_called_once()
            ftp.replies[b'SIZE']=b'550 Missing\r\n'
            with patch('c64u_browser.disk_run.socket.create_connection') as no_dma:
                failed=core.execute_managed_d64(failure_plan.plan_id).wait(5)
            self.assertEqual('rejected',failed.result.outcome)
            no_dma.assert_not_called()
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(before,core.preferences.path.read_bytes())
            self.assertEqual(files,ftp.files)
            self.assertFalse(core.game_library.path.exists())
            self.assertLessEqual(set(ftp.verbs),{b'USER',b'PASS',b'FEAT',b'TYPE',b'PASV',b'CWD',b'PWD',b'MLSD',b'LIST',b'SIZE',b'RETR',b'QUIT'})

    def test_session_replaced_after_ftp_cleanup_before_dispatch_admission(self):
        from tests.test_ftp_reads import ReadMigrationTests
        from c64u_ftp_server import FakeC64UFtp
        from c64u_browser.managed_library import parse_manifest
        tree={b'/':b'type=dir; USB0\r\n',b'/USB0':b'type=dir; ARGONAUT_LIBRARY\r\n',
              ROOT.encode():b'type=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\ntype=file; manifest.json\r\n',
              (ROOT+'/games').encode():b'type=file;size='+str(len(DATA)).encode()+b'; canonical.d64\r\n'}
        with FakeC64UFtp(directories=tree,files={(ROOT+'/manifest.json').encode():document(),FILE.encode():DATA}) as ftp:
            core,profile=ReadMigrationTests.core(self,ftp)
            core.connect(profile,initial_browse=False)
            session=core.device_session()
            library=parse_manifest(document(),session.device_id,ROOT)
            core.configure_game_library(ROOT,identity=library.identity)
            service=core.managed_d64_preflight
            selection=service.selection(library,GAME,session)
            plan=service.prepare(selection).wait(5).result
            entered=Event();release=Event();read=service._validated_bytes
            def after_cleanup(*args):
                data=read(*args)
                self.assertEqual(0,core._ftp_manager.active_count)
                entered.set()
                if not release.wait(5):raise AssertionError('Dispatch release missing')
                return data
            with patch.object(service,'_validated_bytes',side_effect=after_cleanup), \
                 patch('c64u_browser.disk_run.socket.create_connection') as dma:
                job=core.execute_managed_d64(plan.plan_id)
                try:
                    self.assertTrue(entered.wait(5))
                    core.connect(profile,initial_browse=False)
                    self.assertNotEqual(session,core.device_session())
                finally:release.set()
                result=job.wait(5)
            self.assertEqual('failed',result.state)
            self.assertEqual('rejected',result.result.outcome)
            self.assertEqual('dispatch-admission',result.result.stage)
            dma.assert_not_called()
            self.assertEqual(0,core._ftp_manager.active_count)
            with self.assertRaises(ManagedD64ExecutionError):core.execute_managed_d64(plan.plan_id)
