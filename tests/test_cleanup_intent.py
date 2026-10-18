"""Network-blocked upload intent tests; all transfers use the memory FTP peer."""
from dataclasses import FrozenInstanceError, replace
from threading import Event, Thread
from unittest.mock import patch
import unittest

from c64u_browser.file_service import CopyRequest, FileLocation
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import DeviceSession
import test_partial_authority as recovery
import c64u_browser.file_service as files


class CleanupIntent(unittest.TestCase):
    setUp = recovery.RecoveryAuthority.setUp
    issue = recovery.RecoveryAuthority.issue

    def start(self, *, success=False):
        preview=self.service.prepare_copy(CopyRequest(FileLocation.core_host(self.root),
            ('new',),FileLocation.c64u('/USB2'))).wait(5)
        self.assertEqual('succeeded',preview.state)
        entered,release=Event(),Event()
        original=files.execute_plan
        def transfer(*args,**kwargs):
            report=original(*args,**kwargs)
            entered.set()
            if not release.wait(5):raise AssertionError('unreleased transfer')
            return report
        self.peer.interrupted=not success
        mock=patch.object(files,'execute_plan',side_effect=transfer)
        mock.start();self.addCleanup(mock.stop);self.addCleanup(release.set)
        job=self.service.execute_copy(preview.result.plan_id)
        self.assertTrue(entered.wait(5))
        return job,release

    def finish(self,job,release):
        release.set()
        result=job.wait(5)
        self.peer.interrupted=False
        return result

    def take_without_work(self,job):
        before=list(self.peer.calls)
        with patch.object(self.scheduler,'submit',side_effect=AssertionError('cleanup submitted')), \
             patch.object(self.service,'prepare_partial_delete',side_effect=AssertionError('cleanup prepared')), \
             patch.object(self.service,'execute_delete',side_effect=AssertionError('cleanup executed')):
            value=self.service._take_cleanup_eligibility(job)
        self.assertEqual(before,self.peer.calls)
        return value

    def test_genuine_origin_immutable_single_use_no_dispatch(self):
        job,release=self.start()
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        result=self.finish(job,release)
        self.assertEqual('failed',result.state)
        record=result.result.partial_upload
        self.assertIs(job,self.service._recoveries[id(record)].origin)
        value=self.take_without_work(job)
        self.assertIs(value.partial_upload,record)
        self.assertEqual(self.session,value.session)
        with self.assertRaises(FrozenInstanceError):value.job_id='other'
        self.assertIsNone(self.take_without_work(job))
        self.assertEqual('available',self.service._recoveries[id(record)].state)

    def test_fabricated_job_same_id_rejected(self):
        job,release=self.start()
        fake=CoreJob(job.operation,lambda _:None);fake.id=job.id
        self.assertFalse(self.service._request_upload_cancel(job.id,'delete'))
        self.assertIsNone(self.take_without_work(job.id))
        self.assertFalse(self.service._request_upload_cancel(fake,'delete'))
        self.assertIsNone(self.take_without_work(fake))
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        self.finish(job,release)
        self.assertIsNotNone(self.take_without_work(job))

    def test_duplicate_and_conflicting_delete_decisions(self):
        job,release=self.start();events=[]
        job.add_listener(lambda event:events.append(event.kind))
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.assertFalse(self.service._request_upload_cancel(job,'keep'))
        self.assertEqual(1,events.count('cancel-requested'))
        self.finish(job,release)
        self.assertIsNotNone(self.take_without_work(job))

    def test_keep_cannot_upgrade(self):
        job,release=self.start()
        self.assertTrue(self.service._request_upload_cancel(job,'keep'))
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.finish(job,release)
        self.assertIsNone(self.take_without_work(job))

    def test_existing_cancellation_cannot_upgrade(self):
        job,release=self.start();self.assertTrue(job.request_cancel())
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.finish(job,release);self.assertIsNone(self.take_without_work(job))

    def test_completion_before_cancel_refused(self):
        job,release=self.start();self.finish(job,release)
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.assertIsNone(self.take_without_work(job))

    def test_success_after_accepted_cancel_never_eligible(self):
        job,release=self.start(success=True)
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        self.assertEqual('succeeded',self.finish(job,release).state)
        self.assertIsNone(self.take_without_work(job))

    def test_cross_job_record_substitution(self):
        other=self.issue().result.partial_upload
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        result=self.finish(job,release)
        # Fault injection at the result boundary: a genuine same-session record
        # from another upload must not satisfy this job's accepted decision.
        job.result=replace(result.result,partial_upload=other)
        self.assertIsNone(self.take_without_work(job))
        job.result=result.result
        self.assertIsNone(self.take_without_work(job))

    def test_unknown_and_published_evidence_rejected(self):
        for disposition in ('location-unknown','published'):
            with self.subTest(disposition=disposition):
                job,release=self.start();self.service._request_upload_cancel(job,'delete')
                result=self.finish(job,release)
                entry=self.service._recoveries[id(result.result.partial_upload)]
                entry.evidence=replace(entry.evidence,disposition=disposition)
                self.assertIsNone(self.take_without_work(job))

    def test_session_and_device_changes(self):
        for changed in (DeviceSession('fixture','new'),DeviceSession('other','fixture-session')):
            with self.subTest(session=changed):
                self.session=DeviceSession('fixture','fixture-session')
                job,release=self.start();self.service._request_upload_cancel(job,'delete')
                self.finish(job,release);self.session=changed
                self.assertIsNone(self.take_without_work(job))
                self.assertFalse(self.service._request_upload_cancel(job,'delete'))

    def test_disconnect_invalidates_even_if_session_value_restored(self):
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        self.service.invalidate_recovery()
        self.finish(job,release)
        self.assertIsNone(self.take_without_work(job))
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))

    def test_shutdown_pending_issuance_and_late_callback(self):
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        self.service.close();result=self.finish(job,release)
        self.assertIsNone(result.result.partial_upload)
        self.assertIsNone(self.take_without_work(job))
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))

    def test_premature_handoff_retires_even_on_failed_validation(self):
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        self.assertIsNone(self.take_without_work(job))
        self.finish(job,release);self.assertIsNone(self.take_without_work(job))

    def test_concurrent_handoff_only_one_winner(self):
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        self.finish(job,release);values=[]
        threads=[Thread(target=lambda:values.append(self.service._take_cleanup_eligibility(job))) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5);self.assertFalse(thread.is_alive())
        self.assertEqual(1,sum(value is not None for value in values))

    def test_receipt_installed_before_reentrant_listener(self):
        job,release=self.start();seen=[]
        def listener(event):
            if event.kind=='cancel-requested':
                origin=self.service._upload_origins[job]
                seen.append((origin.decision,origin.receipt is not None))
                seen.append(self.service._request_upload_cancel(job,'keep'))
        job.add_listener(listener)
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        self.assertEqual([('delete',True),False],seen)
        self.finish(job,release)

    def test_queued_cancel_has_no_recovery(self):
        release,blocker=recovery.RecoveryAuthority.block_lane(self)
        # Use another lane for preparation first would bypass the barrier;
        # instead prepare before installing the next barrier.
        release.set();blocker.wait(5)
        preview=self.service.prepare_copy(CopyRequest(FileLocation.core_host(self.root),('new',),FileLocation.c64u('/USB2'))).wait(5)
        release,blocker=recovery.RecoveryAuthority.block_lane(self)
        job=self.service.execute_copy(preview.result.plan_id)
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        release.set();blocker.wait(5)
        self.assertEqual('cancelled',job.wait(5).state)
        self.assertIsNone(self.take_without_work(job))

    def test_actual_cooperative_cancel_preserves_lease_and_partial(self):
        from c64u_browser.jobs import _current_job
        accepted=[]
        self.peer.before_write=lambda path:accepted.append(
            self.service._request_upload_cancel(_current_job(),'delete'))
        preview=self.service.prepare_copy(CopyRequest(FileLocation.core_host(self.root),
            ('new',),FileLocation.c64u('/USB2'))).wait(5)
        job=self.service.execute_copy(preview.result.plan_id)
        result=job.wait(5)
        self.assertEqual([True],accepted)
        self.assertEqual('cancelled',result.state,result.error)
        self.assertEqual(0,self.peer.active)
        self.assertEqual(self.peer.acquired,self.peer.released)
        self.assertIsNotNone(self.take_without_work(job))
        self.assertFalse(any(call[0] in ('delete','rmdir') for call in self.peer.calls))

    def test_usb_restore_uses_same_trusted_job_context(self):
        from c64u_browser.jobs import _current_job
        from c64u_browser.usb_backup import UsbBackupService, BackupRequest
        self.peer.files[b'/USB2/original']=b'backup bytes'
        usb=UsbBackupService(lambda:self.client,lambda:self.session,self.scheduler,file_service=self.service)
        preview=usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB2'),(),FileLocation.core_host(self.root/'backup'))).wait(5)
        self.assertEqual('succeeded',usb.execute_backup(preview.result.plan_id).wait(5).state)
        del self.peer.files[b'/USB2/original']
        preview=usb.prepare_restore(FileLocation.core_host(self.root/'backup'),FileLocation.c64u('/USB2')).wait(5)
        accepted=[]
        self.peer.before_write=lambda path:accepted.append(self.service._request_upload_cancel(_current_job(),'delete'))
        job=usb.execute_restore(preview.result.plan_id)
        result=job.wait(5)
        self.assertEqual([True],accepted)
        self.assertEqual('cancelled',result.state,result.error)
        value=self.take_without_work(job)
        self.assertIsNotNone(value)
        self.assertIs(value.partial_upload,result.result.partial_upload)

    def test_non_upload_job_rejected_without_cancelling(self):
        job=self.service.prepare_copy(CopyRequest(FileLocation.core_host(self.root),
            ('new',),FileLocation.c64u('/USB2')))
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.assertEqual('succeeded',job.wait(5).state)

    def test_wrong_snapshot_session_retires_intent(self):
        job,release=self.start();self.service._request_upload_cancel(job,'delete')
        self.finish(job,release)
        job._session_id='different'
        self.assertIsNone(self.take_without_work(job))
        job._session_id=self.session.session_id
        self.assertIsNone(self.take_without_work(job))
