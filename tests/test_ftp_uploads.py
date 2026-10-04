"""3C staged additions: real loopback transport and Core jobs, never devices."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.api import BrowserError
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.transfers import upload_managed, UploadFailure
from c64u_browser.file_service import CopyRequest, FileLocation
from c64u_browser.jobs import JobCancelled
from c64u_browser.usb_backup import BackupRequest


def server(**kwargs):
    return FakeC64UFtp(directories={b'/': b'', b'/USB1': b'', b'/USB1/other': b''},
                      files={b'/USB1/existing': b'old'}, mutation_tree=True, **kwargs)


class UploadTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core
    connect = reads.ReadMigrationTests.connect

    def source(self, data=b'abc'):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path = Path(temp.name)/'new';path.write_bytes(data)
        return path

    def failure(self, core, path, progress=lambda n:None):
        with self.assertRaises((UploadFailure, JobCancelled)) as caught:
            upload_managed(core._client, path, '/USB1', progress)
        self.assertEqual(0, core._ftp_manager.active_count)
        return caught.exception

    def _refused_upload_command(self, verb):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source();events=[]
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),
                ('new',),FileLocation.c64u('/USB1'))).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)
            def diagnostic(event):
                events.append(event)
                if event['operation']=='STOR' and event['kind']=='command' and event['verb']==verb:
                    ftp.replies[verb.encode()]=b'550 SECRET refusal\r\n'
            core._ftp_manager._diagnostic=diagnostic
            before=ftp.connections
            with patch('ftplib.FTP',side_effect=AssertionError('legacy fallback')):
                result=core.files.execute_copy(preview.result.plan_id).wait(5)
            self.assertEqual('failed',result.state);self.assertFalse(result.error.retryable)
            self.assertIsNone(result.result.partial_path);self.assertIsNone(result.result.partial_upload)
            evidence=result.result.uploads[0];stor=evidence.stor;error=evidence.transport_error
            submitted=verb=='STOR'
            self.assertEqual(submitted,stor['submitted'])
            self.assertEqual('rejected' if submitted else 'not-started',stor['outcome'])
            self.assertEqual(550 if submitted else None,stor['preliminary_reply'])
            self.assertIsNone(stor['terminal_reply']);self.assertEqual(0,stor['transferred'])
            self.assertIsNone(stor['sha256'])
            self.assertEqual('no-candidate' if submitted else 'not-started',evidence.disposition)
            self.assertEqual('preliminary-reply' if submitted else 'stor-'+verb.lower(),error['phase'])
            self.assertEqual('rejected',error['outcome']);self.assertEqual(550,error['reply_code'])
            self.assertEqual('stor-failed' if submitted else 'protocol-error',error['code'])
            self.assertNotIn('SECRET',json.dumps(result.as_dict()))
            self.assertEqual(int(submitted),ftp.verbs.count(b'STOR'))
            self.assertFalse(set(ftp.verbs)&{b'RNFR',b'RNTO',b'DELE',b'RETR'})
            self.assertFalse(any(b'c64u-part-' in path for path in ftp.files))
            self.assertEqual(1,ftp.connections-before);self.assertEqual(0,core._ftp_manager.active_count)
            commands=[e['verb'] for e in events if e['kind']=='command' and e['operation']=='STOR']
            self.assertEqual(1,commands.count(verb))
            self.assertTrue(any(e['kind']=='lifecycle' and e['state']=='failed' for e in events))
            self.assertTrue(any(e['kind']=='lifecycle' and e['state']=='disconnected' for e in events))

    def test_type_refusal_keeps_stor_not_started(self):
        self._refused_upload_command('TYPE')

    def test_pasv_refusal_keeps_stor_not_started(self):
        self._refused_upload_command('PASV')

    def test_actual_stor_refusal_remains_rejected(self):
        self._refused_upload_command('STOR')

    def test_data_connect_failure_keeps_stor_not_started(self):
        with server() as ftp:
            core,_=self.connect(ftp);pending=[False];original=socket.socket
            def diagnostic(event):
                if event['operation']=='STOR' and event['kind']=='command' and event['verb']=='PASV':
                    pending[0]=True
            core._ftp_manager._diagnostic=diagnostic
            class DataTimeout(original):
                def connect(sock,address):
                    if pending[0] and address[1] in ftp.pasv_ports:raise TimeoutError()
                    return super().connect(address)
            with patch('socket.socket',DataTimeout):exc=self.failure(core,self.source())
            e=exc.upload_evidence
            self.assertFalse(e.stor['submitted']);self.assertEqual('not-started',e.stor['outcome'])
            self.assertEqual(0,e.stor['transferred']);self.assertIsNone(e.stor['preliminary_reply'])
            self.assertIsNone(e.stor['terminal_reply']);self.assertIsNone(exc.partial_path)
            self.assertEqual('data-connect',e.transport_error['phase'])
            self.assertEqual('data-connect-timeout',e.transport_error['code'])
            self.assertNotIn(b'STOR',ftp.verbs);self.assertNotIn(b'RNFR',ftp.verbs)

    def test_upload_verification_retr_terminal_loss_keeps_staging_candidate(self):
        with server() as ftp:
            core,_=self.connect(ftp);events=[]
            core._ftp_manager._diagnostic=events.append
            ftp.transfer_completion=lambda verb,path:None if verb==b'RETR' else b'226 Done\r\n'
            exc=self.failure(core,self.source());e=exc.upload_evidence
            self.assertEqual('completed',e.stor['outcome']);self.assertEqual(226,e.stor['terminal_reply'])
            self.assertEqual(3,e.stor['transferred'])
            self.assertEqual(hashlib.sha256(b'abc').hexdigest(),e.stor['sha256'])
            self.assertEqual('readback',e.phase);self.assertEqual('failed',e.readback)
            self.assertEqual('completion-unknown',e.error_code)
            self.assertEqual('completion',e.transport_error['phase'])
            self.assertEqual('unknown',e.transport_error['outcome'])
            self.assertEqual(3,e.transport_error['transferred'])
            self.assertEqual('staging-candidate',e.disposition);self.assertEqual(e.staging,exc.partial_path)
            self.assertEqual(b'abc',ftp.files[e.staging.encode()])
            self.assertEqual(1,ftp.verbs.count(b'STOR'));self.assertEqual(1,ftp.verbs.count(b'RETR'))
            self.assertFalse(set(ftp.verbs)&{b'SIZE',b'RNFR',b'RNTO',b'DELE',b'ABOR'})
            self.assertTrue(any(event['kind']=='error' and event['operation']=='RETR' for event in events))

    def test_exact_and_empty_one_lease_sequence_epoch_and_hash(self):
        for payload in (b'', b'a'*20000):
            with self.subTest(size=len(payload)),server() as ftp:
                core,_=self.connect(ftp);epoch=core.device_session();start=ftp.connections
                ftp.commands.clear()
                with patch('ftplib.FTP',side_effect=AssertionError('legacy upload')):
                    result=upload_managed(core._client,self.source(payload),'/USB1')
                self.assertEqual(payload,ftp.files[b'/USB1/new'])
                self.assertEqual(hashlib.sha256(payload).hexdigest(),result['sha256'])
                self.assertEqual(len(payload),result['bytes']);self.assertTrue(result['verified'])
                self.assertEqual('published',result['upload'].disposition)
                self.assertEqual('exact',result['upload'].stor['length_status'])
                self.assertEqual(1,ftp.connections-start)
                self.assertEqual(1,ftp.verbs.count(b'USER'));self.assertEqual(1,ftp.verbs.count(b'FEAT'))
                self.assertEqual([b'MLSD',b'MLSD',b'STOR',b'RETR',b'SIZE',b'MLSD',b'RNFR',b'RNTO'],
                    [v for v in ftp.verbs if v in (b'MLSD',b'STOR',b'RETR',b'SIZE',b'RNFR',b'RNTO')])
                self.assertEqual(0,core._ftp_manager.active_count);self.assertEqual(epoch,core.device_session())
                self.assertFalse(any(b'c64u-part-' in p for p in ftp.files))

    def test_descriptor_is_opened_once_and_measured_descriptor_is_transferred(self):
        with server() as ftp:
            core,_=self.connect(ftp);path=self.source();opened=[];measured=[];fds=[]
            original=Path.open
            import os
            fstat=os.fstat
            def opening(p,*args,**kwargs):
                stream=original(p,*args,**kwargs)
                if p==path:opened.append(stream);fds.append(stream.fileno())
                return stream
            def sizing(fd):measured.append(fd);return fstat(fd)
            adapter=adapter_for(core._client);write=adapter.write_from
            def writing(remote,stream,*args,**kwargs):
                self.assertIs(stream,opened[0]);self.assertEqual(measured,[stream.fileno()])
                return write(remote,stream,*args,**kwargs)
            with patch.object(Path,'open',opening),patch('c64u_browser.transfers.os.fstat',side_effect=sizing),patch.object(adapter,'write_from',side_effect=writing):
                result=upload_managed(core._client,path,'/USB1')
            self.assertEqual(1,len(opened));self.assertEqual(1,len(measured))
            self.assertEqual(fds,measured);self.assertTrue(opened[0].closed);self.assertEqual(3,result['bytes'])

    def test_short_and_overlong_sources_keep_distinct_stor_evidence(self):
        for expected,status in ((4,'short'),(2,'overlong')):
            with self.subTest(status=status),server() as ftp:
                core,_=self.connect(ftp)
                from types import SimpleNamespace
                with patch('c64u_browser.transfers.os.fstat',return_value=SimpleNamespace(st_size=expected)):
                    exc=self.failure(core,self.source())
                evidence=exc.upload_evidence;stor=evidence.stor
                self.assertEqual(status,stor['length_status']);self.assertEqual(expected,stor['expected_bytes'])
                self.assertEqual('source-length',evidence.error_category)
                self.assertEqual('staging-candidate',evidence.disposition)
                self.assertEqual(226 if status=='short' else None,stor['terminal_reply'])
                self.assertEqual('completed' if status=='short' else 'unknown',stor['outcome'])
                self.assertEqual(3 if status=='short' else 0,stor['transferred'])
                self.assertNotIn(b'RETR',ftp.verbs);self.assertNotIn(b'RNFR',ftp.verbs)

    def test_source_changes_same_length_are_not_a_snapshot_contract(self):
        with server() as ftp:
            core,_=self.connect(ftp);path=self.source()
            adapter=adapter_for(core._client);write=adapter.write_from
            def changed(*args,**kwargs):
                path.write_bytes(b'new')
                return write(*args,**kwargs)
            with patch.object(adapter,'write_from',side_effect=changed):
                result=upload_managed(core._client,path,'/USB1')
            self.assertEqual(b'new',ftp.files[b'/USB1/new'])
            self.assertEqual(hashlib.sha256(b'new').hexdigest(),result['sha256'])

    def test_preflight_collisions_and_missing_source_never_claim_partial(self):
        for mode in ('destination','temporary','source'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);path=self.source()
                if mode=='destination':ftp.files[b'/USB1/NEW']=b'existing'
                if mode=='source':path.unlink()
                from types import SimpleNamespace
                with patch('c64u_browser.transfers.uuid.uuid4',return_value=SimpleNamespace(hex='fixed')):
                    if mode=='temporary':ftp.files[b'/USB1/c64u-part-fixed']=b'other'
                    exc=self.failure(core,path)
                self.assertIsNone(exc.partial_path);self.assertNotIn(b'STOR',ftp.verbs)

    def test_cancel_before_source_and_after_pasv_has_no_partial(self):
        for early in (True,False):
            with self.subTest(early=early),server() as ftp:
                core,_=self.connect(ftp);pending=[early]
                def check():
                    if pending[0]:raise JobCancelled()
                def progress(_):pass
                progress.check=check
                original=socket.socket
                class CancelSocket(original):
                    def connect(sock,address):
                        result=super().connect(address)
                        if address[1] in ftp.pasv_ports and b'PASV' in ftp.verbs and ftp.verbs.count(b'MLSD')>=3:
                            pending[0]=True
                        return result
                with patch('socket.socket',CancelSocket):exc=self.failure(core,self.source(),progress)
                self.assertIsNone(exc.partial_path);self.assertNotIn(b'STOR',ftp.verbs)

    def test_stor_refusal_and_terminal_failures(self):
        for mode in ('preliminary','negative','lost','malformed'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp)
                if mode=='preliminary':ftp.replies[b'STOR']=b'550 SECRET refusal\r\n'
                else:
                    completion={'negative':b'451 SECRET failed\r\n','lost':None,'malformed':b'bad\r\n'}[mode]
                    ftp.transfer_completion=lambda verb,path:completion if verb==b'STOR' else b'226 Done\r\n'
                exc=self.failure(core,self.source());data=exc.upload_evidence.stor
                self.assertTrue(data['submitted']);self.assertNotIn('SECRET',str(exc))
                self.assertEqual('rejected' if mode=='preliminary' else 'unknown',data['outcome'])
                self.assertEqual(None if mode=='preliminary' else exc.upload_evidence.staging,exc.partial_path)
                self.assertNotIn(b'RETR',ftp.verbs);self.assertNotIn(b'DELE',ftp.verbs)
                self.assertEqual(1,ftp.verbs.count(b'STOR'))

    def test_partial_send_failure_counts_only_completed_send_blocks(self):
        with server() as ftp:
            core,_=self.connect(ftp);original=socket.socket;pending=[False]
            class SendSocket(original):
                def sendall(sock,data,*args):
                    if pending[0] and len(data)==8192:
                        super().sendall(data[:17]);raise OSError('SECRET send failure')
                    result=super().sendall(data,*args)
                    if len(data)==8192:pending[0]=True
                    return result
            with patch('socket.socket',SendSocket):exc=self.failure(core,self.source(b'x'*20000))
            self.assertEqual(8192,exc.upload_evidence.stor['transferred'])
            self.assertEqual('unknown',exc.upload_evidence.stor['outcome'])
            self.assertNotIn('SECRET',str(exc));self.assertNotIn(b'RNTO',ftp.verbs)

    def test_progress_cancel_and_arbitrary_callback_failure_retain_partial(self):
        for cancelled in (True,False):
            with self.subTest(cancelled=cancelled),server() as ftp:
                core,_=self.connect(ftp)
                def progress(_):
                    if cancelled:raise JobCancelled()
                    raise ValueError('private callback data')
                exc=self.failure(core,self.source(b'x'*20000),progress)
                self.assertEqual(cancelled,isinstance(exc,JobCancelled))
                self.assertEqual(8192,exc.upload_evidence.stor['transferred'])
                self.assertEqual('staging-candidate',exc.upload_evidence.disposition)
                self.assertNotIn(b'DELE',ftp.verbs)

    def test_binding_failure_with_cancel_pending_remains_failure(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def progress(_):
                core._ftp_manager.invalidate(core.device_session().device_id)
                raise JobCancelled()
            exc=self.failure(core,self.source(),progress)
            self.assertIsInstance(exc,UploadFailure)
            self.assertEqual('stale-session',exc.upload_evidence.error_code)
            self.assertTrue(exc.upload_evidence.stor['submitted'])

    def test_readback_failures_and_bound(self):
        for mode in ('corrupt','short','overlong','refused'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp)
                if mode=='refused':ftp.replies[b'RETR']=b'550 unavailable\r\n'
                else:ftp.readback_data=lambda path,data:{'corrupt':b'xyz','short':b'ab','overlong':b'abcd'}[mode]
                exc=self.failure(core,self.source())
                self.assertEqual('completed',exc.upload_evidence.stor['outcome'])
                self.assertEqual('failed',exc.upload_evidence.readback)
                self.assertEqual('staging-candidate',exc.upload_evidence.disposition)
                self.assertNotIn(b'SIZE',ftp.verbs);self.assertNotIn(b'RNFR',ftp.verbs)

    def test_size_failures_do_not_publish(self):
        for reply in (b'213 4\r\n',b'502 Unsupported\r\n',b'213 garbage\r\n'):
            with self.subTest(reply=reply),server() as ftp:
                core,_=self.connect(ftp);ftp.replies[b'SIZE']=reply
                exc=self.failure(core,self.source())
                self.assertEqual('passed',exc.upload_evidence.readback)
                self.assertEqual('failed',exc.upload_evidence.size)
                self.assertNotIn(b'RNFR',ftp.verbs)

    def test_destination_recheck_preserves_concurrent_file(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.transfer_hook=lambda verb,path:ftp.files.update({b'/USB1/NEW':b'other'}) if verb==b'RETR' else None
            exc=self.failure(core,self.source())
            self.assertEqual('conflict',exc.upload_evidence.error_category)
            self.assertEqual(b'other',ftp.files[b'/USB1/NEW']);self.assertNotIn(b'RNFR',ftp.verbs)

    def test_publication_refusal_and_uncertainty(self):
        for stage in (b'RNFR',b'RNTO'):
            for lost in (False,True):
                with self.subTest(stage=stage,lost=lost),server() as ftp:
                    core,_=self.connect(ftp)
                    if lost:ftp.after_mutation[stage]=None
                    else:ftp.replies[stage]=b'550 refusal\r\n'
                    exc=self.failure(core,self.source());e=exc.upload_evidence
                    unknown=stage==b'RNTO' and lost
                    self.assertEqual('location-unknown' if unknown else 'staging-candidate',e.disposition)
                    self.assertEqual(None if unknown else e.staging,exc.partial_path)
                    self.assertEqual(unknown,b'/USB1/new' in ftp.files)
                    self.assertEqual(unknown,bool(e.inspection_message()))
                    self.assertNotIn(b'DELE',ftp.verbs);self.assertEqual(int(stage==b'RNTO'),ftp.verbs.count(b'RNTO'))

    def test_cancel_between_verified_phases_keeps_completed_stor(self):
        for phase in ('readback','size','mutate'):
            with self.subTest(phase=phase),server() as ftp:
                core,_=self.connect(ftp);adapter=adapter_for(core._client)
                with patch.object(adapter,phase,side_effect=JobCancelled()):exc=self.failure(core,self.source())
                self.assertEqual('completed',exc.upload_evidence.stor['outcome'])
                self.assertEqual('staging-candidate',exc.upload_evidence.disposition)
                self.assertNotIn(b'RNFR',ftp.verbs)

    def test_wire_cancellation_after_stor_and_during_readback(self):
        for after_stor in (True,False):
            with self.subTest(after_stor=after_stor),server() as ftp:
                core,_=self.connect(ftp);pending=[False]
                def progress(_):pass
                def check():
                    if pending[0]:raise JobCancelled()
                progress.check=check
                def event(e):
                    if ((after_stor and e['operation']=='STOR' and e['kind']=='transfer-complete') or
                        (not after_stor and e['operation']=='RETR' and e['kind']=='transfer-start')):
                        pending[0]=True
                core._ftp_manager._diagnostic=event
                exc=self.failure(core,self.source(),progress)
                self.assertIsInstance(exc,JobCancelled)
                self.assertEqual('completed',exc.upload_evidence.stor['outcome'])
                self.assertEqual('staging-candidate',exc.upload_evidence.disposition)
                self.assertNotIn(b'SIZE',ftp.verbs);self.assertNotIn(b'RNFR',ftp.verbs)
                self.assertEqual(int(not after_stor),ftp.verbs.count(b'RETR'))

    def test_short_source_with_lost_reply_retains_transport_uncertainty(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            ftp.transfer_completion=lambda verb,path:None if verb==b'STOR' else b'226 Done\r\n'
            from types import SimpleNamespace
            with patch('c64u_browser.transfers.os.fstat',return_value=SimpleNamespace(st_size=4)):
                exc=self.failure(core,self.source())
            self.assertEqual('short',exc.upload_evidence.stor['length_status'])
            self.assertEqual('unknown',exc.upload_evidence.stor['outcome'])
            self.assertEqual('transport',exc.upload_evidence.error_category)

    def test_folder_plan_additions_use_managed_files_and_managed_directory_creation(self):
        with server() as ftp:
            core,_=self.connect(ftp);root=self.source().parent;folder=root/'folder';folder.mkdir()
            (folder/'one').write_bytes(b'one');(folder/'empty').touch()
            request=CopyRequest(FileLocation.core_host(root),('folder',),FileLocation.c64u('/USB1'))
            preview=core.files.prepare_copy(request).wait(5)

            with patch(
                'ftplib.FTP',
                side_effect=AssertionError('legacy remote MKD must not be used'),
            ):
                result=core.files.execute_copy(preview.result.plan_id).wait(5)

            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(b'one',ftp.files[b'/USB1/folder/one'])
            self.assertEqual(b'',ftp.files[b'/USB1/folder/empty'])
            self.assertEqual(2,len(result.result.uploads))
            self.assertEqual(1,len(result.result.folder_steps))
            self.assertEqual('mkdir',result.result.folder_steps[0].operation)

    def test_cancel_during_publication_and_after_ack_preserves_success(self):
        for stage in ('RNFR','RNTO','complete'):
            with self.subTest(stage=stage),server() as ftp:
                core,_=self.connect(ftp);pending=[False]
                def check():
                    if pending[0]:raise JobCancelled()
                def progress(_):pass
                progress.check=check
                def diagnostic(event):
                    if stage=='complete' and event['kind']=='mutation-complete':pending[0]=True
                core._ftp_manager._diagnostic=diagnostic
                ftp.mutation_hook=lambda verb,arg:pending.__setitem__(0,True) if verb.decode()==stage else None
                result=upload_managed(core._client,self.source(),'/USB1',progress)
                self.assertEqual('published',result['upload'].disposition)
                self.assertEqual(b'abc',ftp.files[b'/USB1/new']);self.assertEqual(0,core._ftp_manager.active_count)

    def test_nested_reuse_absolute_paths_and_no_failed_reopen(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=adapter_for(core._client);before=ftp.connections
            with adapter.operation():
                core._client.list_directory('/USB1/other')
                upload_managed(core._client,self.source(),'/USB1')
            self.assertEqual(1,ftp.connections-before)
            self.assertEqual(b'abc',ftp.files[b'/USB1/new'])
            ftp.replies[b'STOR']=b'550 refusal\r\n'
            path=self.source();path=path.rename(path.with_name('second'))
            with adapter.operation():
                with self.assertRaises(UploadFailure):upload_managed(core._client,path,'/USB1')
                before=ftp.connections
                with self.assertRaises(BrowserError):adapter.end_read_attempt()
                with self.assertRaises(Exception):adapter.size('/USB1/new')
                self.assertEqual(before,ftp.connections)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_missing_managed_context_never_falls_back(self):
        with patch('ftplib.FTP',side_effect=AssertionError('fallback')):
            with self.assertRaises(UploadFailure):upload_managed(object(),self.source(),'/USB1')

    def test_file_service_file_validation_shares_upload_lease(self):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source();(source.parent/'empty').touch()
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),
                ('new','empty'),FileLocation.c64u('/USB1'))).wait(5)
            before=ftp.connections;ftp.commands.clear()
            result=core.files.execute_copy(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(('new','empty'),result.result.completed)
            self.assertEqual(2,ftp.connections-before)
            self.assertEqual(2,ftp.verbs.count(b'USER'));self.assertEqual(2,ftp.verbs.count(b'FEAT'))
            self.assertEqual(2,len(result.result.uploads))
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_file_service_job_unknown_publication_has_no_cleanup_shortcut(self):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source()
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),('new',),FileLocation.c64u('/USB1'))).wait(5)
            ftp.after_mutation[b'RNTO']=None
            result=core.files.execute_copy(preview.result.plan_id).wait(5)
            self.assertEqual('failed',result.state);self.assertFalse(result.error.retryable)
            self.assertIsNone(result.result.partial_upload);self.assertIsNone(result.result.partial_path)
            self.assertEqual('location-unknown',result.result.uploads[0].disposition)
            self.assertIn('Publication was not confirmed',result.result.details())
            self.assertIn('location-unknown',json.dumps(result.as_dict()))

    def test_reviewed_partial_cleanup_and_reconnect_refusal(self):
        with server() as ftp:
            core,profile=self.connect(ftp);source=self.source()
            preview=core.files.prepare_copy(CopyRequest(FileLocation.core_host(source.parent),('new',),FileLocation.c64u('/USB1'))).wait(5)
            ftp.replies[b'RETR']=b'550 refused\r\n'
            result=core.files.execute_copy(preview.result.plan_id).wait(5)
            partial=result.result.partial_upload;self.assertIsNotNone(partial)
            before=ftp.connections
            review=core.files.prepare_partial_delete(partial).wait(5)
            self.assertEqual('succeeded',review.state)
            deleted=core.files.execute_delete(review.result.plan_id).wait(5)
            self.assertEqual('succeeded',deleted.state);self.assertEqual(2,ftp.connections-before)
            self.assertNotIn(partial.location.path.encode(),ftp.files)
            core.disconnect();core.connect(profile,remote_folder='/USB1')
            with self.assertRaises(BrowserError):core.files.prepare_partial_delete(partial)

    def test_usb_restore_addition_uses_managed_upload_and_evidence(self):
        with server() as ftp:
            core,_=self.connect(ftp);destination=self.source().parent/'backup'
            preview=core.usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB1'),('/USB1/existing',),FileLocation.core_host(destination))).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)
            backed=core.usb.execute_backup(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',backed.state,backed.error)
            del ftp.files[b'/USB1/existing']
            preview=core.usb.prepare_restore(FileLocation.core_host(destination),FileLocation.c64u('/USB1')).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)
            with patch('ftplib.FTP',side_effect=AssertionError('legacy restore addition')):
                result=core.usb.execute_restore(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(('existing',),result.result.added)
            self.assertEqual('published',result.result.uploads[0].disposition)
            self.assertEqual(b'old',ftp.files[b'/USB1/existing'])

    def test_stale_binding_rejected_before_wire_access(self):
        with server() as ftp:
            core,profile=self.connect(ftp);old=core._client
            core.disconnect();core.connect(profile,remote_folder='/USB1')
            before=ftp.connections
            with self.assertRaises(UploadFailure) as caught:upload_managed(old,self.source(),'/USB1')
            self.assertIsNone(caught.exception.partial_path)
            self.assertEqual(before,ftp.connections)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_batch_late_cancel_records_published_file_and_next_job_is_clean(self):
        with server() as ftp:
            core,_=self.connect(ftp);source=self.source();(source.parent/'next').write_bytes(b'next')
            request=CopyRequest(FileLocation.core_host(source.parent),('new','next'),FileLocation.c64u('/USB1'))
            preview=core.files.prepare_copy(request).wait(5)
            # Cancel from the active job context after the first publication is acknowledged.
            from c64u_browser.jobs import _CURRENT_CHECK
            def diagnostic(event):
                if event['kind']=='mutation-complete':
                    _CURRENT_CHECK.get().__self__.request_cancel()
            core._ftp_manager._diagnostic=diagnostic
            result=core.files.execute_copy(preview.result.plan_id).wait(5)
            self.assertEqual('cancelled',result.state)
            self.assertEqual(('new',),result.result.completed)
            self.assertEqual(('next',),result.result.remaining)
            self.assertEqual('published',result.result.uploads[0].disposition)
            self.assertIsNone(result.result.partial_upload)
            core._ftp_manager._diagnostic=None
            preview=core.files.prepare_copy(replace(request,names=('next',))).wait(5)
            result=core.files.execute_copy(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(b'next',ftp.files[b'/USB1/next'])

    def test_usb_restore_unknown_publication_preserves_result(self):
        with server() as ftp:
            core,_=self.connect(ftp);destination=self.source().parent/'backup'
            preview=core.usb.prepare_backup(BackupRequest(FileLocation.c64u('/USB1'),('/USB1/existing',),FileLocation.core_host(destination))).wait(5)
            self.assertEqual('succeeded',preview.state,preview.error)
            self.assertEqual('succeeded',core.usb.execute_backup(preview.result.plan_id).wait(5).state)
            del ftp.files[b'/USB1/existing']
            preview=core.usb.prepare_restore(FileLocation.core_host(destination),FileLocation.c64u('/USB1')).wait(5)
            ftp.after_mutation[b'RNTO']=None
            result=core.usb.execute_restore(preview.result.plan_id).wait(5)
            self.assertEqual('failed',result.state);self.assertFalse(result.error.retryable)
            self.assertIsNone(result.result.partial_upload)
            self.assertEqual('location-unknown',result.result.uploads[0].disposition)
            self.assertEqual((),result.result.added)
            self.assertEqual(('existing',),result.result.remaining)
            self.assertIn('Publication was not confirmed',result.result.message)

    def test_composite_routes_select_managed_owners(self):
        from c64u_browser.folder_copy import execute_plan, Plan, Step
        path=self.source()
        for replacement,source_local in ((True,True),(False,False)):
            plan=Plan(steps=[Step('new',str(path),'/USB1/new',False,signature=('old',3) if replacement else None)])
            from types import SimpleNamespace
            with patch('c64u_browser.folder_copy.replace_managed') as replace,patch('c64u_browser.folder_copy.execute_managed_step',return_value=SimpleNamespace(upload=None)) as composite,patch('c64u_browser.folder_copy.copy_files',side_effect=AssertionError('raw copy')):
                report=execute_plan(object(),plan,source_local,False)
                self.assertFalse(report.error,report.error)
                self.assertEqual(replacement,replace.called)
                self.assertEqual(not replacement,composite.called)


if __name__=='__main__':unittest.main()
