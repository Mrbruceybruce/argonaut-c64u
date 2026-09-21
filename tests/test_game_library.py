# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.game_library import (
    ArtworkReference, GameLibraryError, GameLibraryService, GameSource,
    default_catalog_path, inspect_crt,
)
from c64u_browser.core import ArgonautCore
from c64u_browser.profiles import Preferences
from c64u_browser.scheduler import DeviceSession


D64_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'


def crt_bytes(payload=b'x' * 8192, name='TEST CART', hardware_type=0):
    header = bytearray(64)
    header[:16] = b'C64 CARTRIDGE   '
    header[0x10:0x14] = (64).to_bytes(4, 'big')
    header[0x14:0x16] = (0x0100).to_bytes(2, 'big')
    header[0x16:0x18] = hardware_type.to_bytes(2, 'big')
    header[0x18:0x1a] = b'\x00\x01'
    encoded = name.encode('ascii')[:32]
    header[0x20:0x20 + len(encoded)] = encoded
    chip = (b'CHIP' + (16 + len(payload)).to_bytes(4, 'big')
            + b'\x00\x00\x00\x00\x80\x00' + len(payload).to_bytes(2, 'big')
            + payload)
    return bytes(header) + chip


class GameLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / 'state' / 'game-library.json'
        self.service = GameLibraryService(
            self.catalog, clock=lambda: 100.0,
            id_factory=self.ids(['game-1', 'game-2', 'plan-1', 'plan-2',
                                 'plan-3', 'plan-4']))
        self.addCleanup(self.service.close)
        self.service.load()

    @staticmethod
    def ids(values):
        iterator = iter(values)
        return lambda: next(iterator)

    def local_crt(self, name='game.crt', data=None):
        path = self.root / name
        path.write_bytes(crt_bytes() if data is None else data)
        return path

    def add(self, path, title=''):
        result = self.service.add(GameSource.core_host(path), title=title).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def test_add_list_get_search_and_metadata_roundtrip(self):
        game = self.local_crt()
        before = game.read_bytes()
        added = self.add(game, 'Space Game')
        self.assertTrue(added.created)
        record = added.record
        self.assertEqual(('CRT', 'Space Game', 'available'),
                         (record.format, record.title, record.state))
        self.assertEqual(record, self.service.get(record.id))
        self.assertEqual((record,), self.service.search('space'))
        self.assertEqual((record,), self.service.search(str(game.parent)))

        self.service.edit_title(record.id, 'New Title')
        self.service.set_favorite(record.id, True)
        self.service.set_notes(record.id, 'Two players and joysticks')
        artwork = self.root / 'cover.png'; artwork.write_bytes(b'png')
        self.service.set_artwork(record.id, ArtworkReference.core_host(artwork))
        updated = self.service.get(record.id)
        self.assertEqual('New Title', updated.title)
        self.assertTrue(updated.favorite)
        self.assertEqual('Two players and joysticks', updated.notes)
        self.assertEqual(str(artwork), updated.artwork.path)
        self.assertEqual((updated,), self.service.search('joysticks', favorite=True))
        self.assertEqual((), self.service.search('', favorite=False))

        reopened = GameLibraryService(self.catalog).load()
        self.addCleanup(reopened.close)
        self.assertEqual(updated, reopened.get(record.id))
        self.assertEqual(before, game.read_bytes())

    def test_d64_and_crt_validation_metadata(self):
        d64 = self.root / 'disk.d64'; d64.write_bytes(D64_FIXTURE.read_bytes())
        disk = self.add(d64).record
        cart = self.add(self.local_crt()).record
        self.assertEqual('D64', disk.format)
        self.assertEqual('ARGONAUT', dict(disk.metadata)['disk_name'])
        self.assertEqual(35, dict(disk.metadata)['tracks'])
        self.assertEqual('CRT', cart.format)
        self.assertEqual('TEST CART', dict(cart.metadata)['cartridge_name'])
        self.assertEqual(1, dict(cart.metadata)['chips'])
        self.assertEqual(8192, dict(cart.metadata)['rom_bytes'])

    def test_rejects_unsupported_or_malformed_files_without_catalog_entry(self):
        unsupported = self.root / 'game.prg'; unsupported.write_bytes(b'hello')
        with self.assertRaisesRegex(GameLibraryError, 'D64 and CRT'):
            self.service.add(GameSource.core_host(unsupported))
        malformed = self.local_crt(data=b'not a cartridge')
        result = self.service.add(GameSource.core_host(malformed)).wait(5)
        self.assertEqual('failed', result.state)
        self.assertEqual('malformed-image', result.error.code)
        self.assertEqual((), self.service.list())
        damaged = bytearray(crt_bytes()); damaged[64:68] = b'NOPE'
        with self.assertRaises(GameLibraryError):inspect_crt(damaged)

    def test_duplicate_source_content_and_changed_source_are_explicit(self):
        first_path = self.local_crt('one.crt')
        first = self.add(first_path).record
        same_source = self.add(first_path)
        self.assertFalse(same_source.created)
        self.assertEqual('source', same_source.duplicate_kind)

        second_path = self.local_crt('two.crt')
        same_content = self.add(second_path)
        self.assertFalse(same_content.created)
        self.assertEqual('content', same_content.duplicate_kind)
        self.assertEqual(first.id, same_content.record.id)

        first_path.write_bytes(crt_bytes(b'y' * 8192, 'CHANGED'))
        changed = self.add(first_path)
        self.assertFalse(changed.created)
        self.assertEqual('source-changed', changed.duplicate_kind)
        self.assertNotEqual(changed.expected_sha256, changed.observed_sha256)
        self.assertEqual('changed', self.service.get(first.id).state)

    def test_validate_marks_missing_changed_and_recovered(self):
        path = self.local_crt()
        record = self.add(path).record
        path.write_bytes(crt_bytes(b'z' * 8192))
        changed = self.service.validate_source(record.id).wait(5).result
        self.assertEqual('changed', changed.record.state)
        self.assertNotEqual(changed.expected_sha256, changed.observed_sha256)

        path.unlink()
        missing = self.service.validate_source(record.id).wait(5).result
        self.assertEqual('missing', missing.record.state)
        path.write_bytes(crt_bytes())
        available = self.service.validate_source(record.id).wait(5).result
        self.assertEqual('available', available.record.state)
        self.assertEqual('', available.record.state_message)

        path.write_bytes(b'broken')
        malformed = self.service.validate_source(record.id).wait(5).result
        self.assertEqual('changed', malformed.record.state)
        self.assertIn('no longer validates', malformed.record.state_message)

    def test_remote_identity_persists_and_unavailable_device_is_structured(self):
        session = [DeviceSession('id:C64-A', 'session-1')]
        reads = []
        def reader(source):
            reads.append(source)
            return crt_bytes()
        service = GameLibraryService(
            self.catalog, remote_reader=reader, session_provider=lambda:session[0],
            id_factory=self.ids(['remote-game']))
        self.addCleanup(service.close); service.load()
        source = GameSource.c64u('id:C64-A', '/USB2/Games/cart.crt')
        added = service.add(source).wait(5)
        self.assertEqual('succeeded', added.state)
        record = added.result.record
        self.assertEqual(('id:C64-A', '/USB2', '/USB2/Games/cart.crt'),
                         (record.source.device_id, record.source.volume,
                          record.source.path))
        session[0] = DeviceSession('id:C64-B', 'session-2')
        validation = service.validate_source(record.id).wait(5).result
        self.assertEqual('unavailable', validation.record.state)
        self.assertEqual(1, len(reads))
        self.assertEqual('id:C64-A', GameLibraryService(self.catalog).load().get(
            record.id).source.device_id)

    def test_remote_read_failure_is_unavailable(self):
        session = DeviceSession('id:C64-A', 'session-1')
        source = GameSource.c64u('id:C64-A', '/SD/cart.crt')
        service = GameLibraryService(
            self.catalog, remote_reader=lambda _source:crt_bytes(),
            session_provider=lambda:session, id_factory=self.ids(['remote']))
        self.addCleanup(service.close);service.load()
        record = service.add(source).wait(5).result.record
        service._remote_reader = lambda _source:(_ for _ in ()).throw(
            ConnectionFailure('network', 'private host'))
        result = service.validate_source(record.id).wait(5).result
        self.assertEqual('unavailable', result.record.state)
        self.assertNotIn('private host', result.record.state_message)

    def test_relink_matching_content_and_reviewed_different_content(self):
        original = self.local_crt('original.crt')
        record = self.add(original).record
        moved = self.local_crt('moved.crt')
        original.unlink()
        preview = self.service.prepare_relink(
            record.id, GameSource.core_host(moved)).wait(5).result
        self.assertTrue(preview.content_matches)
        result = self.service.execute_relink(preview.plan_id).wait(5).result
        self.assertFalse(result.content_changed)
        self.assertEqual(str(moved), result.record.source.path)

        replacement = self.local_crt('replacement.crt', crt_bytes(b'q' * 8192))
        preview = self.service.prepare_relink(
            record.id, GameSource.core_host(replacement)).wait(5).result
        self.assertFalse(preview.content_matches)
        self.assertNotEqual(preview.expected_sha256, preview.observed_sha256)
        with self.assertRaisesRegex(GameLibraryError, 'explicitly accept'):
            self.service.execute_relink(preview.plan_id)
        preview = self.service.prepare_relink(
            record.id, GameSource.core_host(replacement)).wait(5).result
        accepted = self.service.execute_relink(
            preview.plan_id, accept_changed=True).wait(5).result
        self.assertTrue(accepted.content_changed)
        self.assertEqual(preview.observed_sha256, accepted.record.sha256)

    def test_relink_revalidates_after_review_and_plan_is_one_use(self):
        original = self.local_crt('original.crt')
        record = self.add(original).record
        candidate = self.local_crt('candidate.crt')
        preview = self.service.prepare_relink(
            record.id, GameSource.core_host(candidate)).wait(5).result
        candidate.write_bytes(crt_bytes(b'v' * 8192))
        failed = self.service.execute_relink(preview.plan_id).wait(5)
        self.assertEqual('failed', failed.state)
        self.assertEqual('changed-source', failed.error.code)
        self.assertEqual(str(original), self.service.get(record.id).source.path)
        with self.assertRaisesRegex(GameLibraryError, 'already used'):
            self.service.execute_relink(preview.plan_id)

    def test_relink_preview_cannot_overwrite_newer_metadata_decision(self):
        original = self.local_crt('original.crt')
        record = self.add(original).record
        candidate = self.local_crt('candidate.crt')
        preview = self.service.prepare_relink(
            record.id, GameSource.core_host(candidate)).wait(5).result
        self.service.edit_title(record.id, 'Changed after review')
        failed = self.service.execute_relink(preview.plan_id).wait(5)
        self.assertEqual('failed', failed.state)
        self.assertEqual('plan-stale', failed.error.code)
        self.assertEqual(str(original), self.service.get(record.id).source.path)

    def test_remove_deletes_only_catalog_entry(self):
        path = self.local_crt()
        record = self.add(path).record
        removed = self.service.remove(record.id)
        self.assertEqual(record.id, removed.id)
        self.assertTrue(path.is_file())
        self.assertEqual((), self.service.list())

    def test_artwork_is_core_host_reference_and_is_not_managed(self):
        record = self.add(self.local_crt()).record
        missing = self.root / 'missing.png'
        with self.assertRaises(GameLibraryError):
            self.service.set_artwork(record.id, ArtworkReference.core_host(missing))
        artwork = self.root / 'cover.jpg';artwork.write_bytes(b'image')
        self.service.set_artwork(record.id, ArtworkReference.core_host(artwork))
        self.service.set_artwork(record.id, None)
        self.assertTrue(artwork.exists())

    def test_malformed_catalog_is_preserved_and_blocks_operations(self):
        original = '{"schema_version":1,"games":[{"bad":true}]}'
        self.catalog.parent.mkdir(parents=True)
        self.catalog.write_text(original)
        service = GameLibraryService(self.catalog)
        self.addCleanup(service.close)
        with self.assertRaisesRegex(GameLibraryError, 'original file has been kept'):
            service.load()
        self.assertEqual(original, self.catalog.read_text())
        with self.assertRaises(GameLibraryError):service.list()

    def test_failed_atomic_publication_keeps_memory_and_catalog_unchanged(self):
        first = self.add(self.local_crt('first.crt')).record
        before = self.catalog.read_bytes()
        with patch('c64u_browser.game_library.os.replace', side_effect=OSError('disk')):
            failed = self.service.add(GameSource.core_host(
                self.local_crt('second.crt', crt_bytes(b'2' * 8192)))).wait(5)
        self.assertEqual('failed', failed.state)
        self.assertEqual((first,), self.service.list())
        self.assertEqual(before, self.catalog.read_bytes())
        self.assertEqual([], list(self.catalog.parent.glob('.game-library-*')))

    def test_stable_and_development_catalogs_are_isolated(self):
        with patch('c64u_browser.game_library.config_base', return_value=self.root):
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'0'}):
                stable = default_catalog_path()
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
                development = default_catalog_path()
        self.assertNotEqual(stable, development)
        self.assertEqual('argonaut', stable.parent.name)
        self.assertEqual('argonaut-development', development.parent.name)

    def test_core_uses_catalog_beside_its_selected_configuration(self):
        preferences = Preferences(self.root / 'private-state' / 'config.json')
        core = ArgonautCore(preferences=preferences)
        self.addCleanup(core.close)
        self.assertEqual(self.root / 'private-state' / 'game-library.json',
                         core.game_library.path)

    def test_catalog_schema_is_versioned_plain_json(self):
        self.add(self.local_crt())
        data = json.loads(self.catalog.read_text())
        self.assertEqual(1, data['schema_version'])
        self.assertEqual('core-host', data['games'][0]['source']['scope'])
        self.assertEqual('CRT', data['games'][0]['format'])
        self.assertEqual(64, len(data['games'][0]['sha256']))
        self.assertNotIn('password', self.catalog.read_text().casefold())

    def test_import_is_headless_and_has_no_transport_or_display_dependency(self):
        root = str(Path(__file__).resolve().parents[1]);env = dict(os.environ)
        env.pop('DISPLAY', None);env.pop('WAYLAND_DISPLAY', None)
        code = ("import sys; import c64u_browser.game_library as g; "
                "assert 'gi.repository.Gtk' not in sys.modules; "
                "assert 'UltimateClient' not in vars(g)")
        result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':unittest.main()
