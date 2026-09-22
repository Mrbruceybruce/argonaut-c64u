# SPDX-License-Identifier: GPL-3.0-or-later
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.api import ConnectionFailure
from c64u_browser.core import ArgonautCore
from c64u_browser.profiles import Preferences
from c64u_browser.scheduler import DeviceSession
from c64u_browser.sid_format import MAX_SID_BYTES
from c64u_browser.sid_jukebox import (
    SidCatalogError, SidCatalogService, SidSource, default_catalog_path,
)
from tests.test_sid_format import sid_bytes


class SidCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / 'state' / 'sid-jukebox.json'
        counter = itertools.count(1)
        self.service = SidCatalogService(
            self.store, clock=lambda:100.0,
            id_factory=lambda:f'id-{next(counter)}')
        self.addCleanup(self.service.close)
        self.service.load()

    def local_sid(self, name='tune.sid', **kwargs):
        path = self.root / name
        path.write_bytes(sid_bytes(**kwargs))
        return path

    def add(self, path):
        result = self.service.add(SidSource.core_host(path)).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def test_add_list_get_search_favorite_notes_and_roundtrip(self):
        path = self.local_sid(title='Café Tune', author='Rob', released='2026')
        before = path.read_bytes()
        added = self.add(path)
        tune = added.tune
        self.assertTrue(added.created)
        self.assertEqual(('Café Tune', 'available', 'PSID'),
                         (tune.title, tune.state, tune.metadata.format))
        self.assertEqual((tune,), self.service.search('rob'))
        self.service.set_favorite(tune.id, True)
        self.service.set_notes(tune.id, 'Good on a 6581')
        updated = self.service.get(tune.id)
        self.assertEqual((updated,), self.service.search('6581', favorite=True))
        self.assertEqual((), self.service.search('', favorite=False))
        reopened = SidCatalogService(self.store).load()
        self.addCleanup(reopened.close)
        self.assertEqual(updated, reopened.get(tune.id))
        self.assertEqual(before, path.read_bytes())

    def test_duplicate_source_content_and_changed_source(self):
        first_path = self.local_sid('one.sid')
        first = self.add(first_path).tune
        self.assertEqual('source', self.add(first_path).duplicate_kind)
        second_path = self.local_sid('two.sid')
        duplicate = self.add(second_path)
        self.assertEqual(('content', first.id),
                         (duplicate.duplicate_kind, duplicate.tune.id))
        first_path.write_bytes(sid_bytes(title='Changed'))
        changed = self.add(first_path)
        self.assertEqual('source-changed', changed.duplicate_kind)
        self.assertEqual('changed', self.service.get(first.id).state)

    def test_validate_missing_changed_malformed_and_recovered(self):
        path = self.local_sid()
        tune = self.add(path).tune
        path.write_bytes(sid_bytes(title='Changed'))
        changed = self.service.validate_source(tune.id).wait(5).result
        self.assertEqual('changed', changed.tune.state)
        self.assertNotEqual(changed.expected_sha256, changed.observed_sha256)
        path.unlink()
        missing = self.service.validate_source(tune.id).wait(5).result
        self.assertEqual('missing', missing.tune.state)
        path.write_bytes(b'broken')
        malformed = self.service.validate_source(tune.id).wait(5).result
        self.assertEqual('changed', malformed.tune.state)
        path.write_bytes(sid_bytes())
        recovered = self.service.validate_source(tune.id).wait(5).result
        self.assertEqual('available', recovered.tune.state)

    def test_c64u_identity_and_unavailable_state(self):
        session = [DeviceSession('id:C64-A', 'session-1')]
        service = SidCatalogService(
            self.store, remote_reader=lambda _source:sid_bytes(),
            session_provider=lambda:session[0])
        self.addCleanup(service.close); service.load()
        source = SidSource.c64u('id:C64-A', '/USB2/Music/tune.sid')
        added = service.add(source).wait(5)
        self.assertEqual('succeeded', added.state)
        tune = added.result.tune
        self.assertEqual(('id:C64-A', '/USB2'),
                         (tune.source.device_id, tune.source.volume))
        session[0] = DeviceSession('id:C64-B', 'session-2')
        unavailable = service.validate_source(tune.id).wait(5).result
        self.assertEqual('unavailable', unavailable.tune.state)

    def test_core_c64u_sid_reader_applies_sid_specific_size_bound(self):
        core = ArgonautCore(preferences=Preferences(self.root / 'core.json'))
        self.addCleanup(core.close)
        core._device_identity = 'id:C64-A'
        core._client = object()
        source = SidSource.c64u('id:C64-A', '/USB2/Music/tune.sid')
        with patch('c64u_browser.native_files.read_remote',
                   return_value=sid_bytes()) as read:
            core._read_sid_source(source)
        read.assert_called_once_with(core._client, source.path, MAX_SID_BYTES)

    def test_remote_failure_is_sanitized_unavailable(self):
        session = DeviceSession('id:C64-A', 'session-1')
        service = SidCatalogService(
            self.store, remote_reader=lambda _source:sid_bytes(),
            session_provider=lambda:session)
        self.addCleanup(service.close); service.load()
        tune = service.add(SidSource.c64u(
            'id:C64-A', '/SD/tune.sid')).wait(5).result.tune
        service._remote_reader = lambda _source:(_ for _ in ()).throw(
            ConnectionFailure('network', 'private network detail'))
        result = service.validate_source(tune.id).wait(5).result
        self.assertEqual('unavailable', result.tune.state)
        self.assertNotIn('private network detail', result.tune.state_message)

    def test_relink_across_scopes_matching_and_changed_review(self):
        original = self.local_sid('original.sid')
        tune = self.add(original).tune
        session = DeviceSession('id:C64-A', 'session-1')
        service = SidCatalogService(
            self.store, remote_reader=lambda _source:sid_bytes(),
            session_provider=lambda:session)
        self.addCleanup(service.close); service.load()
        remote = SidSource.c64u('id:C64-A', '/USB2/Music/moved.sid')
        preview = service.prepare_relink(tune.id, remote).wait(5).result
        self.assertTrue(preview.content_matches)
        result = service.execute_relink(preview.plan_id).wait(5).result
        self.assertEqual(('c64u', False),
                         (result.tune.source.scope, result.content_changed))

        replacement = self.local_sid('different.sid', title='Different')
        preview = service.prepare_relink(
            tune.id, SidSource.core_host(replacement)).wait(5).result
        self.assertFalse(preview.content_matches)
        with self.assertRaisesRegex(SidCatalogError, 'explicitly accept'):
            service.execute_relink(preview.plan_id)
        preview = service.prepare_relink(
            tune.id, SidSource.core_host(replacement)).wait(5).result
        accepted = service.execute_relink(
            preview.plan_id, accept_changed=True).wait(5).result
        self.assertTrue(accepted.content_changed)
        self.assertEqual('core-host', accepted.tune.source.scope)

    def test_relink_revalidates_and_is_one_use(self):
        tune = self.add(self.local_sid('original.sid')).tune
        candidate = self.local_sid('candidate.sid')
        preview = self.service.prepare_relink(
            tune.id, SidSource.core_host(candidate)).wait(5).result
        candidate.write_bytes(sid_bytes(title='Changed later'))
        result = self.service.execute_relink(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'changed-source'),
                         (result.state, result.error.code))
        with self.assertRaisesRegex(SidCatalogError, 'already used'):
            self.service.execute_relink(preview.plan_id)

    def test_playlist_crud_order_and_subtune_bounds(self):
        first = self.add(self.local_sid('one.sid', songs=3, start=2,
                                        title='One')).tune
        second = self.add(self.local_sid('two.sid', title='Two')).tune
        playlist = self.service.create_playlist('Road Trip')
        item_one = self.service.add_playlist_item(playlist.id, first.id, 3)
        item_two = self.service.add_playlist_item(playlist.id, second.id, 1)
        self.assertEqual((item_one, item_two),
                         self.service.get_playlist(playlist.id).items)
        reordered = self.service.reorder_playlist_item(
            playlist.id, item_two.id, 0)
        self.assertEqual((item_two.id, item_one.id),
                         tuple(item.id for item in reordered.items))
        renamed = self.service.rename_playlist(playlist.id, 'Favorites')
        self.assertEqual('Favorites', renamed.title)
        removed = self.service.remove_playlist_item(playlist.id, item_one.id)
        self.assertEqual(item_one, removed)
        with self.assertRaises(SidCatalogError):
            self.service.add_playlist_item(playlist.id, first.id, 4)
        reopened = SidCatalogService(self.store).load()
        self.addCleanup(reopened.close)
        self.assertEqual((item_two,), reopened.get_playlist(playlist.id).items)
        self.assertEqual(renamed.title,
                         reopened.get_playlist(playlist.id).title)
        self.assertEqual(playlist.id,
                         self.service.delete_playlist(playlist.id).id)

    def test_remove_does_not_delete_source_and_removes_playlist_references(self):
        path = self.local_sid()
        tune = self.add(path).tune
        playlist = self.service.create_playlist('List')
        self.service.add_playlist_item(playlist.id, tune.id, 1)
        removed = self.service.remove(tune.id)
        self.assertEqual(tune.id, removed.id)
        self.assertTrue(path.exists())
        self.assertEqual((), self.service.get_playlist(playlist.id).items)

    def test_playlist_batch_remove_and_reorder_are_atomic(self):
        tunes=[self.add(self.local_sid(f'{index}.sid',title=f'Tune {index}')).tune
               for index in range(4)]
        playlist=self.service.create_playlist('Editable')
        items=tuple(self.service.add_playlist_item(playlist.id,tune.id,1)
                    for tune in tunes)
        reordered=self.service.reorder_playlist_items(
            playlist.id,(items[1].id,items[3].id,items[0].id,items[2].id))
        self.assertEqual((items[1].id,items[3].id,items[0].id,items[2].id),
                         tuple(item.id for item in reordered.items))
        before=self.store.read_bytes()
        with self.assertRaises(SidCatalogError):
            self.service.reorder_playlist_items(
                playlist.id,(items[0].id,items[1].id))
        self.assertEqual(before,self.store.read_bytes())
        removed=self.service.remove_playlist_items(
            playlist.id,(items[1].id,items[0].id))
        self.assertEqual((items[1],items[0]),removed)
        self.assertEqual((items[3].id,items[2].id),tuple(
            item.id for item in self.service.get_playlist(playlist.id).items))
        before=self.store.read_bytes()
        with self.assertRaises(SidCatalogError):
            self.service.remove_playlist_items(
                playlist.id,(items[3].id,'missing'))
        self.assertEqual(before,self.store.read_bytes())

    def test_atomic_store_schema_and_failed_publication(self):
        first = self.add(self.local_sid('first.sid')).tune
        playlist = self.service.create_playlist('List')
        self.service.add_playlist_item(playlist.id, first.id, 1)
        raw = json.loads(self.store.read_text())
        self.assertEqual((1, 'core-host'),
                         (raw['schema_version'], raw['tunes'][0]['source']['scope']))
        self.assertNotIn('password', self.store.read_text().casefold())
        before = self.store.read_bytes()
        with patch('c64u_browser.sid_jukebox.os.replace', side_effect=OSError('disk')):
            result = self.service.add(SidSource.core_host(
                self.local_sid('second.sid', title='Second'))).wait(5)
        self.assertEqual('failed', result.state)
        self.assertEqual((first,), self.service.list())
        self.assertEqual(before, self.store.read_bytes())
        self.assertEqual([], list(self.store.parent.glob('.sid-jukebox-*')))

    def test_malformed_store_is_preserved_and_blocks_operations(self):
        original = '{"schema_version":1,"tunes":[{"bad":true}],"playlists":[]}'
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(original)
        service = SidCatalogService(self.store)
        self.addCleanup(service.close)
        with self.assertRaisesRegex(SidCatalogError, 'original file has been kept'):
            service.load()
        self.assertEqual(original, self.store.read_text())
        with self.assertRaises(SidCatalogError):service.list()

    def test_stable_development_and_core_selected_state_are_isolated(self):
        with patch('c64u_browser.sid_jukebox.config_base', return_value=self.root):
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'0'}):
                stable = default_catalog_path()
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
                development = default_catalog_path()
        self.assertEqual('argonaut', stable.parent.name)
        self.assertEqual('argonaut-development', development.parent.name)
        self.assertNotEqual(stable, development)
        preferences = Preferences(self.root / 'private-state' / 'config.json')
        core = ArgonautCore(preferences=preferences)
        self.addCleanup(core.close)
        self.assertEqual(self.root / 'private-state' / 'sid-jukebox.json',
                         core.sid_catalog.path)

    def test_import_is_headless_and_exposes_no_raw_transport_or_credentials(self):
        root = str(Path(__file__).resolve().parents[1]); env = dict(os.environ)
        env.pop('DISPLAY', None); env.pop('WAYLAND_DISPLAY', None)
        code = ("import sys; import c64u_browser.sid_format as f; "
                "import c64u_browser.sid_jukebox as s; "
                "assert 'gi.repository.Gtk' not in sys.modules; "
                "assert 'UltimateClient' not in vars(s); "
                "assert 'Credentials' not in vars(s); "
                "assert 'UltimateClient' not in vars(f)")
        result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':unittest.main()
