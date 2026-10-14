"""Owner-controlled persistence, cancellation, terminal and closure fault tests."""
import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from c64u_browser.evidence_lifecycle import EvidenceLifecycle, _LIVE_OWNERS
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding
from c64u_browser.required_evidence import EvidenceDirectory, EvidenceFailure, RequiredEvidence
from test_managed_rename_boundary import Sink


class LifecycleTests(unittest.TestCase):
    def owner(self, sink=None):
        session = DeviceSession('fixture-device', 'session')
        scheduler = CoreScheduler(lambda: session)
        core = SimpleNamespace(device_session=lambda: session, scheduler=scheduler,
                               _ftp_manager=SimpleNamespace(active_count=0), close_calls=0)
        def close(): core.close_calls += 1; scheduler.close()
        core.close = close
        self.addCleanup(scheduler.close)
        owner = EvidenceLifecycle(core, sink or Sink())
        # Tests explicitly release their inert registry references, never production resources.
        self.addCleanup(lambda: _LIVE_OWNERS.pop(id(owner), None))
        return owner

    def drain(self, owner):
        with owner.core.scheduler._lock: queues = tuple(owner.core.scheduler._lanes.values())
        for queue in queues: queue.join()

    def test_real_core_managed_lease_and_durable_lifecycle(self):
        from test_ftp_reads import ReadMigrationTests
        from c64u_ftp_server import FakeC64UFtp
        from c64u_browser.ftp_reads import adapter_for
        with FakeC64UFtp(files={b'/USB1/a': b'abc'},
                directories={b'/': b'type=dir; USB1\r\n', b'/USB1': b''}, mutation_tree=True) as server:
            core, profile = ReadMigrationTests.core(self, server)
            core.connect(profile, remote_folder='/USB1')
            with tempfile.TemporaryDirectory() as tmp:
                store = EvidenceDirectory(Path(tmp)/'evidence')
                self.addCleanup(store.close)
                owner = EvidenceLifecycle(core, store)
                self.addCleanup(lambda: _LIVE_OWNERS.pop(id(owner), None))
                def work(job, control):
                    adapter = adapter_for(core._client)
                    with adapter.operation(job.check_cancel):
                        rename = adapter.begin_evidenced_rename('/USB1/a', '/USB1/b', control.evidence)
                        control.observe_ftp(adapter, 'rnfr-accepted')
                        rename.continue_rename()
                        control.observe_ftp(adapter, 'rnto-accepted')
                        self.assertTrue(rename.verified)
                    return True
                owner.start('offline-rename-fixture', work)
                self.assertEqual(owner.wait(2).state, 'succeeded')
                self.drain(owner); owner.close()
                self.assertTrue(owner.complete)
                records = [json.loads(p.read_bytes()) for p in sorted(store.path.iterdir())]
                ownership = [r['value'] for r in records if r['kind'] == 'ftp-ownership']
                self.assertEqual(len(ownership), 2)
                self.assertEqual(ownership[0]['ftp_session_id'], ownership[1]['ftp_session_id'])
                self.assertEqual(ownership[0]['core_session_id'], owner.session.session_id)
                self.assertEqual(ownership[0]['active_count'], 1)
                self.assertTrue(all(r['independent_release'] == 'unverified' for r in ownership))
                self.assertEqual(server.files[b'/USB1/b'], b'abc')

    def test_terminal_persisted_before_close(self):
        sink = Sink(); owner = self.owner(sink)
        owner.start('fixture', lambda job, control: 'ok')
        owner.wait(2); self.drain(owner); owner.close()
        kinds = [k for k, v in sink.records]
        self.assertLess(kinds.index('job-registration'), kinds.index('job-submission-intent'))
        self.assertLess(kinds.index('job-terminal'), kinds.index('core-close-intent'))
        self.assertTrue(owner.complete)
        self.assertEqual(owner.core.close_calls, 1)
        self.assertEqual(sink.records[-1][1]['independent_scheduler_release'], 'unverified')

    def test_terminal_listener_failure_cannot_replace_owner_persistence(self):
        owner = self.owner(); gate = threading.Event()
        job = owner.start('fixture', lambda job, control: gate.wait(2))
        def fail(event): raise OSError('best effort listener')
        job.add_listener(fail); gate.set()
        self.assertEqual(owner.wait(2).state, 'succeeded')
        self.assertTrue(owner.terminal_saved)
        self.drain(owner); owner.close()

    def test_terminal_write_failure_blocks_close_and_retains_owner(self):
        owner = self.owner(Sink(fail='job-terminal'))
        owner.start('fixture', lambda job, control: None)
        with self.assertRaises(OSError): owner.wait(2)
        with self.assertRaises(EvidenceFailure): owner.close()
        self.assertIs(_LIVE_OWNERS[id(owner)], owner)
        self.assertEqual(owner.core.close_calls, 0)
        self.assertFalse(owner.terminal_saved)

    def test_registration_failure_never_submits(self):
        for kind in ('operation-admission', 'job-registration', 'job-submission-intent'):
            with self.subTest(kind=kind):
                owner = self.owner(Sink(fail=kind)); invoked = []
                with self.assertRaises(OSError): owner.start('fixture', lambda *args: invoked.append(True))
                self.assertEqual(invoked, [])
                self.assertEqual(len(owner.core.scheduler._jobs), 0)
                with self.assertRaises(EvidenceFailure): owner.close()

    def test_timeout_does_not_classify_terminal_or_close(self):
        owner = self.owner(); gate = threading.Event(); self.addCleanup(gate.set)
        owner.start('fixture', lambda *args: gate.wait(2))
        with self.assertRaises(TimeoutError): owner.wait(0)
        with self.assertRaises(EvidenceFailure): owner.close()
        gate.set(); owner.wait(2); self.drain(owner); owner.close()

    def test_worker_interrupt_becomes_failed_not_hung_or_successful(self):
        owner = self.owner()
        def work(*args): raise KeyboardInterrupt()
        owner.start('fixture', work)
        self.assertEqual(owner.wait(2).state, 'failed')
        self.assertEqual(owner.interruption, 'KeyboardInterrupt')
        self.drain(owner); owner.close()

    def test_cancellation_intent_and_result_then_real_terminal(self):
        owner = self.owner(); gate = threading.Event()
        def work(job, control): gate.wait(2); job.check_cancel()
        owner.start('fixture', work)
        self.assertTrue(owner.request_cancel()); gate.set()
        self.assertEqual(owner.wait(2).state, 'cancelled')
        kinds = [k for k, v in owner.evidence.sink.records]
        self.assertLess(kinds.index('cancellation-intent'), kinds.index('cancellation-result'))
        self.assertLess(kinds.index('cancellation-result'), kinds.index('job-terminal'))
        self.drain(owner); owner.close()

    def test_cancellation_persistence_failure_retains_owner(self):
        owner = self.owner(Sink(fail='cancellation-result')); gate = threading.Event()
        def work(job, control): gate.wait(2); job.check_cancel()
        job = owner.start('fixture', work)
        with self.assertRaises(OSError): owner.request_cancel()
        gate.set(); self.assertEqual(job.wait(2).state, 'cancelled')
        with self.assertRaises(EvidenceFailure): owner.close()

    def test_close_result_failure_cannot_claim_complete_or_close_twice(self):
        owner = self.owner(Sink(fail='core-close-result'))
        owner.start('fixture', lambda *args: None); owner.wait(2); self.drain(owner)
        with self.assertRaises(OSError): owner.close()
        self.assertTrue(owner.closed); self.assertFalse(owner.complete)
        with self.assertRaises(EvidenceFailure): owner.close()
        self.assertEqual(owner.core.close_calls, 1)

    def test_active_ftp_observation_blocks_close(self):
        owner = self.owner(); owner.start('fixture', lambda *args: None)
        owner.wait(2); self.drain(owner); owner.core._ftp_manager.active_count = 1
        with self.assertRaises(EvidenceFailure): owner.close()
        self.assertEqual(owner.core.close_calls, 0)

    def test_one_admission_only(self):
        owner = self.owner(); owner.start('fixture', lambda *args: None)
        with self.assertRaises(EvidenceFailure): owner.start('second', lambda *args: None)
        owner.wait(2); self.drain(owner); owner.close()

    def test_busy_lane_refuses_without_nested_deadlock(self):
        owner = self.owner(); gate = threading.Event()
        held = owner.core.scheduler.submit(CoreJob('held', lambda job: gate.wait(2)),
                                         JobBinding.device(owner.session))
        try:
            with self.assertRaises(Exception): owner.start('fixture', lambda *args: None)
            self.assertEqual(owner.submission, 'possible')
            self.assertFalse(owner.terminal_saved)
        finally: gate.set(); held.wait(2)

    def test_close_error_is_recorded_not_success(self):
        owner = self.owner(); owner.start('fixture', lambda *args: None)
        owner.wait(2); self.drain(owner)
        def fail(): raise OSError('close failed')
        owner.core.close = fail
        with self.assertRaises(OSError): owner.close()
        self.assertFalse(owner.complete)
        self.assertFalse(owner.evidence.sink.records[-1][1]['returned'])
        with self.assertRaises(EvidenceFailure): owner.close()


class DurableStoreTests(unittest.TestCase):
    def store(self, **kw):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        store = EvidenceDirectory(Path(directory.name)/'evidence', **kw)
        self.addCleanup(store.close)
        return store

    def test_exclusive_private_files_and_exact_receipt(self):
        store = self.store(); channel = RequiredEvidence(store)
        receipt = channel.save('observation', dict(value='literal'))
        raw = (store.path/receipt.name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt.sha256)
        self.assertEqual(os.stat(store.path/receipt.name).st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError): EvidenceDirectory(store.path)

    def test_short_writes_complete_before_receipt(self):
        store = self.store(); real_write = os.write
        with patch('c64u_browser.required_evidence.os.write', side_effect=lambda fd, data: real_write(fd, data[:3])):
            receipt = RequiredEvidence(store).save('test', dict(value='long-enough'))
        self.assertEqual(json.loads((store.path/receipt.name).read_bytes())['value']['value'], 'long-enough')

    def test_zero_write_poison_no_receipt(self):
        store = self.store(); channel = RequiredEvidence(store)
        with patch('c64u_browser.required_evidence.os.write', return_value=0):
            with self.assertRaises(EvidenceFailure): channel.save('test', {})
        self.assertTrue(channel.blocked); self.assertEqual(channel.receipts, [])

    def test_each_fsync_failure_poison(self):
        for index in range(3):
            store = self.store(); channel = RequiredEvidence(store); calls = []
            real_sync = os.fsync
            def sync(fd):
                calls.append(fd)
                if len(calls) == index+1: raise OSError('sync failed')
                real_sync(fd)
            with patch('c64u_browser.required_evidence.os.fsync', side_effect=sync):
                with self.assertRaises(OSError): channel.save('test', {})
            self.assertTrue(store.blocked); self.assertEqual(channel.receipts, [])

    def test_existing_checkpoint_not_overwritten(self):
        store = self.store(); path = store.path/'000000-test.json'; path.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError): RequiredEvidence(store).save('test', {})
        self.assertEqual(path.read_bytes(), b'preserve')

    def test_capacity_bound_and_no_silent_increase(self):
        store = self.store(byte_limit=1)
        with self.assertRaises(EvidenceFailure): store.save('test', {})
        self.assertEqual(list(store.path.iterdir()), [])
        with self.assertRaises(EvidenceFailure): self.store(byte_limit=16*1024*1024+1)

    def test_bad_receipt_propagates_and_blocks(self):
        channel = RequiredEvidence(SimpleNamespace(save=lambda *args: None))
        with self.assertRaises(EvidenceFailure): channel.save('test', {})
        self.assertTrue(channel.blocked)

    def test_changed_directory_identity_refused(self):
        store = self.store(); store.path.rename(store.path.with_name('moved')); store.path.mkdir(mode=0o700)
        with self.assertRaises(EvidenceFailure): store.save('test', {})
        self.assertEqual(list(store.path.iterdir()), [])


if __name__ == '__main__': unittest.main()
