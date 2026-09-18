import io
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from c64u_browser.api import ConnectionFailure, Entry, UltimateClient, BrowserError
from c64u_browser.diagnostics import (LOGGER, JsonEventFormatter,
                                      enable_private_log, disable_private_log,
                                      operation_event)
from c64u_browser.transfers import download, upload
from c64u_browser.files import operate
from c64u_browser.native_files import read_remote
from c64u_browser.disk_run import mount_and_run
from c64u_browser.disk_image import D64Image, D71Image
from c64u_browser.disk_image_edit import D64EditSession
from c64u_browser.test_lab import run_default_checks


class DiagnosticEventsTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JsonEventFormatter())
        LOGGER.addHandler(self.handler)
        self.previous_level = LOGGER.level
        LOGGER.setLevel(logging.INFO)

    def tearDown(self):
        LOGGER.removeHandler(self.handler)
        LOGGER.setLevel(self.previous_level)

    def event(self):
        return json.loads(self.stream.getvalue().strip())

    def test_rest_success_redacts_query_and_credentials(self):
        client = UltimateClient('c64u.local', password='secret')
        with patch.object(client, '_request_json_impl', return_value={'errors': []}):
            client._request_json('PUT', '/v1/drives/a:mount?image=/private/game.d64')
        event = self.event()
        self.assertEqual((event['transport'], event['operation'], event['outcome']),
                         ('rest', 'PUT', 'ok'))
        self.assertEqual(event['target'], '/v1/drives/a:mount')
        self.assertNotIn('secret', self.stream.getvalue())
        self.assertNotIn('game.d64', self.stream.getvalue())
        self.assertGreaterEqual(event['duration_ms'], 0)

    def test_rest_failure_preserves_exception_and_category(self):
        client = UltimateClient('c64u.local')
        failure = ConnectionFailure('network', 'unreachable')
        with patch.object(client, '_request_json_impl', side_effect=failure):
            with self.assertRaises(ConnectionFailure):
                client._request_json('GET', '/v1/info')
        self.assertEqual((self.event()['outcome'], self.event()['error_kind']),
                         ('error', 'network'))

    def test_rest_dynamic_route_segment_is_redacted(self):
        client = UltimateClient('c64u.local')
        with patch.object(client, '_request_json_impl', return_value={'errors': []}):
            client.read_configuration('private-category')
        self.assertEqual(self.event()['target'], '/v1/configs/category')
        self.assertNotIn('private-category', self.stream.getvalue())

    def test_ftp_listing_does_not_record_private_path(self):
        client = UltimateClient('c64u.local')
        with patch.object(client, '_list_directory', return_value=('/', [])):
            client.list_directory('/private/files')
        self.assertEqual(self.event()['target'], 'directory')
        self.assertNotIn('/private/files', self.stream.getvalue())

    def test_ftp_download_event_redacts_file_paths_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                'c64u_browser.transfers.connect') as connect:
            destination = Path(directory) / 'private-download.bin'
            ftp = connect.return_value
            ftp.size.return_value = 3
            ftp.retrbinary.side_effect = lambda _command, callback: callback(b'abc')
            download(Mock(), '/USB2/private-device.bin', destination)
            event = self.event()
            self.assertEqual((event['operation'], event['target'], event['outcome']),
                             ('download', 'file', 'ok'))
            self.assertNotIn('private-device.bin', self.stream.getvalue())
            self.assertNotIn('private-download.bin', self.stream.getvalue())
            self.stream.seek(0)
            self.stream.truncate()
            ftp.retrbinary.side_effect = OSError('private connection detail')
            with self.assertRaises(BrowserError):
                download(Mock(), '/USB2/private-device.bin', destination.with_name('retry.bin'))
            self.assertEqual((self.event()['outcome'], self.event()['error_kind']),
                             ('error', 'BrowserError'))
            self.assertNotIn('private connection detail', self.stream.getvalue())

    def test_ftp_upload_and_file_action_events_use_generic_targets(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                'c64u_browser.transfers.connect') as connect, patch(
                'c64u_browser.files.inspect', return_value=None):
            source = Path(directory) / 'private-upload.bin'
            source.write_bytes(b'abc')
            ftp = connect.return_value
            ftp.storbinary.side_effect = lambda _command, stream, callback: callback(stream.read())
            ftp.retrbinary.side_effect = lambda _command, callback: callback(b'abc')
            ftp.size.return_value = 3
            upload(Mock(), source, '/USB2/Private')
        self.assertEqual((self.event()['operation'], self.event()['target']),
                         ('upload', 'file'))
        self.assertNotIn('private-upload.bin', self.stream.getvalue())
        self.stream.seek(0)
        self.stream.truncate()
        with patch('c64u_browser.files.inspect', return_value=Entry('private.bin', 'file', 3)), patch(
                'c64u_browser.files.connect') as connect:
            operate(Mock(), 'delete', '/USB2/private.bin',
                    confirmation='/USB2/private.bin')
            connect.return_value.delete.assert_called_once()
        self.assertEqual((self.event()['operation'], self.event()['target']),
                         ('file_delete', 'entry'))
        self.assertNotIn('private.bin', self.stream.getvalue())

    def test_flash_or_storage_read_and_dma_run_do_not_log_paths_or_password(self):
        client = UltimateClient('c64u.local', password='private-password')
        with patch('c64u_browser.native_files.connect') as connect:
            ftp = connect.return_value
            ftp.size.return_value = 3
            ftp.retrbinary.side_effect = lambda _command, callback: callback(b'abc')
            self.assertEqual(read_remote(client, '/Flash/roms/private.rom'), b'abc')
        self.assertEqual((self.event()['transport'], self.event()['target']),
                         ('ftp', 'file'))
        self.assertNotIn('private.rom', self.stream.getvalue())
        self.stream.seek(0)
        self.stream.truncate()
        with self.assertRaises(BrowserError):
            mount_and_run(client, '/USB2/private-image.d81')
        self.assertEqual((self.event()['transport'], self.event()['operation'],
                          self.event()['target'], self.event()['outcome']),
                         ('dma', 'mount_and_run', 'disk', 'error'))
        self.assertNotIn('private-image.d81', self.stream.getvalue())
        self.assertNotIn('private-password', self.stream.getvalue())

    def test_disk_image_events_use_format_and_generic_entry_labels(self):
        fixture = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'
        image = D64Image.from_path(fixture)
        directory = image.directory()
        event = self.event()
        self.assertEqual((event['transport'], event['operation'], event['target']),
                         ('disk_image', 'read_directory', 'd64'))
        self.assertNotIn('ARGONAUT', self.stream.getvalue())
        self.stream.seek(0)
        self.stream.truncate()
        self.assertEqual(len(image.read_file(directory.entries[0])), 14)
        event = self.event()
        self.assertEqual((event['transport'], event['operation'], event['target']),
                         ('disk_image', 'read_file', 'entry'))
        self.assertNotIn('HELLO', self.stream.getvalue())
        self.stream.seek(0)
        self.stream.truncate()
        session = D64EditSession(image)
        session.rename(directory.entries[0], 'PRIVATE NAME')
        events = [json.loads(line) for line in self.stream.getvalue().splitlines()]
        event = next(item for item in events if item['operation'] == 'stage_rename')
        self.assertEqual((event['transport'], event['operation'], event['target']),
                         ('disk_image', 'stage_rename', 'entry'))
        self.assertNotIn('PRIVATE NAME', self.stream.getvalue())

    def test_d71_directory_event_uses_only_format_label(self):
        fixture = Path(__file__).with_name('fixtures') / 'vice-1571-authentic.d71'
        D71Image.from_path(fixture).directory()
        event = self.event()
        self.assertEqual((event['transport'], event['operation'], event['target']),
                         ('disk_image', 'read_directory', 'd71'))
        self.assertNotIn('ARGONAUT', self.stream.getvalue())

    def test_development_log_is_private_bounded_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'argonaut-development'
            handler = enable_private_log(base / 'config.json', max_bytes=400,
                                         backups=2)
            try:
                for _ in range(20):
                    with operation_event('ftp', 'download', 'file'):
                        pass
            finally:
                disable_private_log(handler)
            folder = base / 'diagnostics'
            files = sorted(folder.glob('operations.jsonl*'))
            self.assertLessEqual(len(files), 3)
            self.assertGreater(len(files), 1)
            rows = [json.loads(line) for path in files
                    for line in path.read_text().splitlines()]
            self.assertTrue(rows)
            self.assertTrue(all(row['operation'] == 'download' and
                                row['target'] == 'file' and
                                row['origin'] == 'device' for row in rows))
            if os.name != 'nt':
                self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
                self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600
                                    for path in files))

    def test_offline_fixture_events_stay_in_report_not_activity_log(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'argonaut-development'
            handler = enable_private_log(base / 'config.json')
            try:
                report = run_default_checks()
                self.assertEqual(report['status'], 'pass')
                events = [event for check in report['checks']
                          for event in check['operations']]
                self.assertTrue(events)
                self.assertTrue(all(event['origin'] == 'simulation'
                                    for event in events))
                self.assertEqual((base / 'diagnostics/operations.jsonl').read_text(), '')
                with operation_event('ftp', 'download', 'file'):
                    pass
            finally:
                disable_private_log(handler)
            rows = (base / 'diagnostics/operations.jsonl').read_text().splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])['origin'], 'device')


if __name__ == '__main__':
    unittest.main()
