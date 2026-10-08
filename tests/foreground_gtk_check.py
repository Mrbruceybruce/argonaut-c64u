"""Explicit offline GTK admission checks; a display is required, no skips."""
import unittest
from unittest.mock import Mock, patch
from c64u_browser.jobs import CoreJob
from gi.repository import Gtk, GLib
import test_preferences_ui


class ForegroundGtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check(), 'Offline GTK display required')
        self.trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        self.trap.start();self.addCleanup(self.trap.stop)
        self.fixture=test_preferences_ui.PreferencesUI()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.app=self.fixture.app

    def test_refusal_is_immediate_and_gtk_heartbeat_continues(self):
        job=CoreJob('file.synthetic',lambda _: 'done')
        self.assertTrue(self.app.run_file_job(lambda:job,Mock()))
        second=Mock();ticks=[]
        GLib.idle_add(lambda:(ticks.append(True),False)[1])
        for _ in range(20):self.assertFalse(self.app.run_file_job(second,Mock()))
        self.fixture.pump_for(.05)
        second.assert_not_called();self.assertTrue(ticks)
        self.assertIs(job,self.app.transfer_job)
        job.run();self.fixture.pump()
        self.assertFalse(self.app.busy);self.assertIsNone(self.app.foreground.token)
        self.assertFalse(self.app.cancel_button.get_sensitive())

    def test_actual_chooser_acceptances_refuse_after_another_job_starts(self):
        for tab,method in ((self.app.game_library_tab,'game_library_tab'),
                           (self.app.sid_jukebox_tab,'sid_jukebox_tab')):
            # Real Gtk chooser and response signal; hide native presentation.
            with patch.object(Gtk.FileChooserNative,'show'):
                tab.add_local()
            chooser=tab.chooser
            fake_file=Mock();fake_file.get_path.return_value='/tmp/synthetic.sid'
            files=Mock();files.get_n_items.return_value=1;files.get_item.return_value=fake_file
            a=CoreJob('file.synthetic',lambda _:None)
            self.app.run_file_job(lambda:a,Mock())
            with patch.object(Gtk.FileChooserNative,'get_files',return_value=files), \
                 patch.object(tab.client,'add_core_host') as submit:
                chooser.emit('response',Gtk.ResponseType.ACCEPT)
            submit.assert_not_called();self.assertIs(a,self.app.transfer_job)
            self.assertFalse(tab.job_busy)
            a.run();self.fixture.pump()

    def test_immediate_terminal_job_updates_tab_once_and_releases(self):
        tab=self.app.game_library_tab
        job=CoreJob('game-library.synthetic',lambda _:None);job.run()
        done=Mock()
        self.assertTrue(tab._run_job(lambda:job,done))
        self.fixture.pump()
        done.assert_called_once();self.assertFalse(tab.job_busy)
        self.assertIsNone(tab.active_job);self.assertFalse(self.app.busy)

    def test_retained_real_button_handlers_cannot_cancel_running_replacements(self):
        from threading import Event, Thread
        routes=[None,self.app.sid_jukebox_tab,self.app.game_library_tab]
        for tab in routes:
            button=self.app.cancel_button
            captured=[];original=Gtk.Button.connect
            def connect(widget,signal,callback,*args):
                if widget is button and signal=='clicked':captured.append(callback)
                return original(widget,signal,callback,*args)
            def launch(job):
                return self.app.run_file_job(lambda:job,Mock()) if tab is None else tab._run_job(lambda:job,Mock())
            a=CoreJob('file.synthetic',lambda _:None)
            with patch.object(Gtk.Button,'connect',connect):launch(a)
            old=captured[-1]
            with patch.object(self.app.core.files,'cancel',side_effect=lambda _:a.request_cancel()) as cancel:
                old(button);cancel.assert_called_once_with(a.id)
            a.run();self.fixture.pump()
            with patch.object(self.app.core.files,'cancel') as cancel:
                old(button);old(button);cancel.assert_not_called()
            entered,release=Event(),Event()
            b=CoreJob('file.synthetic',lambda job:(entered.set(),release.wait(2),job.check_cancel()))
            with patch.object(Gtk.Button,'connect',connect):launch(b)
            worker=Thread(target=b.run);worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with patch.object(self.app.core.files,'cancel',side_effect=lambda _:b.request_cancel()) as cancel:
                    old(button);old(button);cancel.assert_not_called()
                    self.assertEqual('running',b.snapshot().state)
                    self.assertIs(b,self.app.transfer_job)
                    captured[-1](button);cancel.assert_called_once_with(b.id)
            finally:release.set();worker.join(2);self.fixture.pump()

    def test_retained_bulk_modal_response_and_cancel_authority_are_harmless(self):
        from c64u_browser.game_library_bulk_dialog import BulkImportDialog
        tab=self.app.game_library_tab
        preview=Mock(plan_id='synthetic',default_selected_candidate_ids=('a',),
            eligible_candidate_ids=('a',),candidates=(),issues=(),
            classification_counts=(('new-valid',1),),entries_seen=1,
            supported_candidates=1,directories_scanned=1)
        captured=[];original=Gtk.Dialog.connect
        def connect(widget,signal,callback,*args):
            if signal=='response':captured.append(callback)
            return original(widget,signal,callback,*args)
        with patch.object(Gtk.Dialog,'connect',connect):bulk=BulkImportDialog(tab,preview)
        old=captured[-1];a=CoreJob('file.synthetic',lambda _:None)
        with patch.object(tab.client,'select_bulk_candidates',return_value=Mock()), \
             patch.object(tab.client,'execute_bulk_import',return_value=a):
            bulk.dialog.emit('response',Gtk.ResponseType.OK)
        bound_cancel=bulk.cancel_import
        with patch.object(self.app.core.files,'cancel',side_effect=lambda _:a.request_cancel()) as cancel:
            old(bulk.dialog,Gtk.ResponseType.CANCEL);cancel.assert_called_once_with(a.id)
        a.run();self.fixture.pump();self.assertTrue(bulk.finished)
        with patch.object(self.app.core.files,'cancel') as cancel:
            old(bulk.dialog,Gtk.ResponseType.CANCEL);bound_cancel();cancel.assert_not_called()
        from threading import Event,Thread
        entered,release=Event(),Event()
        b=CoreJob('file.synthetic',lambda _:(entered.set(),release.wait(2)))
        self.app.run_file_job(lambda:b,Mock());worker=Thread(target=b.run);worker.start()
        try:
            self.assertTrue(entered.wait(1));status=self.app.status.get_text()
            with patch.object(self.app.core.files,'cancel') as cancel:
                for _ in range(2):old(bulk.dialog,Gtk.ResponseType.CANCEL);bound_cancel()
                cancel.assert_not_called()
            self.assertEqual('running',b.snapshot().state);self.assertIs(b,self.app.transfer_job)
            self.assertEqual(status,self.app.status.get_text())
        finally:release.set();worker.join(2);self.fixture.pump()
