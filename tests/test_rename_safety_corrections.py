"""PA-5.1AR counterexamples plus deterministic dispatch linearization tests."""
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from c64u_browser.evidence_lifecycle import EvidenceLifecycle, _LIVE_OWNERS
from c64u_browser.jobs import JobCancelled
from c64u_browser.scheduler import CoreScheduler, DeviceSession
from c64u_browser.required_evidence import EvidenceDirectory, EvidenceFailure, RequiredEvidence
from c64u_browser.managed_rename import RenameStopped
from pa51b_fixtures import fixture, MemorySink


class DispatchTests(unittest.TestCase):
    def owner(self, sink):
        session = DeviceSession('inspection-device', 'inspection-session')
        scheduler = CoreScheduler(lambda: session)
        core = SimpleNamespace(device_session=lambda: session, scheduler=scheduler,
                               _ftp_manager=SimpleNamespace(active_count=0), close_calls=0)
        def close(): core.close_calls += 1; scheduler.close()
        core.close = close
        owner = EvidenceLifecycle(core, sink)
        self.addCleanup(scheduler.close)
        self.addCleanup(lambda: _LIVE_OWNERS.pop(id(owner), None))
        return owner

    def work(self, adapter, handles):
        def run(job, owner):
            with adapter.operation(job.check_cancel):
                handle = adapter.begin_evidenced_rename('/from', '/to', owner.evidence)
                handles.append(handle)
                handle.continue_rename()
        return run

    def drain(self, owner):
        for queue in tuple(owner.core.scheduler._lanes.values()): queue.join()

    def test_completed_required_failure_before_wire_stops_both_commands(self):
        for verb in ('RNFR', 'RNTO'):
            for phase in ('cancellation-intent', 'cancellation-result', 'independent-required-save'):
                with self.subTest(verb=verb, phase=phase):
                    reached, release = threading.Event(), threading.Event()
                    def diagnostic(event):
                        if event.get('kind') == 'command' and event.get('verb') == verb:
                            reached.set(); self.assertTrue(release.wait(3))
                    with fixture(diagnostic=diagnostic) as (peer, adapter, current):
                        owner = self.owner(MemorySink(fail=phase)); handles = []
                        job = owner.start('race', self.work(adapter, handles))
                        try:
                            self.assertTrue(reached.wait(3))
                            with self.assertRaises(OSError):
                                if phase == 'independent-required-save': owner.evidence.save(phase, {})
                                else: owner.request_cancel()
                            self.assertTrue(owner.evidence.blocked)
                        finally: release.set()
                        self.assertEqual(job.wait(3).state, 'failed'); self.drain(owner)
                        self.assertEqual(peer.mutations, [] if verb == 'RNFR' else [b'RNFR /from\r\n'])
                        h = next(iter(adapter._rename_owners.values()))
                        observation = h.rnfr if verb == 'RNFR' else h.rnto
                        self.assertFalse(observation.submitted); self.assertFalse(h.verified)
                        self.assertIs(_LIVE_OWNERS[id(owner)], owner)
                        with self.assertRaises(EvidenceFailure): owner.close()
                        self.assertEqual(owner.core.close_calls, 0)
                        self.assertEqual(peer.connected, 1)

    def test_inflight_persistence_failure_wins_before_dispatch_lock(self):
        at_command, release_command = threading.Event(), threading.Event()
        saving, release_save, gate_attempt = threading.Event(), threading.Event(), threading.Event()
        def diagnostic(event):
            if event.get('verb') == 'RNTO': at_command.set(); self.assertTrue(release_command.wait(3))
        def hook(kind, value):
            if kind == 'fault': saving.set(); self.assertTrue(release_save.wait(3))
        with fixture(diagnostic=diagnostic) as (peer, adapter, current):
            owner = self.owner(MemorySink(fail='fault', hook=hook)); handles = []; errors = []
            original = owner.evidence.dispatch
            @contextmanager
            def dispatch(validate):
                if at_command.is_set(): gate_attempt.set()
                with original(validate): yield
            with patch.object(owner.evidence, 'dispatch', dispatch):
                job = owner.start('race', self.work(adapter, handles))
                self.assertTrue(at_command.wait(3))
                def fail():
                    try: owner.evidence.save('fault', {})
                    except OSError as exc: errors.append(exc)
                writer = threading.Thread(target=fail); writer.start()
                try:
                    self.assertTrue(saving.wait(3)); release_command.set()
                    self.assertTrue(gate_attempt.wait(3))
                    self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])
                finally: release_command.set(); release_save.set()
                writer.join(3); self.assertFalse(writer.is_alive())
                self.assertEqual(job.wait(3).state, 'failed'); self.drain(owner)
            self.assertEqual(len(errors), 1)
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])
            self.assertFalse(handles[0].rnto.submitted)

    def test_submission_wins_then_failure_preserves_possible_effects(self):
        in_send, release_send, failed = threading.Event(), threading.Event(), threading.Event()
        with fixture() as (peer, adapter, current):
            owner = self.owner(MemorySink(fail='fault')); handles = []; errors = []
            send, recv = peer.sendall, peer.recv
            def sendall(raw):
                send(raw)
                if raw.startswith(b'RNTO '): in_send.set(); self.assertTrue(release_send.wait(3))
            def receive(n):
                if in_send.is_set(): self.assertTrue(failed.wait(3))
                return recv(n)
            peer.sendall, peer.recv = sendall, receive
            job = owner.start('race', self.work(adapter, handles))
            self.assertTrue(in_send.wait(3))
            self.assertFalse(owner.evidence._lock.acquire(blocking=False))
            attempted = threading.Event()
            def fail():
                attempted.set()
                try: owner.evidence.save('fault', {})
                except OSError as exc: errors.append(exc)
                finally: failed.set()
            writer = threading.Thread(target=fail); writer.start()
            try: self.assertTrue(attempted.wait(3)); self.assertFalse(failed.is_set())
            finally: release_send.set()
            writer.join(3); self.assertFalse(writer.is_alive())
            self.assertEqual(job.wait(3).state, 'failed'); self.drain(owner)
            self.assertEqual(len(errors), 1)
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n', b'RNTO /to\r\n'])
            self.assertTrue(handles[0].rnto.submitted)
            self.assertTrue(handles[0].rnto.remote_effects_possible)
            self.assertFalse(handles[0].verified)

    def test_cancellation_after_submission_cannot_undo_command(self):
        for reply in (b'250 Exact to\r\n', None):
            with self.subTest(reply=reply), fixture({b'RNTO': reply}) as (peer, adapter, current):
                owner = self.owner(MemorySink()); handles = []
                sent, release, cancelled = threading.Event(), threading.Event(), threading.Event()
                send, recv = peer.sendall, peer.recv
                def sendall(raw):
                    send(raw)
                    if raw.startswith(b'RNTO '): sent.set(); self.assertTrue(release.wait(3))
                def receive(n):
                    if sent.is_set(): self.assertTrue(cancelled.wait(3))
                    return recv(n)
                peer.sendall, peer.recv = sendall, receive
                job = owner.start('cancel-race', self.work(adapter, handles))
                self.assertTrue(sent.wait(3)); attempted = threading.Event(); results = []
                def cancel():
                    attempted.set()
                    try: results.append(owner.request_cancel())
                    finally: cancelled.set()
                thread = threading.Thread(target=cancel); thread.start()
                try: self.assertTrue(attempted.wait(3)); self.assertFalse(cancelled.is_set())
                finally: release.set()
                thread.join(3); self.assertFalse(thread.is_alive())
                snapshot = owner.wait(3); self.drain(owner)
                self.assertEqual(results, [True]); self.assertTrue(handles[0].rnto.submitted)
                self.assertEqual(handles[0].rnfr.ftp_session_id, handles[0].rnto.ftp_session_id)
                self.assertEqual(peer.mutations, [b'RNFR /from\r\n', b'RNTO /to\r\n'])
                self.assertEqual(handles[0].verified, reply is not None)
                self.assertEqual(snapshot.state, 'succeeded' if reply else 'cancelled')
                if reply is None:self.assertTrue(handles[0].rnto.remote_effects_possible)
                kinds = [v['kind'] for v in owner.evidence.sink.records]
                self.assertIn('cancellation-result', kinds); self.assertIn('rnto-outcome', kinds)

    def test_cancellation_listener_runs_outside_dispatch_lock(self):
        reached, release = threading.Event(), threading.Event()
        def diagnostic(event):
            if event.get('verb') == 'RNTO': reached.set(); self.assertTrue(release.wait(3))
        with fixture(diagnostic=diagnostic) as (peer, adapter, current):
            owner = self.owner(MemorySink()); handles = []
            job = owner.start('listener', self.work(adapter, handles))
            self.assertTrue(reached.wait(3)); terminals = []
            def listener(event):
                if event.kind == 'cancel-requested':
                    release.set(); terminals.append(job.wait(2).state)
            job.add_listener(listener)
            try: self.assertTrue(owner.request_cancel())
            finally: release.set()
            self.assertEqual(owner.wait(3).state, 'cancelled'); self.drain(owner)
            self.assertEqual(terminals, ['cancelled'])
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])

    def test_session_revalidation_after_diagnostic_before_dispatch(self):
        with fixture() as (peer, adapter, current):
            def diagnostic(event):
                if event.get('verb') == 'RNTO':current[0] = replace(current[0], core_session_id='stale')
            adapter._manager._diagnostic = diagnostic
            with self.assertRaises(Exception), adapter.operation():
                h = adapter.begin_evidenced_rename('/from', '/to', MemorySink()); h.continue_rename()
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n']); self.assertFalse(h.verified)
            self.assertFalse(h.rnto.submitted)

    def test_send_failure_after_boundary_is_unknown_and_not_retried(self):
        with fixture() as (peer, adapter, current):
            send = peer.sendall
            def sendall(raw):
                send(raw)
                if raw.startswith(b'RNTO '):raise OSError('lost during send')
            peer.sendall = sendall
            with self.assertRaises(RenameStopped), adapter.operation():
                h = adapter.begin_evidenced_rename('/from', '/to', MemorySink()); h.continue_rename()
            self.assertTrue(h.rnto.submitted); self.assertTrue(h.rnto.remote_effects_possible)
            self.assertFalse(h.verified); self.assertEqual(len(peer.mutations), 2)
            with self.assertRaises(RenameStopped): h.continue_rename()
            self.assertEqual(len(peer.mutations), 2); self.assertEqual(peer.connected, 1)


class DeferredCancellationTests(unittest.TestCase):
    def test_ambient_deferral_between_commands_does_not_hide_cancellation(self):
        with fixture() as (peer, adapter, current):
            cancelled = [False]; sink = MemorySink()
            def check():
                if cancelled[0]:raise JobCancelled()
            with adapter.operation(check), adapter.defer_cancellation():
                h = adapter.begin_evidenced_rename('/from', '/to', sink); cancelled[0] = True
                with self.assertRaises(JobCancelled):h.continue_rename()
                self.assertFalse(h.verified)
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])
            self.assertTrue(any(r['kind'] == 'rnfr-outcome' for r in sink.records))
            record = sink.records[-1]
            self.assertEqual(record['kind'], 'rename-cancellation')
            self.assertFalse(record['value']['rnto_submitted'])

    def test_previously_deferred_cancellation_stays_sticky(self):
        with fixture() as (peer, adapter, current):
            cancel = [False]
            def check():
                if cancel[0]:raise JobCancelled()
            with adapter.operation(check), adapter.defer_cancellation():
                h = adapter.begin_evidenced_rename('/from', '/to', MemorySink()); cancel[0] = True
                adapter._context.get().check()  # Legacy path observes and defers.
                cancel[0] = False
                with self.assertRaises(JobCancelled):h.continue_rename()
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])

    def test_cancellation_during_rnfr_preserves_accepted_evidence(self):
        with fixture() as (peer, adapter, current):
            cancel = [False]; sink = MemorySink(); send = peer.sendall
            def check():
                if cancel[0]:raise JobCancelled()
            def sendall(raw):
                send(raw)
                if raw.startswith(b'RNFR '):cancel[0] = True
            peer.sendall = sendall
            with self.assertRaises(JobCancelled), adapter.operation(check), adapter.defer_cancellation():
                adapter.begin_evidenced_rename('/from', '/to', sink)
            h = next(iter(adapter._rename_owners.values()))
            self.assertTrue(h.rnfr.accepted); self.assertEqual(h.rnfr.reply, b'350 Exact from\r\n')
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n']); self.assertFalse(h.verified)
            self.assertEqual([r['kind'] for r in sink.records], ['rnfr-intent', 'rnfr-outcome', 'rename-cancellation'])

    def test_cancellation_at_final_dispatch_gate_never_sends_rnto(self):
        with fixture() as (peer, adapter, current):
            cancel = [False]; sink = MemorySink()
            def check():
                if cancel[0]:raise JobCancelled()
            def diagnostic(event):
                if event.get('verb') == 'RNTO':cancel[0] = True
            adapter._manager._diagnostic = diagnostic
            with self.assertRaises(JobCancelled), adapter.operation(check), adapter.defer_cancellation():
                h = adapter.begin_evidenced_rename('/from', '/to', sink); h.continue_rename()
            self.assertFalse(h.rnto.submitted); self.assertFalse(h.verified)
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n'])
            self.assertEqual(sink.records[-1]['kind'], 'rename-cancellation')

    def test_cancelled_before_rnfr_never_sends(self):
        with fixture() as (peer, adapter, current):
            cancel = [False]
            def check():
                if cancel[0]:raise JobCancelled()
            with adapter.operation(check), adapter.defer_cancellation():
                cancel[0] = True
                with self.assertRaises(JobCancelled):adapter.begin_evidenced_rename('/from', '/to', MemorySink())
            self.assertEqual(peer.mutations, [])


class EvidenceIdentityTests(unittest.TestCase):
    def store(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); parent = root/'parent'; parent.mkdir(mode=0o700)
        store = EvidenceDirectory(parent/'evidence'); self.addCleanup(store.close)
        return root, parent, store

    def test_parent_relocation_before_save_refuses_receipt(self):
        root, parent, store = self.store()
        parent.rename(root/'moved'); parent.mkdir(mode=0o700)
        with self.assertRaises(EvidenceFailure):RequiredEvidence(store).save('inspection', {})
        self.assertTrue(store.blocked); self.assertFalse(store.path.exists())
        self.assertEqual(list((root/'moved'/'evidence').iterdir()), [])

    def test_outcome_directory_substitution_cannot_verify_rename(self):
        root, parent, store = self.store(); moved = parent/'retained'; real_sync = os.fsync; swapped = []
        def fsync(fd):
            if os.readlink('/proc/self/fd/'+str(fd)).endswith('000003-rnto-outcome.json') and not swapped:
                store.path.rename(moved); store.path.mkdir(mode=0o700); swapped.append(True)
            return real_sync(fd)
        with fixture() as (peer, adapter, current), adapter.operation():
            h = adapter.begin_evidenced_rename('/from', '/to', store)
            with patch('c64u_browser.required_evidence.os.fsync', side_effect=fsync):
                with self.assertRaises(EvidenceFailure):h.continue_rename()
            self.assertTrue(swapped); self.assertFalse(h.verified); self.assertTrue(store.blocked)
            self.assertEqual(list(store.path.iterdir()), [])
            self.assertEqual(len(list(moved.iterdir())), 4)
            self.assertTrue(h.rnto.remote_effects_possible)
            self.assertEqual(peer.mutations, [b'RNFR /from\r\n', b'RNTO /to\r\n'])

    def test_location_substitution_at_each_sync_barrier(self):
        for barrier in (1, 2, 3):
            with self.subTest(barrier=barrier):
                root, parent, store = self.store(); real_sync = os.fsync; calls = []
                def fsync(fd):
                    calls.append(fd)
                    if len(calls) == barrier:
                        store.path.rename(parent/'retained'); store.path.mkdir(mode=0o700)
                    return real_sync(fd)
                channel = RequiredEvidence(store)
                with patch('c64u_browser.required_evidence.os.fsync', side_effect=fsync):
                    with self.assertRaises(EvidenceFailure):channel.save('inspection', {})
                self.assertTrue(channel.blocked); self.assertEqual(channel.receipts, [])
                self.assertEqual(len(list((parent/'retained').iterdir())), 1)

    def test_parent_swap_during_write_refuses_receipt(self):
        root, parent, store = self.store(); write = os.write; swapped = []
        def changed(fd, data):
            if not swapped:parent.rename(root/'retained'); parent.mkdir(mode=0o700); swapped.append(True)
            return write(fd, data)
        with patch('c64u_browser.required_evidence.os.write', side_effect=changed):
            with self.assertRaises(EvidenceFailure):store.save('inspection', {})
        self.assertTrue(store.blocked); self.assertFalse(store.path.exists())

    def test_record_substitution_and_hardlink_refuse_receipt(self):
        for mode in ('replace', 'hardlink', 'permissions'):
            with self.subTest(mode=mode):
                root, parent, store = self.store(); sync = os.fsync; acted = []
                def fsync(fd):
                    if not acted:
                        path = store.path/'000000-inspection.json'; acted.append(True)
                        if mode == 'replace':path.rename(store.path/'retained'); path.write_bytes(b'other')
                        elif mode == 'hardlink':os.link(path, store.path/'extra-link')
                        else:path.chmod(0o644)
                    return sync(fd)
                with patch('c64u_browser.required_evidence.os.fsync', side_effect=fsync):
                    with self.assertRaises(EvidenceFailure):store.save('inspection', {})
                self.assertTrue(store.blocked)

    def test_symlink_parent_substitution_refuses_before_write(self):
        root, parent, store = self.store(); parent.rename(root/'retained'); parent.symlink_to(root/'retained', target_is_directory=True)
        with self.assertRaises(OSError):store.save('inspection', {})
        self.assertTrue(store.blocked); self.assertEqual(list((root/'retained'/'evidence').iterdir()), [])
