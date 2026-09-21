# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import time
import unittest

from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.disk_run import DmaLaunchError
from c64u_browser.game_launch import GameLaunchError, GameLaunchService
from c64u_browser.game_library import (
    GameLibraryError, GameLibraryService, GameSource, inspect_crt,
)
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding


D64_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'


def crt_bytes(payload=b'x' * 8192, name='TEST CART', hardware_type=0,
              version=0x0100, header_length=64):
    header = bytearray(header_length)
    header[:16] = b'C64 CARTRIDGE   '
    header[0x10:0x14] = header_length.to_bytes(4, 'big')
    header[0x14:0x16] = version.to_bytes(2, 'big')
    header[0x16:0x18] = hardware_type.to_bytes(2, 'big')
    header[0x18:0x1a] = b'\x00\x01'
    encoded = name.encode('ascii')[:32]
    header[0x20:0x20 + len(encoded)] = encoded
    chip = (b'CHIP' + (16 + len(payload)).to_bytes(4, 'big')
            + b'\x00\x00\x00\x00\x80\x00' + len(payload).to_bytes(2, 'big')
            + payload)
    return bytes(header) + chip


class DummyClient:
    pass


class GameLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.session = DeviceSession('id:C64-A', 'session-1')
        self.scheduler = CoreScheduler(lambda:self.session)
        self.addCleanup(self.scheduler.close)
        self.remote = {}
        self.catalog = GameLibraryService(
            self.root / 'game-library.json',
            remote_reader=lambda source:self.remote[source.path],
            session_provider=lambda:self.session, scheduler=self.scheduler,
            id_factory=self.ids('game'))
        self.catalog.load()
        self.media = {'value':'media-one'}
        self.calls = []
        self.service = self.launch_service()

    @staticmethod
    def ids(prefix):
        number = [0]
        def value():
            number[0] += 1
            return f'{prefix}-{number[0]}'
        return value

    def launch_service(self, **changes):
        values = dict(
            volume_identity=lambda source, check:(check(), self.media['value'])[1],
            attached_crt_runner=lambda client, data, source:
                self.calls.append(('host-crt', client, data, source)),
            resident_crt_runner=lambda client, data, source:
                self.calls.append(('remote-crt', client, data, source)),
            d64_runner=lambda client, data, source:
                self.calls.append(('d64', client, data, source)),
            id_factory=self.ids('plan'))
        values.update(changes)
        return GameLaunchService(
            self.catalog, lambda:DummyClient(), lambda:self.session,
            self.scheduler, **values)

    def local(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return GameSource.core_host(path)

    def remote_source(self, path, data):
        self.remote[path] = data
        return GameSource.c64u('id:C64-A', path)

    def add(self, source, title='Game'):
        snapshot = self.catalog.add(source, title=title).wait(5)
        self.assertEqual('succeeded', snapshot.state, snapshot.error)
        return snapshot.result.record

    def preview(self, record):
        result = self.service.prepare_launch(record.id).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def execute(self, preview):
        return self.service.execute_launch(preview.plan_id).wait(5)

    def test_all_four_routes_and_structured_results(self):
        records = (
            self.add(self.local('local.crt', crt_bytes()), 'Local CRT'),
            self.add(self.remote_source('/USB2/remote.crt',
                                        crt_bytes(name='REMOTE')), 'Remote CRT'),
            self.add(self.local('local.d64', D64_FIXTURE.read_bytes()), 'Local D64'),
            self.add(self.remote_source('/USB2/remote.d64',
                                        D64_FIXTURE.read_bytes()), 'Remote D64'),
        )
        expected = ('rest-attached-crt', 'rest-c64u-crt',
                    'dma-run-img', 'dma-run-img')
        for record, mechanism in zip(records, expected):
            preview = self.preview(record)
            self.assertEqual(mechanism, preview.mechanism)
            self.assertEqual(('id:C64-A', 'session-1'),
                             (preview.target_device_id,
                              preview.target_session_id))
            self.assertTrue(preview.reset_expected)
            self.assertTrue(preview.running_program_interrupted)
            json.dumps(preview.as_dict())
            finished = self.execute(preview)
            self.assertEqual('succeeded', finished.state, finished.error)
            result = finished.result
            self.assertEqual('command-accepted', result.status)
            self.assertTrue(result.command_accepted)
            self.assertFalse(result.playable_state_verified)
            json.dumps(result.as_dict())
        self.assertEqual(['host-crt', 'remote-crt', 'd64', 'd64'],
                         [row[0] for row in self.calls])

    def test_crt_parser_accepts_extended_header_and_unknown_hardware(self):
        data = crt_bytes(hardware_type=0xffff, version=0x0200,
                         header_length=80)
        metadata = dict(inspect_crt(data))
        self.assertEqual(0xffff, metadata['hardware_type'])
        record = self.add(self.local('unknown.crt', data))
        preview = self.preview(record)
        self.assertIn('65535', ' '.join(preview.warnings))
        self.assertEqual('succeeded', self.execute(preview).state)
        empty_ram = bytearray(crt_bytes())[:80]
        empty_ram[68:72] = (16).to_bytes(4, 'big')
        empty_ram[72:74] = (1).to_bytes(2, 'big')
        empty_ram[78:80] = b'\0\0'
        self.assertEqual(0, dict(inspect_crt(empty_ram))['rom_bytes'])

    def test_crt_parser_rejects_header_packet_length_rom_and_truncation(self):
        cases = []
        data = bytearray(crt_bytes());data[0x10:0x14] = (63).to_bytes(4, 'big');cases.append(data)
        data = bytearray(crt_bytes());data[0x14:0x16] = b'\0\0';cases.append(data)
        data = bytearray(crt_bytes());data[68:72] = (15).to_bytes(4, 'big');cases.append(data)
        data = bytearray(crt_bytes());data[78:80] = b'\0\0';cases.append(data)
        data = bytearray(crt_bytes());data[76:78] = b'\xff\xff';cases.append(data)
        cases.append(crt_bytes()[:-1])
        for data in cases:
            with self.subTest(length=len(data)):
                with self.assertRaises(GameLibraryError):
                    inspect_crt(data)

    def test_source_change_missing_and_malformed_after_preview_fail_before_launch(self):
        source = self.local('game.crt', crt_bytes())
        record = self.add(source)
        preview = self.preview(record)
        Path(source.path).write_bytes(crt_bytes(b'y' * 8192))
        changed = self.execute(preview)
        self.assertEqual(('failed', 'source-changed'),
                         (changed.state, changed.error.code))
        self.assertFalse(self.calls)

        self.catalog.set_notes(record.id, 'refresh record for next preview')
        # Restore the original content so a new reviewed plan can be created.
        Path(source.path).write_bytes(crt_bytes())
        preview = self.preview(self.catalog.get(record.id))
        Path(source.path).unlink()
        missing = self.execute(preview)
        self.assertEqual(('failed', 'missing-source'),
                         (missing.state, missing.error.code))

        Path(source.path).write_bytes(crt_bytes())
        preview = self.preview(self.catalog.get(record.id))
        Path(source.path).write_bytes(b'broken')
        malformed = self.execute(preview)
        self.assertEqual(('failed', 'malformed-image'),
                         (malformed.state, malformed.error.code))
        self.assertFalse(self.calls)

    def test_catalog_record_change_after_preview_is_rejected(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        preview = self.preview(record)
        self.catalog.set_notes(record.id, 'changed after review')
        failed = self.execute(preview)
        self.assertEqual(('failed', 'record-changed'),
                         (failed.state, failed.error.code))
        self.assertFalse(self.calls)

    def test_device_and_session_changes_after_preview_are_rejected(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        preview = self.preview(record)
        self.session = DeviceSession('id:C64-B', 'session-2')
        with self.assertRaisesRegex(GameLaunchError, 'active C64U changed'):
            self.service.execute_launch(preview.plan_id)

        self.session = DeviceSession('id:C64-A', 'session-3')
        preview = self.preview(record)
        self.session = DeviceSession('id:C64-A', 'session-4')
        with self.assertRaisesRegex(GameLaunchError, 'connection changed'):
            self.service.execute_launch(preview.plan_id)
        self.assertFalse(self.calls)

    def test_launch_requires_an_available_target_device(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        self.session = DeviceSession('', '')
        with self.assertRaises(GameLaunchError) as failure:
            self.service.prepare_launch(record.id)
        self.assertEqual('device-unavailable', failure.exception.code)

    def test_removable_media_change_after_preview_is_rejected(self):
        record = self.add(self.remote_source('/USB2/game.crt', crt_bytes()))
        preview = self.preview(record)
        self.media['value'] = 'replacement-media'
        failed = self.execute(preview)
        self.assertEqual(('failed', 'storage-changed'),
                         (failed.state, failed.error.code))
        self.assertFalse(self.calls)

    def test_expired_and_consumed_plans_fail_safely(self):
        now = [100.0]
        service = self.launch_service(plan_ttl=5, clock=lambda:now[0])
        record = self.add(self.local('game.crt', crt_bytes()))
        preview = service.prepare_launch(record.id).wait(5).result
        now[0] += 6
        with self.assertRaises(GameLaunchError):service.execute_launch(preview.plan_id)
        fresh = service.prepare_launch(record.id).wait(5).result
        self.assertEqual('succeeded', service.execute_launch(fresh.plan_id).wait(5).state)
        with self.assertRaises(GameLaunchError):service.execute_launch(fresh.plan_id)

    def test_queued_and_preconsequential_cancellation_never_launch(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        preview = self.preview(record)
        gate = Event();entered = Event()
        blocker = self.scheduler.submit(
            CoreJob('block', lambda _:(entered.set(), gate.wait(2))),
            JobBinding.device(self.session))
        self.assertTrue(entered.wait(1))
        queued = self.service.execute_launch(preview.plan_id)
        self.assertTrue(self.service.cancel(queued.id));gate.set();blocker.wait(2)
        self.assertEqual('cancelled', queued.wait(2).state)
        self.assertFalse(self.calls)

        preview = self.preview(record)
        entered = Event();release = Event()
        original = self.catalog._inspect_data
        def paused(*args, **kwargs):
            value = original(*args, **kwargs)
            entered.set();release.wait(2)
            return value
        self.catalog._inspect_data = paused
        running = self.service.execute_launch(preview.plan_id)
        self.assertTrue(entered.wait(1));self.assertTrue(self.service.cancel(running.id))
        release.set()
        self.assertEqual('cancelled', running.wait(2).state)
        self.assertFalse(self.calls)

    def test_late_cancellation_preserves_command_accepted_result(self):
        entered = Event();release = Event();count = []
        def runner(client, data, source):
            count.append(1);entered.set();release.wait(2)
        self.service = self.launch_service(attached_crt_runner=runner)
        record = self.add(self.local('game.crt', crt_bytes()))
        running = self.service.execute_launch(self.preview(record).plan_id)
        self.assertTrue(entered.wait(1));self.assertTrue(self.service.cancel(running.id))
        release.set();finished = running.wait(2)
        self.assertEqual('succeeded', finished.state)
        self.assertEqual('command-accepted', finished.result.status)
        self.assertEqual([1], count)

    def test_rejection_uncertainty_and_no_retry(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        attempts = []
        def rejected(*_):
            attempts.append(1);raise ConnectionFailure('api', 'private detail')
        self.service = self.launch_service(attached_crt_runner=rejected)
        failed = self.execute(self.preview(record))
        self.assertEqual(('failed', 'firmware-rejection'),
                         (failed.state, failed.error.code))
        self.assertEqual([1], attempts)
        self.assertNotIn('private', failed.error.message)

        attempts.clear()
        def uncertain(*_):
            attempts.append(1);raise ConnectionFailure('network', 'private')
        self.service = self.launch_service(attached_crt_runner=uncertain)
        failed = self.execute(self.preview(record))
        self.assertEqual(('failed', 'launch-outcome-unknown'),
                         (failed.state, failed.error.code))
        self.assertEqual([1], attempts)

    def test_dma_uncertainty_is_preserved(self):
        record = self.add(self.local('game.d64', D64_FIXTURE.read_bytes()))
        def uncertain(*_):
            raise DmaLaunchError('may have started',
                                 command_may_have_started=True)
        self.service = self.launch_service(d64_runner=uncertain)
        failed = self.execute(self.preview(record))
        self.assertEqual('launch-outcome-unknown', failed.error.code)

        def rejected(*_):
            raise DmaLaunchError('nothing started',
                                 command_may_have_started=False)
        self.service = self.launch_service(d64_runner=rejected)
        failed = self.execute(self.preview(record))
        self.assertEqual('firmware-rejection', failed.error.code)

    def test_headless_contract_has_no_transport_or_credentials(self):
        record = self.add(self.local('game.crt', crt_bytes()))
        preview = self.preview(record)
        payload = json.dumps(preview.as_dict())
        self.assertNotIn('password', payload.casefold())
        self.assertNotIn('UltimateClient', payload)
        root = str(Path(__file__).resolve().parents[1]);env = dict(os.environ)
        env.pop('DISPLAY', None);env.pop('WAYLAND_DISPLAY', None)
        code = ("import sys; import c64u_browser.game_launch; "
                "assert 'gi.repository.Gtk' not in sys.modules")
        result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':unittest.main()
