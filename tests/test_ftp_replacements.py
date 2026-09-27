"""3D composite replacement: loopback sockets and real Core, never devices."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import uuid
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.api import BrowserError
from c64u_browser.file_service import CopyRequest, FileLocation
from c64u_browser.folder_copy import Step, Plan, execute_plan
from c64u_browser.ftp_reads import adapter_for, end_read_attempt
from c64u_browser.jobs import JobCancelled
from c64u_browser.managed_replacement import replace_managed, ReplacementFailure
from c64u_browser.usb_backup import BackupRequest

F=b'/USB1/a'

def server(old=b'old'):
    return FakeC64UFtp(directories={b'/':b'',b'/USB1':b'',b'/USB1/source':b''},
        files={F:old,b'/USB1/sentinel':b'keep',b'/USB1/source/a':b'new'},mutation_tree=True)


class ReplacementTests(unittest.TestCase):
    core=reads.ReadMigrationTests.core
    connect=reads.ReadMigrationTests.connect

    def source(self, data=b'new'):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=Path(temp.name)/'a';path.write_bytes(data);return path

    def run_replace(self, core, ftp, *, source=None, progress=None, signature=None, fail=False):
        path=source or self.source();local=isinstance(path,Path)
        step=Step('a',path,'/USB1/a',False,True,signature or ('a',len(ftp.files[F])))
        before=ftp.connections;epoch=core.device_session();ftp.commands.clear()
        with patch('ftplib.FTP',side_effect=AssertionError('raw FTP')):
            if fail:
                with self.assertRaises((ReplacementFailure,JobCancelled)) as caught:
                    replace_managed(core._client,step,local,progress or (lambda n:None))
                result=caught.exception
            else:result=replace_managed(core._client,step,local,progress or (lambda n:None))
        self.assertEqual(0,core._ftp_manager.active_count)
        self.assertEqual(epoch,core.device_session())
        self.assertLessEqual(ftp.connections-before,1)
        self.assertEqual(b'keep',ftp.files[b'/USB1/sentinel'])
        if ftp.connections>before:
            self.assertEqual(1,ftp.verbs.count(b'USER'));self.assertEqual(1,ftp.verbs.count(b'FEAT'))
        return result

    def test_full_sequence_one_lease_independent_observations(self):
        with server() as ftp:
            core,_=self.connect(ftp);e=self.run_replace(core,ftp)
            self.assertEqual('completed',e.publication);self.assertEqual('completed',e.cleanup)
            self.assertEqual(('mkdir','first_rename','publication_rename','backup_delete','directory_remove'),e.acknowledged)
            self.assertEqual(2,sum(v==b'RETR' and p==F for v,p in ftp.commands))
            self.assertEqual(5,ftp.verbs.count(b'SIZE'));self.assertEqual(3,ftp.verbs.count(b'RETR'))
            self.assertEqual(3,ftp.verbs.count(b'RNTO'));self.assertEqual('published',e.upload.disposition)
            self.assertEqual(b'new',ftp.files[F]);self.assertNotIn(e.backup.encode(),ftp.files)
            self.assertNotIn(e.directory.encode(),ftp.directories)

    def test_empty_original_and_source(self):
        with server(b'') as ftp:
            core,_=self.connect(ftp);e=self.run_replace(core,ftp,source=self.source(b''))
            self.assertEqual(0,e.original_before['bytes']);self.assertEqual(0,e.upload.stor['transferred'])
            self.assertEqual(b'',ftp.files[F])

    def test_stale_signature_before_mkdir(self):
        with server() as ftp:
            core,_=self.connect(ftp);e=self.run_replace(core,ftp,signature=('a',9),fail=True).replacement_evidence
            self.assertEqual('preflight',e.stopped);self.assertNotIn(b'MKD',ftp.verbs)

    def test_same_size_original_change_during_staging(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.transfer_hook=lambda verb,path:ftp.files.update({F:b'bad'}) if verb==b'STOR' else None
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('failed',e.protection);self.assertIsNone(e.first_rename)
            self.assertNotEqual(e.original_before,e.original_after)

    def test_original_size_unavailable_or_malformed(self):
        for reply in (b'502 no\r\n',b'213 invalid\r\n'):
            with self.subTest(reply=reply),server() as ftp:
                core,_=self.connect(ftp);ftp.before_command=lambda v,p:reply if v==b'SIZE' and p==F else None
                e=self.run_replace(core,ftp,fail=True).replacement_evidence
                self.assertEqual('original-before',e.stopped);self.assertNotIn(b'STOR',ftp.verbs)

    def test_original_short_or_overlong(self):
        for data in (b'o',b'older'):
            with self.subTest(data=data),server() as ftp:
                core,_=self.connect(ftp);ftp.readback_data=lambda p,c:data if p==F else c
                e=self.run_replace(core,ftp,fail=True).replacement_evidence
                self.assertEqual('original-before',e.stopped);self.assertIsNone(e.first_rename)

    def test_original_size_changes(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.transfer_hook=lambda v,p:ftp.files.update({F:b'longer'}) if v==b'RETR' and p==F else None
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('original-before',e.stopped);self.assertIsNone(e.first_rename)

    def test_mkdir_refusal_and_lost_reply(self):
        for lost in (False,True):
            with self.subTest(lost=lost),server() as ftp:
                core,_=self.connect(ftp)
                if lost:ftp.after_mutation[b'MKD']=None
                else:ftp.replies[b'MKD']=b'550 SECRET\r\n'
                e=self.run_replace(core,ftp,fail=True).replacement_evidence
                self.assertEqual('unknown' if lost else 'rejected',e.mkdir['outcome'])
                self.assertIsNone(e.original_before);self.assertNotIn(b'RMD',ftp.verbs)

    def test_staging_upload_failure_retains_nested_evidence(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.replies[b'STOR']=b'550 SECRET\r\n'
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('rejected',e.upload.stor['outcome']);self.assertIsNone(e.first_rename)
            self.assertNotIn(b'RMD',ftp.verbs)

    def test_staging_readback_failure(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.readback_data=lambda p,c:b'bad' if b'c64u-part-' in p else c
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('failed',e.upload.readback);self.assertIsNone(e.first_rename)

    def test_nested_staging_publication_unknown_is_not_final_publication(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.after_mutation[b'RNTO']=None
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('not-completed',e.publication);self.assertEqual('location-unknown',e.upload.disposition)
            self.assertEqual((e.upload.staging,e.upload.destination),e.uncertain_paths)
            self.assertEqual(b'old',ftp.files[F]);self.assertIsNone(e.first_rename)

    def test_backup_collision(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            real_uuid=uuid.uuid4;names=iter(('stage','backup'))
            with patch('c64u_browser.managed_replacement.uuid.uuid4',side_effect=lambda:SimpleNamespace(hex=next(names,None) or real_uuid().hex)):
                ftp.files[b'/USB1/c64u-old-backup']=b'keep backup'
                e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('backup-inspection',e.stopped);self.assertIsNone(e.first_rename)

    def exchange_failure(self, field, verb, lost):
        with server() as ftp:
            core,_=self.connect(ftp)
            def target(v,p):
                if field=='first_rename':return v==verb and (p==F if verb==b'RNFR' else b'c64u-old-' in p)
                return v==verb and (b'c64u-replace-' in p and b'c64u-part-' not in p if verb==b'RNFR' else p==F)
            if lost:
                def after(p):return None if target(verb,p) else b'350 Continue\r\n' if verb==b'RNFR' else b'250 Done\r\n'
                ftp.after_mutation[verb]=after
            else:ftp.before_command=lambda v,p:b'550 SECRET refusal\r\n' if target(v,p) else None
            exc=self.run_replace(core,ftp,fail=True);e=exc.replacement_evidence;data=getattr(e,field)
            self.assertFalse(exc.retryable);self.assertEqual(field,e.stopped)
            self.assertEqual(('unknown' if verb==b'RNTO' else 'not-started') if lost else 'rejected',data['outcome'])
            self.assertEqual(verb.decode(),data['stage']);self.assertNotIn(b'DELE',ftp.verbs);self.assertNotIn(b'RMD',ftp.verbs)
            if field=='publication_rename':self.assertEqual('completed',e.first_rename['outcome'])
            if lost and verb==b'RNTO':self.assertEqual(2,len(e.uncertain_paths))
            self.assertEqual('unknown' if field=='publication_rename' and lost and verb==b'RNTO' else 'not-completed',e.publication)

    def test_first_rename_refusal(self):
        for v in (b'RNFR',b'RNTO'):self.exchange_failure('first_rename',v,False)
    def test_first_rnfr_loss(self):self.exchange_failure('first_rename',b'RNFR',True)
    def test_first_rnto_loss(self):self.exchange_failure('first_rename',b'RNTO',True)
    def test_second_rename_refusal(self):
        for v in (b'RNFR',b'RNTO'):self.exchange_failure('publication_rename',v,False)
    def test_second_rnfr_loss(self):self.exchange_failure('publication_rename',b'RNFR',True)
    def test_second_rnto_loss(self):self.exchange_failure('publication_rename',b'RNTO',True)

    def cleanup_failure(self,verb,lost):
        with server() as ftp:
            core,_=self.connect(ftp)
            if lost:ftp.after_mutation[verb]=None
            else:ftp.replies[verb]=b'550 SECRET\r\n'
            exc=self.run_replace(core,ftp,fail=True);e=exc.replacement_evidence
            self.assertEqual('completed',e.publication);self.assertIn('Publication completed; cleanup is incomplete',str(exc))
            self.assertEqual('uncertain' if lost else 'incomplete',e.cleanup)
            self.assertEqual('unknown' if lost else 'rejected',getattr(e,'backup_delete' if verb==b'DELE' else 'directory_remove')['outcome'])
            self.assertEqual(b'new',ftp.files[F]);self.assertEqual(3,ftp.verbs.count(b'RNTO'))
            if verb==b'DELE':self.assertNotIn(b'RMD',ftp.verbs)
            else:self.assertEqual('completed',e.backup_delete['outcome'])
    def test_backup_delete_refused(self):self.cleanup_failure(b'DELE',False)
    def test_backup_delete_lost(self):self.cleanup_failure(b'DELE',True)
    def test_directory_remove_refused(self):self.cleanup_failure(b'RMD',False)
    def test_directory_remove_lost(self):self.cleanup_failure(b'RMD',True)

    def progress(self):
        pending=[False]
        def check():
            if pending[0]:raise JobCancelled()
        def progress(n):check()
        progress.check=check
        return progress,pending

    def test_cancellation_before_and_during_staging_and_original_reads(self):
        for when in ('before','mkdir','stor','first-read','second-read','staged'):
            with self.subTest(when=when),server() as ftp:
                core,_=self.connect(ftp);progress,pending=self.progress();pending[0]=when=='before';reads=[0]
                def transfer(v,p):
                    if v==b'RETR' and p==F:reads[0]+=1
                    if (when=='stor' and v==b'STOR' or when=='first-read' and reads[0]==1 or when=='second-read' and reads[0]==2):pending[0]=True
                def mutation(v,p):
                    if when=='mkdir' and v==b'MKD' or when=='staged' and v==b'RNTO' and b'c64u-replace-' in p:pending[0]=True
                ftp.transfer_hook=transfer;ftp.mutation_hook=mutation
                exc=self.run_replace(core,ftp,progress=progress,fail=True)
                self.assertIsInstance(exc,JobCancelled);self.assertIsNone(exc.replacement_evidence.first_rename)
                self.assertNotIn(b'DELE',ftp.verbs);self.assertNotIn(b'RMD',ftp.verbs)

    def test_final_preexchange_check(self):
        with server() as ftp:
            core,_=self.connect(ftp);progress,pending=self.progress()
            from c64u_browser.managed_replacement import inspect
            def inspected(client,path):
                result=inspect(client,path)
                if 'c64u-old-' in path:pending[0]=True
                return result
            with patch('c64u_browser.managed_replacement.inspect',side_effect=inspected):
                e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertEqual('first_rename',e.stopped);self.assertIsNone(e.first_rename)

    def test_cancellation_deferred_across_exchange_and_cleanup(self):
        for verb,which in ((b'RNFR','first'),(b'RNTO','first'),(b'RNTO','second'),(b'DELE',''),(b'RMD','')):
            with self.subTest(verb=verb,which=which),server() as ftp:
                core,_=self.connect(ftp);progress,pending=self.progress()
                def mutation(v,p):
                    match=(p==F if verb==b'RNFR' or which=='second' else b'c64u-old-' in p) if which else True
                    if v==verb and match:pending[0]=True
                ftp.mutation_hook=mutation
                e=self.run_replace(core,ftp,progress=progress)
                self.assertEqual('completed',e.cleanup);self.assertTrue(pending[0])
                with self.assertRaises(JobCancelled):progress.check()

    def test_pending_cancel_does_not_mask_network_failure(self):
        with server() as ftp:
            core,_=self.connect(ftp);progress,pending=self.progress()
            ftp.mutation_hook=lambda v,p:pending.__setitem__(0,True) if v==b'RNTO' and b'c64u-old-' in p else None
            ftp.after_mutation[b'RNTO']=lambda p:None if p==F else b'250 done\r\n'
            e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertEqual('unknown',e.publication);self.assertNotEqual('cancelled',e.error_category)

    def test_binding_failure_after_first_rename_prevents_second(self):
        with server() as ftp:
            core,_=self.connect(ftp);progress,pending=self.progress();adapter=adapter_for(core._client)
            def hook(v,p):
                if v==b'RNTO' and b'c64u-old-' in p:
                    pending[0]=True;core._ftp_manager.invalidate(adapter.binding.device.physical_id)
            ftp.mutation_hook=hook
            e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertNotEqual('cancelled',e.error_category);self.assertNotIn(b'DELE',ftp.verbs)

    def test_unrelated_check_exception_during_deferral(self):
        with server() as ftp:
            core,_=self.connect(ftp);pending=[False]
            def check():
                if pending[0]:raise ValueError('private callback')
            progress=lambda n:None;progress.check=check
            ftp.mutation_hook=lambda v,p:pending.__setitem__(0,True) if v==b'RNTO' and b'c64u-old-' in p else None
            e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertEqual('completed',e.first_rename['outcome']);self.assertIsNone(e.publication_rename)
            self.assertNotIn(b'DELE',ftp.verbs)

    def test_missing_context_no_fallback(self):
        with patch('ftplib.FTP',side_effect=AssertionError('raw')):
            with self.assertRaises(ReplacementFailure):replace_managed(object(),Step('a',self.source(),'/USB1/a',False,True,('a',3)),True,lambda n:None)

    def test_remote_source_success_and_local_cleanup(self):
        with server() as ftp:
            core,_=self.connect(ftp);paths=[]
            from c64u_browser.managed_replacement import download
            def downloaded(c,s,d,p):paths.append(Path(d).parent);return download(c,s,d,p)
            with patch('c64u_browser.managed_replacement.download',side_effect=downloaded):
                self.run_replace(core,ftp,source='/USB1/source/a')
            self.assertEqual(b'new',ftp.files[b'/USB1/source/a']);self.assertFalse(paths[0].exists())
            self.assertEqual(4,ftp.verbs.count(b'RETR'))

    def test_remote_source_failure_cleans_local_temporary(self):
        with server() as ftp:
            core,_=self.connect(ftp);paths=[]
            from c64u_browser.managed_replacement import download
            def downloaded(c,s,d,p):paths.append(Path(d).parent);return download(c,s,d,p)
            ftp.replies[b'STOR']=b'550 refused\r\n'
            with patch('c64u_browser.managed_replacement.download',side_effect=downloaded):
                self.run_replace(core,ftp,source='/USB1/source/a',fail=True)
            self.assertFalse(paths[0].exists());self.assertEqual(b'old',ftp.files[F])

    def test_file_service_local_and_remote_replacements(self):
        for remote in (False,True):
            with self.subTest(remote=remote),server() as ftp:
                core,_=self.connect(ftp);source=self.source()
                request=CopyRequest(FileLocation.c64u('/USB1/source') if remote else FileLocation.core_host(source.parent),('a',),FileLocation.c64u('/USB1'))
                preview=core.files.prepare_copy(request).wait(5);before=ftp.connections
                with patch('ftplib.FTP',side_effect=AssertionError('raw')):result=core.files.execute_copy(preview.result.plan_id,'replace').wait(5)
                self.assertEqual('succeeded',result.state,result.error);self.assertEqual(('a',),result.result.completed)
                self.assertEqual(1,len(result.result.replacements));self.assertEqual((),result.result.uploads)
                self.assertEqual(1,ftp.connections-before);json.dumps(result.as_dict())

    def test_file_service_cleanup_failure_accounting(self):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source()
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),('a',),FileLocation.c64u('/USB1'))).wait(5)
            ftp.replies[b'DELE']=b'550 SECRET\r\n'
            result=core.files.execute_copy(preview.result.plan_id,'replace').wait(5)
            self.assertEqual('failed',result.state);self.assertFalse(result.error.retryable)
            self.assertEqual(('a',),result.result.remaining);self.assertEqual((),result.result.completed)
            self.assertIsNone(result.result.partial_upload);self.assertEqual('completed',result.result.replacements[0].publication)
            self.assertNotIn('SECRET',json.dumps(result.as_dict()))

    def test_completed_prefix_then_cancel_next_item(self):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source();progress,pending=self.progress()
            ftp.mutation_hook=lambda v,p:pending.__setitem__(0,True) if v==b'RMD' else None
            plan=Plan(steps=[Step('a',source,'/USB1/a',False,True,('a',3)),Step('next',source,'/USB1/next',False)])
            result=execute_plan(core._client,plan,True,False,progress,managed_uploads=True,managed_replacements=True)
            self.assertTrue(result.cancelled);self.assertEqual(['a'],result.completed);self.assertEqual(['next'],result.remaining)
            self.assertEqual('completed',result.replacements[0].publication);self.assertEqual(0,core._ftp_manager.active_count)
            pending[0]=False;self.run_replace(core,ftp)

    def test_failed_enclosing_operation_never_reopens(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=adapter_for(core._client);ftp.replies[b'DELE']=b'550 refused\r\n'
            with adapter.operation():
                with self.assertRaises(ReplacementFailure):replace_managed(core._client,Step('a',self.source(),'/USB1/a',False,True,('a',3)),True,lambda n:None)
                before=ftp.connections
                with self.assertRaises(BrowserError):end_read_attempt(core._client)
                with self.assertRaises(BrowserError):adapter.size('/USB1/a')
                self.assertEqual(before,ftp.connections)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_usb_restore_replacement_and_skip(self):
        with server() as ftp:
            core,_=self.connect(ftp);folder=self.source().parent/'backup'
            preview=core.usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB1'),('/USB1/a',),FileLocation.core_host(folder))).wait(5)
            backup=core.usb.execute_backup(preview.result.plan_id).wait(5);self.assertEqual('succeeded',backup.state,backup.error)
            ftp.files[F]=b'NEW'
            def review():return core.usb.prepare_restore(FileLocation.core_host(folder),FileLocation.c64u('/USB1')).wait(5).result
            plan=review();self.assertEqual(('a',),plan.replacements)
            skipped=core.usb.execute_restore(plan.plan_id).wait(5);self.assertEqual(('a',),skipped.result.skipped)
            plan=review()
            with patch('ftplib.FTP',side_effect=AssertionError('raw')):result=core.usb.execute_restore(plan.plan_id,replace=True).wait(5)
            self.assertEqual('succeeded',result.state,result.error);self.assertEqual(('a',),result.result.replaced)
            self.assertEqual('completed',result.result.replacements[0].publication);self.assertEqual(b'old',ftp.files[F])
            self.assertEqual(b'keep',ftp.files[b'/USB1/sentinel']);self.assertEqual(0,core._ftp_manager.active_count)

    def test_stale_binding_before_any_wire_access(self):
        with server() as ftp:
            core,profile=self.connect(ftp);old=core._client;source=self.source()
            core.disconnect();core.connect(profile,remote_folder='/USB1');before=ftp.connections
            with self.assertRaises(ReplacementFailure) as caught:
                replace_managed(old,Step('a',source,'/USB1/a',False,True,('a',3)),True,lambda n:None)
            self.assertEqual('stale-session',caught.exception.replacement_evidence.error_category)
            self.assertEqual(before,ftp.connections)

    def test_not_submitted_exchange_steps_keep_acknowledged_prefix(self):
        for target in ('first','second'):
            with self.subTest(target=target),server() as ftp:
                core,_=self.connect(ftp);adapter=adapter_for(core._client);real=adapter.mutate
                def mutate(verb,path,destination=None):
                    # Raise before adapter dispatch, after earlier acknowledged steps.
                    if verb=='rename' and (path=='/USB1/a' if target=='first' else destination=='/USB1/a'):
                        raise BrowserError('validation failure before submission')
                    return real(verb,path,destination)
                with patch.object(adapter,'mutate',side_effect=mutate):
                    e=self.run_replace(core,ftp,fail=True).replacement_evidence
                self.assertIsNone(e.first_rename if target=='first' else e.publication_rename)
                if target=='second':self.assertEqual('completed',e.first_rename['outcome'])
                self.assertNotIn(b'DELE',ftp.verbs)

    def test_pending_cancellation_and_recovery_after_acknowledged_first_rename(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=adapter_for(core._client);real=adapter.mutate;progress,pending=self.progress()
            def mutate(verb,path,destination=None):
                result=real(verb,path,destination)
                if verb=='rename' and path=='/USB1/a':
                    pending[0]=True;core._ftp_manager.invalidate(adapter.binding.device.physical_id,recovering=True)
                return result
            with patch.object(adapter,'mutate',side_effect=mutate):
                e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertEqual('completed',e.first_rename['outcome']);self.assertIsNone(e.publication_rename)
            self.assertEqual('device-recovering',e.error_category);self.assertNotIn(b'DELE',ftp.verbs)

    def test_pending_cancel_and_protocol_error_preserve_publication(self):
        with server() as ftp:
            core,_=self.connect(ftp);progress,pending=self.progress()
            ftp.mutation_hook=lambda v,p:pending.__setitem__(0,True) if v==b'RNTO' and p==F else None
            ftp.replies[b'DELE']=b'not FTP\r\n'
            e=self.run_replace(core,ftp,progress=progress,fail=True).replacement_evidence
            self.assertEqual('completed',e.publication);self.assertEqual('uncertain',e.cleanup)
            self.assertEqual('unknown',e.backup_delete['outcome']);self.assertNotEqual('cancelled',e.error_category)

    def test_cancel_during_stor_callback_keeps_nested_evidence_without_cleanup_shortcut(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def progress(n):raise JobCancelled()
            exc=self.run_replace(core,ftp,source=self.source(b'x'*65536),progress=progress,fail=True)
            self.assertIsInstance(exc,JobCancelled);self.assertIsNotNone(exc.replacement_evidence.upload)
            self.assertIsNone(exc.partial_path);self.assertIsNone(exc.replacement_evidence.first_rename)
            self.assertNotIn(b'DELE',ftp.verbs)

    def test_cancel_while_original_data_is_read(self):
        with server() as ftp:
            core,_=self.connect(ftp);progress,pending=self.progress()
            def data(path,content):
                if path==F:pending[0]=True
                return content
            ftp.readback_data=data
            exc=self.run_replace(core,ftp,progress=progress,fail=True)
            self.assertIsInstance(exc,JobCancelled);self.assertIsNone(exc.replacement_evidence.original_before)
            self.assertNotIn(b'STOR',ftp.verbs)

    def test_second_original_observation_rejects_short_transfer(self):
        with server() as ftp:
            core,_=self.connect(ftp);count=[0]
            def data(path,content):
                if path==F:count[0]+=1
                return content[:1] if path==F and count[0]==2 else content
            ftp.readback_data=data
            e=self.run_replace(core,ftp,fail=True).replacement_evidence
            self.assertEqual('original-after',e.stopped);self.assertIsNotNone(e.original_before)
            self.assertEqual('published',e.upload.disposition);self.assertIsNone(e.first_rename)

    def test_generic_review_does_not_bind_same_size_preexecution_content(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.files[F]=b'NEW'
            e=self.run_replace(core,ftp,signature=('a',3))
            self.assertEqual(hashlib.sha256(b'NEW').hexdigest(),e.original_before['sha256'])
            self.assertEqual('completed',e.publication)

    def test_usb_stale_content_review_and_cleanup_failure_evidence(self):
        with server() as ftp:
            core,_=self.connect(ftp);folder=self.source().parent/'backup'
            preview=core.usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB1'),('/USB1/a',),FileLocation.core_host(folder))).wait(5)
            self.assertEqual('succeeded',core.usb.execute_backup(preview.result.plan_id).wait(5).state)
            ftp.files[F]=b'NEW'
            def review():return core.usb.prepare_restore(FileLocation.core_host(folder),FileLocation.c64u('/USB1')).wait(5).result
            plan=review();ftp.files[F]=b'BAD'
            result=core.usb.execute_restore(plan.plan_id,replace=True).wait(5)
            self.assertEqual('failed',result.state);self.assertEqual('changed',result.error.code)
            plan=review();ftp.replies[b'DELE']=b'550 refused\r\n'
            result=core.usb.execute_restore(plan.plan_id,replace=True).wait(5)
            self.assertEqual('failed',result.state);self.assertEqual((),result.result.replaced)
            self.assertEqual(('a',),result.result.remaining);self.assertIsNone(result.result.partial_upload)
            self.assertEqual('completed',result.result.replacements[0].publication)
            self.assertFalse(result.error.retryable);self.assertEqual(b'old',ftp.files[F])

    def test_deferred_routes_remain_explicit(self):
        import ast
        for module in ('replacement','file_copy','c64_ai_install','native_files','__main__'):
            tree=ast.parse(Path('c64u_browser/'+module+'.py').read_text())
            self.assertFalse(any(isinstance(n,ast.Name) and n.id=='replace_managed' for n in ast.walk(tree)))
        source=self.source()
        for local,signature in ((True,('a',3)),(False,None)):
            with patch('c64u_browser.folder_copy.kind',side_effect=['file','file' if local else None]),patch('c64u_browser.folder_copy.copy_files',return_value=('Copied 1 file(s): a',None)) as copy,patch('c64u_browser.folder_copy.replace_managed',side_effect=AssertionError('deferred')) as managed,patch('c64u_browser.folder_copy.replace_file') as legacy:
                plan=Plan(steps=[Step('a',source,'/USB1/a',False,True,signature)])
                execute_plan(object(),plan,False,local,managed_replacements=True)
                managed.assert_not_called()
                if local:legacy.assert_called_once()
                else:copy.assert_called_once()

    def test_core_job_late_cancel_success_and_batch_prefix(self):
        from c64u_browser.jobs import _CURRENT_CHECK
        for batch in (False,True):
            with self.subTest(batch=batch),server() as ftp:
                core,_=self.connect(ftp);source=self.source();(source.parent/'b').write_bytes(b'next')
                ftp.files[b'/USB1/b']=b'previous'
                names=('a','b') if batch else ('a',)
                request=CopyRequest(FileLocation.core_host(source.parent),names,FileLocation.c64u('/USB1'))
                preview=core.files.prepare_copy(request).wait(5)
                def diagnostic(event):
                    if event['kind']=='mutation-complete' and event['mutation']['operation']=='RMD':
                        _CURRENT_CHECK.get().__self__.request_cancel()
                core._ftp_manager._diagnostic=diagnostic
                result=core.files.execute_copy(preview.result.plan_id,'replace').wait(5)
                self.assertEqual('cancelled' if batch else 'succeeded',result.state,result.error)
                self.assertEqual(('a',),result.result.completed)
                self.assertEqual(('b',) if batch else (),result.result.remaining)
                self.assertEqual('completed',result.result.replacements[0].publication)
                core._ftp_manager._diagnostic=None
                fresh=core.files.prepare_copy(replace(request,names=('b',))).wait(5)
                self.assertEqual('succeeded',core.files.execute_copy(fresh.result.plan_id,'replace').wait(5).state)

    def test_remote_source_cancellation_cleans_local_temporary(self):
        with server() as ftp:
            core,_=self.connect(ftp);paths=[]
            from c64u_browser.managed_replacement import download
            def downloaded(c,s,d,p):paths.append(Path(d).parent);return download(c,s,d,p)
            def progress(n):raise JobCancelled()
            with patch('c64u_browser.managed_replacement.download',side_effect=downloaded):
                exc=self.run_replace(core,ftp,source='/USB1/source/a',progress=progress,fail=True)
            self.assertIsInstance(exc,JobCancelled);self.assertFalse(paths[0].exists())
            self.assertNotIn(b'STOR',ftp.verbs);self.assertEqual(b'old',ftp.files[F])

if __name__=='__main__':unittest.main()
