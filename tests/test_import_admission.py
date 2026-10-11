"""Deterministic offline admission, ownership and capacity adversaries."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from c64u_browser.ftp_reads import FtpReadAdapter
from c64u_browser.import_admission import ExecutionAdmission
from c64u_browser.import_capacity import reserve_capacity
from c64u_browser.import_execution import ExecutionAccounting as A
from c64u_browser.import_execution_store import ExecutionJournalStore, _definite_creation_refusal
from c64u_browser.import_journal import encode
from c64u_browser.import_snapshots import SnapshotError
from c64u_browser.import_transaction import TransactionError
from c64u_browser.jobs import JobCancelled
from c64u_browser.scheduler import JobBinding
from tests import test_import_snapshots as snapshot_tests
from tests import test_import_execution as journal_tests
from tests.test_import_plan import manifest
from c64u_browser.api import Entry


class FakeAdmissionReads(FtpReadAdapter):
    def __init__(self, fixture):
        self.fixture = fixture
        self.busy = False; self.active = 0; self.calls = []
        self.data = manifest(); self.hook = lambda phase: None
        self.rows = {}; self.incomplete = False

    @contextmanager
    def operation(self, check=None, *, reject_busy=False):
        if self.busy:raise SnapshotError('ftp-busy', 'Busy FTP lease')
        assert reject_busy
        self.active += 1
        try:
            check(); self.hook('lease'); yield
        finally:self.active -= 1

    def list_directory(self, path, *, budget=None, allow_fallback=True):
        assert not allow_fallback and self.active == 1
        self.calls.append(('list', path)); self.hook('list')
        budget.require(23); budget.consume(23)
        if self.incomplete:raise SnapshotError('listing-incomplete', 'Incomplete listing')
        if path in self.rows:return path, self.rows[path]
        return path, ([] if path.endswith('/games') else [Entry('manifest.json','file',len(self.data)),
            *(Entry(n,'dir',0) for n in ('games','metadata','artwork'))])

    def read(self, path, maximum, *, check=None, budget=None):
        assert self.active == 1
        check(); self.calls.append(('read',path)); self.hook('read')
        budget.require(len(self.data)); budget.consume(len(self.data)); check()
        return self.data


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f = snapshot_tests.AdmissionTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.core = self.f.core
        result = self.f.prepare(self.f.authorize())
        self.assertEqual('succeeded',result.state,result.error)
        self.snapshots = result.result
        self.owner = self.core._import_preparation.execution_owner(self.snapshots)
        self.adapter = FakeAdmissionReads(self.f)
        self.core._client._ftp_reads = self.adapter
        self.journals = self.f.parent/'execution-journals'
        self.addCleanup(patch.stopall)
        patch('socket.socket',side_effect=AssertionError('network forbidden')).start()

    def review(self):return self.core.review_managed_execution(self.snapshots,self.f.f.session)
    def authorize(self):return self.core.confirm_managed_execution(self.review(),confirmed=True)
    def admit(self, auth=None, **kwargs):
        self.journals.mkdir(mode=0o700, exist_ok=True)
        return self.core.admit_managed_execution(auth or self.authorize(),journal_directory=self.journals,**kwargs)

    def test_success_is_readonly_terminal_inspection_without_authority(self):
        before = self.core.preferences.path.read_bytes(); data=self.adapter.data
        auth=self.authorize(); result=self.admit(auth)
        self.assertEqual('admission-checked',result.status)
        self.assertFalse(result.mutation_enabled); self.assertEqual('canceled',result.journal_state)
        self.assertEqual(self.f.tx.budgets.planned_upload_bytes,result.snapshot_validation_reads)
        self.assertEqual(6*23+2*len(data),result.control_read_bytes)
        self.assertEqual(before,self.core.preferences.path.read_bytes());self.assertEqual(data,self.adapter.data)
        self.assertEqual(0,self.adapter.active);self.assertFalse(self.core._import_preparation._executing)
        loaded=ExecutionJournalStore(self.journals).load(self.f.tx.id)
        self.assertEqual('read-only-admission-complete',loaded.reason)
        self.assertEqual(0,loaded.accounting.attempted_upload_bytes)
        self.assertNotIn(auth.token.encode(),encode(loaded))
        with self.assertRaises(ValueError):ExecutionJournalStore(self.journals).save(loaded)
        with self.assertRaises(SnapshotError):self.admit(auth)

    def test_snapshot_confirmation_is_not_execution_authority(self):
        from c64u_browser.import_preparation import SnapshotAuthorization
        with self.assertRaises(SnapshotError):self.admit(SnapshotAuthorization('anything'))
        with self.assertRaises(SnapshotError):self.core.review_managed_execution(replace(self.snapshots),self.f.f.session)

    def test_copied_confirmations_and_authorizations_consume_original(self):
        target=self.review()
        with self.assertRaises(SnapshotError):self.core.confirm_managed_execution(replace(target),confirmed=True)
        with self.assertRaises(SnapshotError):self.core.confirm_managed_execution(target,confirmed=True)
        auth=self.authorize()
        with self.assertRaises(SnapshotError):self.admit(replace(auth))
        with self.assertRaises(SnapshotError):self.admit(auth)

    def test_cross_core_and_expired(self):
        other_fixture=snapshot_tests.AdmissionTests();other_fixture.setUp()
        self.addCleanup(other_fixture.doCleanups)
        other=other_fixture.core
        self.assertIsNot(other,self.core)
        # Even matching visible connection/library values cannot transfer consent.
        other._device_identity=self.core._device_identity
        other._session_id=self.core._session_id
        other._client=self.core._client
        other.preferences.game_library_location=dict(self.core.preferences.game_library_location)
        auth=self.authorize()
        with self.assertRaises(SnapshotError):other.admit_managed_execution(auth,journal_directory=self.journals)
        self.assertIs(auth,self.core._import_admission._authorized[auth.token][0])
        with patch('c64u_browser.import_admission.time.monotonic',return_value=10**20):
            with self.assertRaises(SnapshotError):self.admit(auth)
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.assertFalse(list(self.journals.iterdir()))

    def test_confirmation_decline_and_expiry(self):
        target=self.review();self.assertIsNone(self.core.confirm_managed_execution(target,confirmed=False))
        with self.assertRaises(SnapshotError):self.core.confirm_managed_execution(target,confirmed=True)
        target=self.review()
        with patch('c64u_browser.import_admission.time.monotonic',return_value=target.expires_at):
            with self.assertRaises(SnapshotError):self.core.confirm_managed_execution(target,confirmed=True)

    def test_busy_session_consumes(self):
        auth=self.authorize()
        with self.core._session_admission():
            with self.assertRaises(Exception):self.admit(auth)
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.assertFalse(list(self.journals.iterdir()))

    def test_busy_scheduler_consumes_and_releases_snapshot(self):
        auth=self.authorize()
        with self.core.scheduler.inline(JobBinding.device(self.f.f.session)):
            with self.assertRaises(Exception):self.admit(auth)
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.assertFalse(self.core._import_preparation._executing);self.assertFalse(list(self.journals.iterdir()))

    def test_ftp_busy_consumes_and_retains_truthful_failure(self):
        auth=self.authorize();self.adapter.busy=True
        with self.assertRaises(SnapshotError):self.admit(auth)
        with self.assertRaises(SnapshotError):self.admit(auth)
        journal=ExecutionJournalStore(self.journals).load(self.f.tx.id)
        self.assertEqual('failed',journal.state);self.assertEqual(A(),journal.accounting)
        self.assertEqual(0,self.adapter.active)

    def test_device_session_client_library_policy_generation_changes(self):
        changes=[('_device_identity','different'),('_session_id','different'),('_client',object())]
        for field,value in changes:
            auth=self.authorize();old=getattr(self.core,field);setattr(self.core,field,value)
            try:
                with self.assertRaises(SnapshotError):self.admit(auth)
            finally:setattr(self.core,field,old)
        auth=self.authorize(); old=self.core.preferences.game_library_location
        self.core.preferences.game_library_location={**old,'root':'/USB99'}
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.core.preferences.game_library_location=old
        auth=self.authorize();old=self.core.preferences.app_options['import_batch_mib']
        self.core.preferences.app_options['import_batch_mib']=256 if old!=256 else 512
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.core.preferences.app_options['import_batch_mib']=old
        auth=self.authorize();self.core._import_preparation.invalidate()
        with self.assertRaises(SnapshotError):self.admit(auth)
        self.assertFalse(self.adapter.calls)

    def test_manifest_revision_or_digest_changed(self):
        self.adapter.data=manifest(revision=1)
        with self.assertRaises(SnapshotError) as caught:self.admit()
        self.assertEqual('execution-manifest',caught.exception.code)
        self.assertGreater(caught.exception.execution_evidence.control_read_bytes,0)
        self.assertEqual(0,self.adapter.active)

    def test_session_change_during_admission_releases_every_owner(self):
        def hook(phase):
            if phase=='read':self.core._session_id='replaced-session'
        self.adapter.hook=hook
        with self.assertRaises(SnapshotError) as caught:self.admit()
        self.assertEqual('execution-session',caught.exception.code)
        self.assertEqual(0,self.adapter.active);self.assertFalse(self.core._import_preparation._executing)

    def test_each_selected_library_identity_component_is_bound(self):
        old=self.core.preferences.game_library_location
        for field in ('library_id','device_id','root','path'):
            auth=self.authorize();self.core.preferences.game_library_location={**old,field:'changed'}
            try:
                with self.assertRaises(SnapshotError):self.admit(auth)
            finally:self.core.preferences.game_library_location=old
        self.assertFalse(self.adapter.calls)

    def test_second_manifest_change_rejected(self):
        calls=[]
        def hook(phase):
            if phase=='read':
                calls.append(phase)
                if len(calls)==2:self.adapter.data=manifest(revision=1)
        self.adapter.hook=hook
        with self.assertRaises(SnapshotError):self.admit()
        self.assertEqual('failed',ExecutionJournalStore(self.journals).load(self.f.tx.id).state)

    def test_transaction_and_final_destination_collision(self):
        target=self.review();path=target.transaction.library.path
        for name,directory in ((target.transaction.directory.upper(),path),
                               (target.transaction.items[0].final_path.split('/')[-1].upper(),path+'/games')):
            rows=[Entry(name,'dir',0)]
            if directory==path:rows += [Entry('manifest.json','file',1),*(Entry(n,'dir',0) for n in ('games','metadata','artwork'))]
            self.adapter.rows[directory]=rows
            auth=self.core.confirm_managed_execution(target,confirmed=True)
            with self.assertRaises(SnapshotError) as caught:self.admit(auth)
            self.assertEqual('execution-collision',caught.exception.code)
            # Same attempt may not be restarted; test the second collision using
            # a fresh isolated journal store but the still-live snapshots.
            self.journals=self.journals.with_name(self.journals.name+'-next')
            self.adapter.rows.clear();target=self.review()

    def test_incomplete_or_ambiguous_listing(self):
        self.adapter.incomplete=True
        with self.assertRaises(SnapshotError):self.admit()
        self.assertEqual(0,self.adapter.active)

    def test_duplicate_listing_names(self):
        path=self.f.tx.library.path
        self.adapter.rows[path]=[Entry('games','dir',0),Entry('GAMES','dir',0)]
        with self.assertRaises(SnapshotError) as caught:self.admit()
        self.assertEqual('execution-listing',caught.exception.code)

    def corrupt(self,kind):
        path=self.f.parent/self.owner.name/'item-0001.snapshot'
        if kind=='contents':path.write_bytes(b'x'*path.stat().st_size)
        elif kind=='replace':
            other=path.with_name('replacement');other.write_bytes(path.read_bytes());os.replace(other,path)
        elif kind=='hardlink':os.link(path,self.f.parent/'hardlink')
        elif kind=='symlink':
            other=self.f.parent/'moved';path.rename(other);path.symlink_to(other)
        elif kind=='extra':path.with_name('extra').write_bytes(b'x')
        elif kind=='truncate':path.write_bytes(b'x')

    def test_modified_snapshot(self):
        self.corrupt('contents')
        with self.assertRaises(SnapshotError):self.admit()
        self.assertTrue(self.core._import_preparation._cleanup_blocked)
    def test_replaced_snapshot(self):
        self.corrupt('replace')
        with self.assertRaises(SnapshotError):self.admit()
    def test_hardlinked_snapshot(self):
        self.corrupt('hardlink')
        with self.assertRaises(SnapshotError):self.admit()
    def test_symlink_snapshot(self):
        self.corrupt('symlink')
        with self.assertRaises(SnapshotError):self.admit()
    def test_incomplete_snapshot(self):
        self.owner.sealed.clear()
        with self.assertRaises(SnapshotError):self.admit()
    def test_unexpected_snapshot_file(self):
        self.corrupt('extra')
        with self.assertRaises(SnapshotError):self.admit()

    def test_discard_cannot_race_admission(self):
        attempted=[]
        def hook(phase):
            if phase=='lease':
                with self.assertRaises(SnapshotError):self.core.discard_managed_snapshots(self.snapshots)
                attempted.append(phase)
        self.adapter.hook=hook;self.admit();self.assertEqual(['lease'],attempted)
        self.assertTrue(self.core.discard_managed_snapshots(self.snapshots))

    def test_shutdown_defers_snapshot_cleanup_until_ftp_and_scheduler_release(self):
        events=[];preparation=self.core._import_preparation
        original_operation=self.adapter.operation;original_inline=self.core.scheduler.inline
        original_cleanup=self.owner.cleanup
        @contextmanager
        def operation(*args,**kwargs):
            try:
                with original_operation(*args,**kwargs):yield
            finally:
                self.assertEqual(0,self.adapter.active);events.append('ftp-released')
        @contextmanager
        def inline(*args,**kwargs):
            try:
                with original_inline(*args,**kwargs) as check:yield check
            finally:
                self.assertEqual(['ftp-released'],events)
                reservations=[j for j in self.core.scheduler._jobs.values() if j.operation=='diagnostic.reservation']
                self.assertTrue(reservations)
                self.assertTrue(all(j._done.is_set() for j in reservations))
                events.append('scheduler-released')
        class Pins(set):
            def remove(pins,key):
                self.assertEqual(['ftp-released','scheduler-released'],events)
                super().remove(key);events.append('pin-released')
        preparation._executing=Pins(preparation._executing)
        def cleanup():
            self.assertEqual(['ftp-released','scheduler-released','pin-released'],events)
            self.assertNotIn(self.snapshots.snapshot_id,preparation._executing)
            events.append('cleanup');return original_cleanup()
        def hook(phase):
            if phase=='lease':
                self.assertIn(self.snapshots.snapshot_id,preparation._executing)
                self.core.close();self.assertFalse(self.owner.closed);self.assertEqual([],events)
        self.adapter.hook=hook
        with patch.object(self.adapter,'operation',operation), patch.object(self.core.scheduler,'inline',inline), patch.object(self.owner,'cleanup',cleanup):
            with self.assertRaises(SnapshotError):self.admit()
        self.assertEqual(['ftp-released','scheduler-released','pin-released','cleanup'],events)
        self.assertTrue(self.owner.closed);self.assertFalse(preparation._executing)

    def test_shutdown_release_claims_cleanup_atomically_against_discard(self):
        preparation=self.core._import_preparation
        original=preparation._cleanup_claimed;observed=[]
        def cleanup(result,entry):
            if result is self.snapshots:
                with self.assertRaises(SnapshotError):preparation.discard(result)
                observed.append(result)
            return original(result,entry)
        def hook(phase):
            if phase=='lease':self.core.close()
        self.adapter.hook=hook
        with patch.object(preparation,'_cleanup_claimed',cleanup):
            with self.assertRaises(SnapshotError):self.admit()
        self.assertEqual([self.snapshots],observed);self.assertTrue(self.owner.closed)

    def test_cancellation_at_each_observed_boundary(self):
        # Each attempt has its own store and new consent; no journal replay.
        calls=[0]
        def count():calls[0]+=1
        self.admit(check_cancel=count);boundaries=calls[0]
        for boundary in range(1,boundaries+1):
            self.journals=self.journals.with_name('cancel-'+str(boundary));calls[0]=0
            def cancel():
                calls[0]+=1
                if calls[0]==boundary:raise JobCancelled()
            with self.subTest(boundary=boundary):
                with self.assertRaises(JobCancelled):self.admit(check_cancel=cancel)
                self.assertEqual(0,self.adapter.active)
                self.assertFalse(self.core._import_preparation._executing)
                self.assertFalse(self.core._import_admission._running)

    def test_partial_validation_cancellation_accounting(self):
        real=os.read;did=[False]
        def read(fd,n):
            block=real(fd,n);did[0]=True;return block
        def cancel():
            if did[0]:raise JobCancelled()
        with patch('c64u_browser.import_snapshots.os.read',side_effect=read):
            with self.assertRaises(JobCancelled) as caught:self.admit(check_cancel=cancel)
        self.assertGreater(caught.exception.execution_evidence.snapshot_validation_reads,0)
        self.assertEqual(caught.exception.execution_evidence.snapshot_validation_reads,
                         ExecutionJournalStore(self.journals).load(self.f.tx.id).accounting.snapshot_validation_reads)

    def test_hash_mismatch_despite_unchanged_captured_metadata_is_rejected(self):
        # Simulate a filesystem whose metadata did not reveal corruption. The
        # independent hash still must reject it and charge the complete read.
        from c64u_browser.import_snapshots import file_identity
        self.corrupt('contents')
        path=self.f.parent/self.owner.name/'item-0001.snapshot'
        self.owner.sealed[path.name]=file_identity(path.stat())
        with self.assertRaises(SnapshotError) as caught:self.admit()
        self.assertEqual(self.f.tx.items[0].size,caught.exception.execution_evidence.snapshot_validation_reads)

    def test_snapshot_change_after_hash_before_final_manifest_check(self):
        reads=[]
        def hook(phase):
            if phase=='read':
                reads.append(phase)
                if len(reads)==2:self.corrupt('contents')
        self.adapter.hook=hook
        with self.assertRaises(SnapshotError):self.admit()
        self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_truncated_snapshot(self):
        self.corrupt('truncate')
        with self.assertRaises(SnapshotError):self.admit()

    def test_expiry_during_admission_retains_failed_reads(self):
        target=self.review();auth=self.core.confirm_managed_execution(target,confirmed=True)
        def hook(phase):
            if phase=='read':patch('c64u_browser.import_admission.time.monotonic',return_value=target.expires_at).start()
        self.adapter.hook=hook
        with self.assertRaises(SnapshotError) as caught:self.admit(auth)
        self.assertGreater(caught.exception.execution_evidence.control_read_bytes,0)
        self.assertEqual(0,self.adapter.active)

    def test_concurrent_discard_and_second_admission_fail_while_owned(self):
        ready=threading.Event();release=threading.Event();outcomes=[]
        auth=self.authorize();second=self.authorize()
        def hook(phase):
            if phase=='lease':
                ready.set()
                if not release.wait(5):raise AssertionError('test release timed out')
        self.adapter.hook=hook
        def run():
            try:outcomes.append(self.admit(auth))
            except BaseException as exc:outcomes.append(exc)
        worker=threading.Thread(target=run);worker.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(SnapshotError):self.core.discard_managed_snapshots(self.snapshots)
            with self.assertRaises(SnapshotError):self.admit(second)
        finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual('admission-checked',outcomes[0].status)
        with self.assertRaises(SnapshotError):self.admit(second)

    def test_concurrent_shutdown_preserves_owned_files_until_worker_stops(self):
        ready=threading.Event();release=threading.Event();errors=[]
        auth=self.authorize()
        def hook(phase):
            if phase=='lease':
                ready.set()
                if not release.wait(5):raise AssertionError('test release timed out')
        self.adapter.hook=hook
        def run():
            try:self.admit(auth)
            except BaseException as exc:errors.append(exc)
        worker=threading.Thread(target=run);worker.start()
        try:
            self.assertTrue(ready.wait(5));self.core.close()
            self.assertFalse(self.owner.closed)
        finally:release.set();worker.join(5)
        self.assertFalse(worker.is_alive());self.assertEqual(1,len(errors))
        self.assertTrue(self.owner.closed);self.assertEqual(0,self.adapter.active)

    def test_initial_checkpoint_sync_uncertainty_blocks_snapshot_cleanup(self):
        original=ExecutionJournalStore._append
        def append(store,journal,*,previous):
            original(store,journal,previous=previous)
            raise OSError('post-rename sync uncertain')
        with patch.object(ExecutionJournalStore,'_append',append):
            with self.assertRaises(OSError) as caught:self.admit()
        self.assertEqual('creation-uncertain',caught.exception.execution_evidence.journal_state)
        self.assertTrue(self.core._import_preparation._cleanup_blocked)
        self.core.close();self.assertFalse(self.owner.closed)

    def _assert_definite_refusal(self, auth, directory):
        calls=list(self.adapter.calls)
        before={p.name:p.read_bytes() for p in directory.iterdir()} if directory.exists() else None
        with self.assertRaises(Exception) as caught:
            self.core.admit_managed_execution(auth,journal_directory=directory)
        self.assertTrue(_definite_creation_refusal(caught.exception))
        self.assertEqual('not-created',caught.exception.execution_evidence.journal_state)
        self.assertFalse(caught.exception.execution_evidence.mutation_enabled)
        self.assertEqual(calls,self.adapter.calls)
        self.assertFalse(self.core._import_preparation._cleanup_blocked)
        self.assertFalse(self.core._import_preparation._executing)
        self.assertEqual(0,self.adapter.active)
        if before is None:self.assertFalse(directory.exists())
        else:self.assertEqual(before,{p.name:p.read_bytes() for p in directory.iterdir()})
        with self.assertRaises(SnapshotError):self.core.admit_managed_execution(auth,journal_directory=directory)

    def test_missing_journal_parent_allows_explicit_discard(self):
        self._assert_definite_refusal(self.authorize(),self.f.parent/'missing'/'journals')
        self.assertTrue(self.core.discard_managed_snapshots(self.snapshots))
        self.assertTrue(self.owner.closed);self.assertFalse((self.f.parent/self.owner.name).exists())
        self.assertFalse(self.core._import_preparation._ready)

    def test_missing_journal_parent_allows_shutdown_cleanup(self):
        self._assert_definite_refusal(self.authorize(),self.f.parent/'missing'/'journals')
        self.core.close()
        self.assertTrue(self.owner.closed);self.assertFalse((self.f.parent/self.owner.name).exists())
        self.assertFalse(self.core._import_preparation._ready)

    def test_duplicate_journal_allows_explicit_discard(self):
        self.admit();self._assert_definite_refusal(self.authorize(),self.journals)
        self.assertTrue(self.core.discard_managed_snapshots(self.snapshots))
        self.assertTrue(self.owner.closed);self.assertFalse((self.f.parent/self.owner.name).exists())

    def test_duplicate_journal_allows_shutdown_cleanup(self):
        self.admit();self._assert_definite_refusal(self.authorize(),self.journals)
        self.core.close()
        self.assertTrue(self.owner.closed);self.assertFalse((self.f.parent/self.owner.name).exists())
        self.assertFalse(self.core._import_preparation._ready)

    def test_consequential_store_failures_preserve_uncertainty(self):
        # Inject into real persistence syscalls, after a durable validation intent.
        # Every case has a fresh independent Core and snapshot set.
        for boundary in ('temporary-created','partial-write','replace','file-sync','directory-sync','cleanup','preflight-sync'):
            f=AdmissionTests();f.setUp()
            try:
                arm=[False];captured=[];real_open=os.open;real_fdopen=os.fdopen
                real_replace=os.replace;real_sync=os.fsync;real_unlink=os.unlink
                real_outcome=__import__('c64u_browser.import_execution_store',fromlist=['_ExecutionJournalWriter'])._ExecutionJournalWriter.outcome
                def arm_outcome(writer,*args,**kwargs):
                    captured.append(writer);arm[0]=True
                    return real_outcome(writer,*args,**kwargs)
                def open_(name,*args,**kwargs):
                    fd=real_open(name,*args,**kwargs)
                    if arm[0] and boundary=='temporary-created' and str(name).startswith('execution-write-'):
                        os.close(fd);raise FileNotFoundError('raised after temporary creation')
                    return fd
                def fdopen(fd,*args,**kwargs):
                    stream=real_fdopen(fd,*args,**kwargs)
                    if arm[0] and boundary=='partial-write' and args and args[0]=='wb':
                        class Partial:
                            def __enter__(self):return self
                            def __exit__(self,*exc):stream.close()
                            def write(self,data):stream.write(data[:7]);stream.flush();raise OSError('partial write')
                        return Partial()
                    return stream
                syncs=[0]
                def sync(fd):
                    if arm[0]:
                        syncs[0]+=1
                        if (boundary=='preflight-sync' and syncs[0]==1 or
                            boundary=='file-sync' and syncs[0]==2 or
                            boundary=='directory-sync' and syncs[0]==3):
                            raise OSError('sync failed')
                    return real_sync(fd)
                def replace_(*args,**kwargs):
                    if arm[0] and boundary in ('replace','cleanup'):raise FileNotFoundError('replacement failed')
                    return real_replace(*args,**kwargs)
                def unlink(name,*args,**kwargs):
                    if arm[0] and boundary=='cleanup' and str(name).startswith('execution-write-'):raise OSError('cleanup failed')
                    return real_unlink(name,*args,**kwargs)
                with patch('c64u_browser.import_execution_store._ExecutionJournalWriter.outcome',arm_outcome), patch('os.open',open_), patch('os.fdopen',fdopen), patch('os.fsync',sync), patch('os.replace',replace_), patch('os.unlink',unlink):
                    with self.assertRaises(OSError) as caught:f.admit()
                writer=captured[0]
                self.assertFalse(_definite_creation_refusal(caught.exception),boundary)
                self.assertTrue(writer.blocked,boundary)
                self.assertEqual('intent',writer.current.operations[-1].outcome)
                from c64u_browser.import_journal import decode
                prior=f.journals/ExecutionJournalStore._filename(f.f.tx.id,writer.current.revision)
                self.assertEqual(writer.current,decode(prior.read_bytes()))
                self.assertTrue(f.core._import_preparation._cleanup_blocked,boundary)
                self.assertFalse(f.core._import_preparation._executing)
                self.assertEqual(0,f.adapter.active)
                with self.assertRaises(TransactionError):writer.transition('uncertain',previous=writer.current,reason='no-retry')
                with self.assertRaises(SnapshotError):f.authorize()
                with self.assertRaises(SnapshotError):f.core.discard_managed_snapshots(f.snapshots)
                f.core.close();self.assertFalse(f.owner.closed)
                if boundary=='cleanup':self.assertTrue(list(f.journals.glob('execution-write-*')))
            finally:
                f.owner.cleanup();f.doCleanups()

    def test_unclassified_creation_error_stays_uncertain(self):
        with patch.object(ExecutionJournalStore,'_append',side_effect=FileNotFoundError('unknown boundary')):
            with self.assertRaises(FileNotFoundError) as caught:self.admit()
        self.assertFalse(_definite_creation_refusal(caught.exception))
        self.assertEqual('creation-uncertain',caught.exception.execution_evidence.journal_state)
        self.assertTrue(self.core._import_preparation._cleanup_blocked)

    def test_capacity_failure_before_transport(self):
        auth=self.authorize()
        with patch('c64u_browser.import_admission.reserve_capacity',side_effect=TransactionError('capacity')):
            with self.assertRaises(TransactionError):self.admit(auth)
        self.assertFalse(self.adapter.calls);self.assertFalse(list(self.journals.iterdir()))
        with self.assertRaises(SnapshotError):self.admit(auth)

    def test_journal_failure_preserves_intent_and_blocks_cleanup(self):
        original=ExecutionJournalStore._append
        def append(store,journal,*,previous):
            if journal.revision>=4:raise OSError('sync failed')
            return original(store,journal,previous=previous)
        with patch.object(ExecutionJournalStore,'_append',append):
            with self.assertRaises(OSError):self.admit()
        self.assertEqual('intent',ExecutionJournalStore(self.journals).load(self.f.tx.id).operations[-1].outcome)
        self.assertTrue(self.core._import_preparation._cleanup_blocked);self.assertEqual(0,self.adapter.active)


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.f=journal_tests.ExecutionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tx=self.f.tx3

    def test_reserved_complete_chain_uses_bounded_actual_canonical_bytes(self):
        w=self.f.store.create_reserved(self.tx)
        w.transition('awaiting-confirmation',previous=w.current);w.transition('staging',previous=w.current)
        self.f.uploads(w);w.transition('verifying',previous=w.current)
        for item in self.tx.items:self.f.op(w,'readback',item.staged_path,size=item.size,sha256=item.sha256,accounting=A(readback_bytes=item.size))
        w.transition('verified-staged',previous=w.current)
        reserved=w._reservation
        self.assertLessEqual(reserved.used_revisions,reserved.capacity.revisions)
        self.assertEqual(reserved.used_bytes,sum(p.stat().st_size for p in self.f.root.glob('*.execution-*')))
        self.assertLessEqual(reserved.used_bytes,reserved.capacity.aggregate_bytes)

    def test_exact_aggregate_boundary_and_one_byte_less(self):
        # journal_bytes itself changes JSON width, so converge the boundary.
        bound=reserve_capacity(self.tx).aggregate_bytes
        for _ in range(5):
            tx=replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=bound))
            bound=reserve_capacity(tx).aggregate_bytes
        self.assertEqual(bound,reserve_capacity(tx).aggregate_bytes)
        with self.assertRaises(TransactionError):reserve_capacity(replace(tx,budgets=replace(tx.budgets,journal_bytes=bound-1)))

    def test_terminal_uncertainty_uses_reserved_slot(self):
        w=self.f.store.create_reserved(self.tx)
        w.transition('awaiting-confirmation',previous=w.current);w.transition('staging',previous=w.current)
        w.intent(str(uuid4()),'snapshot-validation','',previous=w.current)
        w.transition('uncertain',previous=w.current,reason='x'*256)
        self.assertLessEqual(w._reservation.used_bytes,w._reservation.capacity.aggregate_bytes)
        self.assertEqual('uncertain',self.f.store.load(self.tx.id).state)

    def test_maximum_failure_counters_and_reason_fit_reserved_encoding(self):
        w=self.f.store.create_reserved(self.tx)
        w.transition('awaiting-confirmation',previous=w.current);w.transition('staging',previous=w.current)
        operation_id=str(uuid4());w.intent(operation_id,'snapshot-validation','',previous=w.current)
        w.outcome(operation_id,'unknown',previous=w.current,size=2**63-1,reason='x'*256,
                  accounting=A(snapshot_validation_reads=2**63-1,control_read_bytes=2**63-1))
        self.assertLessEqual(len(encode(w.current)),w._reservation.capacity.checkpoint_bytes)
        self.assertEqual('uncertain',self.f.store.load(self.tx.id).state)

    def test_insufficient_operation_or_byte_budget_creates_nothing(self):
        for field,value in (('operations',1),('journal_bytes',100)):
            tx=replace(self.tx,budgets=replace(self.tx.budgets,**{field:value}))
            with self.assertRaises(TransactionError):self.f.store.create_reserved(tx)
            self.assertFalse(list(self.f.root.iterdir()))

    def test_unrelated_operation_cannot_spend_reservation(self):
        from c64u_browser.import_execution import ExecutionJournal, ExecutionOperation
        w=self.f.store.create_reserved(self.tx)
        forged=replace(w.current,operations=(ExecutionOperation(str(uuid4()),1,'mkdir','unrelated'),),revision=1)
        with self.assertRaises(TransactionError):w._reservation.check(forged,b'{}')
        self.assertEqual(1,w._reservation.used_revisions)



class WireAdmissionTests(unittest.TestCase):
    @contextmanager
    def fixture(self):
        from c64u_ftp_server import FakeC64UFtp
        from tests import test_ftp_reads as reads
        from tests.test_import_plan import PATH, crt_bytes
        from c64u_browser.managed_library import parse_manifest
        from c64u_browser.picker_model import PickerSelection
        from c64u_browser.import_policy import prepare_transaction_v2
        f=reads.ReadMigrationTests();self.addCleanup(f.doCleanups)
        root=PATH.encode()
        dirs={b'/':b'type=dir; SD\r\ntype=dir; USB1\r\n',
              b'/USB1':b'',b'/SD':b'type=dir; ARGONAUT_LIBRARY\r\n',
              root:b'type=file; manifest.json\r\ntype=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\n',
              root+b'/games':b'',root+b'/metadata':b'',root+b'/artwork':b''}
        files={root+b'/manifest.json':manifest()}
        with FakeC64UFtp(directories=dirs,files=files) as server:
            core,_=f.connect(server);session=core.device_session()
            library=parse_manifest(manifest(),session.device_id,PATH)
            core.configure_game_library(PATH,identity=library.identity,expected_session=session)
            parent=core.preferences.path.parent;source=parent/'a.crt';source.write_bytes(crt_bytes())
            selection=PickerSelection('core-host',str(source),source.name,'','','','games','file')
            first=core.prepare_managed_import((selection,),library,session).wait(10).result
            second=core.prepare_managed_import((selection,),library,session,previous=first).wait(10).result
            tx=prepare_transaction_v2(first,second,library=library.identity,session=session,revision=0,
                manifest_digest=second.manifest_sha256,app_options=core.preferences.app_options)
            target=core.review_managed_snapshots(tx,session)
            auth=core.confirm_managed_snapshots(target,confirmed=True)
            prepared=core.prepare_managed_snapshots(auth,temporary_parent=parent).wait(10)
            self.assertEqual('succeeded',prepared.state,prepared.error)
            target=core.review_managed_execution(prepared.result,session)
            auth=core.confirm_managed_execution(target,confirmed=True)
            folder=parent/'journals';folder.mkdir(mode=0o700)
            yield core,server,auth,folder,dirs,files
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertFalse({b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} & set(server.verbs))
            self.assertEqual(files,server.files)

    def test_real_managed_lease_metering_and_no_mutations(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            connections=server.connections
            result=core.admit_managed_execution(auth,journal_directory=folder)
            self.assertEqual('admission-checked',result.status)
            root=auth and core.preferences.game_library_location['path'].encode()
            self.assertEqual(4*len(dirs[root])+2*len(dirs[root+b'/games'])+2*len(files[root+b'/manifest.json']),result.control_read_bytes)
            self.assertEqual(connections+1,server.connections)
            self.assertFalse(core.game_library.path.exists())

    def test_shutdown_observes_real_lease_reservation_pin_cleanup_order(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            preparation=core._import_preparation
            owner,snapshots=next(iter(preparation._ready.values()))
            adapter=core._client._ftp_reads;events=[]
            original_lease=core._ftp_manager.lease;original_inline=core.scheduler.inline
            original_read=adapter.read;original_cleanup=owner.cleanup
            @contextmanager
            def lease(*args,**kwargs):
                try:
                    with original_lease(*args,**kwargs) as client:yield client
                finally:
                    self.assertEqual(0,core._ftp_manager.active_count);events.append('ftp')
            @contextmanager
            def inline(*args,**kwargs):
                try:
                    with original_inline(*args,**kwargs) as check:yield check
                finally:
                    self.assertEqual(['ftp'],events)
                    reservations=[j for j in core.scheduler._jobs.values() if j.operation=='diagnostic.reservation']
                    self.assertTrue(reservations and all(j._done.is_set() for j in reservations))
                    events.append('scheduler')
            class Pins(set):
                def remove(pins,key):
                    self.assertEqual(['ftp','scheduler'],events)
                    super().remove(key);events.append('pin')
            preparation._executing=Pins(preparation._executing)
            def read(*args,**kwargs):
                result=original_read(*args,**kwargs)
                self.assertEqual(1,core._ftp_manager.active_count)
                core.close();self.assertFalse(owner.closed)
                self.assertIn(snapshots.snapshot_id,preparation._executing)
                self.assertEqual([],events);return result
            def cleanup():
                self.assertEqual(['ftp','scheduler','pin'],events)
                self.assertFalse(preparation._executing)
                events.append('cleanup');return original_cleanup()
            with patch.object(core._ftp_manager,'lease',lease), patch.object(core.scheduler,'inline',inline), patch.object(adapter,'read',read), patch.object(owner,'cleanup',cleanup):
                with self.assertRaises(Exception):core.admit_managed_execution(auth,journal_directory=folder)
            self.assertEqual(['ftp','scheduler','pin','cleanup'],events)
            self.assertTrue(owner.closed);self.assertFalse(preparation._ready)

    def test_no_list_fallback_after_mlsd_rejection(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            server.replies[b'MLSD']=b'502 unsupported\r\n';start=len(server.verbs)
            with self.assertRaises(Exception):core.admit_managed_execution(auth,journal_directory=folder)
            self.assertNotIn(b'LIST',server.verbs[start:])

    def test_incomplete_wire_listing_retains_consumed_bytes(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            root=core.preferences.game_library_location['path'].encode()
            server.directories[root]=b'type=file; incomplete'
            with self.assertRaises(Exception) as caught:core.admit_managed_execution(auth,journal_directory=folder)
            self.assertEqual(len(server.directories[root]),caught.exception.execution_evidence.control_read_bytes)

    def test_wire_lease_contention_is_fail_fast(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            adapter=core._client._ftp_reads
            with core._ftp_manager.lease(adapter.binding):
                before=server.connections
                with self.assertRaises(Exception):core.admit_managed_execution(auth,journal_directory=folder)
                self.assertEqual(before,server.connections)

    def test_adapter_context_contention_rejects_instead_of_waiting(self):
        with self.fixture() as (core,server,auth,folder,dirs,files):
            adapter=core._client._ftp_reads
            with adapter.operation():
                with self.assertRaises(Exception):core.admit_managed_execution(auth,journal_directory=folder)
            self.assertEqual(0,core._ftp_manager.active_count)

    def test_listing_budget_accounts_unsuccessful_reads(self):
        from c64u_browser.import_snapshots import ReadAllowance
        with self.fixture() as (core,server,auth,folder,dirs,files):
            adapter=core._client._ftp_reads;budget=ReadAllowance(7)
            with adapter.operation(reject_busy=True):
                with self.assertRaises(Exception):adapter.list_directory(core.preferences.game_library_location['path'],
                    budget=budget,allow_fallback=False)
            self.assertEqual(7,budget.consumed)


if __name__=='__main__':unittest.main()
