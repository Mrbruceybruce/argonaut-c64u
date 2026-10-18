"""Recovery provenance using real copy/restore services and network-free FTP."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError
from c64u_browser.file_service import CopyRequest, FileLocation, FileService, PartialUpload
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding
from c64u_browser.simulated_ftp_reads import MemoryFilesystem
from c64u_browser.usb_backup import UsbBackupService, BackupRequest


class RecoveryAuthority(unittest.TestCase):
    def setUp(self):
        trap=patch('socket.socket.connect',side_effect=AssertionError('Physical networking forbidden'))
        trap.start();self.addCleanup(trap.stop)
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'new').write_bytes(b'payload')
        self.peer=MemoryFilesystem();self.client=self.peer.attach()
        self.session=DeviceSession('fixture','fixture-session');self.now=0
        self.scheduler=CoreScheduler(lambda:self.session)
        self.addCleanup(self.scheduler.close)
        self.service=FileService(lambda:self.client,lambda:self.session,scheduler=self.scheduler,clock=lambda:self.now)
        self.addCleanup(self.service.close)

    def issue(self):
        preview=self.service.prepare_copy(CopyRequest(FileLocation.core_host(self.root),('new',),FileLocation.c64u('/USB2'))).wait(5)
        self.assertEqual('succeeded',preview.state,preview.error)
        self.peer.interrupted=True
        result=self.service.execute_copy(preview.result.plan_id).wait(5)
        self.peer.interrupted=False
        self.assertEqual('failed',result.state)
        return result

    def record(self):
        result=self.issue();self.assertIsNotNone(result.result.partial_upload,result.error)
        return result.result.partial_upload

    def review(self,record):
        before=list(self.peer.calls)
        result=self.service.prepare_partial_delete(record).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertFalse(any(call[0] in ('write','delete','rmdir','rename','mkdir') for call in self.peer.calls[len(before):]))
        return result.result

    def block_lane(self):
        started=Event();release=Event()
        def wait(job):
            started.set()
            if not release.wait(5):raise AssertionError('fixture release missing')
        blocker=self.scheduler.submit(CoreJob('test.barrier',wait),JobBinding.device(self.session))
        self.assertTrue(started.wait(5));self.addCleanup(release.set)
        return release,blocker

    def test_genuine_copy_and_duplicate_confirmation(self):
        record=self.record();preview=self.review(record)
        result=self.service.execute_delete(preview.plan_id).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual((record.location.path,),result.result.removed)
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        self.assertEqual(1,sum(c[0]=='delete' for c in self.peer.calls))

    def test_genuine_restore(self):
        self.peer.files[b'/USB2/original']=b'backup bytes'
        usb=UsbBackupService(lambda:self.client,lambda:self.session,self.scheduler,file_service=self.service)
        preview=usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB2'),(),FileLocation.core_host(self.root/'backup'))).wait(5)
        self.assertEqual('succeeded',preview.state,preview.error)
        self.assertEqual('succeeded',usb.execute_backup(preview.result.plan_id).wait(5).state)
        del self.peer.files[b'/USB2/original']
        restore=usb.prepare_restore(FileLocation.core_host(self.root/'backup'),FileLocation.c64u('/USB2')).wait(5)
        self.assertEqual('succeeded',restore.state,restore.error)
        self.peer.interrupted=True
        result=usb.execute_restore(restore.result.plan_id).wait(5)
        self.peer.interrupted=False
        self.assertEqual('failed',result.state)
        self.assertIsNotNone(result.result.partial_upload)
        self.review(result.result.partial_upload)

    def test_forged_equal_reconstructed_cross_service(self):
        record=self.record()
        other=FileService(lambda:self.client,lambda:self.session,scheduler=self.scheduler)
        self.addCleanup(other.close)
        for claim in (replace(record),PartialUpload(record.location,record.device_id,record.session_id),
                      replace(record,location=FileLocation.c64u('/USB2/ordinary'))):
            with self.subTest(claim=claim):
                with self.assertRaises(BrowserError):self.service.prepare_partial_delete(claim)
        with self.assertRaises(BrowserError):other.prepare_partial_delete(record)
        self.review(record)

    def test_ordinary_folder_and_substituted_directory_not_traversed(self):
        self.peer.directories.add(b'/USB2/ordinary')
        claim=PartialUpload(FileLocation.c64u('/USB2/ordinary'),self.session.device_id,self.session.session_id)
        before=list(self.peer.calls)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(claim)
        self.assertEqual(before,self.peer.calls)
        record=self.record();path=record.location.path.encode();del self.peer.files[path]
        self.peer.directories.add(path);self.peer.files[path+b'/precious']=b'keep'
        before=len(self.peer.calls)
        result=self.service.prepare_partial_delete(record).wait(5)
        self.assertEqual('failed',result.state)
        self.assertIn('no longer a file',result.error.message)
        self.assertNotIn(('list',path),self.peer.calls[before:])
        self.assertIn(path+b'/precious',self.peer.files)

    def test_concurrent_preparation_and_queued_cancel_release(self):
        record=self.record();release,blocker=self.block_lane()
        job=self.service.prepare_partial_delete(record)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        self.assertTrue(job.request_cancel());release.set();blocker.wait(5)
        self.assertEqual('cancelled',job.wait(5).state)
        self.review(record)

    def test_running_cancel_release(self):
        record=self.record();entered=Event();release=Event()
        from c64u_browser.file_service import deletion_snapshot
        def blocked(*args):
            entered.set();self.assertTrue(release.wait(5));return deletion_snapshot(*args)
        with patch('c64u_browser.file_service.deletion_snapshot',side_effect=blocked):
            job=self.service.prepare_partial_delete(record)
            self.assertTrue(entered.wait(5));job.request_cancel();release.set()
            self.assertEqual('cancelled',job.wait(5).state)
        self.review(record)

    def test_failed_prepare_releases(self):
        record=self.record()
        with patch('c64u_browser.file_service.deletion_snapshot',side_effect=BrowserError('read failed')):
            self.assertEqual('failed',self.service.prepare_partial_delete(record).wait(5).state)
        self.review(record)

    def test_admission_failure_releases(self):
        record=self.record()
        with patch.object(self.scheduler,'submit',side_effect=BrowserError('admission')):
            with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        self.review(record)

    def test_discard_and_expiry(self):
        record=self.record();preview=self.review(record)
        self.assertTrue(self.service.discard_plan(preview.plan_id))
        preview=self.review(record);self.now=301;self.service.cleanup()
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        self.review(record)

    def test_capacity_preserves_all_unresolved_records_and_accounting(self):
        records=[self.record() for _ in range(32)]
        overflow=self.issue()
        self.assertIsNone(overflow.result.partial_upload)
        self.assertIsNotNone(overflow.result.partial_path)
        self.assertTrue(overflow.result.uploads)
        self.assertIn('32',overflow.result.failure)
        self.review(records[0]);self.review(records[-1])
        self.assertEqual(32,len(self.service._recoveries))

    def test_session_change_invalidates_record_and_plan(self):
        record=self.record();preview=self.review(record)
        self.session=DeviceSession('fixture','reconnected')
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        self.assertFalse(self.service._recoveries)

    def test_device_change(self):
        record=self.record();self.session=DeviceSession('other',self.session.session_id)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)

    def test_shutdown(self):
        record=self.record();preview=self.review(record);self.service.close()
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        self.assertIsNone(self.issue().result.partial_upload)

    def test_late_issuance_after_session_change(self):
        original=self.peer.before_read
        def changed(path):self.session=DeviceSession('fixture','next')
        self.peer.before_read=changed
        result=self.issue()
        self.assertIsNone(result.result.partial_upload)
        self.assertTrue(result.result.uploads)
        self.assertIn('session ended',result.result.failure)
        self.peer.before_read=original

    def test_invalidation_during_preparation(self):
        record=self.record();entered=Event();release=Event()
        from c64u_browser.file_service import deletion_snapshot
        def blocked(*args):
            entered.set();self.assertTrue(release.wait(5));return deletion_snapshot(*args)
        with patch('c64u_browser.file_service.deletion_snapshot',side_effect=blocked):
            job=self.service.prepare_partial_delete(record);self.assertTrue(entered.wait(5))
            self.service.invalidate_recovery();release.set()
            self.assertEqual('failed',job.wait(5).state)
        self.assertFalse(self.service._delete_plans)

    def test_execute_admission_refusal_consumes(self):
        record=self.record();preview=self.review(record)
        with patch.object(self.scheduler,'submit',side_effect=BrowserError('busy')):
            with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)
        self.assertFalse(any(c[0]=='delete' for c in self.peer.calls))

    def test_cancelled_execution_consumes(self):
        record=self.record();preview=self.review(record);release,blocker=self.block_lane()
        job=self.service.execute_delete(preview.plan_id);job.request_cancel();release.set();blocker.wait(5)
        self.assertEqual('cancelled',job.wait(5).state)
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
        self.assertFalse(any(c[0]=='delete' for c in self.peer.calls))

    def test_failed_and_uncertain_execution_no_replay(self):
        from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, MutationEvidence, Outcome
        for unknown in (False,True):
            with self.subTest(unknown=unknown):
                record=self.record();preview=self.review(record)
                def fail(*args):
                    raise FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                        'delete','delete',Outcome.UNKNOWN if unknown else Outcome.REJECTED,True,unknown,None))
                self.peer.before_mutation=fail
                result=self.service.execute_delete(preview.plan_id).wait(5)
                self.peer.before_mutation=None
                self.assertEqual('failed',result.state)
                self.assertEqual(record.location.path,result.result.stopped_target)
                self.assertEqual('unknown' if unknown else 'rejected',result.result.mutation['outcome'])
                with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)
                with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)

    def test_generic_reviewed_delete_unchanged(self):
        self.peer.directories.add(b'/USB2/ordinary');self.peer.files[b'/USB2/ordinary/keep']=b'file'
        preview=self.service.prepare_delete((FileLocation.c64u('/USB2/ordinary'),)).wait(5)
        self.assertEqual('succeeded',preview.state)
        self.assertEqual('succeeded',self.service.execute_delete(preview.result.plan_id).wait(5).state)

    def test_nonqualifying_evidence_never_issues(self):
        record=self.record();entry=self.service._recoveries[id(record)]
        for disposition in ('location-unknown','published','not-started','no-candidate'):
            report=SimpleNamespace(partial=entry.path,uploads=[replace(entry.evidence,disposition=disposition)],error='interrupted')
            self.assertIsNone(self.service._partial_from_report(report,self.session,'file.copy.execute'))
        report=SimpleNamespace(partial='/USB2/substituted',uploads=[entry.evidence],error='interrupted')
        self.assertIsNone(self.service._partial_from_report(report,self.session,'file.copy.execute'))

    def test_reviewer_final_generic_dispatch_substitution_cannot_choose_rmdir(self):
        # Original P1: generic snapshots saw a file; files._operate's final
        # inspection saw an empty directory and silently switched to RMD.
        import c64u_browser.files as files
        record=self.record();preview=self.review(record);path=record.location.path.encode()
        original=files.inspect
        def substitute(client,target):
            self.peer.files.pop(path,None);self.peer.directories.add(path)
            return original(client,target)
        with patch.object(files,'inspect',side_effect=substitute) as dynamic_inspection:
            result=self.service.execute_delete(preview.plan_id).wait(5)
        dynamic_inspection.assert_not_called()
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual(1,sum(c[0]=='delete' for c in self.peer.calls))
        self.assertFalse(any(c[0]=='rmdir' for c in self.peer.calls))

    def test_execution_directory_substitution_never_traversed(self):
        for nonempty in (False,True):
            with self.subTest(nonempty=nonempty):
                record=self.record();preview=self.review(record);path=record.location.path.encode()
                self.peer.files.pop(path);self.peer.directories.add(path)
                if nonempty:self.peer.files[path+b'/precious']=b'keep'
                before=len(self.peer.calls)
                with patch('c64u_browser.deletion.prepare',side_effect=AssertionError('Recursive recovery forbidden')) as recursive:
                    result=self.service.execute_delete(preview.plan_id).wait(5)
                recursive.assert_not_called()
                self.assertEqual('failed',result.state)
                self.assertEqual((),result.result.removed)
                self.assertEqual((record.location.path,),result.result.not_attempted)
                self.assertIsNone(result.result.mutation)
                calls=self.peer.calls[before:]
                self.assertNotIn(('list',path),calls)
                self.assertFalse(any(c[0] in ('delete','rmdir') for c in calls))
                self.assertIn(path,self.peer.directories)
                if nonempty:self.assertEqual(b'keep',self.peer.files[path+b'/precious'])
                with self.assertRaises(BrowserError):self.service.execute_delete(preview.plan_id)

    def test_execution_changed_file_size_rejected(self):
        record=self.record();preview=self.review(record)
        self.peer.files[record.location.path.encode()]=b'changed file size'
        result=self.service.execute_delete(preview.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_session_replacement_at_final_dispatch_check(self):
        from c64u_browser.deletion import snapshot
        record=self.record();preview=self.review(record)
        def changed(*args):
            observed=snapshot(*args);self.session=DeviceSession('fixture','replacement');return observed
        with patch('c64u_browser.deletion.snapshot',side_effect=changed):
            result=self.service.execute_delete(preview.plan_id).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('delete',result.error.code)
        self.assertIn('connection changed',result.result.failure)
        self.assertIsNone(result.result.mutation)
        self.assertEqual((record.location.path,),result.result.not_attempted)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_cancel_after_snapshot_before_dispatch(self):
        from c64u_browser.deletion import snapshot
        record=self.record();preview=self.review(record);entered=Event();release=Event()
        def blocked(*args):
            observed=snapshot(*args);entered.set();self.assertTrue(release.wait(5));return observed
        with patch('c64u_browser.deletion.snapshot',side_effect=blocked):
            job=self.service.execute_delete(preview.plan_id)
            self.assertTrue(entered.wait(5));job.request_cancel();release.set()
            result=job.wait(5)
        self.assertEqual('cancelled',result.state)
        self.assertEqual((),result.result.removed)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))
        with self.assertRaises(BrowserError):self.service.prepare_partial_delete(record)


class CoreRecoveryLifecycle(unittest.TestCase):
    """Real Core transitions against the suite's isolated loopback FTP server."""
    def check_transition(self, transition):
        from test_ftp_uploads import server, UploadTests
        fixture=UploadTests()
        self.addCleanup(fixture.doCleanups)
        with server() as ftp:
            core,profile=fixture.connect(ftp)
            source=fixture.source()
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),
                ('new',),FileLocation.c64u('/USB1'))).wait(5)
            ftp.replies[b'RETR']=b'550 refused\r\n'
            failed=core.files.execute_copy(preview.result.plan_id).wait(5)
            record=failed.result.partial_upload
            self.assertIsNotNone(record)
            review=core.files.prepare_partial_delete(record).wait(5)
            self.assertEqual('succeeded',review.state)
            before=ftp.verbs.count(b'DELE')
            if transition=='reconnect':core.reconnect(remote_folder='/USB1')
            elif transition=='disconnect':core.disconnect()
            else:core.close()
            self.assertFalse(core.files._recoveries)
            with self.assertRaises(BrowserError):core.files.prepare_partial_delete(record)
            with self.assertRaises(BrowserError):core.files.execute_delete(review.result.plan_id)
            self.assertEqual(before,ftp.verbs.count(b'DELE'))
            self.assertIn(record.location.path.encode(),ftp.files)

    def test_core_disconnect(self):self.check_transition('disconnect')
    def test_core_reconnect(self):self.check_transition('reconnect')
    def test_core_shutdown(self):self.check_transition('shutdown')


class RecoveryFileWire(unittest.TestCase):
    def test_file_only_wire_outcomes_and_last_boundary_substitution(self):
        from test_ftp_uploads import server, UploadTests
        from c64u_browser.ftp_reads import adapter_for
        for outcome in ('success','refused','unknown','empty-directory','nonempty-directory'):
            with self.subTest(outcome=outcome):
                fixture=UploadTests()
                try:
                    with server() as ftp:
                        core,_=fixture.connect(ftp);source=fixture.source()
                        preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),
                            ('new',),FileLocation.c64u('/USB1'))).wait(5)
                        ftp.replies[b'RETR']=b'550 refused\r\n'
                        failed=core.files.execute_copy(preview.result.plan_id).wait(5)
                        record=failed.result.partial_upload;self.assertIsNotNone(record)
                        review=core.files.prepare_partial_delete(record).wait(5)
                        self.assertEqual('succeeded',review.state)
                        path=record.location.path.encode();adapter=adapter_for(core._client)
                        original=adapter.mutate;before=len(ftp.verbs)
                        if outcome=='refused':ftp.replies[b'DELE']=b'550 refused\r\n'
                        if outcome=='unknown':ftp.after_mutation[b'DELE']=None
                        def at_dispatch(operation,target,destination=None):
                            self.assertEqual('delete',operation)
                            self.assertEqual(record.location.path,target)
                            if outcome.endswith('directory'):
                                ftp.files.pop(path);ftp.directories[path]=b''
                                if outcome=='nonempty-directory':ftp.files[path+b'/precious']=b'keep'
                            return original(operation,target,destination)
                        with patch.object(adapter,'mutate',side_effect=at_dispatch):
                            result=core.files.execute_delete(review.result.plan_id).wait(5)
                        self.assertEqual(1,ftp.verbs[before:].count(b'DELE'))
                        self.assertNotIn(b'RMD',ftp.verbs[before:])
                        if outcome=='success':
                            self.assertEqual('succeeded',result.state)
                            self.assertEqual((record.location.path,),result.result.removed)
                        else:
                            self.assertEqual('failed',result.state)
                            self.assertEqual((),result.result.removed)
                            self.assertEqual('unknown' if outcome=='unknown' else 'rejected',result.result.mutation['outcome'])
                            if outcome.endswith('directory'):self.assertIn(path,ftp.directories)
                            if outcome=='nonempty-directory':self.assertEqual(b'keep',ftp.files[path+b'/precious'])
                        with self.assertRaises(BrowserError):core.files.execute_delete(review.result.plan_id)
                        with self.assertRaises(BrowserError):core.files.prepare_partial_delete(record)
                        self.assertEqual(1,ftp.verbs[before:].count(b'DELE'))
                finally:fixture.doCleanups()
