"""Ordinary worker status ownership; controlled futures, inert UI, no device IO."""
from concurrent.futures import Future
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import unittest

from c64u_browser.gui import Browser
from c64u_browser.drives_tab import DrivesTab
from c64u_browser.operation_status import OperationPresentation


class WorkerStatus(unittest.TestCase):
    def setUp(self):
        self.idles = []
        for target, kwargs in (
            ('c64u_browser.gui.GLib.idle_add', {'side_effect': self.idles.append}),
            ('c64u_browser.gui.refresh_header', {}),
        ):
            p = patch(target, **kwargs); p.start(); self.addCleanup(p.stop)
        self.status = OperationPresentation(Mock())
        self.app = NS(busy=False, foreground=NS(token=None), busy_controls=[],
                      status=self.status, pool=Mock(), recovery=None)
        self.app.run = lambda task, done: Browser.run(self.app, task, done)

    def start(self, done=None):
        future = Future(); self.app.pool.submit.return_value = future
        self.assertTrue(self.app.run(Mock(), done or Mock()))
        self.assertTrue(self.app.busy)
        self.assertEqual('Working…', self.status.get_text())
        return future

    def finish(self, future, error=None):
        if error is None: future.set_result('result')
        else: future.set_exception(error)
        self.idles.pop(0)()

    def test_success_clears_placeholder_and_releases_busy(self):
        done = Mock(); future = self.start(done); self.finish(future)
        done.assert_called_once_with('result')
        self.assertFalse(self.app.busy); self.assertEqual('', self.status.get_text())

    def test_drive_refresh_keeps_feature_success_and_clears_bottom(self):
        future = Future(); self.app.pool.submit.return_value = future
        tab = NS(client=NS(read_drives=Mock()), app=self.app, show=Mock(), message=Mock())
        DrivesTab.request(tab, tab.client.read_drives, 'Drive status refreshed from the active C64U.')
        self.finish(future)
        tab.show.assert_called_once_with('result')
        tab.message.set_text.assert_called_once_with('Drive status refreshed from the active C64U.')
        self.assertEqual('', self.status.get_text()); self.assertFalse(self.app.busy)
        tab.client.read_drives.assert_not_called()

    def test_completion_preserves_explicit_success_and_error(self):
        for message in ('Saved successfully.', 'Read failed; outcome uncertain.'):
            with self.subTest(message=message):
                future = self.start(lambda result: self.status.set_text(message))
                self.finish(future); self.assertEqual(message, self.status.get_text())

    def test_task_failure_reports_error(self):
        done = Mock(); future = self.start(done)
        self.finish(future, ValueError('Read failed'))
        done.assert_not_called(); self.assertFalse(self.app.busy)
        self.assertEqual('Read failed', self.status.get_text())

    def test_completion_failure_reports_error(self):
        future = self.start(Mock(side_effect=ValueError('Completion failed')))
        self.finish(future); self.assertFalse(self.app.busy)
        self.assertEqual('Completion failed', self.status.get_text())

    def test_submission_failure_reports_error_and_calls_done(self):
        self.app.pool.submit.side_effect = RuntimeError('Executor unavailable')
        done = Mock(); self.assertFalse(self.app.run(Mock(), done))
        done.assert_called_once(); self.assertFalse(self.app.busy)
        self.assertIn('Executor unavailable', self.status.get_text())
        self.assertEqual([], self.idles)

    def test_submission_failure_preserves_callback_message(self):
        self.app.pool.submit.side_effect = RuntimeError('Executor unavailable')
        self.assertFalse(self.app.run(Mock(), lambda error: self.status.set_text('Specific failure.')))
        self.assertEqual('Specific failure.', self.status.get_text())

    def test_subsequent_worker_from_completion_retains_its_placeholder(self):
        next_future = []
        first = self.start(lambda result: next_future.append(self.start()))
        self.finish(first)
        self.assertTrue(self.app.busy); self.assertEqual('Working…', self.status.get_text())
        self.finish(next_future[0]); self.assertEqual('', self.status.get_text())

    def test_old_callback_failure_does_not_overwrite_subsequent_worker(self):
        next_future = []
        def done(result):
            next_future.append(self.start())
            raise ValueError('Old completion failed')
        self.finish(self.start(done))
        self.assertEqual('Working…', self.status.get_text()); self.assertTrue(self.app.busy)
        self.finish(next_future[0], ValueError('New read failed'))
        self.assertEqual('New read failed', self.status.get_text())

    def test_submission_failure_callback_can_start_subsequent_worker(self):
        self.app.pool.submit.side_effect = RuntimeError('Executor unavailable')
        next_future = []
        def done(error):
            self.app.pool.submit.side_effect = None
            next_future.append(self.start())
        self.assertFalse(self.app.run(Mock(), done))
        self.assertEqual('Working…', self.status.get_text()); self.assertTrue(self.app.busy)
        self.finish(next_future[0]); self.assertEqual('', self.status.get_text())

    def test_rejected_overlap_does_not_replace_status(self):
        first = self.start(); owner = self.status._text_owner
        self.app.pool.submit.reset_mock(); done = Mock()
        self.assertFalse(self.app.run(Mock(), done))
        self.app.pool.submit.assert_not_called(); done.assert_not_called()
        self.assertIs(owner, self.status._text_owner)
        self.finish(first); self.assertEqual('', self.status.get_text())

    def test_later_identical_message_is_not_cleared(self):
        first = self.start(); self.status.set_text('Working…')
        self.finish(first); self.assertEqual('Working…', self.status.get_text())

    def test_foreground_replacement_survives_old_completion(self):
        for operation in ('file.synthetic', 'file.copy.execute'):
            with self.subTest(operation=operation):
                def done(result): self.status.begin(NS(operation=operation), object())
                self.finish(self.start(done)); view = self.status.view
                self.assertEqual('RUNNING', view.state); self.assertTrue(view.message)
                self.status.finish(self.status.job, self.status.token,
                                   NS(state='succeeded', result=None, error=None))

    def test_managed_terminal_message_revokes_old_ordinary_owner(self):
        owner = self.status.set_text('Working…')
        job = NS(operation='file.synthetic'); token = object()
        self.status.begin(job, token)
        self.status.finish(job, token, NS(state='succeeded', result=None, error=None))
        self.assertFalse(self.status.replace_text(owner, ''))
        self.assertEqual('Completed.', self.status.get_text())

    def test_reentrant_render_does_not_grant_ownership_of_new_message(self):
        def render(view):
            if view.message == 'Working…': self.status.set_text('New message')
        self.status.render = render
        owner = self.status.set_text('Working…')
        self.assertFalse(self.status.replace_text(owner, ''))
        self.assertEqual('New message', self.status.get_text())

    def test_stale_owner_and_ignored_write_cannot_clear_managed_status(self):
        owner = self.status.set_text('Working…')
        self.status.begin(NS(operation='file.synthetic'), object())
        ignored = self.status.set_text('Unrelated')
        self.assertIsNone(ignored)
        self.assertFalse(self.status.replace_text(owner, ''))
        self.assertFalse(self.status.replace_text(ignored, ''))
        self.assertEqual('Working…', self.status.get_text())
