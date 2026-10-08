"""Deterministic B5 presentation and Browser lifecycle checks; no device IO."""
from types import SimpleNamespace as NS
from unittest.mock import Mock
import unittest
from c64u_browser.operation_status import OperationPresentation
from c64u_browser.jobs import JobProgress
import test_foreground_admission

class Presentation(unittest.TestCase):
    def setUp(self):
        self.render=Mock();self.diag=Mock()
        self.p=OperationPresentation(self.render,self.diag)
        self.job=NS(operation='file.copy.execute');self.token=object()
    def begin(self, cancellable=True):self.p.begin(self.job,self.token,cancellable)
    def progress(self, count=12,total=None,message='Downloading…',phase='read',unit='bytes'):
        self.p.progress(self.job,self.token,JobProgress(phase,count,total,unit,message),lambda _,p:p.message)
    def finish(self,state='succeeded',message=None):
        self.p.finish(self.job,self.token,NS(state=state,result=NS(message=message),error=None))
    def test_idle_ordinary_and_noncancellable(self):
        self.p.set_text('Ready');self.assertEqual('Ready',self.p.message)
        self.assertFalse(self.p.view.cancel_available)
        self.begin(False);self.progress();self.assertIn('12 bytes',self.p.message)
        send=Mock();self.assertFalse(self.p.request_cancel(self.job,self.token,send));send.assert_not_called()
    def test_counts_unknown_known_phase_and_zero(self):
        self.begin();self.progress();self.assertEqual('Downloading… · 12 bytes',self.p.message)
        self.progress(total=20);self.assertEqual('Downloading… · 12 / 20 bytes',self.p.message)
        self.progress(3,5,'Verifying…','verify','files');self.assertIn('Verifying… · 3 / 5 files',self.p.message)
        self.progress(0,0,'Publishing…');self.assertEqual('Publishing…',self.p.message)
        self.assertNotIn('%',self.p.message)
        self.progress(12,None,'Transferred 12 bytes','transfer');self.assertEqual('Transferred 12 bytes',self.p.message)
    def test_sticky_one_shot_shared_view_and_transient_precedence(self):
        self.begin();modal=Mock();self.p.subscribe(self.job,modal);send=Mock(return_value=True)
        self.assertTrue(self.p.request_cancel(self.job,self.token,send));sticky=self.p.message
        self.progress();self.p.set_text('Unrelated');self.p.request_cancel(self.job,self.token,send)
        send.assert_called_once();self.assertEqual(sticky,self.p.message)
        self.assertEqual('CANCELLATION_REQUESTED',self.p.state)
        self.assertFalse(self.p.view.cancel_available);self.assertEqual(modal.call_args.args[0],self.p.view)
    def test_refusal_error_and_reentrant_request_do_not_retry(self):
        for send in (Mock(return_value=False),Mock(side_effect=RuntimeError('secret sentinel'))):
            self.begin();self.assertFalse(self.p.request_cancel(self.job,self.token,send))
            self.assertNotIn('Cancelling',self.p.message);self.assertNotIn('secret sentinel',self.p.message)
            self.progress();self.p.request_cancel(self.job,self.token,send);send.assert_called_once()
            self.assertFalse(self.p.view.cancel_available)
        self.begin();nested=Mock()
        def reenter():self.p.request_cancel(self.job,self.token,nested);return True
        self.p.request_cancel(self.job,self.token,reenter);nested.assert_not_called()
    def test_late_progress_cancel_and_terminal_cannot_change_replacement(self):
        self.begin();self.finish();new=NS(operation='sid-jukebox.playback');token=object()
        self.p.begin(new,token);view=self.p.view
        self.progress();self.p.cancelling(self.job,self.token);self.finish()
        send=Mock();self.p.request_cancel(self.job,self.token,send);send.assert_not_called()
        self.assertEqual(view,self.p.view)
    def test_terminal_outcomes_override_requested_cancellation(self):
        for state,message in [('succeeded','Published; cleanup incomplete'),('succeeded','Completed before cancellation took effect'),('failed','Outcome uncertain; do not replay'),('cancelled','Cancelled before mutation')]:
            self.begin();self.p.cancelling(self.job,self.token);self.finish(state,message)
            self.assertEqual(message,self.p.message);self.assertEqual('TERMINAL',self.p.state)
            self.assertFalse(self.p.view.cancel_available)
            self.p.set_text('Next ordinary error');self.assertEqual('Next ordinary error',self.p.message)
    def test_malformed_progress_and_failed_render_are_contained(self):
        self.begin();self.progress(-1,20,'secret sentinel')
        self.assertIn('Progress unavailable',self.p.message);self.assertNotIn('secret sentinel',self.p.message)
        self.assertTrue(self.p.matches(self.job,self.token));self.diag.assert_called_once()
        self.render.side_effect=ValueError('secret');self.progress();self.assertTrue(self.p.view.cancel_available)
        self.assertEqual(2,self.diag.call_count)

class BrowserPresentation(unittest.TestCase):
    def setUp(self):
        self.f=test_foreground_admission.Admission();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.app=self.f.app
        # Use the actual ordinary-status facade, as in Browser.activate.
        self.app.operation.render=Mock();self.app.status=self.app.operation
    def test_cancel_retains_admission_and_fallback_converges(self):
        job=self.f.start();job.report(JobProgress('read',10,20,'bytes','Reading…'))
        self.app.job_cancel_callback(job)();self.f.pump();self.assertIn('Cancelling',self.app.status.get_text())
        submit=Mock();self.assertFalse(self.app.run_file_job(submit,Mock()));submit.assert_not_called()
        self.assertIn('Cancelling',self.app.status.get_text());job.run()
        self.f.idles.clear();self.f.timers[0]()
        self.assertEqual('Operation cancelled by request.',self.app.status.get_text())
        self.assertIsNone(self.app.foreground.token);self.assertFalse(self.app.operation.view.cancel_available)
    def test_completion_before_click_and_final_progress(self):
        done=Mock();job=self.f.start(done=done);cancel=self.app.job_cancel_callback(job)
        job.report(JobProgress('publish',1,1,'items','Publishing…'));job.run()
        self.assertFalse(cancel());self.f.pump();done.assert_called_once()
        self.assertEqual('Completed.',self.app.status.get_text())
    def test_external_cancel_event_and_noncancellable(self):
        job=self.f.start();job.request_cancel();self.f.pump()
        self.assertEqual('CANCELLATION_REQUESTED',self.app.operation.state)
        job.run();self.f.pump();other=self.f.job()
        self.app.run_file_job(lambda:other,Mock(),cancellable=False)
        self.assertFalse(self.app.operation.view.cancel_available)
        self.assertFalse(self.app.job_cancel_callback(other)())

    def test_late_sid_progress_and_malformed_queued_progress(self):
        job=self.f.job('sid-jukebox.play');self.f.start(job)
        job.report(JobProgress('hash',12,None,'bytes','Old SID validation…'))
        job.run();old=list(self.f.idles);self.f.idles.clear();self.f.timers[0]()
        other=self.f.start();view=self.app.operation.view
        for callback,args in old:callback(*args)
        self.assertEqual(view,self.app.operation.view)
        other.report(NS(completed='invalid'))
        self.f.pump();self.assertIn('Progress unavailable',self.app.status.get_text())
        self.assertIs(other,self.app.foreground.job)
