"""Offline preparation tests. Isolated host files and fake C64U transports only."""
from dataclasses import replace
import errno
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from c64u_browser.import_policy import prepare_transaction_v2
from c64u_browser.import_snapshots import (prepare_snapshots, OwnedSnapshots, SnapshotError,
    CHUNK_BYTES, file_identity)
from c64u_browser.jobs import JobCancelled, CoreJob
from c64u_browser.scheduler import JobBinding
from c64u_browser.picker_model import PickerSelection
from tests import test_import_policy as policies
from tests import test_import_plan as planning


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.f=policies.PolicyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tx=self.f.v2()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.progress=[]

    def run_snapshot(self, tx=None, remote=None, check=lambda:None, report=None):
        return prepare_snapshots(tx or self.tx,self.parent,remote,check,report or self.progress.append)

    def fail(self, **kwargs):
        with self.assertRaises(Exception) as caught:self.run_snapshot(**kwargs)
        e=caught.exception.snapshot_evidence
        self.assertNotEqual('snapshots-ready',e.status)
        self.assertTrue(e.cleanup_complete)
        self.assertEqual([],list(self.parent.iterdir()))
        return caught.exception,e

    def test_local_verified_snapshot_private_and_explicit_cleanup(self):
        with patch('socket.socket',side_effect=AssertionError('network')):
            owner,result=self.run_snapshot()
        self.addCleanup(owner.cleanup)
        self.assertEqual('snapshots-ready',result.status)
        self.assertEqual(self.tx.items[0].size,result.accounting.snapshot_read_bytes)
        path=self.parent/owner.name/'item-0001.snapshot'
        self.assertEqual(self.tx.items[0].sha256,hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(0o600,path.stat().st_mode&0o777)
        self.assertEqual(0o700,path.parent.stat().st_mode&0o777)
        self.assertGreaterEqual(result.accounting.temporary_disk_peak_bytes,path.stat().st_blocks*512)
        self.assertEqual(0,result.accounting.upload_bytes)
        self.assertTrue(owner.cleanup());self.assertEqual([],list(self.parent.iterdir()))

    def test_fixed_buffer_large_source_and_exact_size(self):
        data=b'a'*(3*CHUNK_BYTES+7);item=self.tx.items[0]
        Path(item.source.path).write_bytes(data)
        item=replace(item,size=len(data),sha256=hashlib.sha256(data).hexdigest(),local_identity=file_identity(Path(item.source.path).stat()))
        policy=replace(self.tx.budgets,selected_payload_bytes=len(data),planned_upload_bytes=len(data),planned_readback_bytes=len(data))
        tx=replace(self.tx,items=(item,),budgets=policy)
        real=os.read;counts=[]
        def read(fd,count):counts.append(count);return real(fd,count)
        with patch('c64u_browser.import_snapshots.os.read',side_effect=read):owner,result=self.run_snapshot(tx=tx)
        self.addCleanup(owner.cleanup);self.assertLessEqual(max(counts),CHUNK_BYTES)
        self.assertEqual(len(data),result.accounting.snapshot_read_bytes)

    def test_modified_source_identity_rejected(self):
        Path(self.tx.items[0].source.path).write_bytes(b'changed')
        unused,e=self.fail();self.assertEqual(0,e.accounting.snapshot_read_bytes)

    def test_hash_mismatch_discards_payload(self):
        tx=replace(self.tx,items=(replace(self.tx.items[0],sha256='f'*64),))
        exc,e=self.fail(tx=tx);self.assertEqual('snapshot-content',exc.code)
        self.assertEqual(tx.items[0].size,e.accounting.snapshot_read_bytes)

    def test_source_changes_during_stream(self):
        def progress(p):
            if dict(p.details)['bytes_read']:Path(self.tx.items[0].source.path).write_bytes(b'changed')
        exc,e=self.fail(report=progress);self.assertEqual('snapshot-source-changed',exc.code)

    def test_cancel_after_local_bytes_keeps_accounting(self):
        cancel=[False]
        def check():
            if cancel[0]:raise JobCancelled()
        def report(p):
            if dict(p.details)['bytes_read']:cancel[0]=True
        exc,e=self.fail(check=check,report=report)
        self.assertTrue(exc.cancelled);self.assertEqual('canceled',e.status)
        self.assertEqual(CHUNK_BYTES,e.accounting.snapshot_read_bytes)

    def remote_tx(self):
        item=self.tx.items[0]
        source=PickerSelection('c64u','/USB1/a.crt','a.crt','/USB1',self.tx.library.device_id,self.tx.session_id,'games','file')
        return replace(self.tx,items=(replace(item,source=source,local_identity=()),))

    def test_remote_stream_and_partial_cancellation_accounting(self):
        data=Path(self.tx.items[0].source.path).read_bytes();tx=self.remote_tx()
        def remote(item,sink,budget,check):

            for offset in range(0,len(data),CHUNK_BYTES):
                block=data[offset:offset+CHUNK_BYTES];budget.consume(len(block));sink.write(block)
        owner,e=self.run_snapshot(tx=tx,remote=remote);self.addCleanup(owner.cleanup)
        self.assertEqual(len(data),e.accounting.snapshot_read_bytes);owner.cleanup()
        def canceled(item,sink,budget,check):
            budget.consume(3);sink.write(data[:3]);raise JobCancelled()
        unused,e=self.fail(tx=tx,remote=canceled)
        self.assertEqual(3,e.accounting.snapshot_read_bytes)

    def test_remote_short_and_overlong_payload(self):
        data=Path(self.tx.items[0].source.path).read_bytes()
        for block in (data[:-1],data+b'x'):
            def remote(item,sink,budget,check):budget.consume(len(block));sink.write(block)
            unused,e=self.fail(tx=self.remote_tx(),remote=remote)
            self.assertEqual(len(block),e.accounting.snapshot_read_bytes)

    def test_read_limit_includes_failed_bytes(self):
        tx=self.remote_tx();tx=replace(tx,budgets=replace(tx.budgets,snapshot_read_allowance=tx.items[0].size))
        def remote(item,sink,budget,check):
            budget.consume(item.size);budget.consume(1)
        exc,e=self.fail(tx=tx,remote=remote)
        self.assertEqual('snapshot-read-budget',exc.code);self.assertEqual(tx.items[0].size,e.accounting.snapshot_read_bytes)

    def test_disk_full_and_partial_write(self):
        real=os.write;calls=[]
        def write(fd,data):
            if calls:raise OSError(errno.ENOSPC,'full')
            calls.append(1);return real(fd,data[:3])
        with patch('c64u_browser.import_snapshots.os.write',side_effect=write):
            exc,e=self.fail()
        self.assertEqual(errno.ENOSPC,exc.errno)
        self.assertGreater(e.accounting.temporary_disk_peak_bytes,0)
        self.assertEqual(CHUNK_BYTES,e.accounting.snapshot_read_bytes)

    def test_actual_disk_budget_and_exact_boundary(self):
        owner=OwnedSnapshots(self.parent,self.tx);self.addCleanup(owner.cleanup)
        fd=owner.create(1)
        try:
            base=owner.measure();unit=os.fstatvfs(owner.directory).f_frsize
            owner.limit=base+unit;owner.write(fd,b'x')
            self.assertEqual(base+unit,owner.measure())
            with self.assertRaisesRegex(SnapshotError,'allowance'):owner.write(fd,b'x'*unit)
        finally:os.close(fd)

    def test_no_symlink_source_or_parent(self):
        path=Path(self.tx.items[0].source.path);target=path.with_name('real.crt');path.rename(target);path.symlink_to(target)
        self.fail()
        link=self.parent/'link';link.symlink_to(self.parent,target_is_directory=True)
        with self.assertRaises(OSError):prepare_snapshots(self.tx,link,None,lambda:None,lambda p:None)
        self.assertTrue(link.is_symlink());self.assertTrue(target.exists())

    def test_no_adoption_and_cleanup_refuses_replacement(self):
        owner=OwnedSnapshots(self.parent,self.tx);fd=owner.create(1);os.close(fd)
        path=self.parent/owner.name/'item-0001.snapshot'
        with self.assertRaises(FileExistsError):owner.create(1)
        path.unlink();target=self.parent/'sentinel';target.write_bytes(b'keep');path.symlink_to(target)
        self.assertFalse(owner.cleanup());self.assertEqual(b'keep',target.read_bytes());self.assertTrue(path.is_symlink())

    def test_path_traversal_parent_refused(self):
        with self.assertRaises(SnapshotError):OwnedSnapshots(str(self.parent)+'/../bad',self.tx)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f=planning.ImportCoreTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.core=self.f.core
        first=self.f.run_plan().result;second=self.f.run_plan(previous=first).result
        self.tx=prepare_transaction_v2(first,second,library=self.f.library.identity,session=self.f.session,
            revision=0,manifest_digest=second.manifest_sha256,app_options=self.core.preferences.app_options)
        self.parent=Path(self.f.temp.name)

    def review(self,tx=None):return self.core.review_managed_snapshots(tx or self.tx,self.f.session)
    def authorize(self):return self.core.confirm_managed_snapshots(self.review(),confirmed=True)
    def prepare(self,auth):return self.core.prepare_managed_snapshots(auth,temporary_parent=self.parent).wait(5)

    def test_explicit_confirm_one_use_and_no_catalog_mutation(self):
        before=self.core.preferences.path.read_bytes();manifest=self.f.read.return_value
        target=self.review();self.assertIn('does not import',target.message)
        auth=self.core.confirm_managed_snapshots(target,confirmed=True)
        with self.assertRaises(SnapshotError):self.core.confirm_managed_snapshots(target,confirmed=True)
        result=self.prepare(auth);self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual('snapshots-ready',result.result.status)
        with self.assertRaises(SnapshotError):self.prepare(auth)
        self.assertTrue(self.core.discard_managed_snapshots(result.result))
        self.assertEqual(before,self.core.preferences.path.read_bytes());self.assertEqual(manifest,self.f.read.return_value)
        self.assertFalse(self.core.game_library.path.exists())

    def test_cancel_confirmation_and_forged_copy(self):
        target=self.review()
        self.assertIsNone(self.core.confirm_managed_snapshots(target,confirmed=False))
        with self.assertRaises(SnapshotError):self.core.confirm_managed_snapshots(target,confirmed=True)
        target=self.review()
        with self.assertRaises(SnapshotError):self.core.confirm_managed_snapshots(replace(target),confirmed=True)

    def test_expired_confirmation_and_authorization(self):
        target=self.review()
        with patch('c64u_browser.import_preparation.time.monotonic',return_value=target.expires_at):
            with self.assertRaisesRegex(SnapshotError,'expired'):self.core.confirm_managed_snapshots(target,confirmed=True)
        auth=self.authorize()
        with patch('c64u_browser.import_preparation.time.monotonic',return_value=10**20):
            with self.assertRaisesRegex(SnapshotError,'expired'):self.prepare(auth)
        with self.assertRaises(SnapshotError):self.prepare(auth)

    def test_policy_change_and_confirmation_transaction_replacement(self):
        target=self.review();changed=replace(target.transaction,budgets=replace(target.transaction.budgets,upload_allowance=1))
        with self.assertRaises(SnapshotError):self.core.confirm_managed_snapshots(replace(target,transaction=changed),confirmed=True)
        auth=self.authorize();self.core.preferences.app_options['import_batch_mib']=256
        with self.assertRaisesRegex(SnapshotError,'preferences'):self.prepare(auth)

    def test_disconnect_reconnect_and_selected_library_change(self):
        for action in (lambda:self.core.configure_game_library(''),lambda:self.core.connect(self.f.fixture.profile),self.core.disconnect):
            auth=self.authorize();action()
            with self.assertRaises(SnapshotError):self.prepare(auth)
            self.core.connect(self.f.fixture.profile)
            self.f.session=self.core.device_session();self.tx=replace(self.tx,session_id=self.f.session.session_id)
            self.core.configure_game_library(self.tx.library.path,identity=self.tx.library,expected_session=self.f.session)

    def test_manifest_revision_and_digest_change(self):
        from tests.test_managed_library import manifest
        for data in (manifest(revision=1),self.f.read.return_value+b' '):
            auth=self.authorize();self.f.read.return_value=data
            result=self.prepare(auth)
            self.assertEqual('failed',result.state);self.assertEqual('snapshot-manifest',result.error.code)
            self.assertEqual('failed',result.result.status)

    def test_device_library_root_and_session_mismatch(self):
        for tx in (replace(self.tx,session_id='other'),replace(self.tx,library=replace(self.tx.library,device_id='other')),
                   replace(self.tx,library=replace(self.tx.library,root='/USB1',path='/USB1/ARGONAUT_LIBRARY'))):
            with self.assertRaises(Exception):self.review(tx)

    def test_busy_foreground_refuses_and_consumes_authority(self):
        started=threading.Event();release=threading.Event()
        auth=self.authorize()
        def task(job):started.set();release.wait(5)
        job=self.core.scheduler.submit(CoreJob('busy',task),JobBinding.device(self.f.session));started.wait(5)
        try:
            with self.assertRaisesRegex(Exception,'already running'):self.prepare(auth)
            with self.assertRaises(SnapshotError):self.prepare(auth)
        finally:release.set();job.wait(5)

    def test_close_cleans_ready_snapshots(self):
        result=self.prepare(self.authorize());self.assertEqual('succeeded',result.state,result.error)
        self.assertTrue(list(self.parent.glob('argonaut-snapshots-*')))
        self.core.close();self.assertEqual([],list(self.parent.glob('argonaut-snapshots-*')))

    def test_change_during_snapshot_refuses_ready_and_cleans(self):
        real=os.write
        def changed(fd,data):
            count=real(fd,data);self.core.preferences.game_library_location=None;return count
        with patch('c64u_browser.import_snapshots.os.write',side_effect=changed):result=self.prepare(self.authorize())
        self.assertEqual('failed',result.state);self.assertTrue(result.result.cleanup_complete)
        self.assertEqual([],list(self.parent.glob('argonaut-snapshots-*')))


    def test_non_boolean_confirmation_and_serialized_authority_refused(self):
        from c64u_browser.import_preparation import SnapshotAuthorization
        with self.assertRaises(SnapshotError):self.core.confirm_managed_snapshots(self.review(),confirmed=1)
        auth=self.authorize()
        with self.assertRaises(SnapshotError):self.prepare(SnapshotAuthorization(auth.token))
        with self.assertRaises(SnapshotError):self.core.prepare_managed_snapshots(self.tx,temporary_parent=self.parent)

    def test_failed_cleanup_blocks_new_attempts(self):
        result=self.prepare(self.authorize());self.assertEqual('succeeded',result.state,result.error)
        path=next(self.parent.glob('argonaut-snapshots-*'))/'foreign'
        path.write_text('preserve')
        self.assertFalse(self.core.discard_managed_snapshots(result.result))
        with self.assertRaises(SnapshotError):self.authorize()
        self.assertEqual('preserve',path.read_text())

    def test_close_during_preparation_cleans_without_ready_result(self):
        real=os.write
        def shutdown(fd,data):
            count=real(fd,data);self.core.close();return count
        with patch('c64u_browser.import_snapshots.os.write',side_effect=shutdown):result=self.prepare(self.authorize())
        self.assertEqual('failed',result.state);self.assertTrue(result.result.cleanup_complete)
        self.assertEqual([],list(self.parent.glob('argonaut-snapshots-*')))

    def test_final_manifest_recheck_prevents_ready(self):
        original=self.f.read.return_value
        self.f.read.side_effect=[original,original+b' ']
        result=self.prepare(self.authorize())
        self.assertEqual('failed',result.state);self.assertEqual('snapshot-manifest',result.error.code)
        self.assertTrue(result.result.cleanup_complete)
        self.assertGreater(result.result.accounting.snapshot_read_bytes,0)
        self.assertEqual([],list(self.parent.glob('argonaut-snapshots-*')))


class ManagedWireSnapshotTests(unittest.TestCase):
    def wire_case(self, mode):
        from c64u_ftp_server import FakeC64UFtp
        from tests import test_ftp_reads as reads
        from tests.test_game_library import crt_bytes
        from tests.test_managed_library import manifest, PATH
        from c64u_browser.managed_library import parse_manifest
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        root=PATH.encode();payload=crt_bytes()
        directories={b'/':b'type=dir; SD\r\ntype=dir; USB1\r\n',
            b'/SD':b'type=dir; ARGONAUT_LIBRARY\r\n',b'/USB1':b'type=file; a.crt\r\n',
            root:b'type=file; manifest.json\r\ntype=dir; games\r\ntype=dir; metadata\r\ntype=dir; artwork\r\n',
            root+b'/games':b'',root+b'/metadata':b'',root+b'/artwork':b''}
        files={root+b'/manifest.json':manifest(),b'/USB1/a.crt':payload}
        with FakeC64UFtp(directories=directories,files=files) as server:
            core,unused=fixture.connect(server);session=core.device_session()
            library=parse_manifest(manifest(),session.device_id,PATH)
            core.configure_game_library(PATH,identity=library.identity,expected_session=session)
            source=PickerSelection('c64u','/USB1/a.crt','a.crt','/USB1',session.device_id,session.session_id,'games','file')
            first=core.prepare_managed_import((source,),library,session).wait(5)
            second=core.prepare_managed_import((source,),library,session,previous=first.result).wait(5)
            self.assertEqual('succeeded',second.state,second.error)
            tx=prepare_transaction_v2(first.result,second.result,library=library.identity,session=session,
                revision=0,manifest_digest=second.result.manifest_sha256,app_options=core.preferences.app_options)
            target=core.review_managed_snapshots(tx,session)
            auth=core.confirm_managed_snapshots(target,confirmed=True)
            started=threading.Event();release=threading.Event();real=os.write
            def write(fd,data):
                count=real(fd,data)
                if mode=='cancel':started.set();release.wait(5)
                return count
            if mode=='changed':server.files[b'/USB1/a.crt']=b'x'*len(payload)
            baseline=dict(server.files)
            with tempfile.TemporaryDirectory() as folder:
                with patch('c64u_browser.import_snapshots.os.write',side_effect=write),patch('ftplib.FTP',side_effect=AssertionError('legacy FTP')):
                    job=core.prepare_managed_snapshots(auth,temporary_parent=folder)
                    if mode=='cancel':
                        self.assertTrue(started.wait(5));job.request_cancel();release.set()
                    result=job.wait(5)
                if mode=='success':
                    self.assertEqual('succeeded',result.state,result.error)
                    self.assertEqual(len(payload),result.result.accounting.snapshot_read_bytes)
                    self.assertTrue(core.discard_managed_snapshots(result.result))
                else:
                    self.assertEqual('cancelled' if mode=='cancel' else 'failed',result.state,result.error)
                    self.assertIn(result.result.status,('canceled','failed'))
                    self.assertGreater(result.result.accounting.snapshot_read_bytes,0)
                    self.assertTrue(result.result.cleanup_complete)
                self.assertEqual([],list(Path(folder).iterdir()))
            self.assertEqual(0,core._ftp_manager.active_count)
            self.assertFalse({b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} & set(server.verbs))
            self.assertEqual(baseline,server.files)
            self.assertFalse(core.game_library.path.exists())
            core.close()

    def test_managed_remote_stream_releases_lease_without_mutation(self):self.wire_case('success')
    def test_managed_remote_cancel_releases_lease_without_ready(self):self.wire_case('cancel')
    def test_managed_remote_changed_hash_releases_lease_and_cleans(self):self.wire_case('changed')


class CleanupAdmissionCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.f=AdmissionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.result=self.f.prepare(self.f.authorize()).result
        self.service=self.f.core._import_preparation
        self.owner=self.service._ready[self.result.snapshot_id][0]

    def cleanup_race(self, fail=False):
        if fail:(self.f.parent/self.owner.name/'unrelated').write_text('preserve')
        started=threading.Event();release=threading.Event();outcomes=[];errors=[]
        real=self.owner.cleanup
        def paused():
            started.set()
            if not release.wait(5):raise RuntimeError('test timeout')
            return real()
        def discard():
            try:outcomes.append(self.f.core.discard_managed_snapshots(self.result))
            except BaseException as exc:errors.append(exc)
        with patch.object(self.owner,'cleanup',side_effect=paused) as cleanup:
            thread=threading.Thread(target=discard);thread.start()
            try:
                self.assertTrue(started.wait(5))
                self.assertIn(self.result.snapshot_id,self.service._ready)
                with self.assertRaises(SnapshotError):self.f.authorize()
                with self.assertRaises(SnapshotError):self.f.core.discard_managed_snapshots(self.result)
                self.assertEqual(1,cleanup.call_count)
            finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual([],errors)
        self.assertEqual([not fail],outcomes)
        return self.service.cleanup_evidence

    def test_pending_cleanup_refuses_concurrent_preparation_and_repeated_discard(self):
        evidence=self.cleanup_race()
        self.assertEqual('discarded',evidence.status);self.assertTrue(evidence.cleanup_complete)
        self.assertFalse(self.service._ready)
        later=self.f.prepare(self.f.authorize())
        self.assertEqual('succeeded',later.state,later.error)
        self.assertTrue(self.f.core.discard_managed_snapshots(later.result))

    def test_uncertain_cleanup_retains_ownership_and_preserves_unrelated_content(self):
        evidence=self.cleanup_race(fail=True)
        self.assertEqual('cleanup-uncertain',evidence.status);self.assertFalse(evidence.cleanup_complete)
        self.assertTrue(self.service._cleanup_blocked)
        self.assertIn(self.result.snapshot_id,self.service._ready)
        with self.assertRaises(SnapshotError):self.f.authorize()
        with self.assertRaises(SnapshotError):self.f.core.discard_managed_snapshots(self.result)
        path=self.f.parent/self.owner.name/'unrelated'
        self.assertEqual('preserve',path.read_text())
        with patch.object(self.owner,'cleanup',side_effect=AssertionError('no retry')):
            self.f.core.close()
        self.assertEqual('preserve',path.read_text())

    def test_cancellation_during_discard_keeps_blocking_uncertainty(self):
        with patch.object(self.owner,'cleanup',side_effect=JobCancelled()):
            with self.assertRaises(JobCancelled):self.f.core.discard_managed_snapshots(self.result)
        self.assertFalse(self.service.cleanup_evidence.cleanup_complete)
        self.assertEqual('cleanup-uncertain',self.service.cleanup_evidence.status)
        self.assertTrue(self.service._cleanup_blocked)
        with self.assertRaises(SnapshotError):self.f.authorize()
        self.assertIn(self.result.snapshot_id,self.service._ready)
        self.owner.cleanup()  # Test fixture disposal only, not a production retry.

    def test_shutdown_does_not_race_active_discard(self):
        real=self.owner.cleanup;started=threading.Event();release=threading.Event()
        def paused():started.set();release.wait(5);return real()
        with patch.object(self.owner,'cleanup',side_effect=paused) as cleanup:
            thread=threading.Thread(target=lambda:self.f.core.discard_managed_snapshots(self.result));thread.start()
            try:
                self.assertTrue(started.wait(5));self.f.core.close()
                self.assertEqual(1,cleanup.call_count)
                with self.assertRaises(SnapshotError):self.f.authorize()
            finally:release.set();thread.join(5)
        self.assertTrue(self.service.cleanup_evidence.cleanup_complete)

    def test_preparation_cleanup_interruption_reports_uncertainty_not_ready(self):
        self.f.core.discard_managed_snapshots(self.result)
        tx=replace(self.f.tx,items=(replace(self.f.tx.items[0],sha256='f'*64),))
        target=self.f.review(tx);auth=self.f.core.confirm_managed_snapshots(target,confirmed=True)
        owners=[];real=OwnedSnapshots.cleanup
        def interrupted(owner):owners.append(owner);raise JobCancelled()
        with patch.object(OwnedSnapshots,'cleanup',interrupted):result=self.f.prepare(auth)
        self.assertEqual('failed',result.state)
        self.assertNotEqual('snapshots-ready',result.result.status)
        self.assertFalse(result.result.cleanup_complete)
        self.assertTrue(self.service._cleanup_blocked)
        with self.assertRaises(SnapshotError):self.f.authorize()
        for owner in owners:real(owner)


class DiskAllocationCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.f=SnapshotTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tx=replace(self.f.tx,budgets=replace(self.f.tx.budgets,temporary_disk_limit=1048576))
        self.owner=OwnedSnapshots(self.f.parent,self.tx);self.addCleanup(self.owner.cleanup)
        self.fd=self.owner.create(1);self.addCleanup(os.close,self.fd)
        self.unit=os.fstatvfs(self.owner.directory).f_frsize

    def fill_to_last_block(self):
        count=self.owner.limit-self.owner.measure()-self.unit
        while count:
            block=b'x'*min(CHUNK_BYTES,count);self.owner.write(self.fd,block);count-=len(block)
        self.owner.write(self.fd,b'x')
        self.assertEqual(self.owner.limit,self.owner.measure())

    def test_fragmented_writes_reuse_existing_allocation(self):
        base=self.owner.measure()
        for unused in range(23):self.owner.write(self.fd,b'x')
        self.assertEqual(23,self.owner.written)
        self.assertEqual(base+self.unit,self.owner.measure())

    def test_one_byte_append_at_valid_one_mib_allocation_boundary(self):
        self.fill_to_last_block();before=self.owner.measure()
        self.owner.write(self.fd,b'y')
        self.assertEqual(before,self.owner.measure())
        self.assertEqual(os.fstat(self.fd).st_size,self.owner.written)

    def test_exact_limit_then_one_byte_into_next_block_is_refused(self):
        self.fill_to_last_block()
        self.owner.write(self.fd,b'x'*(self.unit-1))
        self.assertEqual(self.owner.limit,self.owner.measure())
        size=os.fstat(self.fd).st_size
        with self.assertRaisesRegex(SnapshotError,'allowance'):self.owner.write(self.fd,b'y')
        self.assertEqual(size,os.fstat(self.fd).st_size)
        self.assertEqual(self.owner.limit,self.owner.peak)

    def test_crossing_into_a_new_block_charges_it_once(self):
        base=self.owner.measure();self.owner.write(self.fd,b'x'*(self.unit-1))
        self.owner.write(self.fd,b'yz')
        self.assertEqual(base+2*self.unit,self.owner.measure())
        self.assertEqual(self.unit+1,self.owner.written)

    def test_partial_write_then_error_preserves_logical_and_allocated_evidence(self):
        real=os.write;calls=[]
        def partial(fd,data):
            if calls:raise OSError(errno.ENOSPC,'full')
            calls.append(True);return real(fd,data[:3])
        with patch('c64u_browser.import_snapshots.os.write',side_effect=partial):
            with self.assertRaises(OSError):self.owner.write(self.fd,b'abcdef')
        self.assertEqual(3,self.owner.written)
        self.assertGreaterEqual(self.owner.peak,os.fstat(self.fd).st_blocks*512)

    def test_exception_after_write_side_effect_is_accounted(self):
        real=os.write
        def side_effect(fd,data):real(fd,data[:2]);raise OSError(errno.ENOSPC,'full')
        with patch('c64u_browser.import_snapshots.os.write',side_effect=side_effect):
            with self.assertRaises(OSError):self.owner.write(self.fd,b'abcdef')
        self.assertEqual(2,self.owner.written)
        self.assertGreaterEqual(self.owner.peak,os.fstat(self.fd).st_blocks*512)

    def test_different_allocation_units_and_missing_or_delayed_block_evidence(self):
        from types import SimpleNamespace as Info
        for unit in (1024,4096,65536):
            for info in (Info(st_size=unit+1),Info(st_size=unit+1,st_blocks=0),Info(st_size=unit+1,st_blocks=-1)):
                self.assertEqual(2*unit,self.owner._footprint(info,unit))
            self.assertEqual(3*unit,self.owner._footprint(Info(st_size=unit+1,st_blocks=3*unit//512),unit))
        self.assertTrue(self.owner.conservative)

    def test_filesystem_block_size_fallback_and_unknown_unit_refusal(self):
        from types import SimpleNamespace as Info
        with patch('c64u_browser.import_snapshots.os.fstatvfs',return_value=Info(f_frsize=0,f_bsize=16384)):
            self.assertEqual(16384,self.owner._allocation_unit()[1])
        with patch('c64u_browser.import_snapshots.os.fstatvfs',return_value=Info(f_frsize=0,f_bsize=0)):
            with self.assertRaises(SnapshotError):self.owner._allocation_unit()

    def test_actual_allocation_exceeding_estimate_is_observed_and_refused(self):
        real=os.write;self.owner.limit=self.owner.measure()+self.unit
        def preallocated(fd,data):
            count=real(fd,data);os.posix_fallocate(fd,0,2*self.unit);return count
        with patch('c64u_browser.import_snapshots.os.write',side_effect=preallocated):
            with self.assertRaises(SnapshotError):self.owner.write(self.fd,b'x')
        self.assertGreater(self.owner.peak,self.owner.limit)
        self.assertGreaterEqual(self.owner.peak,os.fstat(self.fd).st_blocks*512)

    def test_cleanup_interruption_never_claims_success(self):
        self.owner.write(self.fd,b'x')
        with patch('c64u_browser.import_snapshots.os.unlink',side_effect=JobCancelled()):
            with self.assertRaises(JobCancelled):self.owner.cleanup()
        self.assertTrue(self.owner.closed)
        self.assertFalse(self.owner.cleaned)
        self.assertFalse(self.owner.cleanup())


class InitializationCleanupCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.f=AdmissionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.before_preferences=self.f.core.preferences.path.read_bytes()
        self.before_manifest=self.f.f.read.return_value
        self.service=self.f.core._import_preparation

    def tearDown(self):
        self.assertEqual(self.before_preferences,self.f.core.preferences.path.read_bytes())
        self.assertEqual(self.before_manifest,self.f.f.read.return_value)
        self.assertFalse(self.f.core.game_library.path.exists())

    def run_failure(self):
        result=self.f.prepare(self.f.authorize())
        self.assertNotEqual('succeeded',result.state)
        self.assertNotEqual('snapshots-ready',result.result.status)
        return result

    def assert_blocked(self,result):
        self.assertFalse(result.result.cleanup_complete)
        self.assertTrue(self.service._cleanup_blocked)
        self.assertEqual(result.result,self.service.cleanup_evidence)
        with self.assertRaises(SnapshotError):self.f.authorize()
        with self.assertRaises(SnapshotError):self.f.core.discard_managed_snapshots(result.result)

    def test_failure_before_directory_creation_reports_proven_safe_cleanup(self):
        with patch('c64u_browser.import_snapshots.open_directory',side_effect=PermissionError('parent denied')):
            result=self.run_failure()
        self.assertTrue(result.result.cleanup_complete)
        self.assertEqual('PermissionError',result.result.failure.primary_error)
        self.assertEqual('',result.result.failure.directory)
        self.assertFalse(self.service._cleanup_blocked)
        self.assertEqual([],list(self.f.parent.glob('argonaut-snapshots-*')))
        self.assertTrue(self.f.review())

    def test_unknown_failure_before_owner_return_never_assumes_cleanup_success(self):
        with patch('c64u_browser.import_snapshots.OwnedSnapshots',side_effect=RuntimeError('constructor unavailable')):
            result=self.run_failure()
        self.assert_blocked(result)
        self.assertEqual('RuntimeError',result.result.failure.primary_error)
        self.assertIsNone(self.service._uncertain_owner)

    def test_setup_failure_after_directory_creation_cleans_once_and_releases_admission(self):
        original=OwnedSnapshots.cleanup;calls=[]
        def cleanup(owner):calls.append(owner.name);return original(owner)
        with patch.object(OwnedSnapshots,'measure',side_effect=SnapshotError('allocation-setup','unavailable')), patch.object(OwnedSnapshots,'cleanup',cleanup):
            result=self.run_failure()
        self.assertEqual(1,len(calls))
        self.assertEqual('allocation-setup',result.error.code)
        self.assertTrue(result.result.cleanup_complete)
        self.assertEqual('initialization',result.result.failure.phase)
        self.assertTrue(result.result.failure.directory_identity)
        self.assertFalse(Path(result.result.failure.directory).exists())
        self.assertTrue(self.f.review())

    def test_exact_allocation_failure_then_interrupted_directory_removal(self):
        def allocation(owner):
            owner.peak=1234;owner.conservative=True
            raise SnapshotError('allocation-setup','unavailable')
        with patch.object(OwnedSnapshots,'measure',allocation),patch('c64u_browser.import_snapshots.os.rmdir',side_effect=JobCancelled()) as remove:
            result=self.run_failure()
        self.assertEqual(1,remove.call_count)
        self.assertEqual('failed',result.state);self.assertEqual('allocation-setup',result.error.code)
        self.assert_blocked(result)
        evidence=result.result
        self.assertEqual(('SnapshotError','JobCancelled'),(evidence.failure.primary_error,evidence.failure.cleanup_error))
        self.assertEqual(1234,evidence.accounting.temporary_disk_peak_bytes)
        self.assertEqual('conservative-rounded',evidence.disk_accounting)
        self.assertTrue(Path(evidence.failure.directory).is_dir())
        self.assertIsNotNone(self.service._uncertain_owner)
        with patch.object(OwnedSnapshots,'cleanup',side_effect=AssertionError('uncertain cleanup retried')):
            self.f.core.close()
        self.assertTrue(self.service._cleanup_blocked)
        self.assertEqual(evidence,self.service.cleanup_evidence)

    def test_secondary_cleanup_exception_preserves_primary_and_open_owner(self):
        primary=SnapshotError('allocation-setup','primary failure')
        with patch.object(OwnedSnapshots,'measure',side_effect=primary),patch.object(OwnedSnapshots,'cleanup',side_effect=OSError(errno.EIO,'cleanup failure')) as cleanup:
            result=self.run_failure()
        self.assertEqual(1,cleanup.call_count)
        self.assertEqual('allocation-setup',result.error.code)
        self.assert_blocked(result)
        self.assertEqual('OSError',result.result.failure.cleanup_error)
        self.assertEqual(errno.EIO,result.result.failure.cleanup_errno)
        self.assertIs(primary.snapshot_owner,self.service._uncertain_owner)
        self.assertIsInstance(primary.snapshot_cleanup_error,OSError)
        self.service._uncertain_owner.cleanup()  # Fixture disposal after assertions only.

    def test_primary_cancellation_is_not_replaced_by_secondary_exception(self):
        with patch.object(OwnedSnapshots,'measure',side_effect=JobCancelled()),patch.object(OwnedSnapshots,'cleanup',side_effect=RuntimeError('secondary')):
            result=self.run_failure()
        self.assertEqual('cancelled',result.state)
        self.assert_blocked(result)
        self.assertEqual(('JobCancelled','RuntimeError'),(result.result.failure.primary_error,result.result.failure.cleanup_error))
        self.service._uncertain_owner.cleanup()

    def test_partial_file_creation_failure_preserves_bytes_and_ownership(self):
        original=OwnedSnapshots.create
        def create(owner,ordinal):
            fd=original(owner,ordinal)
            try:os.write(fd,b'partial')
            finally:os.close(fd)
            raise OSError(errno.EIO,'after partial creation')
        with patch.object(OwnedSnapshots,'create',create):result=self.run_failure()
        self.assertTrue(result.result.cleanup_complete)
        self.assertEqual(7,result.result.host_bytes_written)
        self.assertGreater(result.result.accounting.temporary_disk_peak_bytes,0)
        self.assertEqual(1,len(result.result.failure.owned_files))
        self.assertFalse(Path(result.result.failure.directory).exists())
        self.assertTrue(self.f.review())

    def test_unrelated_content_survives_initialization_cleanup(self):
        def allocation(owner):
            fd=os.open('unrelated',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=owner.directory)
            try:os.write(fd,b'preserve')
            finally:os.close(fd)
            raise SnapshotError('allocation-setup','unavailable')
        with patch.object(OwnedSnapshots,'measure',allocation):result=self.run_failure()
        self.assert_blocked(result)
        path=Path(result.result.failure.directory)/'unrelated'
        self.assertEqual(b'preserve',path.read_bytes())
        self.f.core.close();self.assertEqual(b'preserve',path.read_bytes())
