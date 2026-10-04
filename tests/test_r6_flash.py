"""R6 Flash policy, snapshots and consequences; real loopback, never hardware."""
import ast
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.api import BrowserError
from c64u_browser.file_service import FileLocation
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.jobs import CoreJob, JobCancelled, _CURRENT_CHECK
from c64u_browser.scheduler import JobBinding
from c64u_browser.native_files import upload_flash, validate_upload, MAX_BYTES, parse_cfg


def server(missing=False, **kwargs):
    folders={b'/':b'',b'/USB1':b'',b'/Flash':b''}
    if not missing:folders[b'/Flash/roms']=b''
    return FakeC64UFtp(directories=folders,files={b'/USB1/source.bin':b'private-payload'},
                      mutation_tree=True,**kwargs)


class FlashTests(unittest.TestCase):
    core=reads.ReadMigrationTests.core
    connect=reads.ReadMigrationTests.connect

    def source(self,data=b'private-payload'):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        path=Path(directory.name)/'new.bin';path.write_bytes(data)
        return path

    def prepare(self,core,source=None):
        source=source or FileLocation.core_host(self.source())
        snapshot=core.files.prepare_native_upload(source,'/Flash/roms','new.bin').wait(5)
        self.assertEqual('succeeded',snapshot.state,snapshot.error)
        return snapshot.result

    def failed(self,core,**kwargs):
        with self.assertRaises((BrowserError,JobCancelled)) as caught:
            upload_flash(core._client,'/Flash/roms','new.bin',b'private-payload',**kwargs)
        self.assertEqual(0,core._ftp_manager.active_count)
        return caught.exception.flash_evidence

    def no_cleanup(self,ftp):
        self.assertFalse(set(ftp.verbs)&{b'DELE',b'RMD',b'ABOR'})

    def test_exact_policy_matrix_and_boundaries(self):
        crt=b'C64 CARTRIDGE   '+b'\0'*48
        for folder,name,data in (('/Flash/roms',' Mixed.BIN',b'x'),('/Flash/roms','.hidden.ROM',b'x'),
                ('/Flash/roms','x.64C',b'x'),('/Flash/carts','x.CRT',crt),
                ('/Flash/configs','x.CFG',b'\xef\xbb\xbf[A]\r\nX=\r\n')):
            with self.subTest(name=name):validate_upload(folder,name,data)
        validate_upload('/Flash/roms','a'*26+'.bin',b'x'*MAX_BYTES)
        validate_upload('/Flash/configs','a'*60+'.cfg',b'[A]\nX=1\n')
        for name in ('','.', '..','a/b.bin','a\\b.bin','a:b.bin','a*.bin','a?.bin','a.bin ',
                     'a.bin.','a\x00.bin','a\x7f.bin','a'*27+'.bin','é'*14+'.bin','\ud800.bin'):
            with self.subTest(name=repr(name)),self.assertRaises((BrowserError,UnicodeError)):
                validate_upload('/Flash/roms',name,b'x')
        for folder,name,data in (('/Flash/ROMS','x.bin',b'x'),('/Flash','x.bin',b'x'),
                ('/Flash/roms/sub','x.bin',b'x'),('/Flash/roms','x.crt',crt),
                ('/Flash/carts','x.bin',crt),('/Flash/carts','x.crt',crt[:63]),
                ('/Flash/carts','x.crt',b'x'*64),('/Flash/configs','x.bin',b'[A]\nX=1\n'),
                ('/Flash/configs','x.cfg',b'[A]\nX=1'),('/Flash/roms','x.bin',b''),
                ('/Flash/roms','x.bin',b'x'*(MAX_BYTES+1)),
                ('/Flash/configs','x.cfg',b'x'*(256*1024+1))):
            with self.subTest(folder=folder,name=name),self.assertRaises(BrowserError):validate_upload(folder,name,data)

    def test_crt_signature_exact_boundary_and_near_misses_before_mutation(self):
        signature=b'C64 CARTRIDGE   '
        self.assertEqual(16,len(signature))
        # Offset 0x10 is outside the signature. No new header-field policy.
        for following in (0,1,255):
            validate_upload('/Flash/carts','valid.crt',signature+bytes([following])+b'\0'*47)
        for offset in range(16):
            malformed=signature[:offset]+b'\0'+signature[offset+1:]+b'\0'*48
            with self.subTest(offset=offset),patch('c64u_browser.native_files.adapter_for',
                    side_effect=AssertionError('validation must precede lease')):
                with self.assertRaises(BrowserError) as caught:
                    upload_flash(object(),'/Flash/carts','invalid.crt',malformed)
                self.assertEqual('refused',caught.exception.flash_evidence.validation)
                self.assertIsNone(caught.exception.flash_evidence.upload)

    def test_cfg_exact_parser_rules(self):
        self.assertEqual({'A':{'X':'',' X':' 1','x':'é'},'a':{'X':'2'}},
                         parse_cfg(b';comment\n#comment\n[A]\nX=\n X= 1\nx=\xe9\n[a]\nX=2\n'))
        for data in (b' [A]\nX=1\n',b'[A]\nX=1\n[A]\nX=2\n',b'[A]\nX=1\nX=2\n',
                     b'[]\nX=1\n',b'[A]\n=1\n',b'[A]\nX=\x01\n',b'[A]\n',
                     b'[A]\nX='+b'x'*126+b'\n'):
            with self.subTest(data=data),self.assertRaises(BrowserError):parse_cfg(data)

    def test_invalid_snapshot_refuses_before_any_adapter_or_raw_access(self):
        for data in (b'',b'x'*(MAX_BYTES+1),bytearray(b'x')):
            with (patch('c64u_browser.native_files.adapter_for',side_effect=AssertionError('lease')),
                  patch('ftplib.FTP',side_effect=AssertionError('raw'))):
                with self.assertRaises(BrowserError) as caught:upload_flash(object(),'/Flash/roms','new.bin',data)
                evidence=caught.exception.flash_evidence
                self.assertEqual('refused',evidence.validation);self.assertIsNone(evidence.upload)

    def test_success_exact_wire_evidence_existing_directory_and_one_lease(self):
        with server() as ftp:
            core,_=self.connect(ftp);before=ftp.connections;ftp.commands.clear();session=core.device_session()
            with (patch('ftplib.FTP',side_effect=AssertionError('raw')),
                  patch('ftplib.FTP',side_effect=AssertionError('raw'))):
                evidence=upload_flash(core._client,'/Flash/roms','New.BIN',b'private-payload')
            self.assertEqual('already-present',evidence.directory_state);self.assertIsNone(evidence.mkdir)
            self.assertTrue(evidence.verified_staged);self.assertEqual('published',evidence.upload.disposition)
            self.assertEqual('exact',evidence.upload.stor['length_status'])
            self.assertEqual(226,evidence.upload.stor['terminal_reply'])
            self.assertEqual(hashlib.sha256(b'private-payload').hexdigest(),evidence.upload.stor['sha256'])
            self.assertEqual('completed',evidence.upload.publication['outcome'])
            self.assertEqual(b'private-payload',ftp.files[b'/Flash/roms/New.BIN'])
            self.assertEqual([b'STOR',b'RETR',b'SIZE',b'RNFR',b'RNTO'],
                             [v for v in ftp.verbs if v in (b'MKD',b'STOR',b'RETR',b'SIZE',b'RNFR',b'RNTO')])
            self.assertEqual(1,ftp.connections-before);self.assertEqual(0,core._ftp_manager.active_count)
            self.assertEqual(session,core.device_session());self.no_cleanup(ftp)
            self.assertNotIn('private-payload',json.dumps(asdict(evidence)))

    def test_missing_known_directory_created_managed(self):
        for folder in ('roms','carts','configs'):
            with self.subTest(folder=folder),server(missing=True) as ftp:
                core,_=self.connect(ftp)
                name,data={'roms':('x.bin',b'x'),'carts':('x.crt',b'C64 CARTRIDGE   '+b'\0'*48),
                           'configs':('x.cfg',b'[A]\nX=1\n')}[folder]
                result=upload_flash(core._client,'/Flash/'+folder,name,data)
                self.assertEqual('acknowledged-created',result.directory_state)
                self.assertEqual('completed',result.mkdir['outcome'])
                self.assertEqual(('directory-created','published'),result.acknowledged)
                self.assertEqual(1,ftp.verbs.count(b'MKD'));self.no_cleanup(ftp)
                self.assertEqual(0,core._ftp_manager.active_count)

    def test_wrong_case_type_ambiguous_or_missing_parent_refuses(self):
        for mode in ('parent-missing','parent-case','parent-file','parent-ambiguous','child-case','child-file','child-ambiguous'):
            with self.subTest(mode=mode),server(missing=True) as ftp:
                if mode=='parent-missing':del ftp.directories[b'/Flash']
                if mode=='parent-case':del ftp.directories[b'/Flash'];ftp.directories[b'/FLASH']=b''
                if mode=='parent-file':del ftp.directories[b'/Flash'];ftp.files[b'/Flash']=b'x'
                if mode=='parent-ambiguous':ftp.directories[b'/FLASH']=b''
                if mode=='child-case':ftp.directories[b'/Flash/ROMS']=b''
                if mode=='child-file':ftp.files[b'/Flash/roms']=b'x'
                if mode=='child-ambiguous':ftp.directories.update({b'/Flash/roms':b'',b'/Flash/ROMS':b''})
                core,_=self.connect(ftp);e=self.failed(core)
                self.assertEqual('refused',e.directory_state)
                self.assertNotIn(b'MKD',ftp.verbs);self.assertNotIn(b'STOR',ftp.verbs)

    def test_immediate_pre_mkdir_race_rechecks_all_matches(self):
        for wrong in (False,True):
            with self.subTest(wrong=wrong),server(missing=True) as ftp:
                core,_=self.connect(ftp);count=[0]
                def after(verb,path):
                    if verb==b'MLSD' and next(arg for cmd,arg in reversed(ftp.commands) if cmd==b'CWD')==b'/Flash':
                        count[0]+=1
                        if count[0]==1:ftp.directories[b'/Flash/ROMS' if wrong else b'/Flash/roms']=b''
                ftp.transfer_hook=after
                if wrong:self.failed(core)
                else:self.assertEqual('already-present',upload_flash(core._client,'/Flash/roms','new.bin',b'x').directory_state)
                self.assertGreaterEqual(count[0],2)
                self.assertNotIn(b'MKD',ftp.verbs)
                if wrong:self.assertNotIn(b'STOR',ftp.verbs)

    def test_mkdir_rejected_and_unknown_no_replay_or_cleanup(self):
        for unknown in (False,True):
            with self.subTest(unknown=unknown),server(missing=True) as ftp:
                core,_=self.connect(ftp)
                if unknown:ftp.after_mutation[b'MKD']=None
                else:ftp.replies[b'MKD']=b'550 SECRET server prose\r\n'
                e=self.failed(core)
                self.assertEqual('creation-unknown' if unknown else 'refused',e.directory_state)
                self.assertEqual('unknown' if unknown else 'rejected',e.mkdir['outcome'])
                self.assertEqual(1,ftp.verbs.count(b'MKD'));self.assertNotIn(b'STOR',ftp.verbs)
                self.no_cleanup(ftp);self.assertNotIn('SECRET',json.dumps(asdict(e)))

    def test_cancellation_after_mkdir_ack_retains_consequence_in_job(self):
        with server(missing=True) as ftp:
            core,_=self.connect(ftp);preview=self.prepare(core)
            def diagnostic(event):
                if event['kind']=='mutation-complete' and event['operation']=='MKD':
                    _CURRENT_CHECK.get().__self__.request_cancel()
            core._ftp_manager._diagnostic=diagnostic
            result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('cancelled',result.state,result.error)
            self.assertEqual('acknowledged-created',result.result.flash.directory_state)
            self.assertEqual(('directory-created',),result.result.flash.acknowledged)
            self.assertIn('Created directory: /Flash/roms',result.error.message)
            self.assertNotIn(b'STOR',ftp.verbs);self.assertEqual(0,core._ftp_manager.active_count)
            self.no_cleanup(ftp)

    def test_local_reviewed_snapshot_survives_source_change_and_deletion(self):
        with server() as ftp:
            core,_=self.connect(ftp);path=self.source();preview=self.prepare(core,FileLocation.core_host(path))
            path.write_bytes(b'changed');path.unlink()
            with patch('pathlib.Path.open',side_effect=AssertionError('source reopen')):
                result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(b'private-payload',ftp.files[b'/Flash/roms/new.bin'])
            self.assertEqual('local-capture',result.result.flash.source_observation['kind'])
            self.assertNotIn('private-payload',repr(preview)+json.dumps(result.as_dict()))
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_remote_managed_snapshot_two_lifetimes_and_same_publisher(self):
        with server() as ftp:
            core,_=self.connect(ftp);before=ftp.connections;ftp.commands.clear()
            with patch('ftplib.FTP',side_effect=AssertionError('raw')):
                preview=self.prepare(core,FileLocation.c64u('/USB1/source.bin'))
                self.assertEqual([b'SIZE',b'RETR',b'SIZE'],[v for v in ftp.verbs if v in (b'SIZE',b'RETR')])
                self.assertEqual(1,ftp.connections-before);self.assertEqual(0,core._ftp_manager.active_count)
                ftp.files[b'/USB1/source.bin']=b'changed'
                with patch('c64u_browser.file_service.upload_flash',wraps=upload_flash) as publisher:
                    result=core.files.execute_native_upload(preview.plan_id).wait(5)
                self.assertEqual(1,publisher.call_count)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(b'private-payload',ftp.files[b'/Flash/roms/new.bin'])
            self.assertEqual(b'changed',ftp.files[b'/USB1/source.bin'])
            self.assertEqual('managed-size-retr-size',result.result.flash.source_observation['kind'])
            self.assertEqual(2,ftp.connections-before);self.assertEqual(0,core._ftp_manager.active_count)

    def test_remote_short_overlong_changed_size_empty_and_bound_refuse(self):
        for mode in ('short','overlong','changed','empty','oversize'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp)
                if mode in ('short','overlong'):
                    ftp.readback_data=lambda path,data:data[:-1] if mode=='short' else data+b'x'
                if mode=='changed':ftp.transfer_hook=lambda verb,path:ftp.files.update({path:b'changed'}) if verb==b'RETR' else None
                if mode=='empty':ftp.files[b'/USB1/source.bin']=b''
                if mode=='oversize':ftp.replies[b'SIZE']=b'213 16777217\r\n'
                result=core.files.prepare_native_upload(FileLocation.c64u('/USB1/source.bin'),'/Flash/roms','new.bin').wait(5)
                self.assertEqual('failed',result.state);self.assertIsNotNone(result.result.flash)
                if mode in ('empty','oversize'):self.assertNotIn(b'RETR',ftp.verbs)
                self.assertNotIn(b'MKD',ftp.verbs);self.assertNotIn(b'STOR',ftp.verbs)
                self.assertEqual(0,core._ftp_manager.active_count)

    def test_same_length_remote_rewrite_is_observed_bytes_not_atomicity(self):
        with server() as ftp:
            core,_=self.connect(ftp);ftp.readback_data=lambda path,data:b'x'*len(data)
            preview=self.prepare(core,FileLocation.c64u('/USB1/source.bin'))
            ftp.readback_data=None
            result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertEqual(b'x'*15,ftp.files[b'/Flash/roms/new.bin'])

    def test_destination_and_staging_collisions(self):
        for staging in (False,True):
            with self.subTest(staging=staging),server() as ftp:
                core,_=self.connect(ftp)
                ftp.files[b'/Flash/roms/ARGONAUT-PART-fixed' if staging else b'/Flash/roms/NEW.BIN']=b'other'
                with patch('c64u_browser.native_files.uuid.uuid4',return_value=SimpleNamespace(hex='fixed')):e=self.failed(core)
                self.assertEqual('not-started',e.upload.disposition);self.assertNotIn(b'STOR',ftp.verbs)
                self.no_cleanup(ftp)

    def test_destination_and_directory_races_before_publication(self):
        for directory in (False,True):
            with self.subTest(directory=directory),server() as ftp:
                core,_=self.connect(ftp)
                def after(verb,path):
                    if verb==b'RETR':
                        if directory:ftp.directories[b'/Flash/ROMS']=b''
                        else:ftp.files[b'/Flash/roms/NEW.BIN']=b'other'
                ftp.transfer_hook=after;e=self.failed(core)
                self.assertTrue(e.verified_staged);self.assertEqual('failed',e.upload.destination_recheck)
                self.assertNotIn(b'RNFR',ftp.verbs);self.no_cleanup(ftp)

    def test_exact_length_short_overlong_snapshot_stream_faults(self):
        for data,status in ((b'x','short'),(b'x'*16,'overlong')):
            with self.subTest(status=status),server() as ftp:
                core,_=self.connect(ftp);adapter=adapter_for(core._client);original=adapter.write_from
                def write(path,stream,expected):return original(path,io.BytesIO(data),expected)
                with patch.object(adapter,'write_from',side_effect=write):e=self.failed(core)
                self.assertEqual(status,e.upload.stor['length_status']);self.assertNotIn(b'RNFR',ftp.verbs)
                self.no_cleanup(ftp)

    def test_snapshot_hash_mismatch_never_publishes(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=adapter_for(core._client);original=adapter.write_from
            with patch.object(adapter,'write_from',side_effect=lambda path,stream,expected:original(path,io.BytesIO(b'x'*expected),expected)):
                e=self.failed(core)
            self.assertEqual('staging-candidate',e.upload.disposition);self.assertNotIn(b'RNFR',ftp.verbs)

    def test_readback_corrupt_short_overlong_and_size_failure(self):
        for mode in ('corrupt','short','overlong','size','size-unavailable'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp)
                if mode.startswith('size'):ftp.replies[b'SIZE']=b'502 unavailable\r\n' if mode=='size-unavailable' else b'213 14\r\n'
                else:ftp.readback_data=lambda path,data:{'corrupt':b'x'*len(data),'short':data[:-1],'overlong':data+b'x'}[mode]
                e=self.failed(core);self.assertFalse(e.verified_staged)
                self.assertEqual('staging-candidate',e.upload.disposition);self.assertNotIn(b'RNFR',ftp.verbs)
                self.no_cleanup(ftp)

    def test_stor_rejection_and_lost_reply(self):
        for lost in (False,True):
            with self.subTest(lost=lost),server() as ftp:
                core,_=self.connect(ftp)
                if lost:ftp.transfer_completion=lambda verb,path:None if verb==b'STOR' else b'226 Done\r\n'
                else:ftp.replies[b'STOR']=b'550 SECRET server prose\r\n'
                e=self.failed(core)
                self.assertEqual('staging-candidate' if lost else 'no-candidate',e.upload.disposition)
                self.assertNotIn(b'RETR',ftp.verbs);self.assertEqual(1,ftp.verbs.count(b'STOR'));self.no_cleanup(ftp)
                self.assertNotIn('SECRET',json.dumps(asdict(e)))

    def test_cancellation_before_stor_during_stor_and_readback(self):
        for phase in ('before','STOR','RETR'):
            with self.subTest(phase=phase),server() as ftp:
                core,_=self.connect(ftp);pending=[phase=='before']
                def check():
                    if pending[0]:raise JobCancelled()
                def diagnostic(event):
                    if event['kind']=='transfer-start' and event['operation']==phase:pending[0]=True
                core._ftp_manager._diagnostic=diagnostic
                e=self.failed(core,check=check)
                self.assertTrue(e.cancellation_requested);self.assertEqual('cancelled',e.error_category)
                self.assertNotIn(b'RNFR',ftp.verbs);self.no_cleanup(ftp)
                if phase=='before':self.assertNotIn(b'STOR',ftp.verbs)
                else:self.assertEqual('staging-candidate',e.upload.disposition)

    def test_cancellation_after_publication_ack_preserves_success(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare(core)
            def diagnostic(event):
                if event['kind']=='mutation-complete' and event['operation']=='rename':
                    _CURRENT_CHECK.get().__self__.request_cancel()
            core._ftp_manager._diagnostic=diagnostic
            result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
            self.assertTrue(result.result.flash.cancellation_requested)
            self.assertEqual('published',result.result.flash.upload.disposition)
            self.assertEqual(0,core._ftp_manager.active_count);self.no_cleanup(ftp)

    def test_unknown_publication_job_evidence_never_replays_or_cleans(self):
        with server(after_mutation={b'RNTO':None}) as ftp:
            core,_=self.connect(ftp);preview=self.prepare(core)
            result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('failed',result.state);self.assertFalse(result.error.retryable)
            e=result.result.flash
            self.assertEqual('location-unknown',e.upload.disposition)
            self.assertEqual('unknown',e.upload.publication['outcome'])
            self.assertIn(e.upload.staging,result.error.message);self.assertIn(e.upload.destination,result.error.message)
            self.assertEqual(1,ftp.verbs.count(b'RNTO'));self.no_cleanup(ftp)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_rename_refusals_and_rnfr_loss_remain_staged(self):
        for verb,lost in ((b'RNFR',False),(b'RNTO',False),(b'RNFR',True)):
            with self.subTest(verb=verb,lost=lost),server() as ftp:
                core,_=self.connect(ftp)
                if lost:ftp.after_mutation[verb]=None
                else:ftp.replies[verb]=b'550 SECRET refusal\r\n'
                e=self.failed(core)
                self.assertEqual('staging-candidate',e.upload.disposition);self.assertTrue(e.verified_staged)
                self.no_cleanup(ftp);self.assertEqual(1,ftp.verbs.count(b'RNFR'))

    def test_same_device_reconnect_refuses_old_plan(self):
        with server() as ftp:
            core,profile=self.connect(ftp);preview=self.prepare(core);old=core.device_session()
            core.connect(profile,remote_folder='/USB1');self.assertNotEqual(old,core.device_session())
            ftp.commands.clear();result=core.files.execute_native_upload(preview.plan_id).wait(5)
            self.assertEqual('failed',result.state);self.assertEqual('session',result.error.code)
            self.assertEqual('queued',result.result.flash.phase)
            self.assertEqual((),result.result.flash.acknowledged)
            self.assertNotIn(b'STOR',ftp.verbs);self.assertEqual(0,core._ftp_manager.active_count)

    def test_queued_cancellation_releases_snapshot_and_retains_unstarted_evidence(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare(core)
            stored=core.files._native_plans[preview.plan_id]
            ready,release=Event(),Event()
            def hold(job):
                ready.set();release.wait(5)
            blocker=core.scheduler.submit(CoreJob('test.hold',hold),JobBinding.device(core.device_session()))
            self.assertTrue(ready.wait(5))
            try:
                ftp.commands.clear()
                job=core.files.execute_native_upload(preview.plan_id)
                job.request_cancel()
            finally:release.set()
            blocker.wait(5);result=job.wait(5)
            self.assertEqual('cancelled',result.state)
            self.assertEqual('queued',result.result.flash.cancellation_phase)
            self.assertEqual((),result.result.flash.acknowledged)
            self.assertEqual(b'',stored.data)
            self.assertNotIn('private-payload',json.dumps(result.as_dict()))
            self.assertEqual([],ftp.commands)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_scheduler_admission_failure_releases_snapshot(self):
        with server() as ftp:
            core,_=self.connect(ftp);preview=self.prepare(core)
            stored=core.files._native_plans[preview.plan_id]
            with patch.object(core.files._scheduler,'submit',side_effect=BrowserError('closed')):
                with self.assertRaises(BrowserError):core.files.execute_native_upload(preview.plan_id)
            self.assertEqual(b'',stored.data)
            self.assertNotIn(preview.plan_id,core.files._native_plans)

    def test_mid_operation_binding_invalidation_refuses_publication(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            def diagnostic(event):
                if event['kind']=='transfer-complete' and event['operation']=='STOR':
                    core._ftp_manager.invalidate(core.device_session().device_id)
            core._ftp_manager._diagnostic=diagnostic;e=self.failed(core)
            self.assertEqual('staging-candidate',e.upload.disposition)
            self.assertNotIn(b'RNFR',ftp.verbs);self.no_cleanup(ftp)

    def test_remote_preparation_requires_adapter_and_cancels_in_read(self):
        with server() as ftp:
            core,_=self.connect(ftp);adapter=core._client._ftp_reads
            core._client._ftp_reads=None
            with patch('ftplib.FTP',side_effect=AssertionError('raw')):
                result=core.files.prepare_native_upload(FileLocation.c64u('/USB1/source.bin'),'/Flash/roms','new.bin').wait(5)
            self.assertEqual('failed',result.state);self.assertNotIn(b'RETR',ftp.verbs)
            core._client._ftp_reads=adapter
            def diagnostic(event):
                if event['kind']=='transfer-start' and event['operation']=='RETR':_CURRENT_CHECK.get().__self__.request_cancel()
            core._ftp_manager._diagnostic=diagnostic
            result=core.files.prepare_native_upload(FileLocation.c64u('/USB1/source.bin'),'/Flash/roms','new.bin').wait(5)
            self.assertEqual('cancelled',result.state);self.assertIsNotNone(result.result.flash)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_static_flash_paths_no_raw_factory_or_activation_and_ui_routing(self):
        import c64u_browser.native_files as native
        import inspect
        tree=ast.parse(inspect.getsource(native._upload_flash))
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        attributes={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        self.assertFalse(names&{'connect','ftplib','upload_managed'})
        self.assertFalse(attributes&{'open_ftp','storbinary','retrbinary','reset','reboot','apply','activate'})
        gui=Path('c64u_browser/flash_dialog.py').read_text()
        self.assertIn('self.prepare(path,False)',gui);self.assertIn('self.prepare(path,True)',gui)
        self.assertIn('result.result.message if result.result',gui)
        self.assertNotIn('def connect(',Path('c64u_browser/transfers.py').read_text())
        self.assertNotIn('def open_ftp(',Path('c64u_browser/core.py').read_text())
