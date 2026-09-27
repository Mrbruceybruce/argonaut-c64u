"""Slice 3A Core streaming integration against loopback control/data sockets."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as read_fixtures
from test_ftp_reads import ROOT
from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.ftp_reads import adapter_for, read_operation
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.transfers import download
from c64u_browser.file_service import FileLocation
from c64u_browser.usb_backup import BackupRequest


class StreamingMigrationTests(unittest.TestCase):
    core = read_fixtures.ReadMigrationTests.core
    connect = read_fixtures.ReadMigrationTests.connect

    def destination(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / 'download'

    def test_nested_listing_download_hash_one_lease_and_unchanged_epoch(self):
        data = b'abc' * 9000
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': data}) as server:
            core, _ = self.connect(server)
            before = server.connections
            epoch = core.device_session()
            target = self.destination()
            with patch('ftplib.FTP', side_effect=AssertionError('legacy read')):
                with read_operation(core._client):
                    self.assertEqual(before, server.connections)  # lazy
                    core._client.list_directory('/USB1')
                    with read_operation(core._client):
                        result = download(core.device_operations, '/USB1/a', target)
                        job = CoreJob('hash', lambda _: None)
                        size, digest = core.usb._remote_hash(core._client, '/USB1/a', job, 'verify', 0, len(data))
                    self.assertEqual(1, core._ftp_manager.active_count)
            self.assertEqual(data, target.read_bytes())
            self.assertEqual({'path': str(target), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}, result)
            self.assertEqual((result['bytes'], result['sha256']), (size, digest))
            self.assertEqual(1, server.connections - before)
            self.assertEqual(server.connections, server.verbs.count(b'USER'))
            self.assertEqual(server.connections, server.verbs.count(b'FEAT'))
            self.assertEqual([b'SIZE', b'RETR', b'SIZE'] * 2,
                             [v for v in server.verbs if v in (b'SIZE', b'RETR')])
            self.assertEqual(epoch, core.device_session())
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_empty_stream_preserves_publication_and_hash(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b''}) as server:
            core, _ = self.connect(server)
            target = self.destination()
            with patch('c64u_browser.transfers.os.fsync', wraps=__import__('os').fsync) as sync:
                result = download(core._client, '/USB1/a', target)
            self.assertEqual(b'', target.read_bytes())
            self.assertEqual(0, result['bytes'])
            self.assertEqual(hashlib.sha256(b'').hexdigest(), result['sha256'])
            sync.assert_called_once()
            self.assertEqual([target], list(target.parent.iterdir()))
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_short_overlong_unavailable_size_and_missing_completion_cleanup(self):
        for fault, code, outcome in (
                ('short', 'size-mismatch', 'completed'),
                ('overlong', 'size-mismatch', 'unknown'),
                ('size', 'size-unavailable', 'rejected'),
                ('terminal', 'completion-unknown', 'unknown')):
            with self.subTest(fault=fault), FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
                core, _ = self.connect(server)
                if fault in ('short', 'overlong'):
                    server.replies[b'SIZE'] = b'213 ' + (b'4' if fault == 'short' else b'2') + b'\r\n'
                elif fault == 'size':server.replies[b'SIZE'] = b'502 unavailable\r\n'
                else:server.completion = None
                target = self.destination()
                with self.assertRaises(ConnectionFailure) as caught:
                    download(core._client, '/USB1/a', target)
                error = caught.exception
                self.assertEqual(code, error.ftp_code)
                self.assertEqual(outcome, error.outcome.value)
                self.assertEqual(error.outcome, error.ftp_error.outcome)
                self.assertEqual(error.transferred, error.ftp_error.transferred)
                self.assertEqual([], list(target.parent.iterdir()))
                self.assertEqual(0, core._ftp_manager.active_count)

    def test_changed_final_size_never_publishes(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            replies = iter((b'213 3\r\n', b'213 4\r\n'))
            server.replies[b'SIZE'] = lambda _: next(replies)
            target = self.destination()
            with self.assertRaisesRegex(BrowserError, 'size changed'):
                download(core._client, '/USB1/a', target)
            self.assertEqual([], list(target.parent.iterdir()))
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_failed_lease_never_reopens_implicitly_even_if_error_is_caught(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            adapter = adapter_for(core._client)
            before = server.connections
            with read_operation(core._client):
                server.replies[b'SIZE'] = b'502 unavailable\r\n'
                with self.assertRaises(ConnectionFailure):adapter.read_into('/USB1/a', io.BytesIO())
                del server.replies[b'SIZE']
                with self.assertRaises(ConnectionFailure):core._client.list_directory('/USB1')
                self.assertEqual(1, server.connections - before)
            self.assertEqual(0, core._ftp_manager.active_count)
            self.assertEqual(3, adapter.read_into('/USB1/a', io.BytesIO()).transferred)
            self.assertEqual(2, server.connections - before)

    def test_failed_authentication_does_not_reacquire_in_same_operation(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core, _ = self.connect(server)
            before = server.connections
            server.replies[b'PASS'] = b'530 refused\r\n'
            with read_operation(core._client):
                with self.assertRaises(ConnectionFailure):core._client.list_directory('/USB1')
                del server.replies[b'PASS']
                with self.assertRaises(ConnectionFailure):core._client.list_directory('/USB1')
            self.assertEqual(1, server.connections - before)
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_cancelled_download_cleans_staging_and_next_job_is_unaffected(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'x' * 50000}) as server:
            core, _ = self.connect(server)
            target = self.destination()
            def task(job):
                def progress(_):job.request_cancel();job.check_cancel()
                progress.check = job.check_cancel
                return download(core._client, '/USB1/a', target, progress)
            job = CoreJob('cancel-read', task)
            self.assertEqual('cancelled', job.run().state)
            self.assertEqual([], list(target.parent.iterdir()))
            self.assertEqual(0, core._ftp_manager.active_count)
            next_job = CoreJob('read', lambda _: download(core._client, '/USB1/a', target))
            self.assertEqual('succeeded', next_job.run().state)
            self.assertEqual(b'x' * 50000, target.read_bytes())

    def test_context_exit_does_not_observe_late_cancellation(self):
        with FakeC64UFtp(directories=ROOT) as server:
            core, _ = self.connect(server)
            def task(job):
                with read_operation(core._client):
                    core._client.list_directory('/USB1')
                    job.request_cancel()
                return 'completed'
            result = CoreJob('late', task).run()
            self.assertEqual('succeeded', result.state)
            self.assertEqual('completed', result.result)
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_concurrent_destination_is_preserved(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            target = self.destination()
            def progress(_):target.write_bytes(b'keep')
            with self.assertRaises(BrowserError):download(core._client, '/USB1/a', target, progress)
            self.assertEqual(b'keep', target.read_bytes())
            self.assertEqual([target], list(target.parent.iterdir()))
            before = server.connections
            with self.assertRaises(BrowserError):download(core._client, '/USB1/a', target)
            self.assertEqual(before, server.connections)

    def test_stale_binding_and_invalidation_are_not_masked_by_cancellation(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'x' * 50000}) as server:
            core, _ = self.connect(server)
            old = core._client
            target = self.destination()
            def task(job):
                def progress(_):core.disconnect();job.request_cancel()
                return download(old, '/USB1/a', target, progress)
            result = CoreJob('invalidated', task).run()
            self.assertEqual('failed', result.state)
            self.assertEqual('session', result.error.code)
            self.assertEqual([], list(target.parent.iterdir()))
            before = server.connections
            with self.assertRaises(ConnectionFailure):download(old, '/USB1/a', target)
            self.assertEqual(before, server.connections)
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_callback_failure_keeps_original_exception_and_transport_evidence(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            failure = BrowserError('caller stopped')
            def progress(_):raise failure
            target = self.destination()
            with self.assertRaises(BrowserError) as caught:
                download(core._client, '/USB1/a', target, progress)
            self.assertIs(failure, caught.exception)
            self.assertEqual('unknown', failure.ftp_error.outcome.value)
            self.assertEqual([], list(target.parent.iterdir()))
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_fsync_precedes_final_size_and_failure_cleans_staging(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            target = self.destination()
            def fail_sync(_):
                self.assertEqual([b'SIZE', b'RETR'],
                                 [v for v in server.verbs if v in (b'SIZE', b'RETR')])
                raise OSError('disk full')
            with patch('c64u_browser.transfers.os.fsync', side_effect=fail_sync):
                with self.assertRaisesRegex(BrowserError, 'disk full'):
                    download(core._client, '/USB1/a', target)
            self.assertEqual([], list(target.parent.iterdir()))
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_sink_failure_releases_lease_and_retains_wire_evidence(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/a': b'abc'}) as server:
            core, _ = self.connect(server)
            failure = OSError('sink unavailable')
            class Sink:
                def write(self, _):raise failure
            with self.assertRaises(OSError) as caught:
                adapter_for(core._client).read_into('/USB1/a', Sink())
            self.assertIs(failure, caught.exception)
            self.assertEqual('local-io-failed', failure.ftp_error.code.value)
            self.assertEqual(0, core._ftp_manager.active_count)

    def test_usb_preview_and_execution_preserve_three_independent_reads(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/game.d64': b'abc'}) as server:
            core, _ = self.connect(server)
            destination = self.destination()
            with patch('ftplib.FTP', side_effect=AssertionError('legacy USB read')):
                preview = core.usb.prepare_backup(BackupRequest(
                    FileLocation.c64u('/USB1'), (), FileLocation.core_host(destination))).wait(5)
                self.assertEqual('succeeded', preview.state, preview.error)
                self.assertEqual(1, server.verbs.count(b'RETR'))
                self.assertEqual(0, core._ftp_manager.active_count)
                before = server.connections
                result = core.usb.execute_backup(preview.result.plan_id).wait(5)
            self.assertEqual('succeeded', result.state, result.error)
            self.assertEqual(3, server.verbs.count(b'RETR'))
            self.assertEqual(6, server.verbs.count(b'SIZE'))
            # One fingerprint lease and one complete per-file verification lease.
            self.assertEqual(2, server.connections - before)
            self.assertEqual(0, core._ftp_manager.active_count)
            self.assertEqual(b'abc', (destination / 'game.d64').read_bytes())
            manifest = json.loads(Path(result.result.manifest_path).read_text())
            self.assertEqual('complete', manifest['state'])

    def test_usb_second_observation_detects_same_size_content_change(self):
        with FakeC64UFtp(directories=ROOT, files={b'/USB1/game.d64': b'abc'}) as server:
            core, _ = self.connect(server)
            destination = self.destination()
            preview = core.usb.prepare_backup(BackupRequest(
                FileLocation.c64u('/USB1'), (), FileLocation.core_host(destination))).wait(5)
            calls = [0]
            def size(_):
                calls[0] += 1
                if calls[0] == 3:server.files[b'/USB1/game.d64'] = b'bad'
                return b'213 3\r\n'
            server.replies[b'SIZE'] = size
            result = core.usb.execute_backup(preview.result.plan_id).wait(5)
            self.assertEqual('failed', result.state)
            self.assertEqual('incomplete', result.result.state)
            self.assertFalse((destination / 'game.d64').exists())
            self.assertEqual(3, server.verbs.count(b'RETR'))
            self.assertEqual(0, core._ftp_manager.active_count)


if __name__ == '__main__':unittest.main()
