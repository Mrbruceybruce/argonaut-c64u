"""Best-effort wording uses captured authority and acknowledged outcomes only."""
import unittest
from unittest.mock import Mock, patch
from c64u_browser.api import BrowserError
from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, MutationEvidence, Outcome
import test_deferred_upload_cleanup as fixtures


class CleanupPresentation(unittest.TestCase):
    setUp=fixtures.CleanupCoordinator.setUp
    start=fixtures.CleanupCoordinator.start
    finish=fixtures.CleanupCoordinator.finish
    context=fixtures.CleanupCoordinator.context
    complete=fixtures.CleanupCoordinator.complete

    def test_changed_size_and_directory_identity_are_safe_failures(self):
        for scenario in ('size','parent'):
            with self.subTest(scenario=scenario):
                app,coordinator,job=self.complete()
                target=job.snapshot().result.partial_upload.location.path
                app.remote='/USB2/unrelated-selection'
                original=self.service._execute_intent_cleanup
                listing=self.client.list_directory
                def execution(evidence):
                    if scenario=='size':self.peer.files[target.encode()]=b'changed size after review'
                    return original(evidence)
                def list_directory(path):
                    actual,entries=listing(path)
                    if scenario=='parent' and coordinator.stage=='executing':actual='/USB2/wrong'
                    return actual,entries
                before=len(self.peer.calls);done=Mock()
                with patch.object(self.service,'_execute_intent_cleanup',side_effect=execution), \
                     patch.object(self.client,'list_directory',side_effect=list_directory):
                    coordinator.complete(done)
                done.assert_called_once();message=done.call_args.args[1]
                self.assertIn('could not safely proceed',message)
                self.assertIn(target,message)
                self.assertIn('may remain',message)
                self.assertNotIn(app.remote,message)
                if scenario=='size':self.assertIn('changed since review',message)
                self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls[before:]))
                self.assertEqual(['file.delete.prepare','file.delete.execute'],self.sequence)
                calls=list(self.peer.calls);coordinator.complete(done)
                self.assertEqual(calls,self.peer.calls);done.assert_called_once()

    def test_definite_rejection_and_uncertainty_never_claim_success(self):
        for outcome in (Outcome.REJECTED,Outcome.UNKNOWN):
            app,coordinator,job=self.complete();done=Mock()
            target=job.snapshot().result.partial_upload.location.path
            failure=FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                'delete','DELE',outcome,True,True,None))
            with patch.object(self.peer,'delete',side_effect=failure) as dispatch:
                coordinator.complete(done);coordinator.complete(done)
                dispatch.assert_called_once()
            message=done.call_args.args[1]
            self.assertIn('was rejected' if outcome==Outcome.REJECTED else 'outcome is uncertain',message)
            self.assertIn(target,message);self.assertIn('may remain',message)
            self.assertNotIn('Cleanup succeeded',message)
            self.assertFalse(done.call_args.args[2])
            with self.assertRaises(BrowserError):
                self.service.prepare_partial_delete(job.snapshot().result.partial_upload)

    def test_acknowledged_success_only_and_completed_files_preserved(self):
        app,coordinator,job=self.complete();done=Mock()
        self.peer.files[b'/USB2/completed']=b'keep'
        coordinator.complete(done)
        self.assertIn('Cleanup succeeded',done.call_args.args[1])
        self.assertIn('Deleted 1 of 1',done.call_args.args[1])
        self.assertNotIn('may remain',done.call_args.args[1])
        self.assertTrue(done.call_args.args[2])
        self.assertEqual(b'keep',self.peer.files[b'/USB2/completed'])
        self.assertEqual(1,sum(c[0]=='delete' for c in self.peer.calls))

    def test_successful_publication_needs_no_cleanup(self):
        app,coordinator,job=self.complete(success=True);done=Mock()
        before=list(self.peer.calls);coordinator.complete(done)
        self.assertIn('Cleanup was not necessary',done.call_args.args[1])
        self.assertEqual(before,self.peer.calls);self.assertEqual([],self.sequence)
        self.assertNotIn('may remain',done.call_args.args[1])

    def test_keep_preserves_manual_partial_authority(self):
        app,coordinator,job=self.complete(choice='keep');done=Mock()
        coordinator.complete(done)
        self.assertEqual([],self.sequence)
        partial=job.snapshot().result.partial_upload
        preview=self.service.prepare_partial_delete(partial).wait(5)
        self.assertEqual('succeeded',preview.state)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_admission_failure_reports_captured_target(self):
        app,coordinator,job=self.complete();done=Mock()
        app.run_file_job=Mock(return_value=False)
        coordinator.complete(done)
        self.assertIn(job.snapshot().result.partial_upload.location.path,done.call_args.args[1])
        self.assertIn('may remain',done.call_args.args[1])
        app.run_file_job.assert_called_once()

    def test_verified_absence_in_preparation_and_execution(self):
        for stage in ('prepare','execute'):
            with self.subTest(stage=stage):
                app,coordinator,job=self.complete();done=Mock()
                partial=job.snapshot().result.partial_upload;target=partial.location.path
                original=self.service._execute_intent_cleanup
                if stage=='prepare':del self.peer.files[target.encode()]
                def execute(evidence):
                    del self.peer.files[target.encode()]
                    return original(evidence)
                before=len(self.peer.calls)
                with patch.object(self.service,'_execute_intent_cleanup',side_effect=execute):
                    coordinator.complete(done)
                done.assert_called_once()
                self.assertEqual('Cleanup was unnecessary: the incomplete staging file was not found during verification.',done.call_args.args[1])
                self.assertFalse(done.call_args.args[2])
                calls=self.peer.calls[before:]
                self.assertEqual(1 if stage=='prepare' else 2,sum(c[0]=='list' for c in calls))
                self.assertFalse(any(c[0] in ('delete','rmdir') for c in calls))
                coordinator.complete(done)
                self.assertEqual(calls,self.peer.calls[before:]);done.assert_called_once()
                self.assertEqual(['file.delete.prepare'] if stage=='prepare' else
                                 ['file.delete.prepare','file.delete.execute'],self.sequence)

    def test_unverified_missing_like_failures_do_not_claim_absence(self):
        from c64u_browser.api import Entry
        for scenario in ('case','parent','listing','unsupported'):
            with self.subTest(scenario=scenario):
                app,coordinator,job=self.complete();done=Mock()
                target=job.snapshot().result.partial_upload.location.path
                name=target.rsplit('/',1)[-1];listing=self.client.list_directory
                def read(path):
                    if scenario=='listing':raise BrowserError('No such path')
                    actual,entries=listing(path)
                    if scenario=='parent':return '/USB2/redirect',[]
                    entries=[Entry(name.upper(),'file',7) if e.name==name and scenario=='case' else
                             Entry(name,'link',7) if e.name==name and scenario=='unsupported' else e for e in entries]
                    return actual,entries
                before=len(self.peer.calls)
                with patch.object(self.client,'list_directory',side_effect=read):coordinator.complete(done)
                message=done.call_args.args[1]
                self.assertNotIn('Cleanup was unnecessary',message)
                self.assertIn('may remain',message)
                self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls[before:]))

    def test_absence_evidence_has_zero_removals_and_matching_target(self):
        app,coordinator,job=self.complete()
        evidence=self.service._take_cleanup_eligibility(job)
        preview=self.service._prepare_intent_cleanup(evidence).wait(5)
        self.assertEqual('succeeded',preview.state)
        target=evidence.partial_upload.location.path
        del self.peer.files[target.encode()]
        result=self.service._execute_intent_cleanup(evidence).wait(5).result
        self.assertEqual(target,result.absent_target)
        self.assertEqual((),result.removed)
        self.assertIsNone(result.mutation)
        self.assertEqual((target,),result.not_attempted)
        from dataclasses import replace
        coordinator.evidence=evidence
        self.assertTrue(coordinator.confirmed_absence(result))
        self.assertFalse(coordinator.confirmed_absence(replace(result,absent_target='/USB2/other')))
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
