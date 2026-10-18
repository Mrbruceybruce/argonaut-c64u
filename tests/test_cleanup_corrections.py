"""Safety review regressions: teardown evidence and stale completion silence."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from c64u_browser.api import BrowserError
from c64u_browser.file_service import DeleteResult
from c64u_browser.scheduler import DeviceSession
from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, MutationEvidence, Outcome
import test_deferred_upload_cleanup as fixtures


class RecoveryTeardown(unittest.TestCase):
    setUp=fixtures.CleanupContinuation.setUp
    start=fixtures.CleanupContinuation.start
    finish=fixtures.CleanupContinuation.finish
    issued=fixtures.CleanupContinuation.issued
    prepare=fixtures.CleanupContinuation.prepare

    def test_acknowledgement_survives_resource_teardown_exceptions(self):
        for failure in (OSError('lease close failed'),RuntimeError('teardown failed')):
            with self.subTest(failure=type(failure).__name__):
                evidence,_=self.issued();self.prepare(evidence)
                original=self.peer.lease
                @contextmanager
                def broken(*args,**kwargs):
                    with original(*args,**kwargs) as resource:yield resource
                    raise failure
                with patch.object(self.peer,'lease',broken):
                    result=self.service._execute_intent_cleanup(evidence).wait(5)
                self.assertEqual('failed',result.state)
                self.assertEqual((evidence.partial_upload.location.path,),result.result.removed)
                self.assertEqual((),result.result.not_attempted)
                self.assertEqual('completed',result.result.mutation['outcome'])
                self.assertIn('Deleted 1 of 1',result.result.message)
                self.assertIn(str(failure),result.result.message)
                self.assertNotIn('uncertain',result.result.message)
                before=list(self.peer.calls)
                with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
                self.assertEqual(before,self.peer.calls)

    def test_dispatched_without_evidence_is_uncertain_not_unattempted(self):
        evidence,_=self.issued();self.prepare(evidence)
        original=self.peer.delete
        def lost(path):
            original(path)
            raise OSError('acknowledgement lost')
        with patch.object(self.peer,'delete',side_effect=lost) as dispatch:
            result=self.service._execute_intent_cleanup(evidence).wait(5)
            dispatch.assert_called_once()
        self.assertEqual((),result.result.removed)
        self.assertEqual((),result.result.not_attempted)
        self.assertEqual('unknown',result.result.mutation['outcome'])
        self.assertIn('Result uncertain',result.result.message)
        with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)

    def test_explicit_predispatch_rejection_survives_teardown(self):
        evidence,_=self.issued();self.prepare(evidence)
        def rejected(*args):
            raise FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                'delete','DELE',Outcome.REJECTED,False,False,None))
        original=self.peer.lease
        @contextmanager
        def broken(*args,**kwargs):
            try:
                with original(*args,**kwargs) as resource:yield resource
            finally:raise OSError('teardown failed too')
        with patch.object(self.peer,'delete',side_effect=rejected),patch.object(self.peer,'lease',broken):
            result=self.service._execute_intent_cleanup(evidence).wait(5)
        self.assertEqual('rejected',result.result.mutation['outcome'])
        self.assertEqual((evidence.partial_upload.location.path,),result.result.not_attempted)
        self.assertEqual((),result.result.removed)
        self.assertNotIn('uncertain',result.result.message)


class CompletionOwnership(unittest.TestCase):
    setUp=fixtures.CleanupCoordinator.setUp
    start=fixtures.CleanupCoordinator.start
    finish=fixtures.CleanupCoordinator.finish
    context=fixtures.CleanupCoordinator.context
    complete=fixtures.CleanupCoordinator.complete

    def test_stale_success_rejection_uncertainty_and_no_result_are_silent(self):
        for outcome in ('success','rejected','uncertain','no-result'):
            for invalidation in ('session','disconnect','client','owner','closed','foreground'):
                with self.subTest(outcome=outcome,invalidation=invalidation):
                    app,coordinator,job=self.complete();done=Mock()
                    app.status='current status'
                    def ui(*args):app.status='stale status';done(*args)
                    app.run_file_job=lambda *args,**kwargs:True
                    coordinator.complete(ui);coordinator.stage='executing'
                    target=coordinator.evidence.partial_upload.location.path
                    result=DeleteResult((target,),1) if outcome=='success' else DeleteResult((),1,'failure',target,
                        {'outcome':'unknown' if outcome=='uncertain' else 'rejected'},(target,))
                    if invalidation=='session':self.session=DeviceSession('fixture','new')
                    elif invalidation=='disconnect':self.session=DeviceSession('fixture','')
                    elif invalidation=='client':app.client=object()
                    elif invalidation=='owner':app.upload_cleanup=object()
                    elif invalidation=='closed':app.cleanup_closed=True
                    else:app.foreground.reserve();app.busy=True
                    coordinator.executed(SimpleNamespace(result=None if outcome=='no-result' else result,
                        error=SimpleNamespace(message='old error')))
                    done.assert_not_called();self.assertEqual('current status',app.status)
                    self.session=DeviceSession('fixture','fixture-session')

    def test_stale_submission_rejections_are_silent(self):
        for callback in ('preparation_rejected','execution_rejected'):
            self.session=DeviceSession('fixture','fixture-session')
            app,coordinator,job=self.complete();done=Mock()
            app.run_file_job=lambda *args,**kwargs:True
            coordinator.complete(done);self.session=DeviceSession('fixture','new')
            getattr(coordinator,callback)(BrowserError('old rejection'))
            done.assert_not_called()

    def test_current_acknowledged_removal_with_teardown_failure_reports_both(self):
        app,coordinator,job=self.complete();done=Mock()
        original=self.peer.lease
        @contextmanager
        def broken(*args,**kwargs):
            with original(*args,**kwargs) as resource:yield resource
            if any(call[0]=='delete' for call in self.peer.calls):raise OSError('teardown failed')
        with patch.object(self.peer,'lease',broken):coordinator.complete(done)
        done.assert_called_once()
        self.assertTrue(done.call_args.args[2])
        self.assertIn('Deleted 1 of 1',done.call_args.args[1])
        self.assertIn('teardown failed',done.call_args.args[1])
