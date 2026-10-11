"""Explicit offline GTK planning UI checks; no device transport."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.picker_model import PickerSelection, GAMES, PickerMode
from c64u_browser.scheduler import DeviceSession
from c64u_browser.jobs import JobProgress
from c64u_browser.import_plan import ImportPlan, ImportItem
from tests import managed_library_gtk_check as existing
from c0_gtk_input import pump


class ImportReviewGtk(TestCase):
    setUp=existing.ManagedViewGtk.setUp
    tearDown=existing.ManagedViewGtk.tearDown
    loaded=existing.ManagedViewGtk.loaded

    def selected(self):
        self.library=self.loaded(True)
        self.core.prepare_managed_import=Mock()
        self.source=PickerSelection('core-host','/tmp/a.crt','a.crt','','','','games','file')
        review=self.view.import_review
        with patch('c64u_browser.file_picker.FilePicker') as picker:
            review.choose()
            self.assertEqual(PickerMode.OPEN_FILES,picker.call_args.kwargs['mode'])
            self.assertEqual(GAMES,picker.call_args.kwargs['filter'])
            picker.call_args.args[1]((self.source,))
        return review

    def plan(self):
        return ImportPlan('plan',self.library.identity,'one',0,'a'*64,
            (ImportItem(self.source,'CRT','games/a.crt',80,'b'*64,(),'new','Source verified by reading.'),),
            (),(),160,80)

    def test_unconfigured_has_no_add_and_selected_library_offers_add(self):
        review=self.view.import_review
        self.assertFalse(review.add.get_visible())
        self.loaded(True);self.assertTrue(review.add.get_visible())
        self.assertFalse(review.execute.get_sensitive())

    def test_selection_never_submits_and_prepare_is_explicit(self):
        review=self.selected()
        self.app.run_file_job.assert_not_called()
        self.assertIn('several minutes',review.status.get_text())
        review.start()
        self.app.run_file_job.assert_called_once()
        factory=self.app.run_file_job.call_args.args[0];factory()
        self.core.prepare_managed_import.assert_called_once_with((self.source,),self.library,self.session,previous=None)
        self.assertFalse(review.execute.get_sensitive())

    def test_complete_review_shows_destination_results_and_no_execute(self):
        review=self.selected();review.start()
        self.app.run_file_job.call_args.args[1](NS(state='succeeded',result=self.plan()))
        self.assertIn(self.library.identity.path,review.status.get_text())
        self.assertIn('80 bytes would require transfer',review.status.get_text())
        self.assertIn('New game:',review.rows.get_first_child().get_text())
        self.assertTrue(review.recheck.get_visible())
        self.assertFalse(review.execute.get_sensitive())
        self.core.prepare_managed_import.reset_mock();review.execute.emit('clicked')
        self.core.prepare_managed_import.assert_not_called()

    def test_cancel_and_failure_never_present_complete_plan(self):
        review=self.selected()
        for state in ('cancelled','failed'):
            review.start();done=self.app.run_file_job.call_args.args[1]
            done(NS(state=state,error=NS(message='read failed')))
            self.assertIsNone(review.plan)
            self.assertIn('No complete plan',review.status.get_text())
            self.assertFalse(review.execute.get_sensitive())

    def test_budget_failure_removes_prior_review_and_disables_execution(self):
        review=self.selected();review.start()
        self.app.run_file_job.call_args.args[1](NS(state='succeeded',result=self.plan()))
        review.start(revalidate=True)
        self.app.run_file_job.call_args.args[1](NS(state='failed',error=NS(
            code='import-source-budget',message='Source read budget exceeded; choose a smaller batch.')))
        self.assertIsNone(review.plan)
        self.assertIn('budget exceeded',review.status.get_text())
        self.assertIn('No complete plan',review.status.get_text())
        self.assertIsNone(review.rows.get_first_child())
        self.assertFalse(review.execute.get_sensitive())
        self.assertFalse(review.recheck.get_visible())

    def test_busy_and_changed_selection_refuse_submission(self):
        review=self.selected();self.app.busy=True;review.start()
        self.app.run_file_job.assert_not_called()
        self.app.busy=False;self.app.preferences.game_library_location=None;review.start()
        self.app.run_file_job.assert_not_called();self.assertFalse(review.selections)

    def test_disconnect_discards_late_completion_and_review(self):
        review=self.selected();review.start();done=self.app.run_file_job.call_args.args[1]
        self.session=DeviceSession('device','two');self.view.event(NS(kind='reconnected'))
        done(NS(state='succeeded',result=self.plan()))
        self.assertIsNone(review.plan);self.assertFalse(review.selections)

    def test_close_review_has_no_host_association_or_storage_effect(self):
        review=self.selected();before=dict(self.app.preferences.game_library_location)
        review.dismiss.emit('clicked')
        self.assertEqual(before,self.app.preferences.game_library_location)
        self.core.configure_game_library.assert_not_called()
        self.app.run_file_job.assert_not_called()

    def test_progress_and_revalidation_use_existing_job_callback(self):
        review=self.selected();review.start();job=Mock()
        self.app.run_file_job.call_args.kwargs['started'](job)
        listener=job.add_listener.call_args.args[0]
        listener(NS(kind='progress',job=NS(progress=JobProgress('validating',0,1,'files','Reading a.crt',(('bytes_read',42),)))))
        pump();self.assertIn('42 bytes read',review.status.get_text())
        self.app.run_file_job.call_args.args[1](NS(state='succeeded',result=self.plan()))
        old=review.plan;review.start(revalidate=True)
        self.app.run_file_job.call_args.args[0]()
        self.assertEqual(old,self.core.prepare_managed_import.call_args.kwargs['previous'])

    def test_native_focus_and_resizing(self):
        review=self.selected();self.window.set_default_size(650,800);pump()
        self.assertTrue(review.prepare.grab_focus())
        self.assertGreater(review.box.get_width(),0)
        self.assertLessEqual(review.prepare.get_width(),review.box.get_width())


class ImportForegroundGtk(TestCase):
    def test_real_foreground_cancellation_owns_plan_until_terminal(self):
        import test_preferences_ui
        from c64u_browser.jobs import CoreJob
        from c64u_browser.managed_library import LibraryState,parse_manifest
        from tests.test_managed_library import manifest,PATH
        trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        fixture=test_preferences_ui.PreferencesUI();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.addCleanup(fixture.tearDown)
        app=fixture.app;session=DeviceSession('device','one')
        library=parse_manifest(manifest(),'device',PATH)
        app.core.device_session=Mock(return_value=session)
        app.preferences.game_library_location=library.identity.preference()
        app.managed_library_view.render(LibraryState('valid','Loaded',(library,),'one'))
        review=app.managed_library_view.import_review
        review.selections=(PickerSelection('core-host','/tmp/a.crt','a.crt','','','','games','file'),)
        review.context=(library,session)
        job=CoreJob('game-library.import-plan',lambda job:job.check_cancel())
        with patch.object(app.core,'prepare_managed_import',return_value=job), \
             patch.object(app.core.game_library,'cancel',side_effect=lambda _:job.request_cancel()) as cancel:
            review.start();fixture.pump()
            self.assertIs(job,app.transfer_job);self.assertTrue(app.busy)
            self.assertFalse(review.add.get_sensitive());self.assertTrue(app.cancel_button.get_visible())
            app.cancel_button.emit('clicked');cancel.assert_called_once_with(job.id)
            self.assertIs(job,app.transfer_job)
            job.run();fixture.pump()
            self.assertFalse(app.busy);self.assertIsNone(app.foreground.token)
            self.assertIsNone(review.plan);self.assertIn('canceled',review.status.get_text())
            self.assertFalse(review.execute.get_sensitive())
