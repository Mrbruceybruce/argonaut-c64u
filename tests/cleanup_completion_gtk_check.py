"""Exercise real Browser completion/admission and B5, never an extracted callback."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.jobs import CoreJob
from c64u_browser.file_service import DeleteResult, FileJobFailure
from c64u_browser.scheduler import DeviceSession
from c64u_browser.upload_cleanup import UploadCleanup
import test_preferences_ui


class CleanupCompletionGtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check())
        trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f=test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app=self.f.app;self.jobs=[];self.timers=[]
        self.addCleanup(self.finish_jobs)
        self.session=DeviceSession('fixture','old')
        provider=patch.object(self.app.core,'device_session',side_effect=lambda:self.session)
        provider.start();self.addCleanup(provider.stop)
        self.done=Mock();self.abandoned=Mock();self.subscribers=Mock()

    def finish_jobs(self):
        for job in self.jobs:job.run()
        self.f.drain_events()
        self.app.cleanup_closed=False

    def start(self,outcome='success',guarded=True):
        origin=CoreJob('file.copy.execute',lambda _:None)
        token=self.app.foreground.reserve();self.app.foreground.bind(token,origin)
        coordinator=UploadCleanup(self.app,origin,token)
        self.app.foreground.release(token,origin)
        def work(job):
            if outcome=='success':return DeleteResult(('/USB2/staging',),1)
            if outcome=='no-result':raise RuntimeError('old failure without result')
            result=DeleteResult((),1,'old failure','/USB2/staging',
                {'outcome':'unknown' if outcome=='uncertain' else 'rejected'},())
            raise FileJobFailure('delete','old failure',result)
        job=CoreJob('file.delete.execute',work);self.jobs.append(job)
        def abandon():self.abandoned();coordinator.close()
        kwargs=dict(presentation_guard=coordinator.current,presentation_abandoned=abandon) if guarded else {}
        with patch('c64u_browser.gui.GLib.timeout_add',side_effect=lambda interval,fn:self.timers.append(fn) or 1):
            self.assertTrue(self.app.run_file_job(lambda:job,self.done,**kwargs))
        self.app.operation.subscribe(job,self.subscribers);self.subscribers.reset_mock()
        return job,coordinator,self.app.foreground.token

    def current_status(self):
        # Controlled replacement-session presentation while the old worker still
        # owns its release token. Both model and rendered text must survive.
        message='Connected to current session · 7 files verified · do not replace'
        self.app.operation.message=message
        self.app.status_label.set_text(message)
        return message

    def test_stale_terminal_variants_preserve_complete_current_status(self):
        for outcome in ('success','failed','uncertain','no-result'):
            with self.subTest(outcome=outcome):
                self.session=DeviceSession('fixture','old')
                job,coordinator,token=self.start(outcome)
                self.session=DeviceSession('fixture','new')
                expected=self.current_status()
                self.app.cancel_button.grab_focus()
                with patch.object(self.app,'end_file_job',wraps=self.app.end_file_job) as release:
                    result=job.run();self.f.drain_events()
                    job._emit('finished');self.f.drain_events()
                    self.assertFalse(self.timers[-1]())
                    release.assert_called_once_with(job,token)
                self.assertEqual(expected,self.app.status_label.get_text())
                self.assertEqual(expected,self.app.operation.get_text())
                self.assertIsNone(self.app.foreground.token);self.assertFalse(self.app.busy)
                self.assertIs(job.snapshot().result,result.result)
                self.done.assert_not_called();self.subscribers.assert_not_called()
                self.assertTrue(coordinator.finished)
                self.assertFalse(self.app.cancel_button.get_visible())
                focus=self.app.window.get_focus();self.assertIsNotNone(focus);self.assertTrue(focus.is_sensitive())
        self.assertEqual(4,self.abandoned.call_count)

    def test_disconnect_close_and_replaced_coordinator_suppress_output(self):
        for reason in ('disconnect','close','coordinator','client'):
            with self.subTest(reason=reason):
                self.session=DeviceSession('fixture','old');self.app.cleanup_closed=False
                job,coordinator,token=self.start()
                if reason=='disconnect':self.session=DeviceSession('fixture','')
                elif reason=='close':self.app.cleanup_closed=True
                elif reason=='coordinator':self.app.upload_cleanup=object()
                else:self.app.client=object()
                expected=self.current_status();job.run();self.f.drain_events()
                self.assertEqual(expected,self.app.status_label.get_text())
                self.assertEqual(expected,self.app.operation.get_text())
                self.assertIsNone(self.app.foreground.token)
                self.done.assert_not_called()
                self.app.client=None;self.app.upload_cleanup=None

    def test_current_completion_keeps_normal_terminal_and_exactly_once_callback(self):
        for outcome in ('success','failed','uncertain','no-result'):
            with self.subTest(outcome=outcome):
                self.done.reset_mock();job,_,_=self.start(outcome)
                job.run();self.f.drain_events();job._emit('finished');self.f.drain_events()
                self.done.assert_called_once_with(job.snapshot())
                self.abandoned.assert_not_called()
                self.assertEqual('TERMINAL',self.app.operation.state)
                self.assertIsNone(self.app.foreground.token)
                self.assertEqual(self.app.status_label.get_text(),self.app.operation.get_text())
                self.assertIn('Deleted 1 of 1' if outcome=='success' else ('could not' if outcome=='no-result' else 'old failure'),self.app.status_label.get_text())

    def test_newer_active_b5_owner_and_text_are_untouched(self):
        old,_,token=self.start()
        # Simulate ownership moving before the obsolete worker delivers.
        self.app.foreground.release(token,old);self.app.transfer_job=None;self.app.busy=False
        new=CoreJob('file.synthetic',lambda _:None);self.jobs.append(new)
        self.app.run_file_job(lambda:new,Mock())
        newtoken=self.app.foreground.token;expected=self.app.status_label.get_text()
        old.run();self.f.drain_events()
        self.assertTrue(self.app.foreground.owns(newtoken,new))
        self.assertEqual('RUNNING',self.app.operation.state)
        self.assertEqual(expected,self.app.status_label.get_text())
        self.assertTrue(self.app.cancel_button.get_visible());self.done.assert_not_called()
        new.run();self.f.drain_events()

    def test_existing_snapshot_fallback_uses_same_guard(self):
        job,_,_=self.start('uncertain');self.session=DeviceSession('fixture','replacement')
        expected=self.current_status()
        with patch.object(job,'_emit'):job.run()
        self.assertFalse(self.timers[-1]());self.f.drain_events()
        self.assertEqual(expected,self.app.status_label.get_text())
        self.assertIsNone(self.app.foreground.token);self.done.assert_not_called()

    def test_unguarded_noncleanup_behavior_is_unchanged(self):
        job,_,_=self.start(guarded=False)
        self.session=DeviceSession('fixture','new');self.current_status()
        job.run();self.f.drain_events()
        self.done.assert_called_once();self.abandoned.assert_not_called()
        self.assertEqual('Deleted 1 of 1 item(s).',self.app.status_label.get_text())


    def test_callback_error_after_session_change_cannot_replace_status(self):
        job,_,_=self.start()
        expected='New session status after feature callback'
        def callback(snapshot):
            self.session=DeviceSession('fixture','new')
            self.app.status.set_text(expected)
            raise RuntimeError('obsolete callback error')
        self.done.side_effect=callback
        job.run();self.f.drain_events()
        self.assertEqual(expected,self.app.status_label.get_text())
        self.assertEqual(expected,self.app.operation.get_text())
        self.assertIsNone(self.app.foreground.token)
