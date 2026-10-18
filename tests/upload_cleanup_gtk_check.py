"""Actual Browser copy/dialog/cleanup chain on a disposable GTK display."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch
import unittest
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
from c64u_browser.file_service import FileService
from c64u_browser.scheduler import CoreScheduler, DeviceSession
from c64u_browser.simulated_ftp_reads import MemoryFilesystem
import test_preferences_ui
import c64u_browser.file_service as files


class UploadCleanupGtk(unittest.TestCase):
    def setUp(self):
        self.assertTrue(Gtk.init_check())
        trap=patch('socket.socket.connect',side_effect=AssertionError('Network forbidden'))
        trap.start();self.addCleanup(trap.stop)
        self.f=test_preferences_ui.PreferencesUI();self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.addCleanup(self.f.tearDown)
        self.app=self.f.app
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'new').write_bytes(b'payload')
        self.peer=MemoryFilesystem();self.client=self.peer.attach()
        self.session=DeviceSession('fixture','fixture-session')
        self.scheduler=CoreScheduler(lambda:self.session);self.addCleanup(self.scheduler.close)
        self.service=FileService(lambda:self.client,lambda:self.session,scheduler=self.scheduler)
        self.addCleanup(self.service.close)
        for name,value in (('files',self.service),('device_session',lambda:self.session)):
            handle=patch.object(self.app.core,name,value);handle.start();self.addCleanup(handle.stop)
        self.app.client=self.client;self.app.local=self.root
        self.sequence=[];self.jobs=[];self.release=Event();self.entered=Event()
        self.addCleanup(self.release.set)
        self.original_run=self.app.run_file_job
        def run(submit,done,**kwargs):
            def capture():
                self.assertEqual(0,self.peer.active)
                job=submit();self.jobs.append(job);self.sequence.append(job.operation)
                return job
            return self.original_run(capture,done,**kwargs)
        self.app.run_file_job=run
        self.app.refresh_local=Mock()
        self.app.copy_report=Mock()
        def refresh(work,done):
            self.sequence.append('refresh')
            self.assertIsNone(self.app.foreground.token)
            self.assertEqual(0,self.peer.active)
            # Run the normal completion presentation with a controlled listing.
            done((None,None))
            return True
        self.app.run=refresh
        self.original_execute=files.execute_plan
        def upload(*args,**kwargs):
            report=self.original_execute(*args,**kwargs)
            self.entered.set()
            if not self.release.wait(5):raise AssertionError('upload not released')
            return report
        handle=patch.object(files,'execute_plan',side_effect=upload)
        handle.start();self.addCleanup(handle.stop)
        self.addCleanup(self.finish_jobs)

    def finish_jobs(self):
        self.release.set()
        for _ in range(8):
            for job in tuple(self.jobs):job.wait(5)
            self.f.drain_events()
            if not self.app.busy:break
        self.assertFalse(self.app.busy)

    def begin(self):
        self.peer.interrupted=True
        self.app.start_copy(True,self.root,('new',),False,'/USB2',self.client)
        self.jobs[0].wait(5);self.f.drain_events()
        self.assertTrue(self.entered.wait(5))
        self.app.cancel_button.emit('clicked');self.f.drain_events()
        self.assertIsNotNone(self.app.upload_cancel_dialog)
        return self.app.upload_cancel_dialog

    def test_delete_chain_preserves_completed_files_and_final_status(self):
        self.peer.files[b'/USB2/completed']=b'keep'
        dialog=self.begin();dialog.delete_button.emit('clicked')
        self.assertIn('Cancelling',self.app.status.get_text())
        self.release.set();self.finish_jobs()
        self.assertEqual(['file.copy.prepare','file.copy.execute','file.delete.prepare','file.delete.execute','refresh'],self.sequence)
        self.assertEqual(b'keep',self.peer.files[b'/USB2/completed'])
        self.assertEqual(1,sum(call[0]=='delete' for call in self.peer.calls))
        self.assertFalse(any(call[0]=='rmdir' for call in self.peer.calls))
        self.assertIn('Deleted 1 of 1',self.app.status.get_text())
        self.assertIn('unfinished',self.app.status.get_text())
        self.assertFalse(any(w.get_modal() for w in self.f.owned_windows()))
        focus=self.app.window.get_focus();self.assertIsNotNone(focus);self.assertTrue(focus.is_sensitive())

    def test_keep_and_continue_do_not_start_cleanup(self):
        dialog=self.begin();dialog.keep_button.emit('clicked')
        self.release.set();self.finish_jobs()
        self.assertEqual(['file.copy.prepare','file.copy.execute','refresh'],self.sequence)
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))

    def test_continue_does_not_request_cancellation(self):
        dialog=self.begin();dialog.continue_button.emit('clicked')
        self.assertFalse(self.jobs[1]._cancel.is_set())
        self.release.set();self.finish_jobs()
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))
        self.assertEqual('refresh',self.sequence[-1])

    def test_session_replacement_prevents_cleanup_and_refresh(self):
        dialog=self.begin();dialog.delete_button.emit('clicked')
        self.session=DeviceSession('fixture','new-session');self.service.invalidate_recovery()
        self.release.set();self.finish_jobs()
        self.assertNotIn('refresh',self.sequence)
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))
        self.assertNotIn('Cleanup not started: the device/session changed',self.app.status.get_text())

    def test_preparation_rejection_refreshes_only_after_result(self):
        dialog=self.begin();dialog.delete_button.emit('clicked')
        with patch('c64u_browser.file_service.deletion_snapshot',side_effect=RuntimeError('controlled rejection')):
            self.release.set();self.finish_jobs()
        self.assertEqual(['file.copy.prepare','file.copy.execute','file.delete.prepare','refresh'],self.sequence)
        self.assertIn('preparation stopped',self.app.status.get_text())
        self.assertFalse(any(call[0]=='delete' for call in self.peer.calls))

    def test_late_refresh_after_session_replacement_cannot_update_listing_or_status(self):
        callbacks=[]
        self.app.run=lambda work,done:callbacks.append((work,done)) or True
        dialog=self.begin();dialog.delete_button.emit('clicked')
        self.release.set();self.finish_jobs()
        self.assertEqual(1,len(callbacks))
        self.session=DeviceSession('fixture','replacement')
        self.app.status.set_text('New connection state')
        self.app.show_remote=Mock()
        with patch.object(self.client,"list_directory") as listing:
            self.assertIsNone(callbacks[0][0]()[0])
            listing.assert_not_called()
        callbacks[0][1]((object(),None))
        self.app.show_remote.assert_not_called()
        self.assertEqual('New connection state',self.app.status.get_text())


    def test_stale_browser_completion_cannot_write_even_without_result(self):
        import ast
        from types import SimpleNamespace
        from c64u_browser.file_service import CopyResult
        tree=ast.parse(Path('c64u_browser/gui.py').read_text())
        callback=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
                      and n.name=='refreshed_after_cleanup')
        namespace=dict(self=self.app,coordinator=[SimpleNamespace(owns_presentation=lambda:False)])
        exec(compile(ast.Module(body=[callback],type_ignores=[]),'gui.py','exec'),namespace)
        self.app.status.set_text('Current session status')
        self.app.show_remote=Mock()
        for result in (None,CopyResult((),(),('unfinished',))):
            for outcome in ('Deleted 1 of 1','Rejected','Result uncertain'):
                namespace['refreshed_after_cleanup'](
                    SimpleNamespace(result=result,error=SimpleNamespace(message='old error')),
                    outcome,False,False)
                self.assertEqual('Current session status',self.app.status.get_text())
        self.app.show_remote.assert_not_called();self.app.refresh_local.assert_not_called()


    def absence_case(self, stage):
        dialog=self.begin();dialog.delete_button.emit('clicked')
        original=self.service._execute_intent_cleanup
        if stage=='prepare':
            for path in tuple(self.peer.files):
                if path.startswith(b'/USB2/c64u-part-'):del self.peer.files[path]
        def execute(evidence):
            del self.peer.files[evidence.partial_upload.location.path.encode()]
            return original(evidence)
        with patch.object(self.service,'_execute_intent_cleanup',side_effect=execute):
            self.release.set();self.finish_jobs()
        self.assertIn('Cleanup was unnecessary: the incomplete staging file was not found during verification.',self.app.status.get_text())
        self.assertNotIn('may remain',self.app.status.get_text())
        self.assertNotIn('Cleanup succeeded',self.app.status.get_text())
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))
        result=self.jobs[-1].snapshot().result
        self.assertEqual((),result.removed)
        self.assertIsNotNone(result.absent_target)
        self.assertEqual(1,self.sequence.count('file.delete.prepare'))
        self.assertEqual(0 if stage=='prepare' else 1,self.sequence.count('file.delete.execute'))

    def test_verified_absence_during_preparation_status(self):
        self.absence_case('prepare')

    def test_verified_absence_during_execution_status(self):
        self.absence_case('execute')
