"""E2 one-use staging, durable failure boundaries and loopback-only transport."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from c64u_browser.import_execution_store import ExecutionJournalStore
from c64u_browser.import_execution_policy4 import encode_record, planned_operations
from c64u_browser.import_journal import encode
from c64u_browser.import_snapshots import SnapshotError
from c64u_browser.import_transaction import TransactionError
from c64u_browser.jobs import JobCancelled
from c64u_browser.scheduler import JobBinding
from c64u_browser.c64u_ftp_types import Outcome, SessionState
from tests import test_import_admission as admission
from tests import test_ftp_reads as reads
from tests.test_import_plan import PATH, crt_bytes, manifest


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.f=admission.AdmissionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.core=self.f.core;self.snapshots=self.f.snapshots

    def review(self):return self.core.review_managed_staging(self.snapshots,self.f.f.f.session)
    def authorize(self):return self.core.confirm_managed_staging(self.review(),confirmed=True,exclusive_writer_acknowledged=True)
    def stage(self,auth):return self.core.stage_managed_import(auth,journal_directory=self.f.journals)

    def test_readonly_and_snapshot_authority_cannot_stage(self):
        from c64u_browser.import_preparation import SnapshotAuthorization
        for auth in (self.f.authorize(),SnapshotAuthorization('not-staging'),self.review()):
            with self.assertRaises(SnapshotError):self.stage(auth)
        self.assertFalse(self.f.adapter.calls)

    def test_exact_types_copies_replay_cross_core_and_decline(self):
        target=self.review();tx=target.transaction
        self.assertEqual(4,tx.execution_policy_version)
        for text in (tx.id,tx.library.device_id,tx.library.library_id,tx.library.path,tx.items[0].final_path):self.assertIn(text,target.message)
        with self.assertRaises(SnapshotError):self.core.confirm_managed_staging(replace(target),confirmed=True,exclusive_writer_acknowledged=True)
        with self.assertRaises(SnapshotError):self.core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
        target=self.review();self.assertIsNone(self.core.confirm_managed_staging(target,confirmed=False))
        auth=self.authorize()
        with self.assertRaises(SnapshotError):self.stage(replace(auth))
        with self.assertRaises(SnapshotError):self.stage(auth)
        other=admission.AdmissionTests();other.setUp();self.addCleanup(other.doCleanups)
        auth=self.authorize()
        with self.assertRaises(SnapshotError):other.core.stage_managed_import(auth,journal_directory=other.journals)
        self.assertIs(auth,self.core._import_staging._authorized[auth.token][0])

    def test_expiry_and_binding_changes(self):
        target=self.review()
        with patch('c64u_browser.import_admission.time.monotonic',return_value=target.expires_at):
            with self.assertRaises(SnapshotError):self.core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
        for field,value in (('_session_id','changed'),('_device_identity','changed'),('_client',object())):
            auth=self.authorize();old=getattr(self.core,field);setattr(self.core,field,value)
            try:
                with self.assertRaises(SnapshotError):self.stage(auth)
            finally:setattr(self.core,field,old)
        auth=self.authorize();self.core._import_preparation.invalidate()
        with self.assertRaises(SnapshotError):self.stage(auth)
        self.assertFalse(self.f.adapter.calls)

    def test_exclusive_writer_acknowledgment_must_be_explicit_true(self):
        target=self.review()
        for kwargs in ({}, *({'exclusive_writer_acknowledged':v} for v in (False,None,0,1,'yes'))):
            with self.subTest(kwargs=kwargs),self.assertRaises(SnapshotError) as caught:
                self.core.confirm_managed_staging(target,confirmed=True,**kwargs)
            self.assertEqual('staging-exclusive-writer',caught.exception.code)
            self.assertFalse(self.core._import_staging._authorized)
        self.assertFalse(self.f.adapter.calls)
        for phrase in (target.transaction.library.root,'no other FTP client','Argonaut instance',
                       'C64U-side operation','not a technical lock','may overwrite'):
            self.assertIn(phrase,target.message)
        auth=self.core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
        self.assertIs(auth,self.core._import_staging._authorized[auth.token][0])

    def test_acknowledgment_cannot_confirm_readonly_or_wrong_target(self):
        readonly=self.core.review_managed_execution(self.snapshots,self.f.f.f.session)
        target=self.review()
        for invalid in (readonly, replace(target,transaction=replace(target.transaction,manifest_revision=99))):
            with self.assertRaises(SnapshotError):
                self.core.confirm_managed_staging(invalid,confirmed=True,exclusive_writer_acknowledged=True)
        other=admission.AdmissionTests();other.setUp();self.addCleanup(other.doCleanups)
        target=self.review()
        with self.assertRaises(SnapshotError):
            other.core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
        self.assertFalse(other.core._import_staging._authorized)
        self.assertFalse(self.core._import_staging._authorized)

    def test_acknowledged_capability_expires_and_library_changes_fail_closed(self):
        target=self.review()
        auth=self.core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
        with patch('c64u_browser.import_admission.time.monotonic',return_value=target.expires_at):
            with self.assertRaises(SnapshotError):self.stage(auth)
        with self.assertRaises(SnapshotError):self.stage(auth)
        auth=self.authorize()
        self.core.preferences.game_library_location={**self.core.preferences.game_library_location,'library_id':'changed'}
        with self.assertRaises(SnapshotError):self.stage(auth)
        self.assertFalse(self.f.adapter.calls)

    def test_busy_scheduler_consumes_without_lease(self):
        auth=self.authorize()
        with self.core.scheduler.inline(JobBinding.device(self.f.f.f.session)):
            with self.assertRaises(Exception):self.stage(auth)
        with self.assertRaises(SnapshotError):self.stage(auth)
        self.assertFalse(self.f.adapter.calls);self.assertFalse(self.core._import_preparation._executing)


class StagingTests(unittest.TestCase):
    @contextmanager
    def fixture(self, *, count=1, beige=False):
        from c64u_ftp_server import FakeC64UFtp
        from c64u_browser.managed_library import parse_manifest
        from c64u_browser.picker_model import PickerSelection
        from c64u_browser.import_policy import prepare_transaction_v2
        f=reads.ReadMigrationTests();self.addCleanup(f.doCleanups)
        library_path='/USB0/ARGONAUT_LIBRARY' if beige else PATH
        root=library_path.encode();original=manifest()
        dirs={b'/':b'',b'/USB0':b'',b'/USB1':b'',b'/SD':b'',root:b'',**{root+b'/'+n:b'' for n in (b'games',b'metadata',b'artwork')}}
        with FakeC64UFtp(directories=dirs,files={root+b'/manifest.json':original},mutation_tree=True,
                after_mutation={b'MKD':lambda path:b'257 "'+path.replace(b'"',b'""')+b'" created\r\n'}) as server:
            if beige:
                import copy
                live=copy.deepcopy(reads.INFO)
                live['info'].update(unique_id='25EA78',firmware_version='1.1.0s2')
                with patch.object(reads,'INFO',live):
                    core,profile=f.core(server)
                    core.connect(replace(profile,device_id='25EA78'),remote_folder='/USB1')
            else:core,_=f.connect(server)
            session=core.device_session()
            library=parse_manifest(original,session.device_id,library_path)
            core.configure_game_library(library_path,identity=library.identity,expected_session=session)
            parent=core.preferences.path.parent;selections=[]
            for n in range(count):
                source=parent/f'{n}.crt';data=bytearray(crt_bytes());data[-1]=n;source.write_bytes(data)
                selections.append(PickerSelection('core-host',str(source),source.name,'','','','games','file'))
            first=core.prepare_managed_import(tuple(selections),library,session).wait(10).result
            second=core.prepare_managed_import(tuple(selections),library,session,previous=first).wait(10).result
            tx=prepare_transaction_v2(first,second,library=library.identity,session=session,revision=0,
                manifest_digest=second.manifest_sha256,app_options=core.preferences.app_options)
            prep=core.confirm_managed_snapshots(core.review_managed_snapshots(tx,session),confirmed=True)
            result=core.prepare_managed_snapshots(prep,temporary_parent=parent).wait(10)
            self.assertEqual('succeeded',result.state,result.error)
            snapshots=result.result;owner=core._import_preparation.execution_owner(snapshots)
            target=core.review_managed_staging(snapshots,session)
            auth=core.confirm_managed_staging(target,confirmed=True,exclusive_writer_acknowledged=True)
            folder=parent/'journals';folder.mkdir(mode=0o700)
            self.core,self.server,self.auth,self.folder,self.tx,self.snapshots,self.owner=core,server,auth,folder,target.transaction,snapshots,owner
            self.start=len(server.commands)
            try:yield
            finally:
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertFalse(core._import_preparation._executing)
                self.assertFalse({b'DELE',b'RMD',b'RNFR',b'RNTO',b'APPE',b'ABOR',b'QUIT'} & set(server.verbs[self.start:]))
                self.assertEqual(original,server.files[root+b'/manifest.json'])
                self.assertFalse(any(p.startswith(root+b'/games/') for p in server.files))
                self.assertFalse(core.game_library.path.exists())
                core.close()
                if not owner.closed:owner.cleanup() # test-only host fixture disposal

    def stage(self,**kwargs):return self.core.stage_managed_import(self.auth,journal_directory=self.folder,**kwargs)
    def journal(self):return ExecutionJournalStore(self.folder).load(self.tx.id)
    def failure(self,**kwargs):
        with self.assertRaises(Exception) as caught:self.stage(**kwargs)
        self.assertTrue(hasattr(caught.exception,'staging_evidence'))
        return caught.exception
    def path(self,name=''):return (self.tx.library.path+'/'+self.tx.directory+('/'+name if name else '')).encode()

    def test_success_exact_artifacts_and_durable_history_one_lease(self):
        with self.fixture():
            before=self.server.connections;receipt=self.stage();j=self.journal()
            self.assertEqual('verified-staged',receipt.state);self.assertEqual('verified-staged',j.state)
            self.assertEqual(4,j.transaction.execution_policy_version)
            self.assertEqual(planned_operations(self.tx),tuple((o.kind,o.path) for o in j.operations))
            self.assertEqual(7,len(j.operations));self.assertEqual(22,len(list(self.folder.glob('*.execution-*'))))
            self.assertEqual(encode_record(self.tx),self.server.files[self.path('transaction.json')])
            for item in self.tx.items:self.assertEqual(item.sha256,hashlib.sha256(self.server.files[(self.tx.library.path+'/'+item.staged_path).encode()]).hexdigest())
            self.assertEqual(receipt.accounting,j.accounting)
            self.assertEqual(self.tx.budgets.planned_upload_bytes,j.accounting.confirmed_sender_bytes)
            self.assertEqual(j.accounting.confirmed_sender_bytes,j.accounting.readback_bytes)
            self.assertEqual(0,j.accounting.uncertain_send_bytes);self.assertEqual(before+1,self.server.connections)
            self.assertNotIn(self.auth.token.encode(),encode(j))
            for method in ('outcome','publish','resume'):self.assertFalse(hasattr(receipt,method))
            with self.assertRaises(ValueError):ExecutionJournalStore(self.folder).save(j)
            with self.assertRaises(SnapshotError):self.stage()
            self.assertTrue(self.core.discard_managed_snapshots(self.snapshots))

    def test_intent_precedes_every_mutation_and_ack_precedes_later_commands(self):
        with self.fixture():
            seen=[]
            def before(verb,path):
                if verb in (b'MKD',b'STOR'):
                    j=self.journal();self.assertEqual('intent',j.operations[-1].outcome)
                    self.assertEqual(path,(self.tx.library.path+'/'+j.operations[-1].path).encode())
                    seen.append(j.operations[-1].kind)
            self.server.before_command=before;self.stage()
            self.assertEqual(['mkdir','record-upload','upload'],seen)

    def test_mkd_collision_casefold_before_dispatch(self):
        with self.fixture():
            self.server.directories[self.path().upper().replace(b'/SD/ARGONAUT_LIBRARY',b'/SD/ARGONAUT_LIBRARY')]=b''
            self.failure();self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_mkd_lost_wrong_relative_missing_and_ambiguous_paths(self):
        for reply in (None,b'257 "/wrong"\r\n',b'257 "relative"\r\n',b'257 created\r\n',b'257 "x" "y"\r\n',b'299 OK\r\n'):
            with self.subTest(reply=reply),self.fixture():
                self.server.after_mutation[b'MKD']=reply
                e=self.failure();self.assertEqual('uncertain',self.journal().state)
                self.assertTrue(e.staging_evidence.remote_effects_possible)
                self.assertTrue(self.core._import_preparation._cleanup_blocked)
                self.assertNotIn(b'STOR',self.server.verbs[self.start:]);self.assertEqual(1,self.server.verbs.count(b'MKD'))

    def test_unexpected_directory_contents_after_durable_mkd(self):
        with self.fixture():
            def hook(verb,path):
                if verb==b'MKD':self.server.files[path+b'/unexpected']=b'x'
            self.server.mutation_hook=hook
            self.failure();j=self.journal()
            self.assertEqual('completed',j.operations[1].outcome)
            self.assertEqual('record-upload',j.operations[-1].kind);self.assertEqual('rejected',j.operations[-1].outcome)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_lost_record_or_payload_final_reply_keeps_intent_and_exposure(self):
        for record in (True,False):
            with self.subTest(record=record),self.fixture():
                def completion(verb,path):
                    if verb==b'STOR' and path.endswith(b'transaction.json')==record:return None
                    return b'226 Complete\r\n'
                self.server.transfer_completion=completion
                e=self.failure();j=self.journal();op=j.operations[-1]
                self.assertEqual('unknown',op.outcome);self.assertEqual('uncertain',j.state)
                self.assertEqual('record-upload' if record else 'upload',op.kind)
                self.assertGreater(op.accounting.control_upload_bytes if record else op.accounting.confirmed_sender_bytes,0)
                self.assertEqual(j.accounting,e.staging_evidence.accounting)
                self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_cancellation_after_each_acknowledged_mutation_is_durable(self):
        for kind in ('mkdir','record-upload','upload'):
            with self.subTest(kind=kind),self.fixture():
                pending=[False]
                def hook(event):
                    if ((kind=='mkdir' and event['kind']=='mutation-complete') or
                        (kind!='mkdir' and event['kind']=='transfer-complete' and event.get('operation')=='STOR' and
                         ((self.journal().operations[-1].kind)==kind))):pending[0]=True
                self.core._ftp_manager._diagnostic=hook
                def cancel():
                    if pending[0]:raise JobCancelled()
                self.failure(check_cancel=cancel);j=self.journal()
                self.assertEqual(kind,j.operations[-1].kind);self.assertEqual('completed',j.operations[-1].outcome)
                self.assertEqual('canceled',j.state)
                self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_readback_mismatch_short_overlong_and_changed_size(self):
        for record in (True,False):
            for fault in ('hash','short','overlong','size','lost'):
                with self.subTest(record=record,fault=fault),self.fixture():
                    def selected(path):return path.startswith(self.path()+b'/') and path.endswith(b'transaction.json')==record
                    def data(path,value):
                        if not selected(path):return value
                        if fault=='hash':return bytes([value[0]^1])+value[1:]
                        if fault=='short':return value[:-1]
                        if fault=='overlong':return value+b'x'
                        return value
                    self.server.readback_data=data
                    if fault=='size':
                        def hook(verb,path):
                            if verb==b'RETR' and selected(path):self.server.files[path]+=b'x'
                        self.server.transfer_hook=hook
                    if fault=='lost':self.server.transfer_completion=lambda verb,path:None if verb==b'RETR' and selected(path) else b'226 done\r\n'
                    e=self.failure();j=self.journal()
                    self.assertIn(j.state,('failed','uncertain'))
                    self.assertEqual('record-readback' if record else 'readback',j.operations[-1].kind)
                    self.assertGreater(j.operations[-1].size,0)
                    self.assertEqual(j.accounting,e.staging_evidence.accounting)

    def test_manifest_policy_session_library_changes_stop_next_write(self):
        for change in ('manifest','policy','session','library'):
            with self.subTest(change=change),self.fixture():
                def hook(verb,path):
                    if verb!=b'MKD':return
                    if change=='manifest':self.server.files[(PATH+'/manifest.json').encode()]=manifest(revision=1)
                    elif change=='policy':self.core.preferences.app_options['import_batch_mib']=256
                    elif change=='session':self.core._session_id='new-session'
                    else:self.core.preferences.game_library_location={**self.core.preferences.game_library_location,'library_id':'changed'}
                self.server.mutation_hook=hook
                # Restore the manifest for the fixture's invariant after observing failure.
                self.failure();self.server.files[(PATH+'/manifest.json').encode()]=manifest()
                self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_final_membership_and_destination_collision(self):
        for fault in ('extra','destination'):
            with self.subTest(fault=fault),self.fixture():
                def hook(verb,path):
                    if verb==b'RETR' and path.endswith(b'item-0001.crt'):
                        if fault=='extra':self.server.files[self.path('extra')]=b'x'
                        else:self.server.directories[(PATH+'/'+self.tx.items[0].final_path).encode()]=b''
                self.server.transfer_hook=hook;self.failure()
                self.assertEqual('final-validation',self.journal().operations[-1].kind)
                self.assertNotEqual('verified-staged',self.journal().state)

    def test_deadline_final_gate_and_no_transfer_deadline(self):
        for late in (False,True):
            with self.subTest(late=late),self.fixture():
                target=self.core._import_staging._authorized[self.auth.token][1][0]
                clock=[target.expires_at-1]
                def hook(event):
                    if late and event['kind']=='mutation-complete':clock[0]=target.expires_at+1000
                    if not late and event['kind']=='listing-complete':clock[0]=target.expires_at
                self.core._ftp_manager._diagnostic=hook
                with patch('c64u_browser.import_admission.time.monotonic',side_effect=lambda:clock[0]):
                    if late:self.assertEqual('verified-staged',self.stage().state)
                    else:self.failure();self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_tampered_snapshots_and_discard_blocking(self):
        with self.fixture():
            p=Path(self.owner.parent_path)/self.owner.name/'item-0001.snapshot';p.write_bytes(b'x'*p.stat().st_size)
            self.failure();self.assertNotIn(b'MKD',self.server.verbs[self.start:])
            self.assertTrue(self.core._import_preparation._cleanup_blocked)
        with self.fixture():
            attempts=[]
            def hook(verb,path):
                if verb==b'MKD':
                    with self.assertRaises(SnapshotError):self.core.discard_managed_snapshots(self.snapshots)
                    attempts.append(verb)
            self.server.mutation_hook=hook;self.stage();self.assertEqual([b'MKD'],attempts)

    def test_capacity_refusal_before_lease_and_mutation(self):
        with self.fixture():
            before=self.server.connections
            with patch('c64u_browser.import_staging.reserve_capacity',side_effect=TransactionError('capacity')):self.failure()
            self.assertEqual(before,self.server.connections);self.assertFalse(list(self.folder.iterdir()))

    def test_journal_intent_outcome_and_terminal_failures_stop_dispatch(self):
        for kind,phase in (('mkdir','intent'),('mkdir','completed'),('record-upload','completed'),('upload','completed'),('final-validation','completed'),('terminal','verified-staged')):
            with self.subTest(kind=kind,phase=phase),self.fixture():
                append=ExecutionJournalStore._append
                def fail(store,journal,*,previous):
                    op=journal.operations[-1] if journal.operations else None
                    if (kind=='terminal' and journal.state==phase) or (op and op.kind==kind and op.outcome==phase):raise OSError('sync failure')
                    return append(store,journal,previous=previous)
                with patch.object(ExecutionJournalStore,'_append',fail):e=self.failure()
                self.assertEqual('persistence-uncertain',e.staging_evidence.journal_state)
                self.assertTrue(self.core._import_preparation._cleanup_blocked)
                if kind=='mkdir':self.assertNotIn(b'STOR',self.server.verbs[self.start:])
                if phase=='intent':self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_partial_payload_send_exposure(self):
        with self.fixture():
            from c64u_browser.c64u_ftp import C64UFtpClient
            original=C64UFtpClient._state_to
            def state(client,value):
                original(client,value)
                if value==SessionState.TRANSFERRING and client._operation=='STOR' and self.journal().operations[-1].kind=='upload':
                    data=client._data
                    class Socket:
                        calls=0
                        def __getattr__(self,name):return getattr(data,name)
                        def sendall(self,block):
                            self.calls+=1
                            if self.calls==2:data.sendall(block[:17]);raise OSError('send loss')
                            return data.sendall(block)
                    client._data=Socket()
            with patch.object(C64UFtpClient,'_state_to',state):e=self.failure()
            a=self.journal().accounting
            self.assertEqual(8192,a.confirmed_sender_bytes);self.assertEqual(8272,a.attempted_upload_bytes)
            self.assertEqual(80,a.uncertain_send_bytes);self.assertEqual(a,e.staging_evidence.accounting)

    def test_shutdown_after_mkd_preserves_evidence_and_release_order(self):
        with self.fixture():
            prep=self.core._import_preparation;events=[]
            lease=self.core._ftp_manager.lease;inline=self.core.scheduler.inline
            @contextmanager
            def owned_lease(*args,**kwargs):
                try:
                    with lease(*args,**kwargs) as client:yield client
                finally:events.append('ftp')
            @contextmanager
            def owned_scheduler(*args,**kwargs):
                try:
                    with inline(*args,**kwargs) as check:yield check
                finally:self.assertEqual(['ftp'],events);events.append('scheduler')
            class Pins(set):
                def remove(pins,key):
                    self.assertEqual(['ftp','scheduler'],events);events.append('snapshot');super().remove(key)
            prep._executing=Pins()
            def hook(verb,path):
                if verb==b'MKD':self.core.close();self.assertFalse(self.owner.closed)
            self.server.mutation_hook=hook
            with patch.object(self.core._ftp_manager,'lease',owned_lease),patch.object(self.core.scheduler,'inline',owned_scheduler):self.failure()
            self.assertEqual(['ftp','scheduler','snapshot'],events)
            self.assertTrue(prep._cleanup_blocked);self.assertFalse(self.owner.closed)

    def test_ftp_busy_is_consumed_and_no_remote_effects(self):
        with self.fixture():
            adapter=self.core._client._ftp_reads
            with self.core._ftp_manager.lease(adapter.binding):
                before=self.server.connections;e=self.failure()
                self.assertEqual(before,self.server.connections)
                self.assertFalse(e.staging_evidence.remote_effects_possible)
            with self.assertRaises(SnapshotError):self.stage()
            self.assertFalse(self.core._import_preparation._cleanup_blocked)

    def test_byte_budgets_stop_before_next_submission_and_retain_actuals(self):
        from c64u_browser.import_staging import _Staging
        for field in ('snapshot_reads','control_reads','control_writes','uploads','readbacks'):
            with self.subTest(field=field),self.fixture():
                original=_Staging.__init__
                def initialize(execution,*args,**kwargs):
                    original(execution,*args,**kwargs);getattr(execution,field).limit=0
                with patch.object(_Staging,'__init__',initialize):e=self.failure()
                self.assertEqual(e.staging_evidence.accounting,self.journal().accounting)
                if field in ('snapshot_reads','control_reads','control_writes'):self.assertNotIn(b'STOR',self.server.verbs[self.start:])
                elif field=='uploads':self.assertEqual(1,self.server.verbs[self.start:].count(b'STOR'))
                else:
                    payload_reads=[p for v,p in self.server.commands[self.start:] if v==b'RETR' and p.endswith(b'item-0001.crt')]
                    self.assertFalse(payload_reads)

    def test_snapshot_tampered_between_validation_and_payload(self):
        with self.fixture():
            def hook(verb,path):
                if verb==b'STOR' and path.endswith(b'transaction.json'):
                    p=Path(self.owner.parent_path)/self.owner.name/'item-0001.snapshot'
                    p.write_bytes(b'z'*p.stat().st_size)
            self.server.transfer_hook=hook
            self.failure();self.assertEqual(1,self.server.verbs[self.start:].count(b'STOR'))
            self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_same_transaction_journal_is_not_adopted_and_definite_refusal_allows_discard(self):
        with self.fixture():
            ExecutionJournalStore(self.folder).create_reserved(self.tx)
            e=self.failure()
            self.assertEqual('not-created',e.staging_evidence.journal_state)
            self.assertFalse(e.staging_evidence.inspection_required)
            self.assertFalse(self.core._import_preparation._cleanup_blocked)
            self.assertNotIn(b'MKD',self.server.verbs[self.start:])
            self.assertTrue(self.core.discard_managed_snapshots(self.snapshots))

    def test_actual_directory_fsync_failure_retains_uncertainty_without_remote_mutation(self):
        import errno
        original=os.fsync
        with self.fixture():
            calls=[0]
            def fsync(fd):
                calls[0]+=1
                if calls[0]==1:raise OSError(errno.EIO,'directory sync failed')
                return original(fd)
            with patch('c64u_browser.import_execution_store.os.fsync',fsync):e=self.failure()
            self.assertEqual('creation-uncertain',e.staging_evidence.journal_state)
            self.assertTrue(self.core._import_preparation._cleanup_blocked)
            self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_shutdown_before_mutation_drains_owners_then_cleans_host(self):
        with self.fixture():
            called=[]
            def hook(event):
                if not called and event['kind']=='listing-complete':
                    called.append(True);self.core.close();self.assertFalse(self.owner.closed)
            self.core._ftp_manager._diagnostic=hook
            self.failure();self.assertTrue(called);self.assertTrue(self.owner.closed)
            self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_membership_collision_before_payload_never_overwrites(self):
        with self.fixture():
            path=self.path('item-0001.crt')
            def hook(verb,name):
                if verb==b'STOR' and name.endswith(b'transaction.json'):self.server.files[path]=b'external'
            self.server.transfer_hook=hook
            self.failure();self.assertEqual(b'external',self.server.files[path])
            self.assertEqual('present',self.journal().operations[-1].collision)
            self.assertEqual(1,self.server.verbs[self.start:].count(b'STOR'))

    def test_crash_reload_prefixes_remain_inspection_only(self):
        from c64u_browser.import_journal import decode
        from c64u_browser.import_execution import validate_successor
        with self.fixture():
            self.stage();previous=None
            for path in sorted(self.folder.glob('*.execution-*')):
                current=decode(path.read_bytes())
                if previous is not None:validate_successor(previous,current)
                self.assertFalse(hasattr(current,'outcome'))
                with self.assertRaises(ValueError):ExecutionJournalStore(self.folder).save(current)
                previous=current
            self.assertEqual('verified-staged',previous.state)

    def test_rejected_mkd_does_not_claim_cleanup_or_absence(self):
        with self.fixture():
            self.server.after_mutation[b'MKD']=b'550 not accepted\r\n'
            e=self.failure();self.assertTrue(e.staging_evidence.remote_effects_possible)
            self.assertEqual('rejected',self.journal().operations[-1].outcome)
            self.assertIn(self.path(),self.server.directories)
            self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_ambiguous_or_incomplete_listings_disable_mutation(self):
        for payload in (b'type=file; incomplete',b'type=dir; games\r\ntype=dir; GAMES\r\n'):
            with self.subTest(payload=payload),self.fixture():
                self.server.mutation_tree=False
                self.server.directories[PATH.encode()]=payload
                self.failure();self.assertNotIn(b'MKD',self.server.verbs[self.start:])
                self.assertNotIn(b'LIST',self.server.verbs[self.start:])

    def test_violated_exclusive_writer_contract_can_overwrite_between_check_and_stor(self):
        # Deliberate operating-contract violation, not an unconditional safety claim.
        with self.fixture():
            target=self.path('item-0001.crt');injected=[]
            def before(verb,path):
                if verb==b'STOR' and path==target:
                    self.assertNotIn(target,self.server.files)
                    self.server.files[target]=b'external writer data'
                    injected.append(path)
            self.server.before_command=before
            receipt=self.stage()
            self.assertEqual([target],injected)
            self.assertEqual('verified-staged',receipt.state)
            self.assertNotEqual(b'external writer data',self.server.files[target])
            self.assertEqual(self.tx.items[0].sha256,hashlib.sha256(self.server.files[target]).hexdigest())
            self.assertEqual(1,sum(v==b'STOR' and p==target for v,p in self.server.commands[self.start:]))
            self.assertEqual('point-in-time',receipt.evidence_scope)
            # Fixture teardown also forbids deletion, adoption/rename and cleanup commands.

    def test_equal_length_replacement_after_readback_leaves_only_point_in_time_receipt(self):
        from c64u_browser.import_staging import _Staging
        with self.fixture():
            target=self.path('item-0001.crt');original=_Staging.readback;observed=[]
            def readback(execution,path,*args,**kwargs):
                result=original(execution,path,*args,**kwargs)
                if path.endswith('item-0001.crt'):
                    observed.append(hashlib.sha256(self.server.files[target]).hexdigest())
                    self.server.files[target]=b'z'*len(self.server.files[target])
                return result
            with patch.object(_Staging,'readback',readback):receipt=self.stage()
            self.assertEqual([self.tx.items[0].sha256],observed)
            self.assertEqual('verified-staged',receipt.state)
            self.assertEqual('point-in-time',receipt.evidence_scope)
            self.assertIs(True,receipt.requires_publication_revalidation)
            path,size,digest=receipt.verified_artifacts[-1]
            self.assertEqual(self.tx.items[0].staged_path,path)
            self.assertEqual(size,len(self.server.files[target]))
            # An independent later hash catches what final SIZE/membership cannot.
            self.assertNotEqual(digest,hashlib.sha256(self.server.files[target]).hexdigest())
            self.assertEqual(self.tx,receipt.transaction)
            for name in ('token','authorize','execute','publish','cleanup','retry','recover'):
                self.assertFalse(hasattr(receipt,name))

    def test_staging_core_api_has_no_ui_callers(self):
        import ast
        root=Path(__file__).parents[1]/'c64u_browser'
        endpoints={'review_managed_staging','confirm_managed_staging','stage_managed_import'}
        for source in root.glob('*.py'):
            if source.name=='core.py':continue
            tree=ast.parse(source.read_text())
            callers=[node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call)
                     and isinstance(node.func,ast.Attribute) and node.func.attr in endpoints]
            self.assertEqual([],callers,source.name)
