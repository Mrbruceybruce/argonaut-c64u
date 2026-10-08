"""Explicit offline real GTK B5 checks, no skips or device access."""
import unittest
from unittest.mock import Mock,patch
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from c64u_browser.jobs import CoreJob,JobProgress
from c64u_browser.game_library_bulk_dialog import BulkImportDialog
import test_preferences_ui

class B5Gtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(),'GTK display required')
        trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f=test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown);self.app=self.f.app
    def labels(self,widget):
        found=[]
        if isinstance(widget,Gtk.Button):found.append(widget.get_label())
        child=widget.get_first_child()
        while child:found+=self.labels(child);child=child.get_next_sibling()
        return found
    def test_retirement_contextual_routes_and_keyboard_focus(self):
        self.assertNotIn('Cancel transfer',self.labels(self.app.window))
        self.assertNotIn('Cancel operation',self.labels(self.app.window))
        self.assertFalse(self.app.cancel_button.get_visible())
        self.assertEqual('Cancel',self.app.cancel_button.get_label())
        for tab,operation,service in [(None,'file.copy.execute',self.app.core.files),
                (self.app.sid_jukebox_tab,'sid-jukebox.play',self.app.core.sid_jukebox),
                (self.app.game_library_tab,'game-library.launch',self.app.core.game_launch)]:
            job=CoreJob(operation,lambda _:None)
            if tab:tab._run_job(lambda:job,Mock())
            else:self.app.run_file_job(lambda:job,Mock())
            self.f.pump();self.assertTrue(self.app.cancel_button.get_visible())
            self.assertTrue(self.app.cancel_button.grab_focus())
            with patch.object(service,'cancel',side_effect=lambda _:job.request_cancel()) as cancel:
                self.app.cancel_button.emit('clicked');self.app.cancel_button.emit('clicked')
                cancel.assert_called_once_with(job.id)
            self.assertFalse(self.app.cancel_button.get_visible())
            self.assertIsNot(self.app.window.get_focus(),self.app.cancel_button)
            job.run();self.f.pump();self.assertFalse(self.app.busy)
        self.assertIsNone(self.app.foreground.token)
    def test_terminal_focus_and_noncancellable(self):
        job=CoreJob('file.synthetic',lambda _:None);self.app.run_file_job(lambda:job,Mock())
        self.f.pump();self.app.cancel_button.grab_focus();job.run();self.f.pump()
        self.assertFalse(self.app.cancel_button.get_visible())
        self.assertIsNot(self.app.window.get_focus(),self.app.cancel_button)
        other=CoreJob('file.synthetic',lambda _:None)
        self.app.run_file_job(lambda:other,Mock(),cancellable=False)
        self.assertFalse(self.app.cancel_button.get_visible());other.run();self.f.pump()
    def test_bulk_modal_and_global_share_progress_and_single_cancellation(self):
        for modal_first in (True,False):
            tab=self.app.game_library_tab
            preview=Mock(plan_id='synthetic',default_selected_candidate_ids=('a',),
                eligible_candidate_ids=('a',),candidates=(),issues=(),
                classification_counts=(('new-valid',1),),entries_seen=1,
                supported_candidates=1,directories_scanned=1)
            bulk=BulkImportDialog(tab,preview)
            job=CoreJob('game-library.bulk-import',lambda _:None)
            with patch.object(tab.client,'select_bulk_candidates',return_value=Mock()),patch.object(tab.client,'execute_bulk_import',return_value=job):
                bulk.dialog.emit('response',Gtk.ResponseType.OK)
            self.assertEqual('Cancel import',bulk.cancel_button.get_label())
            job.report(JobProgress('import',1,3,'candidates','Importing…'));self.f.pump()
            self.assertEqual(self.app.status.get_text(),bulk.progress.get_text())
            with patch.object(self.app.core.game_library,'cancel',side_effect=lambda _:job.request_cancel()) as cancel:
                if modal_first:bulk.dialog.emit('response',Gtk.ResponseType.CANCEL)
                else:self.app.cancel_button.emit('clicked')
                bulk.cancel_import();self.app.cancel_button.emit('clicked')
                cancel.assert_called_once_with(job.id)
            job.report_committed(JobProgress('publish',2,3,'candidates','Publishing…'));self.f.pump()
            self.assertIn('Cancelling',bulk.progress.get_text())
            self.assertEqual(self.app.status.get_text(),bulk.progress.get_text())
            self.assertFalse(bulk.cancel_button.get_sensitive());self.assertFalse(self.app.cancel_button.get_visible())
            job.run();self.f.pump();self.assertTrue(bulk.finished)
            self.assertEqual('Close',bulk.cancel_button.get_label());self.assertNotIn('Cancelling',self.app.status.get_text())
            bulk.dialog.destroy()
