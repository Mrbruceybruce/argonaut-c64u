"""Slice 3B mutation certainty, ownership and Core integration; loopback only."""
import ast
from dataclasses import replace
import json
from pathlib import Path
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from c64u_ftp_server import FakeC64UFtp
import test_c64u_ftp as protocol_fixtures
import test_ftp_reads as read_fixtures
from c64u_browser.c64u_ftp_types import FtpOperationError, Outcome, ErrorCode, FtpPolicy
from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.ftp_reads import adapter_for, read_operation, end_read_attempt
from c64u_browser.files import operate_managed, child
from c64u_browser.file_service import FileLocation
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import JobBinding


def server(**kwargs):
    return FakeC64UFtp(directories={b'/': b'', b'/USB1': b''},
                      files={b'/USB1/Test': b'abc'}, mutation_tree=True, **kwargs)


class MutationProtocolTests(unittest.TestCase):
    manager = protocol_fixtures.ProtocolTests.manager

    def failure(self, client, call):
        with self.assertRaises(FtpOperationError) as caught:call()
        error = caught.exception
        self.assertEqual('failed', client.state.value)
        return error

    def test_rename_refusals_and_lost_replies(self):
        for stage in (b'RNFR', b'RNTO'):
            for lost in (False, True):
                with self.subTest(stage=stage,lost=lost), server() as ftp:
                    if lost:ftp.after_mutation[stage] = None
                    else:ftp.replies[stage] = b'550 SECRET peer prose\r\n'
                    manager = self.manager(ftp)
                    with manager.lease(self.binding) as client:
                        error = self.failure(client, lambda: client.rename(b'/USB1/Test',b'/USB1/New'))
                        evidence = error.mutation
                        expected = ('unknown' if stage == b'RNTO' else 'not-started') if lost else 'rejected'
                        self.assertEqual(expected,evidence.outcome.value)
                        self.assertEqual(stage.decode(),evidence.stage)
                        self.assertTrue(evidence.stage_submitted)
                        self.assertEqual(stage==b'RNTO',evidence.consequential_submitted)
                        self.assertEqual((('RNFR',350),) if stage==b'RNTO' else (),evidence.acknowledged)
                        self.assertEqual(None if lost else 550,evidence.reply_code)
                        self.assertNotIn('SECRET',json.dumps(error.as_dict()))
                    self.assertEqual(0,manager.active_count)
                    self.assertEqual(1,ftp.verbs.count(b'RNFR'))
                    self.assertEqual(int(stage==b'RNTO'),ftp.verbs.count(b'RNTO'))
                    self.assertEqual(lost and stage==b'RNTO',b'/USB1/New' in ftp.files)

    def test_rename_success_and_legacy_reply_classes(self):
        with server(after_mutation={b'RNFR':b'399 Continue\r\n',b'RNTO':b'299 Done\r\n'}) as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                result=client.rename(b'/USB1/Test',b'/USB1/New')
                self.assertEqual(Outcome.COMPLETED,result.outcome)
                self.assertEqual((('RNFR',399),('RNTO',299)),result.acknowledged)
                self.assertEqual(b'abc',ftp.files[b'/USB1/New'])
            self.assertEqual(0,manager.active_count)

    def test_cancel_before_rnfr_and_between_commands(self):
        for before in (True,False):
            with self.subTest(before=before),server() as ftp:
                pending=[False];manager=self.manager(ftp)
                with manager.lease(self.binding,cancelled=lambda:pending[0]) as client:
                    pending[0]=before
                    ftp.mutation_hook=lambda verb,_:pending.__setitem__(0,True)
                    if before:
                        error=self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/New'))
                        self.assertEqual(Outcome.NOT_STARTED,error.outcome)
                        self.assertNotIn(b'RNFR',ftp.verbs)
                    else:
                        self.assertEqual(Outcome.COMPLETED,client.rename(b'/USB1/Test',b'/USB1/New').outcome)
                        self.assertIn(b'RNTO',ftp.verbs)
                self.assertEqual(0,manager.active_count)

    def test_binding_failure_after_acknowledged_rnfr_prevents_rnto(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                original=client._mutation_command
                def command(*args):
                    original(*args)
                    if args[0]=='RNFR':self.current=None
                with patch.object(client,'_mutation_command',side_effect=command):
                    error=self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/New'))
                self.assertEqual(ErrorCode.STALE,error.code)
                self.assertEqual(Outcome.NOT_STARTED,error.outcome)
                self.assertEqual((('RNFR',350),),error.mutation.acknowledged)
                self.assertFalse(error.mutation.stage_submitted)
                self.assertNotIn(b'RNTO',ftp.verbs)

    def test_explicit_invalidation_is_effective_during_deferral(self):
        with server() as ftp:
            manager=self.manager(ftp);pending=[False]
            with manager.lease(self.binding,cancelled=lambda:pending[0]) as client:
                def invalidate(verb,_):
                    pending[0]=True
                    manager.invalidate(self.binding.device.physical_id)
                ftp.mutation_hook=invalidate
                error=self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/New'))
                self.assertEqual(ErrorCode.STALE,error.code)
                self.assertNotIn(b'RNTO',ftp.verbs)

    def test_rnto_send_failure_marks_unknown(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                control=client._control
                class Socket:
                    def __getattr__(self,name):return getattr(control,name)
                    def sendall(self,data):
                        if data.startswith(b'RNTO'):raise OSError('synthetic send failure')
                        return control.sendall(data)
                client._control=Socket()
                error=self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/New'))
                self.assertEqual(Outcome.UNKNOWN,error.outcome)
                self.assertTrue(error.mutation.consequential_submitted)
                self.assertEqual((('RNFR',350),),error.mutation.acknowledged)

    def test_no_command_interleaves_with_rename(self):
        gate=threading.Event();entered=threading.Event();results=[]
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                def hook(verb,_):
                    if verb==b'RNFR':entered.set();gate.wait(2)
                ftp.mutation_hook=hook
                worker=threading.Thread(target=lambda:results.append(client.rename(b'/USB1/Test',b'/USB1/New')))
                worker.start()
                try:
                    self.assertTrue(entered.wait(2))
                    with self.assertRaises(FtpOperationError) as caught:client.size(b'/USB1/Test')
                    self.assertEqual(ErrorCode.BUSY,caught.exception.code)
                finally:gate.set();worker.join(3)
                self.assertEqual(Outcome.COMPLETED,results[0].outcome)
                self.assertEqual([b'RNFR',b'RNTO'],ftp.verbs[-2:])

    def test_failure_after_rnfr_ack_before_rnto_is_not_started(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                send=client._send
                def fail(verb,*args):
                    if verb=='RNTO':raise OSError('disconnected before submission')
                    return send(verb,*args)
                with patch.object(client,'_send',side_effect=fail):
                    error=self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/New'))
                self.assertEqual(Outcome.NOT_STARTED,error.outcome)
                self.assertFalse(error.mutation.consequential_submitted)
                self.assertEqual((('RNFR',350),),error.mutation.acknowledged)
                self.assertNotIn(b'RNTO',ftp.verbs)

    def test_timeout_and_malformed_completion_are_unknown(self):
        for fault in ('timeout','malformed','unexpected'):
            with self.subTest(fault=fault),server() as ftp:
                gate=threading.Event()
                manager=self.manager(ftp,policy=FtpPolicy(control_reply=.05))
                with manager.lease(self.binding) as client:
                    if fault=='timeout':
                        ftp.after_mutation[b'MKD']=lambda _:(gate.wait(1),b'257 done\r\n')[1]
                    else:ftp.after_mutation[b'MKD']=b'garbage\r\n' if fault=='malformed' else b'350 later\r\n'
                    try:error=self.failure(client,lambda:client.mkdir(b'/USB1/new'))
                    finally:gate.set()
                    self.assertEqual(Outcome.UNKNOWN,error.outcome)
                    self.assertTrue(error.mutation.consequential_submitted)
                    self.assertIn(b'/USB1/new',ftp.directories)
                self.assertEqual(0,manager.active_count)

    def test_recovery_invalidation_after_submission_keeps_evidence(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                ftp.mutation_hook=lambda *_:manager.invalidate(self.binding.device.physical_id,recovering=True)
                with self.assertRaises(FtpOperationError) as caught:client.mkdir(b'/USB1/new')
                error=caught.exception
                self.assertEqual(ErrorCode.RECOVERING,error.code)
                self.assertEqual(Outcome.UNKNOWN,error.outcome)
                self.assertTrue(error.mutation.consequential_submitted)
                self.assertEqual('recovering',client.state.value)

    def test_single_mutation_accept_refuse_and_lost_completion(self):
        for method,verb in (('mkdir',b'MKD'),('delete',b'DELE'),('rmdir',b'RMD')):
            for mode in ('accept','refuse','lost'):
                with self.subTest(verb=verb,mode=mode),server() as ftp:
                    ftp.directories[b'/USB1/empty']=b''
                    path=b'/USB1/Test' if method=='delete' else b'/USB1/new' if method=='mkdir' else b'/USB1/empty'
                    if mode=='refuse':ftp.replies[verb]=b'550 PRIVATE\r\n'
                    if mode=='lost':ftp.after_mutation[verb]=None
                    manager=self.manager(ftp)
                    with manager.lease(self.binding) as client:
                        call=lambda:getattr(client,method)(path)
                        result=call() if mode=='accept' else self.failure(client,call).mutation
                        self.assertEqual({'accept':'completed','refuse':'rejected','lost':'unknown'}[mode],result.outcome.value)
                        self.assertTrue(result.consequential_submitted)
                    self.assertEqual(0,manager.active_count)
                    self.assertEqual(1,ftp.verbs.count(verb))

    def test_single_mutation_legacy_codes_and_late_cancel(self):
        for method,verb,code in (('mkdir',b'MKD',299),('delete',b'DELE',200),('rmdir',b'RMD',299)):
            with self.subTest(method=method),server() as ftp:
                ftp.directories[b'/USB1/empty']=b'';pending=[False]
                ftp.after_mutation[verb]=str(code).encode()+b' done\r\n'
                ftp.mutation_hook=lambda *_:pending.__setitem__(0,True)
                manager=self.manager(ftp)
                with manager.lease(self.binding,cancelled=lambda:pending[0]) as client:
                    path=b'/USB1/Test' if method=='delete' else b'/USB1/new' if method=='mkdir' else b'/USB1/empty'
                    result=getattr(client,method)(path)
                    self.assertEqual(code,result.reply_code)
                    self.assertEqual(Outcome.COMPLETED,result.outcome)

    def test_single_mutation_cancel_before_submission(self):
        for method in ('mkdir','delete','rmdir'):
            with self.subTest(method=method),server() as ftp:
                pending=[False];manager=self.manager(ftp)
                with manager.lease(self.binding,cancelled=lambda:pending[0]) as client:
                    pending[0]=True
                    error=self.failure(client,lambda:getattr(client,method)(b'/USB1/Test'))
                    self.assertEqual(Outcome.NOT_STARTED,error.outcome)
                    self.assertFalse(error.mutation.stage_submitted)
                self.assertFalse(set(ftp.verbs)&{b'MKD',b'DELE',b'RMD'})

    def test_nonempty_directory_refused(self):
        with server() as ftp:
            manager=self.manager(ftp)
            with manager.lease(self.binding) as client:
                error=self.failure(client,lambda:client.rmdir(b'/USB1'))
                self.assertEqual(Outcome.REJECTED,error.outcome)
                self.assertIn(b'/USB1/Test',ftp.files)

    def test_diagnostics_are_sanitized(self):
        with server(after_mutation={b'RNTO':None}) as ftp:
            events=[];manager=self.manager(ftp,'password-SECRET',events=events)
            with manager.lease(self.binding) as client:
                self.failure(client,lambda:client.rename(b'/USB1/Test',b'/USB1/PRIVATE'))
            text=json.dumps(events)
            for secret in ('password-SECRET','/USB1','PRIVATE','PASS'):self.assertNotIn(secret,text)
            error=next(e for e in events if e['kind']=='error')
            self.assertEqual('unknown',error['mutation']['outcome'])
            self.assertEqual('RNTO',error['mutation']['stage'])


class MutationCoreTests(unittest.TestCase):
    core=read_fixtures.ReadMigrationTests.core
    connect=read_fixtures.ReadMigrationTests.connect

    def rename(self,core,name='New'):
        return core.files.rename(FileLocation.c64u('/USB1/Test'),name).wait(5)

    def test_rename_and_mkdir_use_managed_jobs_and_one_lease(self):
        with server() as ftp:
            core,_=self.connect(ftp);epoch=core.device_session();before=ftp.connections
            with patch('ftplib.FTP',side_effect=AssertionError('legacy mutation')):
                result=self.rename(core)
                self.assertEqual('succeeded',result.state,result.error)
                self.assertEqual('file.rename',result.operation)
                self.assertEqual('c64u:'+epoch.device_id,result.lane)
                self.assertEqual('/USB1/New',result.result.destination)
                self.assertEqual(1,ftp.connections-before)
                folder=core.files.create_folder(FileLocation.c64u('/USB1'),'newdir').wait(5)
                self.assertEqual('succeeded',folder.state,folder.error)
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(epoch,core.device_session())
            self.assertEqual(ftp.connections,ftp.verbs.count(b'FEAT'))
            self.assertEqual(ftp.connections,ftp.verbs.count(b'USER'))

    def test_nested_mutations_and_listings_share_lease(self):
        with server() as ftp:
            core,_=self.connect(ftp);before=ftp.connections
            with read_operation(core._client):
                core._client.list_directory('/USB1')
                operate_managed(core._client,'mkdir','/USB1/fresh')
                operate_managed(core._client,'rename','/USB1/Test','New')
                self.assertEqual(1,core._ftp_manager.active_count)
            self.assertEqual(1,ftp.connections-before)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_case_only_success_exact_case_and_no_redundant_sessions(self):
        with server() as ftp:
            core,_=self.connect(ftp);before=ftp.connections
            result=self.rename(core,'test')
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual('passed',result.result.verification)
            self.assertEqual(2,len(result.result.completed))
            self.assertIn(b'/USB1/test',ftp.files)
            self.assertEqual(1,ftp.connections-before)
            self.assertEqual(2,ftp.verbs.count(b'RNTO'))

    def test_case_only_first_and_second_step_failures(self):
        for first,mode in ((True,'lost'),(False,'refuse'),(False,'lost')):
            with self.subTest(first=first,mode=mode),server() as ftp:
                core,_=self.connect(ftp);calls=[0]
                if mode=='lost':
                    def reply(_):
                        calls[0]+=1
                        return None if calls[0]==(1 if first else 2) else b'250 done\r\n'
                    ftp.after_mutation[b'RNTO']=reply
                else:
                    # Install refusal only after the first RNTO has completed.
                    ftp.mutation_hook=lambda verb,_:ftp.replies.update({b'RNTO':b'550 refused\r\n'}) if verb==b'RNTO' else None
                result=self.rename(core,'test')
                self.assertEqual('failed',result.state)
                self.assertEqual(0 if first else 1,len(result.result.completed))
                self.assertEqual('unknown' if mode=='lost' else 'rejected',result.result.stopped['outcome'])
                self.assertTrue(result.result.temporary.startswith('/USB1/c64u-rename-'))
                self.assertFalse(result.error.retryable)
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertEqual(1 if first else 2,ftp.verbs.count(b'RNTO'))
                if mode=='refuse':self.assertIn(result.result.temporary.encode(),ftp.files)

    def test_case_verification_mismatch_keeps_completed_steps(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def hook(verb,path):
                if verb==b'RNTO' and path==b'/USB1/test':ftp.files[b'/USB1/TEST']=ftp.files.pop(path)
            ftp.mutation_hook=hook
            result=self.rename(core,'test')
            self.assertEqual('failed',result.state)
            self.assertEqual(2,len(result.result.completed))
            self.assertEqual('failed',result.result.verification)
            self.assertIsNone(result.result.stopped)

    def test_case_cancel_before_verification_keeps_completed_steps(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def task(job):
                ftp.mutation_hook=lambda verb,_:job.request_cancel()
                return operate_managed(core._client,'rename','/USB1/Test','test',check=job.check_cancel)
            result=CoreJob('case-cancel',task).run()
            self.assertEqual('cancelled',result.state)
            self.assertEqual(2,len(result.result.completed))
            self.assertEqual('unperformed',result.result.verification)
            self.assertIn(b'/USB1/test',ftp.files)
            self.assertEqual(0,core._ftp_manager.active_count)
            ftp.mutation_hook=None
            self.assertEqual('succeeded',core.files.create_folder(FileLocation.c64u('/USB1'),'next').wait(5).state)

    def test_failed_mutation_cannot_use_read_fallback_or_reopen(self):
        with server(after_mutation={b'MKD':None}) as ftp:
            core,_=self.connect(ftp);before=ftp.connections
            with read_operation(core._client):
                with self.assertRaises(ConnectionFailure):operate_managed(core._client,'mkdir','/USB1/new')
                with self.assertRaisesRegex(BrowserError,'cannot restart'):end_read_attempt(core._client)
                with self.assertRaises(ConnectionFailure):core._client.list_directory('/USB1')
            self.assertEqual(1,ftp.connections-before)
            self.assertEqual(1,ftp.verbs.count(b'MKD'))
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_stale_binding_rejected_without_wire_access(self):
        with server() as ftp:
            core,_=self.connect(ftp);old=core._client
            core.disconnect();before=ftp.connections
            with self.assertRaises(ConnectionFailure):operate_managed(old,'mkdir','/USB1/new')
            self.assertEqual(before,ftp.connections)

    def test_queued_rename_rejected_after_session_change(self):
        with server() as ftp:
            core,_=self.connect(ftp);entered=threading.Event();gate=threading.Event()
            blocker=CoreJob('block',lambda _:(entered.set(),gate.wait(3)))
            core.files._scheduler.submit(blocker,JobBinding.device(core.device_session()))
            self.assertTrue(entered.wait(2))
            try:
                job=core.files.rename(FileLocation.c64u('/USB1/Test'),'New')
                core.disconnect()
            finally:gate.set()
            result=job.wait(5)
            self.assertEqual('failed',result.state)
            self.assertNotIn(b'RNFR',ftp.verbs)

    def test_rename_policy_noop_conflict_and_source_validation(self):
        for name,source in (('Test','Test'),('Other','Test'),('New','test'),('../bad','Test')):
            with self.subTest(name=name,source=source),server() as ftp:
                core,_=self.connect(ftp);ftp.files[b'/USB1/Other']=b'keep'
                result=core.files.rename(FileLocation.c64u('/USB1/'+source),name).wait(5)
                self.assertEqual('succeeded' if name=='Test' else 'failed',result.state)
                self.assertNotIn(b'RNFR',ftp.verbs)

    def prepare_deletion(self,core,ftp):
        ftp.directories[b'/USB1/folder']=b''
        ftp.files.update({b'/USB1/folder/a':b'a',b'/USB1/folder/b':b'b'})
        preview=core.files.prepare_delete((FileLocation.c64u('/USB1/folder'),)).wait(5)
        self.assertEqual('succeeded',preview.state,preview.error)
        return preview.result

    def test_reviewed_deletion_ordering_and_one_execution_lease(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare_deletion(core,ftp);before=ftp.connections
            with patch('ftplib.FTP',side_effect=AssertionError('legacy deletion')):
                result=core.files.execute_delete(preview.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(('/USB1/folder/a','/USB1/folder/b','/USB1/folder'),result.result.removed)
            commands=[(v,p) for v,p in ftp.commands if v in (b'DELE',b'RMD')]
            self.assertEqual([(b'DELE',b'/USB1/folder/a'),(b'DELE',b'/USB1/folder/b'),(b'RMD',b'/USB1/folder')],commands)
            self.assertEqual(1,ftp.connections-before)
            self.assertEqual(0,core._ftp_manager.active_count)
            with self.assertRaises(BrowserError):core.files.execute_delete(preview.plan_id)

    def test_reviewed_partial_deletion_refused_and_unknown(self):
        for lost in (False,True):
            with self.subTest(lost=lost),server() as ftp:
                core,_=self.connect(ftp);preview=self.prepare_deletion(core,ftp)
                if lost:
                    ftp.after_mutation[b'DELE']=lambda p:None if p.endswith(b'/b') else b'250 done\r\n'
                else:
                    ftp.mutation_hook=lambda v,p:ftp.replies.update({b'DELE':b'550 refused\r\n'}) if v==b'DELE' else None
                result=core.files.execute_delete(preview.plan_id).wait(5)
                self.assertEqual('failed',result.state)
                self.assertEqual(('/USB1/folder/a',),result.result.removed)
                self.assertEqual('/USB1/folder/b',result.result.stopped_target)
                self.assertEqual('unknown' if lost else 'rejected',result.result.mutation['outcome'])
                self.assertEqual(('/USB1/folder',),result.result.not_attempted)
                self.assertNotIn(b'RMD',ftp.verbs)
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertNotIn('FtpOperationError',json.dumps(result.as_dict()))

    def test_reviewed_changed_tree_refuses_every_mutation(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare_deletion(core,ftp)
            ftp.files[b'/USB1/folder/new']=b'new'
            result=core.files.execute_delete(preview.plan_id).wait(5)
            self.assertEqual('failed',result.state)
            self.assertEqual((),result.result.removed)
            self.assertEqual(tuple(i.path for i in preview.items),result.result.not_attempted)
            self.assertFalse(set(ftp.verbs)&{b'DELE',b'RMD'})

    def test_reviewed_cancel_after_ack_records_removed(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare_deletion(core,ftp)
            gate=threading.Event();entered=threading.Event()
            def hook(verb,_):
                if verb==b'DELE':entered.set();gate.wait(3)
            ftp.mutation_hook=hook
            job=core.files.execute_delete(preview.plan_id)
            try:
                self.assertTrue(entered.wait(2));job.request_cancel()
            finally:gate.set()
            result=job.wait(5)
            self.assertEqual('cancelled',result.state)
            self.assertEqual(('/USB1/folder/a',),result.result.removed)
            self.assertEqual(('/USB1/folder/b','/USB1/folder'),result.result.not_attempted)
            self.assertEqual(1,ftp.verbs.count(b'DELE'))

    def test_partial_upload_reviewed_cleanup_is_session_bound(self):
        from c64u_browser.file_service import PartialUpload
        with server() as ftp:
            core,_=self.connect(ftp);session=core.device_session()
            ftp.files[b'/USB1/c64u-part-owned']=b'partial'
            partial=PartialUpload(FileLocation.c64u('/USB1/c64u-part-owned'),session.device_id,session.session_id)
            preview=core.files.prepare_partial_delete(partial).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)
            result=core.files.execute_delete(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(('/USB1/c64u-part-owned',),result.result.removed)
            self.assertNotIn(b'/USB1/c64u-part-owned',ftp.files)
            core.disconnect()
            with self.assertRaises(BrowserError):core.files.prepare_partial_delete(partial)

    def test_unknown_with_cancellation_pending_is_failure_not_cancelled(self):
        with server(after_mutation={b'RNTO':None}) as ftp:
            core,_=self.connect(ftp)
            def task(job):
                ftp.mutation_hook=lambda *_:job.request_cancel()
                return core.files._managed_mutation(core._client,'rename','/USB1/Test',new_name='New',check=job.check_cancel)
            result=CoreJob('unknown-cancel',task).run()
            self.assertEqual('failed',result.state)
            self.assertEqual('unknown',result.result.stopped['outcome'])
            self.assertFalse(result.error.retryable)
            self.assertEqual(1,ftp.verbs.count(b'RNTO'))

    def test_single_folder_failure_has_structured_nonretryable_result(self):
        with server(replies={b'MKD':b'421 too many ftp connections PRIVATE\r\n'}) as ftp:
            core,_=self.connect(ftp)
            result=core.files.create_folder(FileLocation.c64u('/USB1'),'new').wait(5)
            self.assertEqual('failed',result.state)
            self.assertEqual('rejected',result.result.stopped['outcome'])
            self.assertEqual(421,result.result.stopped['reply_code'])
            self.assertFalse(result.error.retryable)
            self.assertNotIn('PRIVATE',json.dumps(result.as_dict()))

    def test_case_verification_connection_loss_keeps_acknowledgements(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def hook(verb,path):
                if verb==b'RNTO' and path==b'/USB1/test':ftp.replies[b'CWD']=None
            ftp.mutation_hook=hook
            result=self.rename(core,'test')
            self.assertEqual('failed',result.state)
            self.assertEqual(2,len(result.result.completed))
            self.assertEqual('unperformed',result.result.verification)
            self.assertIsNone(result.result.stopped)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_deferral_does_not_suppress_unrelated_callback_failure(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=adapter_for(core._client);failure=BrowserError('callback failed')
            pending=[False]
            def check():
                if pending[0]:raise failure
            with adapter.operation(check):
                with adapter.defer_cancellation():
                    pending[0]=True
                    with self.assertRaises(BrowserError) as caught:adapter.mutate('mkdir','/USB1/new')
                    self.assertIs(failure,caught.exception)
            self.assertNotIn(b'MKD',ftp.verbs)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_delete_roots_and_nonempty_standalone_are_refused(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            for root in ('/','/USB1'):
                result=core.files.prepare_delete((FileLocation.c64u(root),)).wait(5)
                self.assertEqual('failed',result.state)
            ftp.directories[b'/USB1/full']=b'';ftp.files[b'/USB1/full/a']=b'a'
            with self.assertRaisesRegex(BrowserError,'not empty'):
                operate_managed(core._client,'delete','/USB1/full',confirmation='/USB1/full')
            self.assertNotIn(b'RMD',ftp.verbs)

    def test_managed_missing_adapter_never_falls_back(self):
        with patch('c64u_browser.files.connect') as raw:
            with self.assertRaises(BrowserError):operate_managed(SimpleNamespace(),'mkdir','/USB1/new')
            raw.assert_not_called()


class MutationRoutingTests(unittest.TestCase):
    def test_gui_remote_schedules_and_local_keeps_gio(self):
        source=Path('c64u_browser/gui.py').read_text();tree=ast.parse(source)
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='rename_item')
        gio=Mock();namespace={'child':child,'FileLocation':FileLocation,'Gio':gio}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<gui-rename>','exec'),namespace)
        browser=Mock();browser.remote='/USB1';browser.local=Path('/tmp');browser.client=object()
        browser.prompt.side_effect=lambda *a,**k:a[2]('New')
        namespace['rename_item'](browser,False,'Test')
        browser.core.files.rename.assert_called_once_with(FileLocation.c64u('/USB1/Test'),'New')
        browser.run_file_job.assert_called_once();browser.run.assert_not_called()
        browser.reset_mock();browser.run.side_effect=lambda task,done:task()
        namespace['rename_item'](browser,True,'Test')
        browser.core.files.rename.assert_not_called();browser.run_file_job.assert_not_called()
        gio.File.new_for_path.return_value.move.assert_called_once()
        self.assertEqual(gio.FileCopyFlags.NONE,gio.File.new_for_path.return_value.move.call_args.args[1])

    def rename_gui(self):
        tree=ast.parse(Path('c64u_browser/gui.py').read_text())
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='rename_item')
        namespace={'child':child,'FileLocation':FileLocation,'Gio':Mock()}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<gui-rename>','exec'),namespace)
        browser=Mock();browser.remote='/USB1';browser.client=Mock()
        binding=SimpleNamespace(device_id='device-A',session_id='session-A')
        browser.core.device_session.return_value=binding
        browser.core.files.rename.return_value.snapshot.return_value=binding
        browser.prompt.side_effect=lambda *a,**k:a[2]('New')
        namespace['rename_item'](browser,False,'Test')
        done=browser.run_file_job.call_args.args[1]
        result=SimpleNamespace(state='succeeded',device_id='device-A',session_id='session-A',
                               result=SimpleNamespace(destination='/USB1/New'))
        return browser,done,result

    def test_gui_same_session_completion_refreshes_intended_folder(self):
        browser,done,result=self.rename_gui()
        done(result)
        browser.refresh_local.assert_called_once()
        browser.run.assert_called_once()
        refresh,apply=browser.run.call_args.args
        listing=('/USB1',[]);browser.client.list_directory.return_value=listing
        apply(refresh())
        browser.client.list_directory.assert_called_once_with('/USB1')
        browser.show_remote.assert_called_once_with(listing)
        browser.status.set_text.assert_called_with('Completed: /USB1/New')
        browser.core.files.rename.assert_called_once()
        # Current-context errors still reach Browser.run's existing handling.
        failure=ConnectionFailure('network','refresh failed')
        browser.client.list_directory.side_effect=failure
        with self.assertRaises(ConnectionFailure) as caught:apply(refresh())
        self.assertIs(failure,caught.exception)

    def test_gui_old_session_completion_with_same_facade_does_not_refresh(self):
        for device,session in (('device-A','session-B'),('device-B','session-B')):
            with self.subTest(device=device):
                browser,done,result=self.rename_gui();facade=browser.client
                browser.core.device_session.return_value=SimpleNamespace(device_id=device,session_id=session)
                done(result)
                self.assertIs(facade,browser.client)
                browser.run.assert_not_called();browser.refresh_local.assert_not_called()
                facade.list_directory.assert_not_called();browser.show_remote.assert_not_called()
                browser.status.set_text.assert_called_with('Rename completed on the previous connection.')
                browser.core.files.rename.assert_called_once()

    def test_gui_folder_change_before_completion_does_not_start_refresh(self):
        browser,done,result=self.rename_gui();browser.remote='/USB1/other'
        done(result)
        browser.run.assert_not_called();browser.client.list_directory.assert_not_called()
        browser.show_remote.assert_not_called()

    def test_gui_refresh_worker_rechecks_session_and_folder_before_read(self):
        for change in ('session','folder'):
            with self.subTest(change=change):
                browser,done,result=self.rename_gui();done(result)
                refresh,apply=browser.run.call_args.args
                if change=='session':
                    browser.core.device_session.return_value=SimpleNamespace(device_id='device-A',session_id='session-B')
                else:browser.remote='/USB1/other'
                apply(refresh())
                browser.client.list_directory.assert_not_called();browser.show_remote.assert_not_called()
                browser.core.files.rename.assert_called_once()

    def test_gui_inflight_refresh_result_and_error_are_discarded_after_context_change(self):
        for change in ('device','session','folder'):
            for fails in (False,True):
                with self.subTest(change=change,fails=fails):
                    browser,done,result=self.rename_gui();done(result)
                    refresh,apply=browser.run.call_args.args
                    if fails:browser.client.list_directory.side_effect=OSError('old read failed')
                    else:browser.client.list_directory.return_value=('/USB1',[])
                    listing=refresh()
                    browser.client.list_directory.assert_called_once_with('/USB1')
                    if change=='folder':browser.remote='/USB1/other'
                    else:browser.core.device_session.return_value=SimpleNamespace(
                        device_id='device-B' if change=='device' else 'device-A',session_id='session-B')
                    browser.status.reset_mock()
                    apply(listing)
                    browser.show_remote.assert_not_called();browser.status.set_text.assert_not_called()
                    browser.core.files.rename.assert_called_once()

    def test_deferred_composites_keep_explicit_legacy_routes(self):
        # These are migration-boundary assertions; full behavioral suites still run.
        for name in ('folder_copy','replacement','transfers','native_files'):
            source=Path('c64u_browser/'+name+'.py').read_text()
            self.assertNotIn('operate_managed',source)
        for name in ('folder_copy','replacement'):
            tree=ast.parse(Path('c64u_browser/'+name+'.py').read_text())
            self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                                and n.func.id=='operate' for n in ast.walk(tree)))
        for name in ('transfers','replacement'):
            source=Path('c64u_browser/'+name+'.py').read_text()
            self.assertIn('ftp.rename(',source)
        native=ast.parse(Path('c64u_browser/native_files.py').read_text())
        publisher=next(n for n in native.body if isinstance(n,ast.FunctionDef) and n.name=='_upload_flash')
        calls=[n.func for n in ast.walk(publisher) if isinstance(n,ast.Call)]
        self.assertFalse(any(isinstance(n,ast.Name) and n.id=='connect' for n in calls))
        self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr in
                             ('rename','storbinary','open_ftp') for n in calls))
        self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                            and n.func.attr=='mutate' and n.args
                            and isinstance(n.args[0],ast.Constant) and n.args[0].value=='rename'
                            for n in ast.walk(publisher)))
        # The separate native read compatibility route is still deferred.
        reader=next(n for n in native.body if isinstance(n,ast.FunctionDef) and n.name=='_read_remote')
        self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
                            and n.func.id=='connect' for n in ast.walk(reader)))
        self.assertIn('def open_ftp(',Path('c64u_browser/core.py').read_text())


if __name__=='__main__':unittest.main()
