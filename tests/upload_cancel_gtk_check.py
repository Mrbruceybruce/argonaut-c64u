"""Offline GTK cancellation decisions with controlled, registered Core jobs."""
import unittest
from threading import Barrier, Thread
from unittest.mock import patch, Mock
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gdk
from c64u_browser.jobs import CoreJob, JobProgress
from c64u_browser.scheduler import DeviceSession
from c64u_browser.upload_cancel_dialog import UploadCancelDialog
import test_preferences_ui


class UploadCancelGtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check())
        self.trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        self.trap.start();self.addCleanup(self.trap.stop)
        self.f=test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app=self.f.app;self.service=self.app.core.files
        self.session=DeviceSession('fixture','upload-session')
        provider=patch.object(self.service,'_session_provider',side_effect=lambda:self.session)
        provider.start();self.addCleanup(provider.stop)
        self.jobs=[]
        self.addCleanup(self.finish_all)
        self.forbidden=[]
        for name in ('prepare_partial_delete','execute_delete','_take_cleanup_eligibility'):
            mock=patch.object(self.service,name,side_effect=AssertionError('Cleanup boundary crossed'))
            self.forbidden.append(mock.start());self.addCleanup(mock.stop)
        submit=patch.object(self.app.core.scheduler,'submit',side_effect=AssertionError('Unexpected job submission'))
        self.forbidden.append(submit.start());self.addCleanup(submit.stop)

    def drain(self):self.f.drain_events()

    def start(self, *, eligible=True, registered=True, operation='file.copy.execute'):
        job=CoreJob(operation,lambda _:None)
        if registered:self.service._register_upload_job(job,self.session,eligible)
        job._queue('c64u:fixture',self.session.device_id,self.session.session_id)
        self.jobs.append(job)
        self.assertTrue(self.app.run_file_job(lambda:job,lambda _:None))
        self.drain()
        return job

    def finish_all(self):
        if self.app.upload_cancel_dialog:self.app.upload_cancel_dialog.dismiss()
        for job in self.jobs:job.run(_scheduled=True)
        self.drain()
        for mock in self.forbidden:mock.assert_not_called()

    def open(self):
        self.app.cancel_button.emit('clicked');self.drain()
        dialog=self.app.upload_cancel_dialog
        self.assertIsNotNone(dialog)
        return dialog

    def test_continue_preserves_upload_and_focus(self):
        job=self.start();dialog=self.open()
        dialog.continue_button.emit('clicked');self.drain()
        self.assertIsNone(self.app.upload_cancel_dialog)
        self.assertFalse(job._cancel.is_set())
        self.assertIsNone(self.service._upload_origins[job].decision)
        self.assertTrue(self.app.operation.view.cancel_available)
        focus=self.app.window.get_focus()
        self.assertIsNotNone(focus);self.assertTrue(focus.is_sensitive())

    def test_keep_one_shot_and_sticky_cancelling(self):
        job=self.start();dialog=self.open();events=[]
        job.add_listener(lambda event:events.append(event.kind))
        with patch.object(self.service,'cancel',side_effect=AssertionError('Independent cancellation')):
            dialog.keep_button.emit('clicked')
            dialog.response(dialog.dialog,dialog.DELETE)
            self.app.cancel_button.emit('clicked')
            self.drain()
        self.assertEqual('keep',self.service._upload_origins[job].decision)
        self.assertEqual(1,events.count('cancel-requested'))
        self.assertEqual('CANCELLATION_REQUESTED',self.app.operation.state)
        job.report_committed(JobProgress('late',1,2,'files','Late progress'));self.drain()
        self.assertIn('Cancelling',self.app.status.get_text())
        self.assertFalse(self.app.cancel_button.get_visible())
        focus=self.app.window.get_focus()
        self.assertIsNotNone(focus);self.assertTrue(focus.is_sensitive())

    def test_delete_records_only_intent(self):
        job=self.start();dialog=self.open()
        dialog.delete_button.emit('clicked');self.drain()
        self.assertEqual('delete',self.service._upload_origins[job].decision)
        self.assertTrue(job._cancel.is_set())
        self.assertIsNone(self.app.upload_cancel_dialog)
        self.assertFalse(any(w.get_modal() for w in self.f.owned_windows()))

    def test_layout_default_accessibility_and_escape(self):
        job=self.start();dialog=self.open()
        self.assertIs(dialog.keep_button,dialog.dialog.get_default_widget())
        self.assertIs(dialog.keep_button,dialog.dialog.get_focus())
        self.assertEqual(['Continue Upload','Cancel & Keep','Cancel & Clean Up'],
            [b.get_label() for b in (dialog.continue_button,dialog.keep_button,dialog.delete_button)])
        self.assertTrue(dialog.dialog.get_modal())
        self.assertIs(self.app.window,dialog.dialog.get_transient_for())
        self.assertEqual(12,dialog.content.get_spacing())
        self.assertEqual(16,dialog.content.get_margin_bottom())
        for side in ('top','start','end'):
            self.assertEqual(20,getattr(dialog.content,'get_margin_'+side)())
        self.assertEqual(8,dialog.footer.get_spacing())
        self.assertEqual(Gtk.Align.END,dialog.footer.get_halign())
        child=dialog.content.get_first_child(); explanations=[]
        while child:
            explanations.append(child.get_text())
            self.assertTrue(child.get_wrap());child=child.get_next_sibling()
        explanation=' '.join(explanations)
        for phrase in ('continues while this dialog is open', 'Cancellation is cooperative',
                       'attempts cleanup once', 'verified incomplete staging file',
                       'C64U has not finished updating', 'Completed files are kept'):
            self.assertIn(phrase,explanation)
        self.assertTrue(dialog.keys.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0)))
        self.drain();self.assertFalse(job._cancel.is_set())

    def test_window_close_is_continue(self):
        job=self.start();dialog=self.open();dialog.dialog.close();self.drain()
        self.assertFalse(job._cancel.is_set())
        self.assertIsNone(self.app.upload_cancel_dialog)

    def test_parent_close_dismisses_without_cancelling_or_releasing_job(self):
        job=self.start();self.open();token=self.app.foreground.token
        self.assertTrue(self.app.close())
        self.assertFalse(job._cancel.is_set())
        self.assertIsNone(self.app.upload_cancel_dialog)
        self.assertTrue(self.app.foreground.owns(token,job))

    def test_repeated_open_reuses_single_dialog(self):
        self.start();first=self.open();second=self.open()
        self.assertIs(first,second)
        self.assertEqual(1,sum(w.get_modal() for w in self.f.owned_windows()))

    def test_finished_job_closes_dialog_and_late_response_is_harmless(self):
        job=self.start();dialog=self.open()
        job.run(_scheduled=True);self.drain()
        self.assertIsNone(self.app.upload_cancel_dialog)
        newer=self.start();dialog.response(dialog.dialog,dialog.DELETE)
        self.assertFalse(newer._cancel.is_set());self.assertFalse(job._cancel.is_set())

    def test_completion_before_gtk_notification_rejects_confirmation(self):
        job=self.start();dialog=self.open();job.run(_scheduled=True)
        dialog.response(dialog.dialog,dialog.DELETE)
        self.assertFalse(job._cancel.is_set());self.drain()

    def test_replaced_session_rejects_before_notification(self):
        job=self.start();dialog=self.open()
        self.session=DeviceSession('fixture','replacement')
        dialog.response(dialog.dialog,dialog.DELETE)
        self.assertFalse(job._cancel.is_set())

    def test_disconnect_event_closes_dialog(self):
        job=self.start();dialog=self.open()
        self.service.invalidate_recovery()
        self.app.core._emit('disconnected');self.drain()
        self.assertTrue(dialog.responded);self.assertIsNone(self.app.upload_cancel_dialog)
        dialog.response(dialog.dialog,dialog.KEEP);self.assertFalse(job._cancel.is_set())

    def test_external_cancellation_closes_dialog(self):
        job=self.start();dialog=self.open();job.request_cancel();self.drain()
        self.assertTrue(dialog.responded)
        self.assertIsNone(self.service._upload_origins[job].decision)
        self.assertIn('Cancelling',self.app.status.get_text())

    def test_download_and_unregistered_and_nonupload_immediate_cancel(self):
        for operation,registered,eligible in (
            ('file.copy.execute',True,False), # Download: same operation, ineligible plan.
            ('file.copy.execute',False,True),
            ('file.folder.create',True,True),
        ):
            with self.subTest(operation=operation,registered=registered,eligible=eligible):
                job=self.start(operation=operation,registered=registered,eligible=eligible)
                with patch.object(self.service,'cancel',side_effect=lambda _:job.request_cancel()) as cancel:
                    self.app.cancel_button.emit('clicked');self.drain()
                    cancel.assert_called_once_with(job.id)
                self.assertIsNone(self.app.upload_cancel_dialog)
                job.run(_scheduled=True);self.drain()

    def test_stale_foreground_token_cannot_cancel(self):
        job=self.start();dialog=self.open()
        token=self.app.foreground.token
        # Controlled ownership fault: job has not finished but the token changed.
        self.app.foreground.token=object()
        try:
            dialog.response(dialog.dialog,dialog.DELETE)
            self.assertFalse(job._cancel.is_set())
        finally:self.app.foreground.token=token

    def test_competing_keep_delete_one_winner(self):
        job=self.start();dialog=self.open();barrier=Barrier(3);accepted=[]
        def choose(choice):
            barrier.wait();accepted.append((choice,self.service._request_upload_cancel(job,choice)))
        threads=[Thread(target=choose,args=(choice,)) for choice in ('keep','delete')]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(5);self.assertFalse(thread.is_alive())
        self.drain()
        self.assertEqual(1,sum(ok for _,ok in accepted))
        self.assertEqual(next(choice for choice,ok in accepted if ok),self.service._upload_origins[job].decision)
        self.assertTrue(dialog.responded)

    def test_native_dark_light_setting_does_not_change_decision(self):
        self.start();dialog=self.open();settings=Gtk.Settings.get_default()
        before=settings.get_property('gtk-application-prefer-dark-theme')
        try:
            for dark in (True,False):
                settings.set_property('gtk-application-prefer-dark-theme',dark);self.drain()
                self.assertTrue(dialog.keep_button.is_sensitive())
                self.assertIs(dialog.keep_button,dialog.dialog.get_default_widget())
        finally:settings.set_property('gtk-application-prefer-dark-theme',before)
