"""Offline GTK launch workflow through real Browser foreground admission."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from gi.repository import Gtk
import managed_library_gtk_check as fixtures
from c64u_browser.managed_library import LibraryState,parse_manifest
from c64u_browser.managed_d64_preflight import ManagedD64Selection,ManagedD64Plan
from c64u_browser.managed_d64_execution import ManagedD64Outcome,ManagedD64ExecutionError
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import DeviceSession
from tests.test_managed_library import manifest,game,PATH,GAME


class LaunchGtkTests(unittest.TestCase):
    configured=fixtures.ManagedViewGtk.configured
    restoration_browser=fixtures.ManagedViewGtk.restoration_browser
    drain_restoration_callbacks=fixtures.ManagedViewGtk.drain_restoration_callbacks

    def setUp(self):
        fixtures.ManagedViewGtk.setUp(self)
        _,self.idles=self.restoration_browser()
        self.library=parse_manifest(manifest(games=[game(format='D64',path='games/a.d64',size=174848)]),'device',PATH)
        self.app.preferences.game_library_location=self.library.identity.preference()
        self.core.managed_d64_preflight=NS(selection=Mock(),prepare=Mock(),discard_plan=Mock(return_value=True))
        self.service=self.core.managed_d64_preflight
        self.review=self.view.launch_review
        self.view.render(LibraryState('valid','Loaded',(self.library,),self.session.session_id))
        self.view.rows.select_row(self.view.rows.get_first_child())
        selected=ManagedD64Selection(self.session,self.library.identity,self.library.revision,
            self.library.manifest_sha256,self.library.games[0],0)
        self.plan=ManagedD64Plan('plan',selected,100,400)
        self.prepare_job=CoreJob('preflight',lambda _:self.plan)
        self.service.prepare.return_value=self.prepare_job
        self.execution_job=CoreJob('execute',lambda _:ManagedD64Outcome('accepted','dma-response','Accepted','plan'))
        self.core.execute_managed_d64=Mock(return_value=self.execution_job)
        self.app.preferences.save=Mock(side_effect=AssertionError('No preference writes'))

    def tearDown(self):
        self.core.configure_game_library.assert_not_called()
        self.app.preferences.save.assert_not_called()
        fixtures.ManagedViewGtk.tearDown(self)

    def drain(self):self.drain_restoration_callbacks(self.idles)

    def ready(self):
        self.review.prepare()
        self.assertTrue(self.app.busy)
        self.prepare_job.run();self.drain()
        self.assertIsNotNone(self.review.dialog)
        self.assertFalse(self.app.busy)

    def confirm(self):
        self.ready();self.review.dialog.response(Gtk.ResponseType.OK)

    def test_d64_selection_bound_to_snapshot_and_uuid(self):
        self.assertTrue(self.review.button.get_sensitive())
        self.review.prepare()
        self.service.selection.assert_called_once_with(self.library,GAME,self.session)
        self.core.execute_managed_d64.assert_not_called()
        self.assertIs(self.app.transfer_job,self.prepare_job)
        self.prepare_job.run();self.drain()

    def test_unsupported_format_visible_but_cannot_prepare(self):
        library=parse_manifest(manifest(games=[game()]),'device',PATH)
        self.view.render(LibraryState('valid','Loaded',(library,),self.session.session_id))
        self.view.rows.select_row(self.view.rows.get_first_child())
        self.assertFalse(self.review.button.get_sensitive())
        self.review.prepare();self.service.prepare.assert_not_called()

    def test_preview_and_no_automatic_execution(self):
        self.ready()
        text=self.review.dialog.get_content_area().get_first_child().get_text()
        for value in ('A game','device',PATH,PATH+'/games/a.d64','D64','174,848','a'*64,'DMA RUN_IMG','interrupt or reset'):
            self.assertIn(value,text)
        self.core.execute_managed_d64.assert_not_called()

    def test_explicit_confirmation_uses_foreground_and_plan_id(self):
        self.confirm()
        self.core.execute_managed_d64.assert_called_once_with('plan')
        self.assertIs(self.app.transfer_job,self.execution_job)
        self.assertFalse(self.review.button.get_sensitive())
        self.execution_job.run();self.drain()
        self.assertIn('Launch Accepted',self.review.status.get_text())
        self.assertIn('not been verified',self.review.status.get_text())

    def test_dialog_cancel_discards_without_execution(self):
        self.ready();self.review.dialog.response(Gtk.ResponseType.CANCEL)
        self.service.discard_plan.assert_called_once_with('plan')
        self.core.execute_managed_d64.assert_not_called()
        self.assertIsNone(self.review.dialog)

    def test_window_close_discards_without_execution(self):
        self.ready();self.review.dialog.emit('close-request')
        self.service.discard_plan.assert_called_once_with('plan')
        self.core.execute_managed_d64.assert_not_called()

    def test_duplicate_activation_and_response_do_not_execute_twice(self):
        self.review.prepare();self.review.prepare()
        self.service.prepare.assert_called_once()
        self.prepare_job.run();self.drain()
        dialog=self.review.dialog
        dialog.response(Gtk.ResponseType.OK);dialog.response(Gtk.ResponseType.OK)
        self.review.prepare()
        self.core.execute_managed_d64.assert_called_once()
        self.execution_job.run();self.drain()

    def test_preparation_failure_never_opens_review(self):
        self.prepare_job=CoreJob('preflight',lambda _:(_ for _ in ()).throw(ValueError('bad D64')))
        self.service.prepare.return_value=self.prepare_job
        self.review.prepare();self.prepare_job.run();self.drain()
        self.assertIsNone(self.review.dialog)
        self.assertIn('preparation failed',self.review.status.get_text())
        self.core.execute_managed_d64.assert_not_called()

    def test_cancel_preparation(self):
        self.review.prepare();self.prepare_job.request_cancel();self.prepare_job.run();self.drain()
        self.assertIn('Cancelled',self.review.status.get_text())
        self.assertIsNone(self.review.dialog)
        self.core.execute_managed_d64.assert_not_called()

    def test_disconnect_during_preparation_cancels_and_invalidates(self):
        self.review.prepare()
        self.session=DeviceSession('','');self.view.event(NS(kind='disconnected'))
        self.prepare_job.run();self.drain()
        self.assertEqual('cancelled',self.prepare_job.snapshot().state)
        self.assertIsNone(self.review.dialog)
        self.assertIsNone(self.view.rows.get_selected_row())
        self.core.execute_managed_d64.assert_not_called()

    def test_completed_preparation_callback_after_reconnect_discards_plan(self):
        self.review.prepare();self.prepare_job.run()
        self.session=DeviceSession('device','two');self.view.event(NS(kind='reconnected'))
        self.drain()
        self.service.discard_plan.assert_called_with('plan')
        self.assertIsNone(self.review.dialog)
        self.core.execute_managed_d64.assert_not_called()

    def test_preference_change_closes_review(self):
        self.ready();self.app.preferences.game_library_location=None
        self.view.event(NS(kind='library-location-changed'))
        self.assertIsNone(self.review.dialog);self.assertIsNone(self.review.current())
        self.service.discard_plan.assert_called_with('plan')

    def test_library_render_invalidates_selection_and_review(self):
        self.ready();self.view.render(self.view.state)
        self.assertIsNone(self.review.dialog)
        self.assertIsNone(self.view.rows.get_selected_row())
        self.service.discard_plan.assert_called_with('plan')

    def test_view_close_discards_review(self):
        self.ready();self.view.close()
        self.assertIsNone(self.review.dialog)
        self.service.discard_plan.assert_called_with('plan')

    def test_expired_plan_synchronous_rejection(self):
        outcome=ManagedD64Outcome('rejected','admission','Plan expired.','plan')
        self.core.execute_managed_d64.side_effect=ManagedD64ExecutionError(outcome)
        self.confirm();self.drain()
        self.assertIn('Launch Rejected',self.review.status.get_text())
        self.assertIn('expired',self.review.status.get_text())
        self.core.execute_managed_d64.assert_called_once()

    def test_consumed_plan_synchronous_rejection(self):
        outcome=ManagedD64Outcome('rejected','admission','Plan already used.','plan')
        self.core.execute_managed_d64.side_effect=ManagedD64ExecutionError(outcome)
        self.confirm();self.drain()
        self.assertIn('already used',self.review.status.get_text())
        self.core.execute_managed_d64.assert_called_once()

    def test_failed_job_structured_uncertain_not_rejected(self):
        outcome=ManagedD64Outcome('uncertain','dma-submit','Response lost.','plan')
        self.execution_job=CoreJob('execute',lambda _:(_ for _ in ()).throw(ManagedD64ExecutionError(outcome)))
        self.core.execute_managed_d64.return_value=self.execution_job
        self.confirm();self.execution_job.run();self.drain()
        self.assertIn('Launch Uncertain',self.review.status.get_text())
        self.assertIn('Inspect the C64',self.review.status.get_text())
        self.core.execute_managed_d64.assert_called_once()

    def test_synchronous_uncertain_not_overwritten_by_admission_failure(self):
        self.core.execute_managed_d64.side_effect=ManagedD64ExecutionError(
            ManagedD64Outcome('uncertain','dma-submit','Lost response.','plan'))
        self.confirm();self.drain()
        self.assertIn('Launch Uncertain',self.review.status.get_text())
        self.core.execute_managed_d64.assert_called_once()

    def test_generic_failed_job_never_claims_safe_rejection(self):
        self.execution_job=CoreJob('execute',lambda _:(_ for _ in ()).throw(ValueError('unknown')))
        self.core.execute_managed_d64.return_value=self.execution_job
        self.confirm();self.execution_job.run();self.drain()
        self.assertIn('outcome unavailable',self.review.status.get_text())
        self.assertNotIn('Launch Rejected',self.review.status.get_text())

    def test_rejected_job_reports_no_submission(self):
        outcome=ManagedD64Outcome('rejected','validation','Changed D64.','plan')
        self.execution_job=CoreJob('execute',lambda _:(_ for _ in ()).throw(ManagedD64ExecutionError(outcome)))
        self.core.execute_managed_d64.return_value=self.execution_job
        self.confirm();self.execution_job.run();self.drain()
        self.assertIn('command was not submitted',self.review.status.get_text())

    def test_stale_execution_completion_reports_history_without_restoring_rows(self):
        self.confirm()
        self.session=DeviceSession('','');self.view.event(NS(kind='disconnected'))
        self.execution_job.run();self.drain()
        self.assertIsNone(self.view.rows.get_first_child())
        self.assertIsNone(self.review.dialog)
        self.assertIn('Previous launch on device',self.app.status.set_text.call_args.args[0])
        self.assertIn('Launch Accepted',self.app.status.set_text.call_args.args[0])

    def test_busy_review_confirmation_discards_without_execution(self):
        self.ready();self.app.busy=True
        self.review.dialog.response(Gtk.ResponseType.OK)
        self.core.execute_managed_d64.assert_not_called()
        self.service.discard_plan.assert_called_with('plan')
        self.assertIn('Launch Rejected',self.review.status.get_text())
        self.app.busy=False

    def test_wrong_session_or_device_disables_preparation(self):
        for session in (DeviceSession('other','one'),DeviceSession('device','two'),DeviceSession('','')):
            self.session=session;self.review.update();self.review.prepare()
            self.assertFalse(self.review.button.get_sensitive())
        self.service.prepare.assert_not_called()

    def test_display_label_cannot_change_launch_authority(self):
        self.view.rows.get_first_child().get_child().set_text('Different game /USB9/other.d64')
        self.review.prepare()
        self.service.selection.assert_called_once_with(self.library,GAME,self.session)
        self.prepare_job.run();self.drain()
        self.assertIn(PATH+'/games/a.d64',self.review.dialog.get_content_area().get_first_child().get_text())

    def test_selection_change_discards_review(self):
        self.ready();self.view.rows.unselect_all()
        self.assertIsNone(self.review.dialog)
        self.service.discard_plan.assert_called_with('plan')
        self.assertFalse(self.review.button.get_sensitive())

    def test_preparation_synchronous_failure_releases_foreground(self):
        self.service.selection.side_effect=ValueError('Stale selection')
        self.review.prepare()
        self.assertFalse(self.app.busy)
        self.assertIsNone(self.app.foreground.token)
        self.assertIn('Stale selection',self.review.status.get_text())
        self.service.prepare.assert_not_called()
        self.core.execute_managed_d64.assert_not_called()

    def test_foreground_reservation_blocks_confirmation_without_losing_plan(self):
        self.ready();token=self.app.foreground.reserve()
        try:self.review.dialog.response(Gtk.ResponseType.OK)
        finally:self.app.foreground.release(token)
        self.service.discard_plan.assert_called_with('plan')
        self.core.execute_managed_d64.assert_not_called()
        self.assertIn('Launch Rejected',self.review.status.get_text())

    def test_view_close_before_preparation_delivery_discards_plan(self):
        self.review.prepare();self.prepare_job.run();self.view.close();self.drain()
        self.service.discard_plan.assert_called_with('plan')
        self.assertIsNone(self.review.dialog)
        self.core.execute_managed_d64.assert_not_called()

    def test_offline_event_discards_review(self):
        self.ready();self.session=DeviceSession('device','')
        self.view.event(NS(kind='offline'))
        self.service.discard_plan.assert_called_with('plan')
        self.assertIsNone(self.review.dialog)
        self.assertIsNone(self.view.rows.get_selected_row())
