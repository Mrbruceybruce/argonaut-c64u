"""R1 production routing and evidence over loopback sockets; no devices."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.file_service import CopyRequest, FileLocation
from c64u_browser.folder_copy import Step, Plan, execute_plan
from c64u_browser.folder_steps import execute_managed_step, FolderStepFailure
from c64u_browser.jobs import JobCancelled
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.usb_backup import BackupRequest

S=b'/USB1/source/a'
D=b'/USB1/dest/a'

def server(data=b'abc'):
    return FakeC64UFtp(directories={b'/':b'',b'/USB1':b'',b'/USB1/source':b'',b'/USB1/dest':b''},
                      files={S:data,b'/USB1/sentinel':b'keep'},mutation_tree=True)

class FolderStepTests(unittest.TestCase):
    core=reads.ReadMigrationTests.core
    connect=reads.ReadMigrationTests.connect

    def preview(self, core, names=('a',)):
        r=core.files.prepare_copy(CopyRequest(FileLocation.c64u('/USB1/source'),names,
                                             FileLocation.c64u('/USB1/dest'))).wait(5)
        self.assertEqual('succeeded',r.state,r.error)
        return r.result.plan_id

    def execute(self,core,ftp,plan,connections=1):
        before=ftp.connections;epoch=core.device_session();ftp.commands.clear()
        with patch('ftplib.FTP',side_effect=AssertionError('raw fallback')):
            r=core.files.execute_copy(plan).wait(5)
        self.assertIn(r.state,('succeeded','failed','cancelled'))
        self.assertEqual(0,core._ftp_manager.active_count)
        self.assertEqual(epoch,core.device_session())
        self.assertLessEqual(ftp.connections-before,connections)
        self.assertEqual(ftp.connections-before,ftp.verbs.count(b'USER'))
        self.assertEqual(ftp.connections-before,ftp.verbs.count(b'FEAT'))
        self.assertEqual(b'keep',ftp.files[b'/USB1/sentinel'])
        self.assertFalse(any(p==S and v in (b'STOR',b'RNFR',b'RNTO',b'DELE',b'RMD') for v,p in ftp.commands))
        json.dumps(r.as_dict())
        return r

    def test_normal_and_empty_independent_observations(self):
        for data in (b'abc',b''):
            with self.subTest(data=data),server(data) as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                r=self.execute(core,ftp,plan)
                self.assertEqual('succeeded',r.state,r.error)
                e=r.result.folder_steps[0]
                self.assertEqual(dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()),e.source_observation)
                self.assertEqual(e.source_observation,e.destination_observation)
                self.assertEqual((e.upload,),r.result.uploads)
                self.assertEqual(2,ftp.verbs.count(b'RETR'));self.assertEqual(3,ftp.verbs.count(b'SIZE'))
                self.assertEqual(data,ftp.files[S]);self.assertEqual(data,ftp.files[D])
                self.assertTrue(all(p.startswith(b'/') for v,p in ftp.commands if v in (b'STOR',b'RETR',b'SIZE',b'RNFR',b'RNTO')))

    def test_source_short_overlong_changed_size(self):
        for mode in ('short','overlong','changed'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                if mode=='changed':ftp.transfer_hook=lambda v,p:ftp.files.update({S:b'longer'}) if v==b'RETR' and p==S else None
                else:ftp.readback_data=lambda p,c:(b'a' if mode=='short' else b'longer') if p==S else c
                r=self.execute(core,ftp,plan)
                self.assertEqual('failed',r.state);self.assertNotIn(b'STOR',ftp.verbs)
                self.assertEqual('source-download',r.result.folder_steps[0].phase)

    def test_source_terminal_reply_missing(self):
        with server() as ftp:
            core,_=self.connect(ftp);plan=self.preview(core)
            ftp.transfer_completion=lambda v,p:None
            r=self.execute(core,ftp,plan)
            self.assertEqual('failed',r.state);self.assertNotIn(b'STOR',ftp.verbs)
            self.assertIsNotNone(r.result.folder_steps[0].transport_error)

    def test_destination_readback_and_size_failure(self):
        for mode in ('hash','size'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                if mode=='hash':ftp.readback_data=lambda p,c:b'bad' if p!=S else c
                else:ftp.before_command=lambda v,p:b'502 no\r\n' if v==b'SIZE' and p!=S else None
                r=self.execute(core,ftp,plan)
                self.assertEqual('failed',r.state);self.assertIsNotNone(r.result.partial_upload)
                self.assertNotIn(D,ftp.files);self.assertNotIn(b'RNTO',ftp.verbs)

    def test_stor_refusal_and_lost_completion(self):
        for mode in ('refused','unknown'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                if mode=='refused':ftp.replies[b'STOR']=b'550 PRIVATE\r\n'
                else:
                    ftp.transfer_completion=lambda v,p:None if v==b'STOR' else b'226 Done\r\n'
                r=self.execute(core,ftp,plan)
                self.assertEqual('failed',r.state);self.assertFalse(r.error.retryable)
                self.assertNotIn('PRIVATE',json.dumps(r.as_dict()));self.assertNotIn(b'RNTO',ftp.verbs)
                self.assertEqual(1,len(r.result.uploads))

    def test_publication_unknown_has_no_partial_shortcut(self):
        with server() as ftp:
            core,_=self.connect(ftp);plan=self.preview(core);ftp.after_mutation[b'RNTO']=None
            r=self.execute(core,ftp,plan)
            self.assertEqual('failed',r.state);self.assertEqual('unknown',r.result.folder_steps[0].publication)
            self.assertEqual('location-unknown',r.result.uploads[0].disposition)
            self.assertIsNone(r.result.partial_upload)
            self.assertEqual(1,r.result.details().count('Publication was not confirmed'))

    def test_destination_appears_before_or_during_transfer(self):
        for during in (False,True):
            with self.subTest(during=during),server() as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                if during:ftp.transfer_hook=lambda v,p:ftp.files.update({D:b'keep'}) if v==b'STOR' else None
                else:ftp.files[D]=b'keep'
                r=self.execute(core,ftp,plan)
                self.assertEqual('failed',r.state);self.assertEqual(b'keep',ftp.files[D]);self.assertNotIn(b'RNTO',ftp.verbs)

    def directory_plan(self,core,ftp):
        ftp.directories[b'/USB1/source/folder']=b''
        return self.preview(core,('folder',))

    def test_directory_accept_refuse_unknown(self):
        for mode in ('accept','refuse','unknown'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.directory_plan(core,ftp)
                if mode=='refuse':ftp.replies[b'MKD']=b'550 PRIVATE\r\n'
                if mode=='unknown':ftp.after_mutation[b'MKD']=None
                r=self.execute(core,ftp,plan);e=r.result.folder_steps[0]
                if mode=='accept':
                    self.assertEqual(('folder/',),r.result.completed);self.assertEqual('completed',e.mutation.completed[0]['outcome'])
                else:
                    self.assertEqual('failed',r.state);self.assertFalse(r.error.retryable)
                    self.assertEqual('unknown' if mode=='unknown' else 'rejected',e.mutation.stopped['outcome'])
                    self.assertIsNone(r.result.partial_upload)
                self.assertEqual(1,ftp.verbs.count(b'MKD'))

    def test_directory_source_destination_and_case_changes(self):
        for mode in ('source','destination','case'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.directory_plan(core,ftp)
                if mode=='source':del ftp.directories[b'/USB1/source/folder']
                else:ftp.directories[b'/USB1/dest/'+(b'Folder' if mode=='case' else b'folder')]=b''
                r=self.execute(core,ftp,plan)
                self.assertEqual('failed',r.state);self.assertNotIn(b'MKD',ftp.verbs)

    def test_checked_destination_ancestor_change_stops_child(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.directories[b'/USB1/source/folder']=b''
            ftp.files[b'/USB1/source/folder/a']=b'abc'
            plan=self.preview(core,('folder',))

            changed=[False]
            def hook(verb,path):
                if not changed[0] and verb==b'MKD' and path==b'/USB1/dest/folder':
                    changed[0]=True
                    ftp.directories.pop(b'/USB1/dest/folder',None)
                    ftp.files[b'/USB1/dest/folder']=b'changed'

            ftp.mutation_hook=hook
            result=self.execute(core,ftp,plan,connections=2)

            self.assertEqual('failed',result.state)
            self.assertEqual(('folder/',),result.result.completed)
            self.assertEqual(('folder/a',),result.result.remaining)
            self.assertNotIn(b'/USB1/dest/folder/a',ftp.files)

    def test_directory_merge_no_mutation(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.directories[b'/USB1/dest/folder']=b''
            plan=self.directory_plan(core,ftp);r=self.execute(core,ftp,plan,connections=3)
            self.assertEqual('succeeded',r.state);self.assertNotIn(b'MKD',ftp.verbs)
            self.assertEqual((),r.result.folder_steps)

    def test_stale_plan_no_wire(self):
        with server() as ftp:
            core,_=self.connect(ftp);plan=self.directory_plan(core,ftp);core._session_id='changed'
            r=self.execute(core,ftp,plan,connections=0)
            self.assertEqual('failed',r.state)

    def test_missing_adapter_fails_closed(self):
        step=Step('a','/USB1/source/a','/USB1/dest/a',False)
        with patch('ftplib.FTP',side_effect=AssertionError('raw')):
            with self.assertRaises(FolderStepFailure) as caught:
                execute_managed_step(object(),step,lambda n:None,lambda:None)
        evidence=caught.exception.folder_step_evidence
        self.assertEqual('setup',evidence.phase)
        self.assertEqual('unperformed',evidence.validation)
        self.assertEqual('setup',evidence.error_category)

    def test_nested_files_use_separate_steps_and_leases(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.directories[b'/USB1/source/folder']=b''
            ftp.files[b'/USB1/source/folder/a']=b'abc';ftp.files[b'/USB1/source/folder/b']=b'def'
            plan=self.preview(core,('folder',));r=self.execute(core,ftp,plan,connections=3)
            self.assertEqual('succeeded',r.state,r.error);self.assertEqual(3,ftp.verbs.count(b'USER'))
            self.assertEqual(('folder/','folder/a','folder/b'),r.result.completed)

    def test_inner_cleanup_preserves_source_failure_and_cancel(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel),server() as ftp:
                core,_=self.connect(ftp);ftp.commands.clear()
                if not cancel:ftp.readback_data=lambda p,c:b'a'
                def progress(n):
                    if cancel:raise JobCancelled()
                step=Step('a',S.decode(),D.decode(),False)
                # Only the download staging unlink fails; temporary directory cleanup remains real.
                import os
                unlink=os.unlink
                def fail(path,*args,**kwargs):
                    if str(path).startswith('/') and Path(path).name.startswith('.c64u-'):raise OSError('PRIVATE')
                    return unlink(path,*args,**kwargs)
                with patch('c64u_browser.transfers.os.unlink',side_effect=fail):
                    with self.assertRaises((FolderStepFailure,JobCancelled)) as caught:
                        execute_managed_step(core._client,step,progress,lambda:None)
                e=caught.exception.folder_step_evidence
                self.assertEqual(cancel,bool(getattr(caught.exception,'cancelled',False)))
                self.assertTrue(e.local_cleanup);self.assertIsNotNone(e.transport_error)
                self.assertNotIn(b'STOR',ftp.verbs);self.assertNotIn('PRIVATE',str(caught.exception))

    def test_outer_cleanup_preserves_all_primary_outcomes(self):
        for mode in ('source','upload','cancel','success'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);plan=self.preview(core)
                if mode=='source':ftp.readback_data=lambda p,c:b'a'
                if mode=='upload':ftp.after_mutation[b'RNTO']=None
                actual=tempfile.TemporaryDirectory
                class BadCleanup:
                    def __init__(self,**kw):self.inner=actual(**kw);self.name=self.inner.name
                    def cleanup(self):self.inner.cleanup();raise OSError('PRIVATE')
                if mode=='cancel':
                    def stopped(*a,**kw):raise JobCancelled()
                    download_patch=patch('c64u_browser.folder_steps.download',side_effect=stopped)
                else:
                    from contextlib import nullcontext
                    download_patch=nullcontext()
                with patch('c64u_browser.folder_steps.tempfile.TemporaryDirectory',BadCleanup),download_patch:
                    r=self.execute(core,ftp,plan)
                e=r.result.folder_steps[0]
                self.assertEqual('cancelled' if mode=='cancel' else 'failed',r.state)
                self.assertTrue(e.local_cleanup);self.assertEqual((),r.result.completed)
                self.assertNotIn('PRIVATE',json.dumps(r.as_dict()))
                if mode=='upload':self.assertEqual('unknown',e.publication)
                if mode=='success':
                    self.assertEqual('completed',e.publication);self.assertIsNone(r.result.partial_upload)
                    self.assertIn('must not be replayed',r.result.details())

    def test_local_publication_conflict_stops_upload(self):
        with server() as ftp:
            core,_=self.connect(ftp);plan=self.preview(core)
            from c64u_browser.platform_support import publish_new
            def race(src,dst):Path(dst).write_bytes(b'other');return publish_new(src,dst)
            with patch('c64u_browser.transfers.publish_new',side_effect=race):r=self.execute(core,ftp,plan)
            self.assertEqual('failed',r.state);self.assertNotIn(b'STOR',ftp.verbs)

    def test_late_mkdir_and_publication_cancel_keep_prefix(self):
        for directory in (False,True):
            with self.subTest(directory=directory),server() as ftp:
                core,_=self.connect(ftp);cancelled=[False]
                ftp.mutation_hook=lambda v,p:cancelled.__setitem__(0,True)
                def check():
                    if cancelled[0]:raise JobCancelled()
                def progress(n):check()
                progress.check=check
                if directory:
                    ftp.directories[b'/USB1/source/folder']=b''
                    steps=[Step('folder','/USB1/source/folder','/USB1/dest/folder',True)]
                else:steps=[Step('a',S.decode(),D.decode(),False)]
                steps.append(Step('later',S.decode(),'/USB1/dest/later',False))
                report=execute_plan(core._client,Plan(steps=steps),False,False,progress,managed_folders=True)
                self.assertTrue(report.cancelled);self.assertEqual(1,len(report.completed));self.assertEqual(['later'],report.remaining)
                cancelled[0]=False;ftp.mutation_hook=None
                self.assertEqual('/USB1',core._client.list_directory('/USB1')[0])

    def test_cancel_before_and_during_source_or_upload(self):
        for phase in ('before','source','upload','verify'):
            with self.subTest(phase=phase),server() as ftp:
                core,_=self.connect(ftp);cancel=[phase=='before']
                def check():
                    if cancel[0]:raise JobCancelled()
                def progress(n):check()
                progress.check=check
                def hook(v,p):
                    if ((phase=='source' and v==b'RETR' and p==S) or
                        (phase=='upload' and v==b'STOR') or
                        (phase=='verify' and v==b'RETR' and p!=S)):cancel[0]=True
                ftp.transfer_hook=hook
                report=execute_plan(core._client,Plan(steps=[Step('a',S.decode(),D.decode(),False)]),False,False,progress,managed_folders=True)
                self.assertTrue(report.cancelled);self.assertFalse(report.completed);self.assertNotIn(D,ftp.files)
                self.assertEqual(0,core._ftp_manager.active_count)

    def test_usb_restore_missing_directory_uses_managed_mkdir(self):
        with server() as ftp:
            core,_=self.connect(ftp)

            ftp.directories[b'/USB1/source/folder']=b''
            ftp.files[b'/USB1/source/folder/a']=b'backup-data'

            temporary=tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            backup=Path(temporary.name)/'backup'

            preview=core.usb.prepare_backup(
                BackupRequest(
                    FileLocation.c64u('/USB1'),
                    ('/USB1/source/folder/a',),
                    FileLocation.core_host(backup),
                )
            ).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)

            saved=core.usb.execute_backup(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',saved.state,saved.error)

            ftp.files.pop(b'/USB1/source/folder/a')
            ftp.directories.pop(b'/USB1/source/folder')

            restore=core.usb.prepare_restore(
                FileLocation.core_host(backup),
                FileLocation.c64u('/USB1'),
            ).wait(5)
            self.assertEqual('succeeded',restore.state,restore.error)

            before=ftp.connections
            epoch=core.device_session()
            ftp.commands.clear()

            with patch('ftplib.FTP',side_effect=AssertionError('raw fallback')):
                result=core.usb.execute_restore(restore.result.plan_id).wait(5)

            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(
                b'backup-data',
                ftp.files[b'/USB1/source/folder/a'],
            )
            self.assertTrue(result.result.folder_steps)
            self.assertEqual(
                'mkdir',
                result.result.folder_steps[0].operation,
            )
            self.assertTrue(
                any(
                    verb==b'MKD' and path==b'/USB1/source/folder'
                    for verb,path in ftp.commands
                )
            )
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(epoch,core.device_session())

            connections=ftp.connections-before
            self.assertEqual(connections,ftp.verbs.count(b'USER'))
            self.assertEqual(connections,ftp.verbs.count(b'FEAT'))
