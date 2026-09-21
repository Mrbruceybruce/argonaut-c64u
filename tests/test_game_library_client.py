# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from c64u_browser.game_library import (
    AddResult, ArtworkReference, GameLibraryService, GameSource,
)
from c64u_browser.game_library_client import (
    GameLibraryClient, add_results_text, client_error_text, mechanism_text,
    source_text,
)
from c64u_browser.jobs import JobError


D64_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'


class GameLibraryClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.library = GameLibraryService(self.root / 'catalog.json').load()
        self.addCleanup(self.library.close)
        self.launcher = Mock()
        self.client = GameLibraryClient(self.library, self.launcher)

    def add_disk(self, name='game.d64', title='Game'):
        path = self.root / name
        path.write_bytes(D64_FIXTURE.read_bytes())
        result = self.client.add_core_host(path).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        record = result.result.record
        if title != 'game':record = self.library.edit_title(record.id, title)
        self.client.select(record.id)
        return path, record

    def test_empty_search_favorites_selection_and_details(self):
        self.assertEqual((), self.client.records())
        _, first = self.add_disk('one.d64', 'Space Game')
        _, second = self.add_disk('two.d64', 'Puzzle Game')
        self.library.set_notes(first.id, 'joystick action')
        self.library.set_favorite(first.id, True)
        self.client.query = 'joystick'
        self.assertEqual((first.id,), tuple(row.id for row in self.client.records()))
        self.client.query = '';self.client.favorites_only = True
        self.assertEqual((first.id,), tuple(row.id for row in self.client.records()))
        self.assertEqual(second.id, self.client.select(second.id).id)

    def test_duplicate_content_add_summary_reports_no_new_record(self):
        first = self.root / 'first.d64'
        duplicate = self.root / 'identical-copy.d64'
        first.write_bytes(D64_FIXTURE.read_bytes())
        duplicate.write_bytes(first.read_bytes())

        created = self.client.add_core_host(first).wait(5).result
        repeated = self.client.add_core_host(duplicate).wait(5).result

        self.assertTrue(created.created)
        self.assertFalse(repeated.created)
        self.assertEqual('content', repeated.duplicate_kind)
        self.assertEqual(created.record.id, repeated.record.id)
        self.assertEqual(1, len(self.library.list()))
        message = add_results_text((repeated,))
        self.assertIn('No new game records', message)
        self.assertIn('duplicate content', message)
        self.assertNotIn('Added 1', message)

    def test_add_summary_distinguishes_source_change_and_rejection(self):
        path, record = self.add_disk()
        same = self.client.add_core_host(path).wait(5).result
        path.write_bytes(D64_FIXTURE.read_bytes()[:-1])
        failed = self.client.add_core_host(path).wait(5)
        message = add_results_text((same,), (client_error_text(failed.error),))
        self.assertIn('already cataloged from the same source', message)
        self.assertIn('rejected', message)
        self.assertEqual(record.id, same.record.id)
        changed = add_results_text((AddResult(
            same.record, False, 'source-changed', 'old', 'new'),))
        self.assertIn('changed content', changed)
        self.assertIn('not added', changed)

    def test_metadata_artwork_remove_and_launch_sensitivity(self):
        path, record = self.add_disk()
        self.client.edit_title('Renamed')
        self.client.set_favorite(True);self.client.set_notes('My notes')
        artwork = self.root / 'cover.png';artwork.write_bytes(b'png')
        self.client.set_artwork(artwork)
        updated = self.client.selected()
        self.assertEqual(('Renamed', True, 'My notes', str(artwork)),
                         (updated.title, updated.favorite, updated.notes,
                          updated.artwork.path))
        self.assertTrue(self.client.can_launch(True))
        self.library._edit(record.id, state='missing', state_message='missing')
        self.assertFalse(self.client.can_launch(True))
        self.library._edit(record.id, state='unavailable', state_message='offline')
        self.assertFalse(self.client.can_launch(True))
        self.client.remove()
        self.assertTrue(path.is_file())
        self.assertEqual((), self.library.list())

    def test_explicit_source_scopes_validate_and_relink_forwarding(self):
        library = Mock();launcher = Mock();client = GameLibraryClient(library, launcher)
        library.add.return_value = 'add-job'
        self.assertEqual('add-job', client.add_core_host('/tmp/game.d64'))
        source = library.add.call_args.args[0]
        self.assertEqual('core-host', source.scope)
        self.assertTrue(Path(source.path).is_absolute())
        self.assertEqual('add-job', client.add_c64u(
            'id:C64-A', '/USB2/Games/game.crt'))
        source = library.add.call_args.args[0]
        self.assertEqual(('c64u', 'id:C64-A', '/USB2'),
                         (source.scope, source.device_id, source.volume))

        client.selected_id = 'game-id'
        library.validate_source.return_value = 'validate-job'
        self.assertEqual('validate-job', client.validate())
        library.validate_source.assert_called_once_with('game-id')
        library.prepare_relink.return_value = 'review-job'
        self.assertEqual('review-job', client.prepare_relink_c64u(
            'id:C64-A', '/USB2/new.crt'))
        reviewed = library.prepare_relink.call_args.args[1]
        self.assertEqual('c64u', reviewed.scope)
        library.execute_relink.return_value = 'relink-job'
        self.assertEqual('relink-job', client.execute_relink('plan', True))
        library.execute_relink.assert_called_once_with(
            'plan', accept_changed=True)

    def test_launch_preview_forwarding_and_presentation_labels(self):
        library = Mock();launcher = Mock();client = GameLibraryClient(library, launcher)
        client.selected_id = 'game-id'
        launcher.prepare_launch.return_value = 'preview-job'
        launcher.execute_launch.return_value = 'launch-job'
        self.assertEqual('preview-job', client.prepare_launch())
        launcher.prepare_launch.assert_called_once_with('game-id')
        self.assertEqual('launch-job', client.execute_launch('plan-id'))
        launcher.execute_launch.assert_called_once_with('plan-id')
        self.assertIn('local cartridge', mechanism_text('rest-attached-crt'))
        self.assertIn('C64U storage', mechanism_text('rest-c64u-crt'))
        self.assertIn('disk image', mechanism_text('dma-run-img'))
        self.assertIn('This computer', source_text(GameSource.core_host('/tmp/a.crt')))
        self.assertIn('id:C64-A', source_text(
            GameSource.c64u('id:C64-A', '/USB2/a.crt')))

    def test_structured_result_error_wording_preserves_distinctions(self):
        unknown = client_error_text(JobError('launch-outcome-unknown', 'hidden'))
        self.assertIn('outcome unknown', unknown)
        self.assertIn('inspect', unknown.casefold())
        for code in ('malformed-image', 'missing-source', 'source-changed',
                     'device-changed', 'session-changed', 'storage-changed',
                     'firmware-rejection'):
            with self.subTest(code=code):
                text = client_error_text(JobError(code, 'sanitized fallback'))
                self.assertTrue(text);self.assertNotIn('success', text.casefold())
        self.assertEqual('safe message',
                         client_error_text(JobError('future-code', 'safe message')))

    def test_gtk_client_source_contains_no_direct_transport_or_runner_calls(self):
        source = (Path(__file__).resolve().parents[1] /
                  'c64u_browser' / 'game_library_tab.py').read_text()
        for forbidden in ('UltimateClient', 'run_crt(', 'run_crt_data(',
                          'run_image_bytes(', '.password', 'open_dma('):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':unittest.main()
