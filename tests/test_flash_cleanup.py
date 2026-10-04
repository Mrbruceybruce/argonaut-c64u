"""Exact Flash qualification cleanup, real managed loopback; no hardware."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
import ast
import hashlib
import json
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

import test_ftp_reads as reads
from c64u_ftp_server import FakeC64UFtp
from c64u_browser.api import BrowserError
from c64u_browser.file_service import FileLocation
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.jobs import CoreJob, _CURRENT_CHECK
from c64u_browser.scheduler import JobBinding

PAYLOAD = b'PRIVATE-fixture-bytes'
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
TARGET = '/Flash/roms/disposable.bin'


def server():
    return FakeC64UFtp(directories={b'/':b'', b'/USB1':b'', b'/Flash':b'',
        b'/Flash/roms':b'', b'/Flash/carts':b'', b'/Flash/configs':b''},
        files={TARGET.encode():PAYLOAD}, mutation_tree=True)


class CleanupTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core
    connect = reads.ReadMigrationTests.connect

    def prepare(self, core, path=TARGET, size=len(PAYLOAD), digest=DIGEST):
        r = core.files.prepare_flash_cleanup(path, size, digest).wait(5)
        self.assertEqual('succeeded', r.state, r.error)
        self.assertEqual(0, core._ftp_manager.active_count)
        return r.result

    def execute(self, core, ftp, preview):
        ftp.commands.clear()
        r = core.files.execute_flash_cleanup(preview.plan_id).wait(5)
        self.assertEqual(0, core._ftp_manager.active_count)
        self.assertFalse(set(ftp.verbs) & {b'RMD', b'MKD', b'STOR', b'RNFR', b'RNTO', b'ABOR'})
        self.assertLessEqual(ftp.verbs.count(b'DELE'), 1)
        text = json.dumps(r.as_dict())
        for secret in ('PRIVATE', 'fixture-bytes', 'SECRET', 'temporary-password'):
            self.assertNotIn(secret, text)
        return r

    def block(self, core):
        started, release = Event(), Event(); self.addCleanup(release.set)
        job = CoreJob('test.block', lambda job:(started.set(), release.wait(5)))
        core.scheduler.submit(job, JobBinding.device(core.device_session()))
        self.assertTrue(started.wait(2))
        return release

    def test_success_all_approved_parents_single_use_and_no_raw_access(self):
        for folder in ('roms', 'carts', 'configs'):
            with self.subTest(folder=folder), server() as ftp:
                path = '/Flash/'+folder+'/disposable.bin'; ftp.files[path.encode()] = PAYLOAD
                core,_ = self.connect(ftp); before = ftp.connections
                with patch('ftplib.FTP', side_effect=AssertionError('raw')):
                    p = self.prepare(core, path)
                    with self.assertRaises(FrozenInstanceError):p.path = '/Flash/roms/other'
                    r = self.execute(core, ftp, p)
                self.assertEqual('succeeded', r.state, r.error)
                self.assertTrue(r.result.complete); self.assertTrue(r.result.acknowledged)
                self.assertEqual('passed', r.result.pre_delete)
                self.assertEqual(DIGEST, r.result.observed_sha256)
                self.assertEqual(2, ftp.connections-before)
                self.assertEqual([(b'DELE', path.encode())], [c for c in ftp.commands if c[0] == b'DELE'])
                self.assertNotIn(path.encode(), ftp.files)
                self.assertGreater(ftp.verbs[ftp.verbs.index(b'DELE')+1:].count(b'MLSD'), 0)
                with self.assertRaises(BrowserError):core.files.execute_flash_cleanup(p.plan_id)

    def test_syntax_and_expected_evidence_refused_before_adapter(self):
        with server() as ftp:
            core,_ = self.connect(ftp); ftp.commands.clear()
            for path in ('/Flash/x', '/Flash/ROMS/x', '/Flash/roms', '/Flash/roms/',
                    '/USB1/x', '/Flash/roms/../x', '/Flash/roms/sub/x', '/Flash//roms/x',
                    '/Flash/roms/.', '/Flash/roms/..', '/Flash/roms/a\\b', '/Flash/roms/a:b',
                    '/Flash/roms/a*', '/Flash/roms/a?', '/Flash/roms/a\r\nDELE x',
                    '/Flash/roms/a\x00', '/Flash/roms/a\x7f', '/Flash/roms/x.', '/Flash/roms/x ',
                    '/Flash/roms/'+'a'*65, ['/Flash/roms/x']):
                with self.subTest(path=path), self.assertRaises(BrowserError):
                    core.files.prepare_flash_cleanup(path, len(PAYLOAD), DIGEST)
            for size, digest in ((0,DIGEST),(-1,DIGEST),(True,DIGEST),(16777217,DIGEST),
                                 (1,'SECRET'),(1,'g'*64)):
                with self.subTest(size=size), self.assertRaises(BrowserError):
                    core.files.prepare_flash_cleanup(TARGET,size,digest)
            self.assertEqual([],ftp.commands)

    def test_wrong_identity_type_size_hash_case_duplicate_and_missing_refused(self):
        for mode in ('directory','non-file','duplicate','case','missing','size','hash',
                     'parent-missing','parent-case','parent-duplicate','parent-file','root-duplicate'):
            with self.subTest(mode=mode),server() as ftp:
                core,_ = self.connect(ftp)
                if mode=='directory':del ftp.files[TARGET.encode()]; ftp.directories[TARGET.encode()]=b''
                if mode=='non-file':
                    ftp.mutation_tree=False
                    ftp.directories[b'/']=b'type=dir; Flash\r\n'
                    ftp.directories[b'/Flash']=b'type=dir; roms\r\n'
                    ftp.directories[b'/Flash/roms']=b'type=OS.unix=slink;size=21; disposable.bin\r\n'
                if mode in ('duplicate','case'):
                    ftp.files[b'/Flash/roms/DISPOSABLE.BIN']=PAYLOAD
                    if mode=='case':del ftp.files[TARGET.encode()]
                if mode=='missing':del ftp.files[TARGET.encode()]
                if mode.startswith('parent-'):
                    if mode!='parent-duplicate':del ftp.directories[b'/Flash/roms']
                    if mode in ('parent-case','parent-duplicate'):ftp.directories[b'/Flash/ROMS']=b''
                    if mode=='parent-file':ftp.files[b'/Flash/roms']=PAYLOAD
                if mode=='root-duplicate':ftp.directories[b'/FLASH']=b''
                r=core.files.prepare_flash_cleanup(TARGET,len(PAYLOAD)+(mode=='size'),
                                                   '0'*64 if mode=='hash' else DIGEST).wait(5)
                self.assertEqual('failed',r.state)
                self.assertNotIn(b'DELE',ftp.verbs);self.assertEqual(0,core._ftp_manager.active_count)
                if mode=='hash':self.assertEqual(DIGEST,r.result.observed_sha256)

    def test_changed_or_disappeared_after_review_refused(self):
        for mode in ('same-size','size','missing','directory','duplicate'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core)
                if mode=='same-size':ftp.files[TARGET.encode()]=b'x'*len(PAYLOAD)
                if mode=='size':ftp.files[TARGET.encode()]=b'x'
                if mode=='missing':del ftp.files[TARGET.encode()]
                if mode=='directory':del ftp.files[TARGET.encode()];ftp.directories[TARGET.encode()]=b''
                if mode=='duplicate':ftp.files[b'/Flash/roms/DISPOSABLE.BIN']=PAYLOAD
                r=self.execute(core,ftp,p)
                self.assertEqual('failed',r.state);self.assertNotIn(b'DELE',ftp.verbs)

    def test_change_after_execution_read_detected_before_delete(self):
        for mode in ('size','directory','duplicate','missing'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core)
                def after(verb,path):
                    if verb!=b'RETR':return
                    if mode=='size':ftp.files[path]=b'x'
                    if mode=='missing':del ftp.files[path]
                    if mode=='directory':del ftp.files[path];ftp.directories[path]=b''
                    if mode=='duplicate':ftp.files[b'/Flash/roms/DISPOSABLE.BIN']=PAYLOAD
                ftp.transfer_hook=after
                r=self.execute(core,ftp,p);self.assertEqual('failed',r.state);self.assertNotIn(b'DELE',ftp.verbs)

    def test_stale_reconnect_profile_and_connection_binding(self):
        for mode in ('session','reconnect','profile','connection','invalidated'):
            with self.subTest(mode=mode),server() as ftp:
                core,profile=self.connect(ftp);p=self.prepare(core)
                if mode=='session':core._session_id='new'
                if mode=='reconnect':core.connect(profile,remote_folder='/USB1')
                if mode=='profile':core.active_profile.host='changed.invalid'
                if mode=='connection':
                    a=adapter_for(core._client);a.binding=replace(a.binding,port=a.binding.port+1)
                if mode=='invalidated':core._ftp_manager.invalidate(core.device_session().device_id, recovering=True)
                r=self.execute(core,ftp,p);self.assertEqual('failed',r.state);self.assertNotIn(b'DELE',ftp.verbs)

    def test_unverified_profile_refused(self):
        with server() as ftp:
            core,_=self.connect(ftp);core.active_profile.device_id='';core.active_profile.device_mac=''
            with self.assertRaises(BrowserError):core.files.prepare_flash_cleanup(TARGET,len(PAYLOAD),DIGEST)
            self.assertNotIn(b'DELE',ftp.verbs)

    def test_queued_cancellation_prepare_and_execute(self):
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core)
            for prepare in (True,False):
                release=self.block(core);ftp.commands.clear()
                job=(core.files.prepare_flash_cleanup(TARGET,len(PAYLOAD),DIGEST) if prepare else
                     core.files.execute_flash_cleanup(p.plan_id))
                job.request_cancel();release.set();r=job.wait(5)
                self.assertEqual('cancelled',r.state);self.assertEqual('queued',r.result.cancellation_phase)
                self.assertEqual([],ftp.commands);self.assertEqual(0,core._ftp_manager.active_count)

    def test_cancel_immediately_before_delete(self):
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core);a=adapter_for(core._client);original=a.mutate
            def cancel(*args):
                _CURRENT_CHECK.get().__self__.request_cancel()
                return original(*args)
            with patch.object(a,'mutate',side_effect=cancel):r=self.execute(core,ftp,p)
            self.assertEqual('cancelled',r.state);self.assertNotIn(b'DELE',ftp.verbs)

    def test_cancel_after_ack_preserves_delete_and_no_replay(self):
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core)
            def diagnostic(event):
                if event['kind']=='mutation-complete' and event['operation']=='DELE':
                    _CURRENT_CHECK.get().__self__.request_cancel()
            core._ftp_manager._diagnostic=diagnostic
            r=self.execute(core,ftp,p)
            self.assertEqual('cancelled',r.state);self.assertTrue(r.result.acknowledged)
            self.assertFalse(r.result.complete);self.assertEqual('absence',r.result.cancellation_phase)
            self.assertEqual(1,ftp.verbs.count(b'DELE'));self.assertIn('acknowledged',r.error.message)

    def test_unknown_or_rejected_delete_no_retry_or_absence_claim(self):
        for unknown in (True,False):
            with self.subTest(unknown=unknown),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core)
                if unknown:ftp.after_mutation[b'DELE']=None
                else:ftp.replies[b'DELE']=b'550 SECRET server prose\r\n'
                r=self.execute(core,ftp,p)
                self.assertEqual('failed',r.state);self.assertFalse(r.result.complete)
                self.assertEqual('unknown' if unknown else 'rejected',r.result.mutation['outcome'])
                self.assertEqual(1,ftp.verbs.count(b'DELE'));self.assertEqual('unperformed',r.result.absence)

    def test_acknowledged_absence_failure_retains_consequence(self):
        for mode in ('listing','reappeared','parent'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core)
                def after(verb,path):
                    if verb!=b'DELE':return
                    if mode=='listing':ftp.replies[b'MLSD']=b'550 SECRET\r\n'
                    if mode=='reappeared':ftp.files[path]=PAYLOAD
                    if mode=='parent':del ftp.directories[b'/Flash/roms']
                ftp.mutation_hook=after
                r=self.execute(core,ftp,p);self.assertEqual('failed',r.state)
                self.assertTrue(r.result.acknowledged);self.assertFalse(r.result.complete)
                self.assertIn('verification incomplete',r.error.message)

    def test_short_overlong_corrupt_and_unavailable_size_read_refused(self):
        for mode in ('short','overlong','corrupt','size'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core)
                if mode=='size':ftp.replies[b'SIZE']=b'502 SECRET\r\n'
                else:ftp.readback_data=lambda path,data:{'short':data[:-1],'overlong':data+b'x','corrupt':b'x'*len(data)}[mode]
                r=self.execute(core,ftp,p);self.assertEqual('failed',r.state);self.assertNotIn(b'DELE',ftp.verbs)

    def test_discard_expiry_and_public_preview_cannot_retarget(self):
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core)
            altered=replace(p,path='/Flash/roms/other')
            self.assertEqual(TARGET,core.files._flash_cleanup_plans[p.plan_id].evidence.path)
            self.assertTrue(core.files.discard_plan(altered.plan_id))
            with self.assertRaises(BrowserError):core.files.execute_flash_cleanup(p.plan_id)
            p=self.prepare(core);core.files._clock=lambda:p_time+1000
            p_time=core.files._flash_cleanup_plans[p.plan_id].created_at
            with self.assertRaises(BrowserError):core.files.execute_flash_cleanup(p.plan_id)
            self.assertNotIn(b'DELE',ftp.verbs)

    def test_ordinary_delete_still_refuses_flash_and_static_ownership(self):
        with server() as ftp:
            core,_=self.connect(ftp)
            r=core.files.prepare_delete((FileLocation.c64u(TARGET),)).wait(5)
            self.assertEqual('failed',r.state);self.assertNotIn(b'DELE',ftp.verbs)
        source=Path('c64u_browser/flash_cleanup.py').read_text();tree=ast.parse(source)
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        mutations=[n for n in calls if n.func.attr=='mutate']
        self.assertEqual(1,len(mutations));self.assertEqual('delete',mutations[0].args[0].value)
        self.assertFalse({n.func.attr for n in calls}&{'connect','open_ftp','end_read_attempt','write_from'})

    def test_read_cancellation_and_mid_operation_binding_change_refuse(self):
        for mode in ('cancel', 'binding'):
            with self.subTest(mode=mode),server() as ftp:
                core,_=self.connect(ftp);p=self.prepare(core);a=adapter_for(core._client)
                original=a.readback
                def read(*args):
                    result=original(*args)
                    if mode=='cancel':_CURRENT_CHECK.get().__self__.request_cancel()
                    else:core.active_profile.host='changed.invalid'
                    return result
                with patch.object(a,'readback',side_effect=read):r=self.execute(core,ftp,p)
                self.assertEqual('cancelled' if mode=='cancel' else 'failed',r.state)
                self.assertNotIn(b'DELE',ftp.verbs)

    def test_operation_release_failure_preserves_acknowledgement(self):
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core);a=adapter_for(core._client)
            original=a.operation;depth=[0]
            @contextmanager
            def release_failure(check=None):
                outer=depth[0]==0;depth[0]+=1
                try:
                    with original(check):yield
                finally:depth[0]-=1
                if outer:raise OSError('SECRET release error')
            with patch.object(a,'operation',release_failure):r=self.execute(core,ftp,p)
            self.assertEqual('failed',r.state);self.assertTrue(r.result.acknowledged)
            self.assertEqual('passed',r.result.absence)

    def test_external_same_size_writer_after_last_hash_is_not_atomic(self):
        # Deliberate limitation witness: FTP has no compare-and-delete primitive.
        with server() as ftp:
            core,_=self.connect(ftp);p=self.prepare(core)
            def after(verb,path):
                if verb==b'RETR':ftp.files[path]=b'x'*len(PAYLOAD)
            ftp.transfer_hook=after
            r=self.execute(core,ftp,p)
            self.assertTrue(r.result.complete)
            self.assertEqual(DIGEST,r.result.observed_sha256)
