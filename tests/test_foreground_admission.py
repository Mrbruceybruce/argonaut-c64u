"""Offline Browser admission regressions: no sockets, device, or real files."""
import ast
from pathlib import Path
from threading import Barrier, Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from c64u_browser.foreground import ForegroundSlot
from c64u_browser.operation_status import OperationPresentation
from c64u_browser.gui import Browser
from c64u_browser.jobs import CoreJob, JobProgress
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding
from c64u_browser.game_library_tab import GameLibraryTab
from c64u_browser.sid_jukebox_tab import SidJukeboxTab
from c64u_browser.game_library_bulk_dialog import BulkImportDialog
from c64u_browser.flash_dialog import FlashFiles


class Admission(unittest.TestCase):
    def setUp(self):
        self.idles=[];self.timers=[]
        self.addCleanup(patch.stopall)
        patch('c64u_browser.gui.GLib.idle_add', side_effect=self.idle).start()
        patch('c64u_browser.gui.GLib.timeout_add', side_effect=lambda ms, fn:self.timers.append(fn)).start()
        self.app=SimpleNamespace(busy=False, foreground=ForegroundSlot(),
            transfer_job=None,busy_controls=[],status=Mock(),cancel_button=Mock(),
            window=Mock(),local=Path('/tmp'))
        for name in ('run_file_job','begin_file_job','end_file_job','cancel_transfer','bind_job_cancel','job_cancel_callback'):
            setattr(self.app,name,lambda *args,_name=name,**kw:getattr(Browser,_name)(self.app,*args,**kw))
        self.app.operation=OperationPresentation(lambda view:self.app.status.set_text(view.message))
        self.app.core=SimpleNamespace(files=SimpleNamespace(cancel=self.cancel))
        self.jobs={}

    def idle(self, fn, *args):
        self.idles.append((fn,args));return len(self.idles)

    def pump(self):
        while self.idles:
            fn,args=self.idles.pop(0);fn(*args)

    def job(self, operation='file.synthetic'):
        job=CoreJob(operation,lambda _: 'result');self.jobs[job.id]=job;return job

    def cancel(self, identity):return self.jobs[identity].request_cancel()

    def start(self, job=None, done=None):
        job=job or self.job();factory=Mock(return_value=job)
        self.assertTrue(self.app.run_file_job(factory,done or Mock()))
        factory.assert_called_once_with();return job

    def test_basic_and_second_refusal_before_service_submission(self):
        a=self.start();b=Mock()
        self.assertFalse(self.app.run_file_job(b,Mock()));b.assert_not_called()
        self.assertIs(a,self.app.transfer_job)
        self.assertIn('already in progress',self.app.status.set_text.call_args.args[0])
        a.run();self.pump();self.assertIsNone(self.app.foreground.token)
        self.assertFalse(self.app.busy)

    def test_reentrant_submission_and_ordinary_worker_refuse_reserved_slot(self):
        second=Mock();worker=Mock()
        def submit():
            self.assertIsNotNone(self.app.foreground.token)
            self.assertIsNone(self.app.foreground.job)
            self.assertFalse(self.app.run_file_job(second,Mock()))
            self.assertFalse(Browser.run(self.app,worker,Mock()))
            return self.job()
        self.assertTrue(self.app.run_file_job(submit,Mock()))
        second.assert_not_called();worker.assert_not_called()

    def test_concurrent_reservation_exactly_one_winner_without_sleep(self):
        slot=ForegroundSlot();barrier=Barrier(3);results=[]
        def attempt():barrier.wait();results.append(slot.reserve())
        threads=[Thread(target=attempt) for _ in range(2)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join(2);self.assertFalse(thread.is_alive())
        self.assertEqual(1,sum(token is not None for token in results))
        slot.release(next(token for token in results if token is not None))

    def test_submission_exception_and_explicit_refusal_release_reservation(self):
        for factory in (Mock(side_effect=ValueError('refused')),Mock(return_value=None),Mock(return_value=False)):
            error=Mock();self.assertFalse(self.app.run_file_job(factory,Mock(),failed=error))
            error.assert_called_once();self.assertIsNone(self.app.foreground.token)
            self.assertIsNone(self.app.transfer_job);self.assertFalse(self.app.busy)
        self.start()

    def test_cancellation_retains_slot_until_authoritative_terminal(self):
        a=self.start();old_cancel=self.app.job_cancel_callback(a);old_cancel()
        self.assertEqual('cancel-requested',a.snapshot().state)
        b=Mock(return_value=self.job())
        self.assertFalse(self.app.run_file_job(b,Mock()));b.assert_not_called()
        a.run();self.pump()
        self.assertTrue(self.app.run_file_job(b,Mock()))
        self.assertEqual('pending',self.app.transfer_job.snapshot().state)
        old_cancel()
        self.assertEqual('pending',self.app.transfer_job.snapshot().state)

    def test_old_finish_progress_cleanup_and_cancel_cannot_affect_new_job(self):
        done=Mock();a=self.start(done=done);token=self.app.foreground.token
        a.report(JobProgress('read',1,None,'bytes','old progress'))
        a.run()
        old_idles=list(self.idles);self.idles.clear()
        self.assertFalse(self.timers[0]()) # missed-event fallback
        done.assert_called_once()
        b=self.start();self.app.status.reset_mock()
        for fn,args in old_idles:fn(*args)
        self.assertFalse(self.app.end_file_job(a,token))
        self.app.job_cancel_callback(a)()
        self.assertIs(b,self.app.transfer_job);self.assertIs(b,self.app.foreground.job)
        self.assertEqual('pending',b.snapshot().state)
        self.app.status.set_text.assert_not_called()

    def test_fallback_after_cancel_and_progress_releases_once(self):
        done=Mock();a=self.start(done=done)
        a.report(JobProgress('read',1,None,'bytes','Reading…'))
        self.app.job_cancel_callback(a)();a.run()
        self.assertFalse(self.timers[0]());self.pump()
        done.assert_called_once();self.assertIsNone(self.app.transfer_job)
        self.app.cancel_button.set_sensitive.assert_called_with(False)

    def test_registration_cannot_replace_existing_job(self):
        a=self.start();b=self.job()
        with self.assertRaises(RuntimeError):self.app.begin_file_job(b,object())
        self.assertIs(a,self.app.transfer_job)

    def tab(self, cls):
        tab=SimpleNamespace(app=self.app,client=Mock(),chooser=None,
            job_busy=False,cancel_button=Mock(),_update_actions=Mock(),_show=Mock(),refresh=Mock())
        for name in ('_run_job','_add_local_paths'):
            setattr(tab,name,lambda *args,_name=name,**kw:getattr(cls,_name)(tab,*args,**kw))
        tab._game_filter=Mock();tab._sid_filter=Mock()
        return tab

    def test_both_delayed_nonmodal_chooser_callbacks_refuse_before_submission(self):
        for cls,module in ((GameLibraryTab,'game_library_tab'),(SidJukeboxTab,'sid_jukebox_tab')):
            with self.subTest(tab=module):
                tab=self.tab(cls);chooser=Mock();file=Mock();file.get_path.return_value='/tmp/fake.sid'
                files=Mock();files.get_n_items.return_value=1;files.get_item.return_value=file
                chooser.get_files.return_value=files
                callbacks={};chooser.connect.side_effect=lambda signal,fn:callbacks.update({signal:fn})
                with patch(f'c64u_browser.{module}.Gtk.FileChooserNative.new',return_value=chooser):
                    cls.add_local(tab)
                a=self.start()
                from gi.repository import Gtk
                callbacks['response'](chooser,Gtk.ResponseType.ACCEPT)
                tab.client.add_core_host.assert_not_called()
                self.assertIs(a,self.app.transfer_job);self.assertFalse(tab.job_busy)
                a.run();self.pump()

    def test_sid_delayed_progress_is_identity_guarded(self):
        tab=self.tab(SidJukeboxTab);a=self.job('sid-jukebox.synthetic')
        self.assertTrue(tab._run_job(lambda:a,Mock()))
        a.report(JobProgress('read',1,None,'bytes','Old SID'))
        a.run();old=list(self.idles);self.idles.clear();self.timers[0]()
        b=self.start();tab._show.reset_mock()
        for fn,args in old:fn(*args)
        tab._show.assert_not_called();self.assertIs(b,self.app.transfer_job)

    def test_flash_delayed_prepare_refuses_before_submission(self):
        owner=SimpleNamespace(app=self.app,tab=SimpleNamespace(client='same'),client='same',
            controls=Mock(),status=Mock(),folder=lambda:'/Flash/roms')
        owner.run_core_job=lambda *args:FlashFiles.run_core_job(owner,*args)
        self.app.core.files.prepare_native_upload=Mock()
        a=self.start()
        FlashFiles.prepare(owner,'/tmp/fake.rom',False)
        self.app.core.files.prepare_native_upload.assert_not_called()
        self.assertIs(a,self.app.transfer_job)

    def test_bulk_import_refusal_does_not_execute_or_change_modal_state(self):
        tab=self.tab(GameLibraryTab)
        bulk=SimpleNamespace(tab=tab,client=tab.client,finished=False,executing=False,
            state=SimpleNamespace(count=1,selected_ids=lambda:('one',)),preview=Mock(),
            progress=Mock(),import_button=Mock(),_finished=Mock())
        a=self.start()
        from gi.repository import Gtk
        BulkImportDialog._response(bulk,Mock(),Gtk.ResponseType.OK)
        bulk.client.execute_bulk_import.assert_not_called()
        self.assertFalse(bulk.executing);self.assertIs(a,self.app.transfer_job)

    def test_core_local_and_device_lanes_still_overlap(self):
        session=DeviceSession('synthetic','one');scheduler=CoreScheduler(lambda:session)
        self.addCleanup(scheduler.close);release=Event();self.addCleanup(release.set)
        entered_a,entered_b=Event(),Event()
        def task(entered):
            def run(job):entered.set();release.wait(2)
            return run
        a=scheduler.submit(CoreJob('device',task(entered_a)),JobBinding.device(session))
        b=scheduler.submit(CoreJob('local',task(entered_b)),JobBinding.core_host())
        try:
            self.assertTrue(entered_a.wait(1));self.assertTrue(entered_b.wait(1))
            self.assertEqual(('running','running'),(a.snapshot().state,b.snapshot().state))
        finally:release.set();a.wait(1);b.wait(1)

    def test_presentation_failure_does_not_abandon_accepted_job(self):
        self.app.cancel_button.set_sensitive.side_effect=RuntimeError('widget destroyed')
        a=self.start();a.run();self.pump()
        self.assertIsNone(self.app.foreground.token);self.assertIsNone(self.app.transfer_job)
    def callback(self, filename, method, callback, namespace):
        """Exercise real nested response bodies without constructing their dialogs."""
        tree=ast.parse((Path(__file__).parents[1]/'c64u_browser'/filename).read_text())
        owner=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==method)
        response=next(n for n in ast.walk(owner) if isinstance(n,ast.FunctionDef) and n.name==callback)
        exec(compile(ast.Module(body=[response],type_ignores=[]),filename,'exec'),namespace)
        return namespace[callback]

    def test_delayed_usb_restore_game_launch_and_sid_play_confirmations(self):
        from gi.repository import Gtk
        a=self.start()
        self.app.core.usb=Mock();self.app.usb_restore_finished=Mock()
        preview=SimpleNamespace(plan_id='reviewed')
        confirmed=self.callback('gui.py','restore_preview','confirmed',
            {'self':self.app,'preview':preview,'Gtk':Gtk})
        confirmed(Mock(),Gtk.ResponseType.OK)
        self.app.core.usb.execute_restore.assert_not_called()
        for cls,filename,method,callback,execute,finish in (
            (GameLibraryTab,'game_library_tab.py','_launch_prepared','answered','execute_launch','_launch_finished'),
            (SidJukeboxTab,'sid_jukebox_tab.py','_play_prepared','response','execute_play','_play_finished')):
            tab=self.tab(cls);setattr(tab,finish,Mock())
            answer=self.callback(filename,method,callback,{'self':tab,'preview':preview,'Gtk':Gtk})
            answer(Mock(),Gtk.ResponseType.OK)
            getattr(tab.client,execute).assert_not_called()
            self.assertFalse(tab.job_busy)
        self.assertIs(a,self.app.transfer_job)

    def test_delayed_files_folder_and_flash_upload_confirmations(self):
        from gi.repository import Gtk
        from c64u_browser.file_service import FileLocation
        a=self.start();self.app.core.files.create_folder=Mock()
        submit=self.callback('gui.py','new_folder','submit',
            {'self':self.app,'parent':'/tmp','local':True,'FileLocation':FileLocation})
        submit('new');self.app.core.files.create_folder.assert_not_called()
        owner=SimpleNamespace(app=self.app,tab=SimpleNamespace(client='same'),client='same',
            controls=Mock(),status=Mock(),refresh=Mock())
        owner.run_core_job=lambda *args:FlashFiles.run_core_job(owner,*args)
        self.app.core.files.execute_native_upload=Mock()
        # prepare contains the chooser-independent upload confirmation callback.
        answer=self.callback('flash_dialog.py','prepare','response',
            {'self':owner,'preview':SimpleNamespace(plan_id='reviewed'),'dialog':Mock(),'Gtk':Gtk})
        answer(Mock(),Gtk.ResponseType.OK)
        self.app.core.files.execute_native_upload.assert_not_called()
        self.assertIs(a,self.app.transfer_job)

    def test_submission_failure_batch_continues_and_terminal_failure_releases(self):
        tab=self.tab(GameLibraryTab);job=self.job('game-library.add')
        tab.client.add_core_host.side_effect=[ValueError('bad source'),job]
        tab._add_local_paths(('/tmp/one','/tmp/two'))
        self.assertEqual(2,tab.client.add_core_host.call_count)
        self.assertIs(job,self.app.transfer_job)
        # A failed managed job is terminal just like successful/cancelled work.
        failing=CoreJob('file.failure',lambda _:(_ for _ in ()).throw(ValueError('failure')))
        job.run();self.pump()
        self.start(failing);failing.run();self.pump()
        self.assertIsNone(self.app.foreground.token)

    def test_short_mutex_reservation_active_failure_and_terminal_identity(self):
        slot=ForegroundSlot();a=slot.reserve()
        self.assertTrue(slot._admission.acquire(blocking=False))
        slot._admission.release()
        self.assertTrue(slot.owns(a,None));self.assertIsNone(slot.reserve())
        job=self.job();slot.bind(a,job)
        self.assertTrue(slot._admission.acquire(blocking=False))
        slot._admission.release()
        self.assertIsNone(slot.reserve())
        self.assertFalse(slot.release(a)) # unbound failure cannot release active job
        self.assertTrue(slot.release(a,job))
        b=slot.reserve();second=self.job();slot.bind(b,second)
        self.assertFalse(slot.release(a));self.assertFalse(slot.release(a,job))
        with self.assertRaises(RuntimeError):slot.bind(a,job)
        self.assertTrue(slot.owns(b,second));slot.release(b,second)

    def test_submission_execution_and_cancellation_run_outside_state_mutex(self):
        slot=self.app.foreground
        def inspect_mutex():
            self.assertTrue(slot._admission.acquire(blocking=False))
            slot._admission.release()
            self.assertIsNone(slot.reserve())
        def task(job):
            inspect_mutex()
            self.assertTrue(slot.owns(slot.token,job))
            self.app.cancel_button.connect.call_args.args[1](self.app.cancel_button)
            job.check_cancel()
        job=CoreJob('file.synthetic',task);self.jobs[job.id]=job
        def submit():inspect_mutex();return job
        def cancel(identity):inspect_mutex();return self.jobs[identity].request_cancel()
        self.app.core.files.cancel=cancel
        self.assertTrue(self.app.run_file_job(submit,Mock()))
        job.run();self.assertEqual('cancelled',job.snapshot().state)
        self.assertTrue(slot.owns(slot.token,job));self.pump()
        self.assertIsNone(slot.token)

    def test_registered_cancel_callbacks_capture_identity_for_all_permanent_buttons(self):
        for cls in (None,GameLibraryTab,SidJukeboxTab):
            with self.subTest(route=cls):
                tab=self.tab(cls) if cls else None
                button=self.app.cancel_button
                def launch(job):
                    return tab._run_job(lambda:job,Mock()) if tab else self.app.run_file_job(lambda:job,Mock())
                a=self.job();launch(a)
                old=button.connect.call_args.args[1]
                request=Mock(side_effect=self.cancel);self.app.core.files.cancel=request
                old(button);request.assert_called_once_with(a.id)
                a.run();self.pump();request.reset_mock()
                old(button);old(button);request.assert_not_called()
                b=self.job();launch(b);current=button.connect.call_args.args[1]
                self.app.status.reset_mock();old(button);old(button)
                request.assert_not_called();self.app.status.set_text.assert_not_called()
                self.assertIs(b,self.app.transfer_job);self.assertEqual('pending',b.snapshot().state)
                current(button);request.assert_called_once_with(b.id)
                b.run();self.pump()

    def test_stale_submission_failure_cannot_clear_replacement_busy_or_status(self):
        b=self.job()
        def submit():
            old=self.app.foreground.token
            self.assertTrue(self.app.foreground.release(old))
            self.app.busy=False
            self.start(b)
            self.app.status.reset_mock()
            raise ValueError('late failure from invalidated reservation')
        failed=Mock()
        self.assertFalse(self.app.run_file_job(submit,Mock(),failed=failed))
        failed.assert_not_called();self.app.status.set_text.assert_not_called()
        self.assertTrue(self.app.busy);self.assertIs(b,self.app.transfer_job)
        self.assertTrue(self.app.foreground.owns(self.app.foreground.token,b))
