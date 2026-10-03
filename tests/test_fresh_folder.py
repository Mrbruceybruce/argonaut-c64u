"""R2 composite over real loopback sockets. Never contacts a physical C64U."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.api import BrowserError
from c64u_browser.file_service import FileLocation, FileJobFailure
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.scheduler import JobBinding
from c64u_browser.transfers import upload_managed


def server():
    return FakeC64UFtp(directories={b'/': b'', b'/USB1': b'', b'/USB1/parent': b''},
                      files={b'/USB1/sentinel': b'keep'}, mutation_tree=True)


class FreshFolderTests(unittest.TestCase):
    core = reads.ReadMigrationTests.core
    connect = reads.ReadMigrationTests.connect

    def source(self, data=b'abc'):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'new'; path.write_bytes(data)
        return path

    def prepare(self, core, source=None, parent='/USB1/parent'):
        snapshot = core.prepare_fresh_folder_upload(FileLocation.core_host(source or self.source()), parent).wait(5)
        self.assertEqual('succeeded', snapshot.state, snapshot.error)
        self.assertEqual(0, core._ftp_manager.active_count)
        return snapshot.result

    def execute(self, core, ftp, preview, connections=1):
        epoch = core.device_session(); before = ftp.connections; ftp.commands.clear()
        with patch('ftplib.FTP', side_effect=AssertionError('raw fallback')):
            snapshot = core.execute_fresh_folder_upload(preview.plan_id).wait(5)
        self.assertEqual(epoch, core.device_session())
        self.assertEqual(0, core._ftp_manager.active_count)
        self.assertEqual(connections, ftp.connections-before)
        self.assertEqual(connections, ftp.verbs.count(b'USER'))
        self.assertEqual(connections, ftp.verbs.count(b'FEAT'))
        self.assertEqual(b'keep', ftp.files[b'/USB1/sentinel'])
        self.assertFalse(set(ftp.verbs) & {b'DELE', b'RMD'})
        for verb, path in ftp.commands:
            if verb in (b'MKD', b'STOR', b'RETR', b'SIZE', b'RNFR', b'RNTO'):
                self.assertTrue(path.startswith(b'/'))
        self.assertNotIn('PRIVATE', json.dumps(snapshot.as_dict()))
        return snapshot

    def test_success_one_execution_lifetime(self):
        with server() as ftp:
            core, profile = self.connect(ftp); source = self.source(); before = ftp.connections
            preview = self.prepare(core, source)
            self.assertEqual(1, ftp.connections-before)
            self.assertNotIn(b'MKD', ftp.verbs)
            r = self.execute(core, ftp, preview); e = r.result
            self.assertEqual('succeeded', r.state, r.error)
            self.assertEqual('published', e.disposition)
            self.assertEqual('completed', e.mkdir_state)
            self.assertEqual('created', e.directory_disposition)
            self.assertEqual(profile.id, e.profile_id)
            self.assertEqual(3, e.bytes); self.assertEqual(hashlib.sha256(b'abc').hexdigest(), e.sha256)
            self.assertEqual('passed', e.upload.destination_recheck)
            self.assertEqual('passed', e.upload.readback); self.assertEqual('passed', e.upload.size)
            self.assertEqual(b'abc', ftp.files[e.path.encode()])
            self.assertEqual(1, ftp.verbs.count(b'MKD')); self.assertEqual(1, ftp.verbs.count(b'STOR'))
            self.assertEqual('not-required', e.local_cleanup)
            with self.assertRaises(FrozenInstanceError):preview.path = '/bad'
            with self.assertRaises(FrozenInstanceError):e.state = 'bad'

    def test_empty_directory_and_fifo_refused_before_mkd(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            empty = self.source(b''); fifo = empty.parent / 'fifo'; os.mkfifo(fifo)
            for path in (empty, empty.parent, fifo, empty.parent/'missing'):
                with self.subTest(path=path):
                    r = core.prepare_fresh_folder_upload(FileLocation.core_host(path), '/USB1').wait(5)
                    self.assertEqual('failed', r.state); self.assertEqual('failed', r.result.preparation)
                    self.assertEqual('not-submitted', r.result.mkdir_state)
            self.assertNotIn(b'MKD', ftp.verbs)

    def test_regular_symlink_is_accepted(self):
        with server() as ftp:
            core, _ = self.connect(ftp); source = self.source(); link = source.parent/'link'; link.symlink_to(source)
            r = self.execute(core, ftp, self.prepare(core, link))
            self.assertEqual('succeeded', r.state); self.assertTrue(r.result.path.endswith('/link'))

    def test_source_changes_before_execution(self):
        for mode in ('empty', 'missing', 'directory', 'fifo'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); source = self.source(); preview = self.prepare(core, source)
                source.unlink()
                if mode == 'empty':source.touch()
                if mode == 'directory':source.mkdir()
                if mode == 'fifo':os.mkfifo(source)
                r = self.execute(core, ftp, preview, connections=0)
                self.assertEqual('failed', r.result.execution); self.assertNotIn(b'MKD', ftp.verbs)

    def test_post_mkd_descriptor_guard_empty_nonregular_unreadable(self):
        for mode in ('empty', 'fifo', 'missing', 'directory'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); source = self.source(); preview = self.prepare(core, source)
                def change(verb, path):
                    if verb != b'MKD':return
                    source.unlink()
                    if mode == 'empty':source.touch()
                    if mode == 'fifo':os.mkfifo(source)
                    if mode == 'directory':source.mkdir()
                ftp.mutation_hook = change
                r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.state); self.assertEqual('created', r.result.directory_disposition)
                self.assertEqual('not-started', r.result.upload_state); self.assertNotIn(b'STOR', ftp.verbs)

    def test_descriptor_length_not_preparation_length(self):
        with server() as ftp:
            core, _ = self.connect(ftp); source = self.source(); preview = self.prepare(core, source)
            ftp.mutation_hook = lambda v,p:source.write_bytes(b'longer') if v == b'MKD' else None
            r = self.execute(core, ftp, preview)
            self.assertEqual('succeeded', r.state); self.assertEqual(3, r.result.observed_size)
            self.assertEqual(6, r.result.upload.expected_bytes); self.assertEqual(6, r.result.bytes)

    def test_bad_parent_and_basename(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            for parent in ('/', '/Flash', 'USB1/parent', '/USB1/', '/USB1/../parent', '/USB1//parent',
                           '/USB1/missing', '/USB1/sentinel', '/usb1', '/USB1/Parent'):
                with self.subTest(parent=parent):
                    r = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), parent).wait(5)
                    self.assertEqual('failed', r.state); self.assertIsNone(r.result.mutation)
            source = self.source(); bad = source.with_name('bad*'); source.rename(bad)
            r = core.prepare_fresh_folder_upload(FileLocation.core_host(bad), '/USB1').wait(5)
            self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)

    def test_supported_root_parent(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            r = self.execute(core, ftp, self.prepare(core, parent='/USB1'))
            self.assertEqual('succeeded', r.state)

    def test_case_ambiguous_parent(self):
        with server() as ftp:
            core, _ = self.connect(ftp); ftp.directories[b'/USB1/Parent'] = b''
            r = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1/parent').wait(5)
            self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)

    def test_changed_ancestor_or_child_collision_before_execution(self):
        for mode in ('ancestor', 'child', 'case-child'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); preview = self.prepare(core)
                if mode == 'ancestor':
                    del ftp.directories[b'/USB1/parent']; ftp.files[b'/USB1/parent'] = b'changed'
                else:ftp.directories[(preview.directory.upper() if mode == 'case-child' else preview.directory).encode()] = b''
                if mode == 'case-child':
                    # Keep parent case exact; only the child has changed spelling.
                    del ftp.directories[preview.directory.upper().encode()]
                    ftp.directories[('/USB1/parent/' + preview.directory.split('/')[-1].upper()).encode()] = b''
                r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)
                self.assertEqual('not-submitted', r.result.mkdir_state)

    def test_generated_collision_and_invalid_uuid_refused(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            class Id:hex = 'fixed'
            ftp.directories[b'/USB1/parent/c64u-transfer-fixed'] = b''
            with patch('c64u_browser.fresh_folder.uuid.uuid4', return_value=Id()):
                r = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1/parent').wait(5)
            self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)
            Id.hex = '../bad'
            with patch('c64u_browser.fresh_folder.uuid.uuid4', return_value=Id()):
                r = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1/parent').wait(5)
            self.assertEqual('failed', r.state)

    def test_plan_consumed_expired_and_bounded(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            self.execute(core, ftp, preview)
            with self.assertRaises(BrowserError):core.execute_fresh_folder_upload(preview.plan_id)
            preview = self.prepare(core); core.files._clock = lambda:10**12
            with self.assertRaises(BrowserError):core.execute_fresh_folder_upload(preview.plan_id)
            core.files.plan_limit = 0; preview = self.prepare(core)
            with self.assertRaises(BrowserError):core.execute_fresh_folder_upload(preview.plan_id)

    def test_mkd_refusal_and_lost_reply_stop_stor(self):
        for mode in ('refused', 'unknown'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); preview = self.prepare(core)
                if mode == 'refused':ftp.replies[b'MKD'] = b'550 PRIVATE\r\n'
                else:ftp.after_mutation[b'MKD'] = None
                r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.state); self.assertNotIn(b'STOR', ftp.verbs)
                self.assertEqual(mode, r.result.mkdir_state); self.assertIsNone(r.result.upload)
                self.assertEqual(1, ftp.verbs.count(b'MKD')); self.assertFalse(r.error.retryable)

    def test_cancellation_during_validation(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            original = core.files._check_session
            def cancel(session):
                from c64u_browser.jobs import check_current_job
                # Explicit cancellation at a validation boundary before MKD.
                original(session); raise JobCancelled()
            with patch.object(core.files, '_check_session', side_effect=cancel):
                r = self.execute(core, ftp, preview, connections=0)
            self.assertEqual('cancelled', r.state); self.assertEqual('not-submitted', r.result.mkdir_state)

    def cancel_at_mutation(self, core, ftp, verb):
        def hook(v, p):
            if v == verb:
                for job in tuple(core.scheduler._jobs.values()):
                    if job.operation == 'file.fresh-folder-upload':job.request_cancel()
        ftp.mutation_hook = hook

    def test_cancel_after_mkd_retains_created(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            self.cancel_at_mutation(core, ftp, b'MKD')
            r = self.execute(core, ftp, preview)
            self.assertEqual('cancelled', r.state); self.assertEqual('completed', r.result.mkdir_state)
            self.assertEqual('directory-created-upload-not-started', r.result.disposition)
            self.assertIsNone(r.result.upload); self.assertNotIn(b'STOR', ftp.verbs)

    def test_late_cancel_after_publication_remains_success(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            self.cancel_at_mutation(core, ftp, b'RNTO')
            r = self.execute(core, ftp, preview)
            self.assertEqual('succeeded', r.state); self.assertEqual('published', r.result.disposition)

    def block_lane(self, core):
        started = threading.Event(); release = threading.Event(); self.addCleanup(release.set)
        blocker = CoreJob('test.block', lambda job:(started.set(), release.wait(5)))
        core.scheduler.submit(blocker, JobBinding.device(core.device_session()))
        self.assertTrue(started.wait(2)); return release

    def test_queued_cancel_snapshot_and_event_evidence(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); release = self.block_lane(core)
            ftp.commands.clear(); job = core.execute_fresh_folder_upload(preview.plan_id); events = []
            job.add_listener(events.append); job.request_cancel(); release.set(); r = job.wait(5)
            self.assertEqual('cancelled', r.state); self.assertEqual('unperformed', r.result.execution)
            self.assertEqual('queued', r.result.cancellation_phase); self.assertIsNone(r.result.upload)
            self.assertEqual(r.result, core.files.job(job.id).result)
            self.assertEqual(r.result, job.snapshot().result)
            self.assertNotIn(b'MKD', ftp.verbs)
            self.assertTrue(all(e.job.result == r.result for e in events if e.kind == 'finished'))

    def test_queued_stale_refusal_unperformed(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); release = self.block_lane(core)
            ftp.commands.clear(); job = core.execute_fresh_folder_upload(preview.plan_id)
            core._session_id = 'changed'; release.set(); r = job.wait(5)
            self.assertEqual('failed', r.state); self.assertEqual('unperformed', r.result.execution)
            self.assertEqual(preview.session_id, r.result.session_id); self.assertNotIn(b'MKD', ftp.verbs)

    def test_changed_profile_binding_refused(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); core.active_profile.device_id = 'OTHER'
            r = self.execute(core, ftp, preview, connections=0)
            self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)

    def test_unbound_and_missing_adapter_refused(self):
        with server() as ftp:
            core, _ = self.connect(ftp); core.active_profile.device_id = ''; core.active_profile.device_mac = ''
            with self.assertRaises(FileJobFailure) as caught:self.prepare(core)
            self.assertEqual('unperformed', caught.exception.result.preparation)
            self.assertEqual('not-submitted', caught.exception.result.mkdir_state)
            core.active_profile.device_id = 'ABC123'; core._client._ftp_reads = None
            r = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1').wait(5)
            self.assertEqual('failed', r.state); self.assertNotIn(b'MKD', ftp.verbs)

    def test_stor_refusal_and_lost_terminal(self):
        for mode in ('refused', 'unknown'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); preview = self.prepare(core)
                if mode == 'refused':ftp.replies[b'STOR'] = b'550 PRIVATE\r\n'
                else:ftp.transfer_completion = lambda v,p:None if v == b'STOR' else b'226 Done\r\n'
                r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.state); self.assertEqual('created', r.result.directory_disposition)
                self.assertEqual('no-candidate' if mode == 'refused' else 'staging-candidate', r.result.upload_state)
                self.assertNotIn(b'RNTO', ftp.verbs)

    def test_stor_setup_refusal_not_started(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            def diagnostic(event):
                if event['operation'] == 'STOR' and event['kind'] == 'command' and event['verb'] == 'TYPE':
                    ftp.replies[b'TYPE'] = b'550 PRIVATE\r\n'
            core._ftp_manager._diagnostic = diagnostic
            r = self.execute(core, ftp, preview)
            self.assertEqual('not-started', r.result.upload_state); self.assertNotIn(b'STOR', ftp.verbs)
            self.assertEqual('created', r.result.directory_disposition)

    def test_interrupted_partial_stor(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core, self.source(b'a'*200000))
            def progress(job, phase='transfer'):
                def callback(count):raise JobCancelled()
                callback.check = job.check_cancel
                return callback
            with patch.object(CoreJob, 'byte_progress', progress):r = self.execute(core, ftp, preview)
            self.assertEqual('cancelled', r.state); self.assertEqual('staging-candidate', r.result.upload_state)
            self.assertIsNone(r.result.upload.stor['sha256']); self.assertNotIn(b'RNTO', ftp.verbs)

    def test_corrupt_readback_and_size_mismatch(self):
        for mode in ('hash', 'size'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); preview = self.prepare(core)
                if mode == 'hash':ftp.readback_data = lambda p,c:b'bad'
                else:ftp.before_command = lambda v,p:b'213 999\r\n' if v == b'SIZE' else None
                r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.state); self.assertEqual('staging-candidate', r.result.upload_state)
                self.assertEqual('failed', r.result.upload.readback if mode == 'hash' else r.result.upload.size)
                self.assertFalse(set(ftp.verbs) & {b'RNFR', b'RNTO', b'DELE', b'RMD'})
                for verb in (b'MKD', b'STOR', b'RETR'):
                    self.assertEqual(1, ftp.verbs.count(verb))
                self.assertIsNone(r.result.upload.publication)
                self.assertNotIn(preview.path.encode(), ftp.files)
                self.assertIn(r.result.upload.staging.encode(), ftp.files)
                self.assertEqual('created', r.result.directory_disposition)
                self.assertFalse(r.error.retryable)

    def test_destination_race(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            ftp.transfer_hook = lambda v,p:ftp.files.update({preview.path.encode(): b'keep'}) if v == b'STOR' else None
            r = self.execute(core, ftp, preview)
            self.assertEqual('failed', r.result.upload.destination_recheck)
            self.assertEqual(b'keep', ftp.files[preview.path.encode()]); self.assertNotIn(b'RNTO', ftp.verbs)

    def test_publication_lost_reply_keeps_both_locations(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); ftp.after_mutation[b'RNTO'] = None
            r = self.execute(core, ftp, preview)
            self.assertEqual('failed', r.state); self.assertEqual('directory-created-file-location-unknown', r.result.disposition)
            self.assertTrue(r.result.upload.publication['consequential_submitted'])
            self.assertEqual('unknown', r.result.upload.publication['outcome'])
            self.assertEqual(1, ftp.verbs.count(b'RNTO'))

    def test_short_overlong_and_same_length_source_change(self):
        for data in (b'a', b'longer', b'XYZ'):
            with self.subTest(data=data), server() as ftp:
                core, _ = self.connect(ftp); source = self.source(); preview = self.prepare(core, source)
                adapter = adapter_for(core._client); original = adapter.write_from
                def change(path, stream, expected, progress):
                    source.write_bytes(data)
                    return original(path, stream, expected, progress)
                with patch.object(adapter, 'write_from', side_effect=change):r = self.execute(core, ftp, preview)
                if len(data) == 3:
                    self.assertEqual('succeeded', r.state); self.assertEqual(data, ftp.files[preview.path.encode()])
                else:
                    self.assertEqual('failed', r.state); self.assertEqual('source-length', r.result.upload.error_category)
                    self.assertNotIn(b'RNTO', ftp.verbs)

    def test_default_managed_zero_byte_support_unchanged(self):
        with server() as ftp:
            core, _ = self.connect(ftp)
            result = upload_managed(core._client, self.source(b''), '/USB1')
            self.assertEqual(0, result['bytes']); self.assertTrue(result['verified'])

    def test_one_transfer_source_open(self):
        with server() as ftp:
            core, _ = self.connect(ftp); source = self.source(); preview = self.prepare(core, source)
            original = os.open; opened = []
            def track(path, *args, **kwargs):
                if Path(path) == source:opened.append(path)
                return original(path, *args, **kwargs)
            with patch('c64u_browser.transfers.os.open', side_effect=track):r = self.execute(core, ftp, preview)
            self.assertEqual('succeeded', r.state); self.assertEqual(1, len(opened))

    def test_release_cleanup_preserves_primary_and_publication(self):
        for mode in ('success', 'cancel', 'unknown', 'refused'):
            with self.subTest(mode=mode), server() as ftp:
                core, _ = self.connect(ftp); preview = self.prepare(core)
                if mode == 'cancel':self.cancel_at_mutation(core, ftp, b'MKD')
                if mode == 'unknown':ftp.after_mutation[b'RNTO'] = None
                if mode == 'refused':ftp.replies[b'STOR'] = b'550 PRIVATE\r\n'
                adapter = adapter_for(core._client); original = adapter.operation; depth = [0]
                @contextmanager
                def failing(check=None):
                    outer = depth[0] == 0; depth[0] += 1
                    try:
                        with original(check):yield
                    finally:depth[0] -= 1
                    if outer:raise OSError('PRIVATE temporary path')
                with patch.object(adapter, 'operation', failing):r = self.execute(core, ftp, preview)
                self.assertEqual('failed', r.result.local_cleanup)
                self.assertEqual('cancelled' if mode == 'cancel' else 'failed', r.state)
                if mode == 'success':
                    self.assertEqual('published-local-cleanup-failed', r.result.disposition)
                    self.assertEqual('published', r.result.upload_state); self.assertTrue(r.result.verified)
                if mode == 'unknown':self.assertEqual('location-unknown', r.result.upload_state)

    def test_source_close_failure_preserves_stor_failure(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); ftp.replies[b'STOR'] = b'550 PRIVATE\r\n'
            original = os.fdopen
            class Wrapped:
                def __init__(self, stream):self.stream = stream
                def __getattr__(self, name):return getattr(self.stream, name)
                def close(self):self.stream.close(); raise OSError('PRIVATE')
            with patch('c64u_browser.transfers.os.fdopen', side_effect=lambda *a,**k:Wrapped(original(*a,**k))):
                r = self.execute(core, ftp, preview)
            self.assertEqual('failed', r.result.local_cleanup)
            self.assertEqual('no-candidate', r.result.upload_state)
            self.assertEqual(550, r.result.upload.stor['preliminary_reply'])

    def test_no_read_fallback_or_reopen_after_consequence(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            adapter = adapter_for(core._client)
            original = adapter.readback
            def fallback(*args):
                with self.assertRaises(BrowserError):adapter.end_read_attempt()
                return original(*args)
            with patch.object(adapter, 'readback', side_effect=fallback):r = self.execute(core, ftp, preview)
            self.assertEqual('succeeded', r.state)

    def test_stale_binding_with_pending_cancel_keeps_failure(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            def progress(job, phase='transfer'):
                def callback(count):
                    core._ftp_manager.invalidate(core.device_session().device_id)
                    job.request_cancel()
                    raise JobCancelled()
                callback.check = job.check_cancel
                return callback
            with patch.object(CoreJob, 'byte_progress', progress):r = self.execute(core, ftp, preview)
            self.assertEqual('failed', r.state)
            self.assertEqual('stale-session', r.result.upload.error_code)
            self.assertEqual('created', r.result.directory_disposition)

    def test_preparation_queued_cancel_truthful_unperformed(self):
        with server() as ftp:
            core, _ = self.connect(ftp); release = self.block_lane(core); before = ftp.connections
            job = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1')
            job.request_cancel(); release.set(); result = job.wait(5).result
            self.assertEqual('unperformed', result.preparation); self.assertEqual('unperformed', result.execution)
            self.assertIsNone(result.directory); self.assertIsNone(result.observed_size)
            self.assertEqual(before, ftp.connections)

    def test_source_close_failure_after_completed_stor(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core); original = os.fdopen
            class Wrapped:
                def __init__(self, stream):self.stream = stream
                def __getattr__(self, name):return getattr(self.stream, name)
                def close(self):self.stream.close(); raise OSError('PRIVATE')
            with patch('c64u_browser.transfers.os.fdopen', side_effect=lambda *a,**k:Wrapped(original(*a,**k))):
                r = self.execute(core, ftp, preview)
            self.assertEqual('failed', r.state); self.assertEqual('failed', r.result.local_cleanup)
            self.assertEqual('completed', r.result.upload.stor['outcome'])
            self.assertEqual('staging-candidate', r.result.upload_state)
            self.assertNotIn(b'RETR', ftp.verbs); self.assertNotIn(b'RNTO', ftp.verbs)

    def test_pretask_stale_preparation_and_discarded_plan(self):
        with server() as ftp:
            core, _ = self.connect(ftp); preview = self.prepare(core)
            self.assertTrue(core.files.discard_plan(preview.plan_id))
            with self.assertRaises(FileJobFailure) as caught:core.execute_fresh_folder_upload(preview.plan_id)
            self.assertIsNone(caught.exception.result.source)
            self.assertEqual('unperformed', caught.exception.result.execution)
            release = self.block_lane(core)
            job = core.prepare_fresh_folder_upload(FileLocation.core_host(self.source()), '/USB1')
            core._session_id = 'changed'; release.set(); r = job.wait(5)
            self.assertEqual('failed', r.state); self.assertEqual('unperformed', r.result.preparation)
