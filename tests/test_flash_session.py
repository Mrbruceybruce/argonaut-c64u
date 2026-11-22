"""Issue 24: synthetic Core and inert GTK; no hardware or live transport."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
import tempfile
import unittest
import gi
gi.require_version('Gtk', '4.0')
from tests import test_core
from c64u_browser.api import BrowserError, Entry
from c64u_browser.core import CoreError
from c64u_browser.flash_dialog import FlashFiles
from c64u_browser.backup_dialog import BackupActions
from c64u_browser.file_service import FileLocation
from c64u_browser.scheduler import JobBinding


class FlashSessionTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection', 'socket.getaddrinfo',
                       'socket.socket.connect', 'socket.socket.connect_ex', 'socket.socket.sendto'):
            p=patch(target, side_effect=AssertionError('OFFLINE'));p.start();self.addCleanup(p.stop)
        self.fixture=test_core.CoreTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.client=self.fixture.created[-1];self.client.list_directory=Mock(return_value=('/', []))
        self.ui=FlashFiles.__new__(FlashFiles)
        self.app=NS(core=self.core,busy=False,window=None,status=Mock(),
                    run=lambda task,done:done(task()))
        self.tab=NS(app=self.app,client=self.core.device_operations,backups=Mock(),pending={},drafts={},reload=Mock())
        self.ui.__dict__.update(tab=self.tab,app=self.app,client=self.tab.client,
            session=self.core.device_session(),closed=False,chooser=None,confirmation=None,
            plan_id=None,dialog=Mock(),status=Mock(),controls=Mock(),folders=Mock(),listing=Mock(),
            save_button=Mock(),preview_button=Mock())
        self.ui.folders.get_active_id.return_value='/Flash/roms'
        self.ui.listing.get_first_child.return_value=None
        self.dialogs=[]
        def widget(*a,**kw):
            w=Mock();w.callbacks={}
            w.connect.side_effect=lambda event,fn:w.callbacks.update({event:fn})
            self.dialogs.append(w);return w
        self.gtk=NS(Dialog=widget,Label=Mock(),ListBoxRow=Mock(),
            FileChooserNative=NS(new=widget),FileChooserAction=NS(OPEN=1,SAVE=2),
            ResponseType=NS(OK=1,CANCEL=0,ACCEPT=1),
            Box=widget,Orientation=NS(VERTICAL=1),CheckButton=widget,ScrolledWindow=widget)
        for module in ('flash_dialog','backup_dialog'):
            p=patch('c64u_browser.'+module+'.Gtk',self.gtk);p.start();self.addCleanup(p.stop)
        self.jobs=[]
        def run_job(factory,done,started,failed):
            try:
                job=factory();self.jobs.append(job);started(job);done(job.wait(5))
            except Exception as exc:failed(exc)
        self.app.run_file_job=run_job

    def reconnect(self):self.core.reconnect()

    def chooser(self,save=False):
        self.ui.listing.get_selected_row.return_value=NS(name='x.bin')
        (self.ui.save_copy if save else self.ui.choose_local)()
        chooser=self.ui.chooser;chooser.get_file.return_value.get_path.return_value='/tmp/x.bin'
        return chooser.callbacks['response']

    def test_stable_service_reconnect_retires(self):
        old=self.tab.client;self.reconnect();self.assertIs(old,self.core.device_operations)
        self.ui.refresh();self.assertTrue(self.ui.closed);self.client.list_directory.assert_not_called()

    def test_different_device_replacement(self):
        factory=self.core._client_factory
        def different(*a,**kw):
            c=factory(*a,**kw);c._info=dict(test_core.INFO,info=dict(test_core.INFO['info'],unique_id='OTHER'));return c
        with patch.object(self.core,'_client_factory',different):
            self.core.connect(replace(self.fixture.profile,id='other',host='192.0.2.21',device_id='OTHER',device_mac=''))
        self.assertFalse(self.ui.current());self.assertTrue(self.ui.closed)

    def test_delayed_upload_chooser(self):
        callback=self.chooser();self.ui.prepare=Mock();self.reconnect();callback(None,1)
        self.ui.prepare.assert_not_called();self.assertTrue(self.ui.closed)

    def test_delayed_save_chooser(self):
        callback=self.chooser(True);self.reconnect()
        with patch.object(self.core.files,'save_native_copy') as save:
            callback(None,1);save.assert_not_called()

    def test_chooser_duplicate_and_folder_capture(self):
        callback=self.chooser();self.ui.prepare=Mock();self.ui.folders.get_active_id.return_value='/Flash/carts'
        callback(None,1);callback(None,1)
        self.ui.prepare.assert_called_once_with('/tmp/x.bin',False,folder='/Flash/roms')

    def test_cancel_consumes_chooser(self):
        callback=self.chooser();self.ui.prepare=Mock();callback(None,0);callback(None,1)
        self.ui.prepare.assert_not_called()

    def test_closed_dialog_ignores_chooser(self):
        callback=self.chooser();self.ui.prepare=Mock();self.ui.close();callback(None,1)
        self.ui.prepare.assert_not_called();self.ui.dialog.destroy.assert_called_once()

    def test_delayed_worker_core_rejects(self):
        pending=[];self.app.run=lambda task,done:pending.append((task,done));self.ui.refresh();self.reconnect()
        task,done=pending[0];result=task();self.assertIsInstance(result,CoreError);done(result)
        self.client.list_directory.assert_not_called()

    def test_stale_preview_completion(self):
        pending=[];self.app.run=lambda task,done:pending.append((task,done))
        self.ui.folders.get_active_id.return_value='/Flash/configs';self.ui.listing.get_selected_row.return_value=NS(name='x.cfg')
        self.ui.preview();self.reconnect();pending[0][1](({}, {}, 0))
        self.tab.backups.preview.assert_not_called()

    def test_closed_completion_and_duplicate(self):
        pending=[];self.app.run=lambda task,done:pending.append(done);done=Mock()
        self.ui.run(lambda:[],done);self.ui.retire();pending[0]([]);pending[0]([]);done.assert_not_called()

    def test_valid_completion_once(self):
        pending=[];self.app.run=lambda task,done:pending.append(done);done=Mock()
        self.ui.run(lambda:[],done);pending[0]([]);pending[0]([]);done.assert_called_once_with([])

    def test_core_stale_read_and_admissions(self):
        session=self.ui.session;self.reconnect()
        with self.assertRaises(CoreError):self.core.read_flash(session,'/Flash/roms')
        with patch('c64u_browser.file_service.read_local') as read:
            with self.assertRaises(BrowserError):
                self.core.files.prepare_native_upload(FileLocation.core_host('/unused'),'/Flash/roms','x.bin',expected_session=session)
            read.assert_not_called()
        with self.assertRaises(BrowserError):
            self.core.files.save_native_copy(FileLocation.c64u('/Flash/roms/x.bin'),FileLocation.core_host('/unused'),expected_session=session)

    def test_core_valid_listing_and_session_gate(self):
        entry=NS(name='roms',kind='dir');self.client.list_directory.side_effect=[('/Flash',[entry]),('/Flash/roms',[])]
        self.assertEqual([],self.core.read_flash(self.ui.session,'/Flash/roms'))
        self.assertEqual(2,self.client.list_directory.call_count)
        with self.core._session_admission():
            with self.assertRaises(CoreError):self.core.read_flash(self.ui.session,'/Flash/roms')
        self.assertEqual(2,self.client.list_directory.call_count)

    def test_valid_prepare_and_stale_confirmation_discards(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'x.bin';path.write_bytes(b'x');self.ui.prepare(str(path),False)
        self.assertEqual('succeeded',self.jobs[0].snapshot().state)
        confirmation=self.ui.confirmation;plan=self.ui.plan_id;self.assertIn(plan,self.core.files._native_plans)
        self.reconnect();confirmation.callbacks['response'](None,1)
        self.assertNotIn(plan,self.core.files._native_plans);self.assertEqual(1,len(self.jobs))

    def test_cancel_confirmation_duplicate_accept(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'x.bin';path.write_bytes(b'x');self.ui.prepare(str(path),False)
        callback=self.ui.confirmation.callbacks['response'];plan=self.ui.plan_id
        callback(None,0);callback(None,1);self.assertNotIn(plan,self.core.files._native_plans);self.assertEqual(1,len(self.jobs))

    def test_stale_prepare_completion_discards_plan(self):
        pending=[]
        self.app.run_file_job=lambda job,done,**kw:pending.append((job(),done))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'x.bin';path.write_bytes(b'x');self.ui.prepare(str(path),False)
            job,done=pending[0];snapshot=job.wait(5)
        self.reconnect();done(snapshot);done(snapshot)
        self.assertNotIn(snapshot.result.plan_id,self.core.files._native_plans);self.assertIsNone(self.ui.confirmation)

    def test_retired_upload_preserves_evidence(self):
        pending=[];self.app.run_file_job=lambda job,done,**kw:pending.append(done)
        self.ui.run_core_job(Mock(),Mock());self.ui.retire()
        evidence=Mock();evidence.message.return_value='Publication outcome unknown; inspect both paths.'
        pending[0](NS(result=NS(flash=evidence)))
        self.assertIn('inspect both paths',self.app.status.set_text.call_args.args[0])

    def test_preview_staging_rejects_reconnect(self):
        self.tab.requires_refresh=False;self.tab.admit_changes=Mock();self.tab.stage=Mock()
        with patch('c64u_browser.backup_dialog.differences',return_value=([('cat',NS(name='name',current='old'),'new')],0)):
            dialog,checks=BackupActions(self.tab).preview({}, {}, expected_session=self.ui.session)
        checks[0].get_active.return_value=True;self.reconnect();dialog.callbacks['response'](None,1)
        self.tab.stage.assert_not_called();self.tab.admit_changes.assert_not_called()

    def test_valid_upload_confirmation_executes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'x.bin';path.write_bytes(b'x');self.ui.prepare(str(path),False)
        callback=self.ui.confirmation.callbacks['response'];plan=self.ui.plan_id
        self.ui.refresh=Mock()
        from c64u_browser.jobs import CoreJob
        job=CoreJob('file.synthetic-upload',lambda _:NS(message='Published synthetic file.'))
        job.run()
        with patch.object(self.core.files,'execute_native_upload',return_value=job) as execute:
            callback(None,1);callback(None,1)
        execute.assert_called_once_with(plan)
        self.assertEqual(2,len(self.jobs));self.ui.refresh.assert_called_once()
        self.assertIsNone(self.ui.confirmation);self.assertIsNone(self.ui.plan_id)
        self.app.status.set_text.assert_called_with('Published synthetic file.')

    def test_valid_native_preview_stages_once(self):
        self.ui.folders.get_active_id.return_value='/Flash/configs'
        self.ui.listing.get_selected_row.return_value=NS(name='x.cfg')
        self.tab.requires_refresh=False;self.tab.admit_changes=Mock(return_value={'name':'new'})
        self.tab.stage=Mock();self.tab.render=Mock();self.tab.update_edit_buttons=Mock()
        self.tab.backups=BackupActions(self.tab)
        setting=NS(name='name',current='old')
        with patch.object(self.core,'read_flash',return_value=({}, {}, 0)) as read, patch(
                'c64u_browser.backup_dialog.differences',return_value=([('cat',setting,'new')],0)):
            self.ui.preview()
        read.assert_called_once_with(self.ui.session,'/Flash/configs',name='x.cfg')
        self.assertTrue(self.ui.closed)
        dialog=next(w for w in self.dialogs if 'response' in w.callbacks)
        checks=[w for w in self.dialogs if 'toggled' in w.callbacks]
        self.assertEqual(1,len(checks));checks[0].get_active.return_value=True
        dialog.callbacks['response'](None,1);dialog.callbacks['response'](None,1)
        self.tab.stage.assert_called_once_with('cat',setting,'new')
        self.tab.admit_changes.assert_called_once();self.tab.render.assert_called_once()
