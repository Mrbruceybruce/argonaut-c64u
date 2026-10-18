"""Real memory-FTP cleanup authority and coordinator tests; no physical network."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from c64u_browser.api import BrowserError
from c64u_browser.foreground import ForegroundSlot
from c64u_browser.upload_cleanup import UploadCleanup
from c64u_browser.scheduler import DeviceSession
import test_cleanup_intent as intent


class CleanupContinuation(unittest.TestCase):
    setUp=intent.CleanupIntent.setUp
    start=intent.CleanupIntent.start
    finish=intent.CleanupIntent.finish

    def issued(self):
        job,release=self.start()
        self.assertTrue(self.service._request_upload_cancel(job,'delete'))
        result=self.finish(job,release)
        evidence=self.service._take_cleanup_eligibility(job)
        self.assertIsNotNone(evidence)
        return evidence,result

    def prepare(self,evidence):
        job=self.service._prepare_intent_cleanup(evidence)
        self.assertEqual('succeeded',job.wait(5).state)
        return job

    def test_exact_staging_only_no_replay_or_generic_recursion(self):
        evidence,result=self.issued();self.peer.files[b'/USB2/completed']=b'keep'
        self.prepare(evidence)
        with patch('c64u_browser.file_service.delete_reviewed',side_effect=AssertionError('generic recursion')):
            deleted=self.service._execute_intent_cleanup(evidence).wait(5)
        self.assertEqual('succeeded',deleted.state,deleted.error)
        self.assertEqual((evidence.partial_upload.location.path,),deleted.result.removed)
        self.assertEqual(b'keep',self.peer.files[b'/USB2/completed'])
        self.assertFalse(any(call[0]=='rmdir' for call in self.peer.calls))
        for action in (self.service._prepare_intent_cleanup,self.service._execute_intent_cleanup):
            with self.assertRaises(BrowserError):action(evidence)
        self.assertEqual(1,sum(call[0]=='delete' for call in self.peer.calls))

    def test_reconstructed_evidence_rejected(self):
        evidence,_=self.issued()
        with self.assertRaises(BrowserError):self.service._prepare_intent_cleanup(replace(evidence))
        self.prepare(evidence)
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(replace(evidence))

    def test_plan_substitution_rejected_and_retires(self):
        evidence,_=self.issued();job=self.prepare(evidence)
        job.result=replace(job.result,plan_id='another-plan')
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)

    def test_expiry_and_session_replacement(self):
        evidence,_=self.issued();self.prepare(evidence);self.now=301
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))
        evidence,_=self.issued();self.prepare(evidence)
        self.session=DeviceSession('fixture','replacement')
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)

    def test_abandon_running_preparation_prevents_plan_issuance(self):
        from threading import Event
        from c64u_browser.file_service import deletion_snapshot
        evidence,_=self.issued();entered,release=Event(),Event()
        def blocked(*args):
            entered.set();self.assertTrue(release.wait(5));return deletion_snapshot(*args)
        with patch('c64u_browser.file_service.deletion_snapshot',side_effect=blocked):
            job=self.service._prepare_intent_cleanup(evidence)
            self.assertTrue(entered.wait(5))
            self.service._abandon_intent_cleanup(evidence);release.set()
            self.assertEqual('failed',job.wait(5).state)
        self.assertFalse(self.service._delete_plans)
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))

    def test_failed_uncertain_and_success_preserve_evidence_no_retry(self):
        from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, MutationEvidence, Outcome
        for outcome in (Outcome.REJECTED,Outcome.UNKNOWN):
            with self.subTest(outcome=outcome):
                evidence,_=self.issued();self.prepare(evidence)
                def failed(*args):
                    raise FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                        'delete','dele',outcome,True,False,None))
                with patch.object(self.peer,'delete',side_effect=failed) as dispatch:
                    result=self.service._execute_intent_cleanup(evidence).wait(5)
                    self.assertEqual('failed',result.state)
                    self.assertEqual(outcome.value,result.result.mutation['outcome'])
                    self.assertEqual((),result.result.removed)
                    dispatch.assert_called_once()
                    with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
                    dispatch.assert_called_once()


class CleanupCoordinator(unittest.TestCase):
    setUp=intent.CleanupIntent.setUp
    start=intent.CleanupIntent.start
    finish=intent.CleanupIntent.finish

    def context(self,job):
        app=SimpleNamespace(core=SimpleNamespace(files=self.service,device_session=lambda:self.session),
            foreground=ForegroundSlot(),busy=True,cleanup_closed=False,upload_cleanup=None)
        token=app.foreground.reserve();app.foreground.bind(token,job)
        coordinator=UploadCleanup(app,job,token)
        self.sequence=[]
        def run(submit,done,failed=None,**presentation):
            self.assertIsNone(app.foreground.token)
            self.assertFalse(app.busy)
            self.assertEqual(0,self.peer.active)
            token=app.foreground.reserve();app.busy=True
            try:child=submit()
            except Exception as exc:
                app.foreground.release(token);app.busy=False;failed(exc);return False
            app.foreground.bind(token,child);self.sequence.append(child.operation)
            result=child.wait(5)
            app.foreground.release(token,child);app.busy=False
            done(result)
            return True
        app.run_file_job=run
        return app,coordinator,token

    def complete(self,choice='delete',success=False):
        job,release=self.start(success=success)
        app,coordinator,token=self.context(job)
        if choice:self.service._request_upload_cancel(job,choice)
        self.finish(job,release)
        app.foreground.release(token,job);app.busy=False
        return app,coordinator,job

    def test_release_cleanup_refresh_order_duplicate_completion(self):
        app,coordinator,job=self.complete();results=[]
        def refresh(*args):self.sequence.append('refresh');results.append(args)
        coordinator.complete(refresh);coordinator.complete(refresh)
        self.assertEqual(['file.delete.prepare','file.delete.execute','refresh'],self.sequence)
        self.assertEqual(1,len(results));self.assertTrue(results[0][2]);self.assertTrue(results[0][3])
        self.assertIn('Deleted 1 of 1',results[0][1])
        self.assertEqual(0,self.peer.active)

    def test_keep_continue_and_late_success_no_cleanup(self):
        for choice,success in (('keep',False),(None,False),('delete',True)):
            with self.subTest(choice=choice,success=success):
                app,coordinator,job=self.complete(choice,success);done=Mock()
                coordinator.complete(done)
                self.assertFalse(self.sequence);done.assert_called_once()
                if success:self.assertIn('completed despite cancellation',done.call_args.args[1])

    def test_unknown_and_missing_record(self):
        for unknown in (True,False):
            app,coordinator,job=self.complete()
            record=job.result.partial_upload
            if unknown:
                entry=self.service._recoveries[id(record)]
                upload=replace(entry.evidence,disposition='location-unknown')
                entry.evidence=upload;job.result=replace(job.result,uploads=(upload,))
            else:job.result=replace(job.result,partial_upload=None)
            done=Mock();coordinator.complete(done)
            self.assertFalse(self.sequence)
            self.assertIn('uncertain' if unknown else 'No verified incomplete staging file',done.call_args.args[1])

    def test_replacement_and_close_suppress_refresh(self):
        app,coordinator,job=self.complete();self.session=DeviceSession('fixture','new')
        done=Mock();coordinator.complete(done)
        self.assertFalse(self.sequence);done.assert_not_called()
        app,coordinator,job=self.complete();app.cleanup_closed=True;coordinator.close()
        done=Mock();coordinator.complete(done);done.assert_not_called()

    def test_preparation_and_execution_admission_rejection_no_retry(self):
        for stage in ('_prepare_intent_cleanup','_execute_intent_cleanup'):
            app,coordinator,job=self.complete();done=Mock()
            with patch.object(self.service,stage,side_effect=BrowserError('admission refused')) as failure:
                coordinator.complete(done)
                failure.assert_called_once()
                self.assertIn('rejected',done.call_args.args[1])
                coordinator.complete(done);failure.assert_called_once()
            self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))

    def test_concurrent_foreground_does_not_admit_or_refresh(self):
        app,coordinator,job=self.complete();app.foreground.reserve();app.busy=True
        done=Mock();coordinator.complete(done)
        self.assertFalse(self.sequence);done.assert_not_called()

    def test_late_preparation_and_execution_callbacks_are_ignored(self):
        app,coordinator,job=self.complete();saved=[]
        app.run_file_job=lambda submit,done,failed=None,**presentation:saved.append((submit,done)) or True
        done=Mock();coordinator.complete(done);coordinator.close()
        saved[0][1](SimpleNamespace(state='succeeded'))
        coordinator.executed(SimpleNamespace(result=None,error=None))
        done.assert_not_called();self.assertFalse(self.sequence)

    def test_duplicate_preparation_callback_cannot_retire_running_execution(self):
        app,coordinator,job=self.complete();pending=[]
        def run(submit,done,failed=None,**presentation):
            child=submit();pending.append((child,done));return True
        app.run_file_job=run;done=Mock();coordinator.complete(done)
        preparation,prepared=pending[0]
        result=preparation.wait(5);prepared(result)
        self.assertEqual(2,len(pending))
        prepared(result)
        self.assertEqual(2,len(pending));done.assert_not_called()
        execution,executed=pending[1];executed(execution.wait(5));executed(execution.snapshot())
        done.assert_called_once()
        self.assertTrue(done.call_args.args[2])

    def test_uncertain_execution_combined_message_without_retry(self):
        from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, MutationEvidence, Outcome
        app,coordinator,job=self.complete();done=Mock()
        def lost(*args):
            raise FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                'delete','dele',Outcome.UNKNOWN,True,False,None))
        with patch.object(self.peer,'delete',side_effect=lost) as dispatch:
            coordinator.complete(done)
            self.assertFalse(done.call_args.args[2])
            self.assertIn('Result uncertain',done.call_args.args[1])
            self.assertIn('Deleted 0 of 1',done.call_args.args[1])
            coordinator.complete(done);dispatch.assert_called_once()

    def test_busy_admission_refusal_retires_without_refresh_or_retry(self):
        for phase in ('prepare','execute'):
            app,coordinator,job=self.complete();original=app.run_file_job
            def run(submit,done,failed=None,**presentation):
                if phase=='prepare' or coordinator.stage=='executing':return False
                return original(submit,done,failed)
            app.run_file_job=run;done=Mock();coordinator.complete(done)
            self.assertIn('not admitted',done.call_args.args[1])
            self.assertFalse(done.call_args.args[3])
            self.assertIsNone(self.service._take_cleanup_eligibility(job))
            self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))
