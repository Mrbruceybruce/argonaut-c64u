# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError, Entry
from c64u_browser.disk_image_edit import create_blank_d64_image
from c64u_browser.game_launch import GameLaunchService
from c64u_browser.game_library import (
    BULK_MAX_CANDIDATES, BULK_MAX_DECLARED_BYTES, BULK_MAX_DEPTH,
    BULK_MAX_DIRECTORIES, BULK_MAX_ENTRIES, BulkImportRequest,
    BulkImportSelection, GameLibraryError, GameLibraryService, GameSource,
)
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import DeviceSession, JobBinding


def crt_bytes(payload=b'x' * 8192, name='BULK CART'):
    header = bytearray(64)
    header[:16] = b'C64 CARTRIDGE   '
    header[0x10:0x14] = (64).to_bytes(4, 'big')
    header[0x14:0x16] = (0x0100).to_bytes(2, 'big')
    header[0x18:0x1a] = b'\x00\x01'
    encoded = name.encode('ascii')[:32]
    header[0x20:0x20 + len(encoded)] = encoded
    chip = (b'CHIP' + (16 + len(payload)).to_bytes(4, 'big')
            + b'\x00\x00\x00\x00\x80\x00' + len(payload).to_bytes(2, 'big')
            + payload)
    return bytes(header) + chip


D64 = create_blank_d64_image('BULK TEST', 'B1').source_bytes


class BulkImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.clock_value = 100.0
        self.ids = iter('plan-%d' % number for number in range(100))
        self.service = GameLibraryService(
            self.root / 'state' / 'game-library.json',
            clock=lambda:self.clock_value, id_factory=lambda:next(self.ids))
        self.addCleanup(self.service.close)
        self.service.load()

    def scan(self, request, service=None):
        service = service or self.service
        result = service.prepare_bulk_import(request).wait(10)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def execute(self, preview, candidate_ids=None, service=None):
        service = service or self.service
        selected = (preview.default_selected_candidate_ids
                    if candidate_ids is None else tuple(candidate_ids))
        selection = service.select_bulk_candidates(preview.plan_id, selected)
        result = service.execute_bulk_import(selection).wait(10)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def test_local_scan_is_deterministic_bounded_hidden_and_symlink_safe(self):
        folder = self.root / 'games'; (folder / 'B').mkdir(parents=True)
        (folder / 'a').mkdir()
        (folder / 'a' / 'two.crt').write_bytes(crt_bytes(b'2' * 32))
        (folder / 'B' / 'one.d64').write_bytes(D64)
        (folder / '.hidden.crt').write_bytes(crt_bytes())
        (folder / 'readme.txt').write_text('not a game')
        (folder / 'link.crt').symlink_to(folder / 'a' / 'two.crt')

        preview = self.scan(BulkImportRequest.core_host_folder(
            folder, recursive=True))
        self.assertEqual(
            ['a/two.crt', 'B/one.d64', 'link.crt', 'readme.txt'],
            [item.relative_path for item in preview.candidates])
        classes = {item.relative_path:item.classification
                   for item in preview.candidates}
        self.assertEqual('inaccessible-file', classes['link.crt'])
        self.assertEqual('unsupported-file', classes['readme.txt'])
        self.assertNotIn('.hidden.crt', classes)
        self.assertEqual(2, len(preview.eligible_candidate_ids))
        self.assertEqual(preview.eligible_candidate_ids,
                         preview.default_selected_candidate_ids)
        self.assertEqual((3, 7, 3), (preview.directories_scanned,
                                    preview.entries_seen,
                                    preview.supported_candidates))
        self.assertEqual(preview.as_dict(),
                         self.scan(BulkImportRequest.core_host_folder(
                             folder, recursive=True)).as_dict() |
                         {'plan_id':preview.plan_id,
                          'created_at':preview.created_at,
                          'expires_at':preview.expires_at})

    def test_hidden_entries_can_be_included(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / '.hidden.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(
            folder, include_hidden=True))
        self.assertEqual(('.hidden.crt',), tuple(
            item.relative_path for item in preview.candidates))

    def test_classifications_and_scanning_never_mutates_catalog(self):
        folder = self.root / 'games'; folder.mkdir()
        cataloged = folder / 'cataloged.crt'; cataloged.write_bytes(crt_bytes())
        added = self.service.add(GameSource.core_host(cataloged)).wait(5).result.record
        duplicate = folder / 'duplicate.crt'; duplicate.write_bytes(crt_bytes())
        changed = folder / 'changed.crt'; changed.write_bytes(crt_bytes(b'a' * 32))
        changed_record = self.service.add(GameSource.core_host(changed)).wait(5).result.record
        changed.write_bytes(crt_bytes(b'b' * 32))
        (folder / 'new.crt').write_bytes(crt_bytes(b'c' * 32))
        (folder / 'new-copy.crt').write_bytes(crt_bytes(b'c' * 32))
        (folder / 'broken.d64').write_bytes(b'broken')
        (folder / 'notes.prg').write_bytes(b'unsupported')
        before_records = self.service.list()
        before_file = self.service.path.read_bytes()

        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        classes = {item.relative_path:item.classification
                   for item in preview.candidates}
        self.assertEqual('already-cataloged-source', classes['cataloged.crt'])
        self.assertEqual('duplicate-catalog-content', classes['duplicate.crt'])
        self.assertEqual('changed-existing-source', classes['changed.crt'])
        self.assertEqual('invalid-image', classes['broken.d64'])
        self.assertEqual('unsupported-file', classes['notes.prg'])
        self.assertEqual({'new-valid', 'duplicate-scan-content'},
                         {classes['new.crt'], classes['new-copy.crt']})
        self.assertEqual(before_records, self.service.list())
        self.assertEqual(before_file, self.service.path.read_bytes())
        self.assertEqual('available', self.service.get(changed_record.id).state)
        duplicate_row = next(item for item in preview.candidates
                             if item.relative_path == 'duplicate.crt')
        self.assertEqual(added.id, duplicate_row.existing_record_id)

    def test_explicit_selection_is_ordered_and_rejects_ineligible_rows(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes(b'a' * 32))
        (folder / 'b.crt').write_bytes(crt_bytes(b'b' * 32))
        (folder / 'x.txt').write_text('x')
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        eligible = preview.eligible_candidate_ids
        selection = self.service.select_bulk_candidates(
            preview.plan_id, tuple(reversed(eligible)))
        self.assertEqual(eligible, selection.approved_candidate_ids)
        self.assertEqual({'plan_id':preview.plan_id,
                          'approved_candidate_ids':list(eligible)},
                         selection.as_dict())
        unsupported = next(item.id for item in preview.candidates
                           if not item.importable)
        with self.assertRaises(GameLibraryError) as caught:
            self.service.select_bulk_candidates(preview.plan_id, (unsupported,))
        self.assertEqual('selection', caught.exception.code)
        self.assertEqual((), self.service.select_bulk_candidates(
            preview.plan_id, ()).approved_candidate_ids)

    def test_plan_expiration_bounded_retention_and_serialization(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        service = GameLibraryService(
            self.root / 'plans.json', clock=lambda:self.clock_value,
            bulk_plan_ttl=30, bulk_plan_limit=2,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        first = self.scan(BulkImportRequest.core_host_folder(folder), service)
        self.clock_value += 1
        second = self.scan(BulkImportRequest.core_host_folder(folder), service)
        self.clock_value += 1
        third = self.scan(BulkImportRequest.core_host_folder(folder), service)
        with self.assertRaises(GameLibraryError):
            service.select_bulk_candidates(first.plan_id, ())
        json.dumps(third.as_dict())
        self.assertTrue(service.discard_bulk_plan(second.plan_id))
        self.assertFalse(service.discard_bulk_plan(second.plan_id))
        self.clock_value += 31
        with self.assertRaises(GameLibraryError):
            service.select_bulk_candidates(third.plan_id, ())

    def test_limits_abort_instead_of_truncating(self):
        scenarios = []
        folder = self.root / 'entries'; folder.mkdir()
        (folder / 'a.txt').write_text('a'); (folder / 'b.txt').write_text('b')
        scenarios.append(('bulk_max_entries', 1, folder, False))
        deep = self.root / 'deep'; (deep / 'child').mkdir(parents=True)
        scenarios.append(('bulk_max_depth', 0, deep, True))
        dirs = self.root / 'dirs'; (dirs / 'a').mkdir(parents=True)
        scenarios.append(('bulk_max_directories', 1, dirs, True))
        candidates = self.root / 'candidates'; candidates.mkdir()
        (candidates / 'a.crt').write_bytes(crt_bytes())
        (candidates / 'b.crt').write_bytes(crt_bytes(b'b' * 32))
        scenarios.append(('bulk_max_candidates', 1, candidates, False))
        sized = self.root / 'bytes'; sized.mkdir()
        (sized / 'a.crt').write_bytes(crt_bytes())
        scenarios.append(('bulk_max_declared_bytes', 1, sized, False))
        for option, value, root, recursive in scenarios:
            with self.subTest(option=option):
                service = GameLibraryService(
                    self.root / f'{option}.json', **{option:value}).load()
                self.addCleanup(service.close)
                job = service.prepare_bulk_import(
                    BulkImportRequest.core_host_folder(root, recursive=recursive))
                result = job.wait(5)
                self.assertEqual('failed', result.state)
                self.assertEqual('scan-limit', result.error.code)

    def test_default_bulk_limits_and_constructor_overrides(self):
        self.assertEqual(
            (10000, 100000, 50000, 32, 32 * 1024 * 1024 * 1024),
            (BULK_MAX_DIRECTORIES, BULK_MAX_ENTRIES, BULK_MAX_CANDIDATES,
             BULK_MAX_DEPTH, BULK_MAX_DECLARED_BYTES))
        service = GameLibraryService(
            self.root / 'custom-limits.json', bulk_max_directories=1,
            bulk_max_entries=2, bulk_max_candidates=3, bulk_max_depth=4,
            bulk_max_declared_bytes=5).load()
        self.addCleanup(service.close)
        self.assertEqual(
            (1, 2, 3, 4, 5),
            (service.bulk_max_directories, service.bulk_max_entries,
             service.bulk_max_candidates, service.bulk_max_depth,
             service.bulk_max_declared_bytes))

    def test_c64u_folder_discovery_is_single_reader_deterministic_and_partial(self):
        session = [DeviceSession('id:device', 'session-1')]
        listings = {
            '/USB2/Games': ('/USB2/Games', [
                Entry('z.crt', 'file', len(crt_bytes(b'z' * 32))),
                Entry('Bad', 'dir', None), Entry('A', 'dir', None),
                Entry('.hidden.d64', 'file', len(D64)),
            ]),
            '/USB2/Games/A': ('/USB2/Games/A', [
                Entry('disk.d64', 'file', len(D64)),
            ]),
        }
        calls = []
        def lister(path):
            calls.append(path)
            if path.endswith('/Bad'):
                raise BrowserError('unreadable branch')
            return listings[path]
        data = {'/USB2/Games/z.crt':crt_bytes(b'z' * 32),
                '/USB2/Games/A/disk.d64':D64}
        reads = []
        def reader(source, limit, progress, check):
            reads.append((source.path, limit)); check()
            value = data[source.path]; progress(len(value), len(value)); return value
        service = GameLibraryService(
            self.root / 'remote.json', remote_lister=lister,
            bulk_remote_reader=reader, session_provider=lambda:session[0],
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_folder(
            'id:device', '/USB2/Games', recursive=True), service)
        self.assertEqual(['/USB2/Games', '/USB2/Games/A', '/USB2/Games/Bad'], calls)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(['A/disk.d64', 'z.crt'],
                         [item.relative_path for item in preview.candidates])
        self.assertEqual(1, len(preview.issues))
        self.assertEqual('branch-unavailable', preview.issues[0].classification)
        self.assertEqual([206114, 64 * 1024 * 1024],
                         sorted(limit for _path, limit in reads))
        self.assertEqual('/USB2', preview.candidates[0].source.volume)

    def test_c64u_explicit_multiple_sources_and_duplicate_path(self):
        session = DeviceSession('id:device', 'session-1')
        paths = ['/USB1/z.crt', '/USB1/a.d64', '/USB1/z.crt']
        data = {'/USB1/z.crt':crt_bytes(), '/USB1/a.d64':D64}
        service = GameLibraryService(
            self.root / 'remote.json',
            bulk_remote_reader=lambda source, _limit, progress, check:(
                check(), progress(len(data[source.path]), len(data[source.path])),
                data[source.path])[-1],
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', paths), service)
        self.assertEqual(['a.d64', 'z.crt', 'z.crt'],
                         [item.relative_path for item in preview.candidates])
        self.assertEqual(1, sum(item.classification == 'duplicate-scan-path'
                                for item in preview.candidates))

    def test_c64u_path_safety_and_bad_candidate_do_not_abort_siblings(self):
        session = DeviceSession('id:device', 'session-1')
        def reader(source, _limit, progress, check):
            check()
            if source.path.endswith('bad.crt'):
                raise BrowserError('private transport detail')
            value = crt_bytes(); progress(len(value), len(value)); return value
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        for paths in (('/USB1/../bad.crt',),
                      ('/USB1/a.crt', '/USB2/b.crt')):
            with self.subTest(paths=paths), self.assertRaises(GameLibraryError):
                service.prepare_bulk_import(
                    BulkImportRequest.c64u_sources('id:device', paths))
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/bad.crt', '/USB1/good.crt')), service)
        classes = {item.relative_path:item.classification
                   for item in preview.candidates}
        self.assertEqual('inaccessible-file', classes['bad.crt'])
        self.assertEqual('new-valid', classes['good.crt'])
        bad = next(item for item in preview.candidates
                   if item.relative_path == 'bad.crt')
        self.assertNotIn('private transport detail', bad.message)

    def test_unreadable_c64u_root_aborts_scan(self):
        session = DeviceSession('id:device', 'session-1')
        service = GameLibraryService(
            self.root / 'remote.json',
            remote_lister=lambda _path:(_ for _ in ()).throw(
                BrowserError('private root detail')),
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        result = service.prepare_bulk_import(BulkImportRequest.c64u_folder(
            'id:device', '/USB1/Games')).wait(5)
        self.assertEqual('failed', result.state)
        self.assertEqual('scan-root', result.error.code)
        self.assertNotIn('private root detail', result.error.message)

    def test_c64u_session_change_aborts_and_no_plan_is_created(self):
        session = [DeviceSession('id:device', 'session-1')]
        def reader(source, limit, progress, check):
            session[0] = DeviceSession('id:device', 'session-2')
            return crt_bytes()
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session[0],
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        result = service.prepare_bulk_import(BulkImportRequest.c64u_sources(
            'id:device', ['/USB1/a.crt'])).wait(5)
        self.assertEqual('failed', result.state)
        self.assertEqual('session', result.error.code)
        self.assertEqual({}, service._bulk_plans)

    def test_cancellation_during_bounded_remote_read(self):
        session = DeviceSession('id:device', 'session-1')
        entered = Event(); release = Event()
        def reader(source, limit, progress, check):
            entered.set(); release.wait(5); check(); return crt_bytes()
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        job = service.prepare_bulk_import(BulkImportRequest.c64u_sources(
            'id:device', ['/USB1/a.crt']))
        self.assertTrue(entered.wait(5)); self.assertTrue(service.cancel(job.id))
        release.set(); result = job.wait(5)
        self.assertEqual('cancelled', result.state)
        self.assertEqual({}, service._bulk_plans)

    def test_stable_development_catalogs_and_plans_are_isolated(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        stable = GameLibraryService(self.root / 'stable' / 'game-library.json').load()
        development = GameLibraryService(self.root / 'development' / 'game-library.json').load()
        self.addCleanup(stable.close); self.addCleanup(development.close)
        preview = self.scan(BulkImportRequest.core_host_folder(folder), development)
        self.assertFalse(stable.path.exists())
        self.assertEqual((), stable.list())
        with self.assertRaises(GameLibraryError):
            stable.select_bulk_candidates(preview.plan_id,
                                          preview.eligible_candidate_ids)

    def test_contract_contains_hash_metadata_and_no_bytes_or_transport(self):
        folder = self.root / 'games'; folder.mkdir()
        data = crt_bytes(); (folder / 'a.crt').write_bytes(data)
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        row = preview.candidates[0]
        self.assertEqual(hashlib.sha256(data).hexdigest(), row.sha256)
        self.assertEqual('BULK CART', dict(row.metadata)['cartridge_name'])
        encoded = json.dumps(preview.as_dict())
        self.assertNotIn('UltimateClient', encoded)
        self.assertNotIn('password', encoded.casefold())
        self.assertFalse(any(isinstance(value, bytes)
                             for value in row.__dict__.values()))

    def test_execute_selected_subset_once_in_scan_order_and_publishes_once(self):
        folder = self.root / 'games'; folder.mkdir()
        for name, byte in (('c.crt', b'c'), ('a.crt', b'a'), ('b.crt', b'b')):
            (folder / name).write_bytes(crt_bytes(byte * 32))
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        rows = {item.relative_path:item for item in preview.candidates}
        selected = (rows['c.crt'].id, rows['a.crt'].id)
        saves = []
        original = self.service._save_locked
        def save():
            saves.append(True); return original()
        with patch.object(self.service, '_save_locked', side_effect=save):
            result = self.execute(preview, selected)
        self.assertEqual(['a.crt', 'c.crt'], [
            Path(item.source.path).name for item in result.records_created])
        self.assertEqual(2, result.created_count)
        self.assertEqual(1, len(saves))
        self.assertTrue(result.catalog_published)
        self.assertEqual('published', result.publication_status)
        self.assertNotIn('b.crt', [Path(item.source.path).name
                                  for item in self.service.list()])
        with self.assertRaises(GameLibraryError) as caught:
            self.service.execute_bulk_import(
                BulkImportSelection(preview.plan_id,
                                    preview.default_selected_candidate_ids))
        self.assertEqual('plan', caught.exception.code)
        json.dumps(result.as_dict())

    def test_execution_rereads_and_rejects_changed_removed_or_malformed_sources(self):
        folder = self.root / 'games'; folder.mkdir()
        changed = folder / 'changed.crt'; changed.write_bytes(crt_bytes(b'a' * 32))
        missing = folder / 'missing.crt'; missing.write_bytes(crt_bytes(b'b' * 32))
        malformed = folder / 'malformed.crt'; malformed.write_bytes(crt_bytes(b'c' * 32))
        good = folder / 'good.d64'; good.write_bytes(D64)
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        changed.write_bytes(crt_bytes(b'z' * 32))  # same total size, different bytes
        missing.unlink()
        malformed.write_bytes(b'broken')
        result = self.execute(preview)
        outcomes = {Path(item.source.path).name:item for item in result.outcomes}
        self.assertEqual('source-changed', outcomes['changed.crt'].classification)
        self.assertEqual('source-missing', outcomes['missing.crt'].classification)
        self.assertEqual('invalid-image', outcomes['malformed.crt'].classification)
        self.assertEqual('created', outcomes['good.d64'].classification)
        self.assertEqual((1, 0, 3), (result.created_count,
                                     result.skipped_count,
                                     result.failure_count))
        self.assertEqual(('good.d64',), tuple(
            Path(item.source.path).name for item in self.service.list()))

    def test_execution_reclassifies_catalog_races_without_duplicates(self):
        folder = self.root / 'games'; folder.mkdir()
        source_race = folder / 'source.crt'; source_race.write_bytes(crt_bytes(b's' * 32))
        content_race = folder / 'content.crt'; content_race.write_bytes(crt_bytes(b'd' * 32))
        unrelated = folder / 'unrelated.crt'; unrelated.write_bytes(crt_bytes(b'u' * 32))
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        self.assertEqual('succeeded', self.service.add(
            GameSource.core_host(source_race)).wait(5).state)
        other = self.root / 'other.crt'; other.write_bytes(content_race.read_bytes())
        self.assertEqual('succeeded', self.service.add(
            GameSource.core_host(other)).wait(5).state)
        result = self.execute(preview)
        outcomes = {Path(item.source.path).name:item for item in result.outcomes}
        self.assertEqual('already-cataloged-source',
                         outcomes['source.crt'].classification)
        self.assertEqual('duplicate-catalog-content',
                         outcomes['content.crt'].classification)
        self.assertEqual('created', outcomes['unrelated.crt'].classification)
        self.assertTrue(result.catalog_changed_since_review)
        hashes = [item.sha256 for item in self.service.list()]
        self.assertEqual(len(hashes), len(set(hashes)))

    def test_concurrent_different_content_at_same_source_is_skipped(self):
        folder = self.root / 'games'; folder.mkdir()
        candidate = folder / 'candidate.crt'; candidate.write_bytes(crt_bytes(b'a' * 32))
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        reviewed = candidate.read_bytes()
        candidate.write_bytes(crt_bytes(b'b' * 32))
        added = self.service.add(GameSource.core_host(candidate)).wait(5).result.record
        candidate.write_bytes(reviewed)
        result = self.execute(preview)
        self.assertEqual('changed-existing-source',
                         result.outcomes[0].classification)
        self.assertEqual('skipped', result.outcomes[0].status)
        self.assertEqual(added.id, result.outcomes[0].record_id)
        self.assertEqual(1, len(self.service.list()))

    def test_persistence_failure_rolls_back_memory_and_disk_and_consumes_plan(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        selection = self.service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        with patch.object(self.service, '_save_locked',
                          side_effect=OSError('disk full')):
            result = self.service.execute_bulk_import(selection).wait(5)
        self.assertEqual('failed', result.state)
        self.assertEqual((), self.service.list())
        self.assertFalse(self.service.path.exists())
        with self.assertRaises(GameLibraryError):
            self.service.execute_bulk_import(selection)

    def test_malformed_selection_does_not_consume_plan_but_valid_attempt_does(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        with self.assertRaises(GameLibraryError):
            self.service.execute_bulk_import(BulkImportSelection(
                preview.plan_id, ('not-eligible',)))
        result = self.execute(preview)
        self.assertEqual(1, result.created_count)
        with self.assertRaises(GameLibraryError):
            self.service.execute_bulk_import(BulkImportSelection(
                preview.plan_id, ()))

    def test_expired_plan_cannot_execute(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        selection = self.service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        self.clock_value += 1801
        with self.assertRaises(GameLibraryError) as caught:
            self.service.execute_bulk_import(selection)
        self.assertEqual('plan', caught.exception.code)

    def test_remote_execution_rereads_accepts_byte_identical_content_without_listing(self):
        session = [DeviceSession('id:device', 'session-1')]
        content = [crt_bytes()]; reads = []; listings = []
        def reader(source, limit, progress, check):
            reads.append(source.path); check(); value = bytes(content[0])
            progress(len(value), len(value)); return value
        service = GameLibraryService(
            self.root / 'remote.json',
            remote_lister=lambda path:listings.append(path),
            bulk_remote_reader=reader, session_provider=lambda:session[0],
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        content[0] = bytes(bytearray(content[0]))
        result = self.execute(preview, service=service)
        self.assertEqual(1, result.created_count)
        self.assertEqual(['/USB1/a.crt', '/USB1/a.crt'], reads)
        self.assertEqual([], listings)
        self.assertEqual('/USB1', result.records_created[0].source.volume)

    def test_remote_changed_content_and_session_change_are_safe(self):
        session = [DeviceSession('id:device', 'session-1')]
        content = [crt_bytes(b'a' * 32)]
        def reader(source, limit, progress, check):
            check(); value=content[0]; progress(len(value),len(value)); return value
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session[0],
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        content[0] = crt_bytes(b'b' * 32)
        result = self.execute(preview, service=service)
        self.assertEqual('source-changed', result.outcomes[0].classification)
        self.assertEqual((), service.list())

        content[0] = crt_bytes(b'c' * 32)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        selection = service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        session[0] = DeviceSession('id:device', 'session-2')
        with self.assertRaises(GameLibraryError) as caught:
            service.execute_bulk_import(selection)
        self.assertEqual('session', caught.exception.code)
        with self.assertRaises(GameLibraryError):
            service.execute_bulk_import(selection)

        session[0] = DeviceSession('id:device', 'session-3')
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        selection = service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        session[0] = DeviceSession('id:other', 'session-4')
        with self.assertRaises(GameLibraryError) as caught:
            service.execute_bulk_import(selection)
        self.assertEqual('device', caught.exception.code)

    def test_execution_progress_is_structured(self):
        session = DeviceSession('id:device', 'session-1')
        content = crt_bytes(); entered = Event(); release = Event(); reads = [0]
        def reader(source, limit, progress, check):
            reads[0] += 1
            if reads[0] == 2:
                entered.set(); release.wait(5)
            check(); progress(len(content), len(content)); return content
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        selection = service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        job = service.execute_bulk_import(selection)
        self.assertTrue(entered.wait(5)); phases = []
        job.add_listener(lambda event:phases.append(event.job.progress.phase)
                         if event.kind == 'progress' else None)
        release.set(); result = job.wait(5)
        self.assertEqual('succeeded', result.state)
        self.assertTrue({'bounded-reading', 'classifying', 'persisting',
                         'complete'}.issubset(set(phases)))

    def test_execution_cancel_during_remote_read_consumes_plan(self):
        session = DeviceSession('id:device', 'session-1')
        content = crt_bytes(); entered = Event(); release = Event(); reads = [0]
        def reader(source, limit, progress, check):
            reads[0] += 1
            if reads[0] == 2:
                entered.set(); release.wait(5)
            check(); progress(len(content), len(content)); return content
        service = GameLibraryService(
            self.root / 'remote.json', bulk_remote_reader=reader,
            session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(service.close)
        preview = self.scan(BulkImportRequest.c64u_sources(
            'id:device', ('/USB1/a.crt',)), service)
        selection = service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        job = service.execute_bulk_import(selection)
        self.assertTrue(entered.wait(5)); self.assertTrue(service.cancel(job.id))
        release.set(); result = job.wait(5)
        self.assertEqual('cancelled', result.state)
        self.assertEqual((), service.list())
        with self.assertRaises(GameLibraryError):
            service.execute_bulk_import(selection)

    def test_cancellation_before_publication_leaves_catalog_unchanged(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        selection = self.service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        job = self.service.execute_bulk_import(selection)
        def cancel_at_persist(event):
            if (event.kind == 'progress' and event.job.progress
                    and event.job.progress.phase == 'persisting'):
                self.service.cancel(job.id)
        job.add_listener(cancel_at_persist)
        result = job.wait(5)
        self.assertEqual('cancelled', result.state)
        self.assertEqual((), self.service.list())
        self.assertFalse(self.service.path.exists())

    def test_queued_execution_cancellation_consumes_plan_without_mutation(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        selection = self.service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        entered = Event(); release = Event()
        def block(_job):
            entered.set(); release.wait(5)
        blocker = self.service._scheduler.submit(
            CoreJob('test.block', block), JobBinding.core_host())
        self.assertTrue(entered.wait(5))
        job = self.service.execute_bulk_import(selection)
        self.assertEqual('queued', job.snapshot().state)
        self.assertTrue(self.service.cancel(job.id)); release.set()
        self.assertEqual('succeeded', blocker.wait(5).state)
        self.assertEqual('cancelled', job.wait(5).state)
        self.assertEqual((), self.service.list())
        with self.assertRaises(GameLibraryError):
            self.service.execute_bulk_import(selection)

    def test_late_cancellation_after_publication_does_not_relabel_result(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        preview = self.scan(BulkImportRequest.core_host_folder(folder))
        selection = self.service.select_bulk_candidates(
            preview.plan_id, preview.eligible_candidate_ids)
        job = self.service.execute_bulk_import(selection)
        def cancel_at_complete(event):
            if (event.kind == 'progress' and event.job.progress
                    and event.job.progress.phase == 'complete'):
                self.service.cancel(job.id)
        job.add_listener(cancel_at_complete)
        result = job.wait(5)
        self.assertEqual('succeeded', result.state)
        self.assertEqual(1, result.result.created_count)
        self.assertEqual(1, len(self.service.list()))

    def test_execution_result_has_no_bytes_credentials_or_transport(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        result = self.execute(self.scan(
            BulkImportRequest.core_host_folder(folder)))
        encoded = json.dumps(result.as_dict())
        self.assertNotIn('password', encoded.casefold())
        self.assertNotIn('UltimateClient', encoded)
        self.assertFalse(any(isinstance(value, bytes)
                             for value in result.__dict__.values()))

    def test_execution_preserves_stable_development_isolation(self):
        folder = self.root / 'games'; folder.mkdir()
        (folder / 'a.crt').write_bytes(crt_bytes())
        stable = GameLibraryService(self.root / 'stable' / 'game-library.json').load()
        development = GameLibraryService(
            self.root / 'development' / 'game-library.json').load()
        self.addCleanup(stable.close); self.addCleanup(development.close)
        preview = self.scan(BulkImportRequest.core_host_folder(folder),
                            development)
        self.execute(preview, service=development)
        self.assertEqual(1, len(development.list()))
        self.assertEqual((), stable.list())
        self.assertFalse(stable.path.exists())

    def test_bulk_and_individual_records_use_identical_launch_storage_verification(self):
        session=DeviceSession('id:device','session-1')
        content={
            '/USB1/manual.crt':crt_bytes(b'm' * 32),
            '/USB1/bulk.crt':crt_bytes(b'b' * 32),
        }
        def bulk_reader(source,limit,progress,check):
            check();data=content[source.path];progress(len(data),len(data));return data
        catalog=GameLibraryService(
            self.root/'launch.json',remote_reader=lambda source:content[source.path],
            bulk_remote_reader=bulk_reader,session_provider=lambda:session,
            id_factory=lambda:next(self.ids)).load()
        self.addCleanup(catalog.close)
        manual=catalog.add(GameSource.c64u(
            session.device_id,'/USB1/manual.crt')).wait(5).result.record
        preview=self.scan(BulkImportRequest.c64u_sources(
            session.device_id,('/USB1/bulk.crt',)),catalog)
        bulk=self.execute(preview,service=catalog).records_created[0]
        stages=[];commands=[]
        launch=GameLaunchService(
            catalog,lambda:object(),lambda:session,catalog._scheduler,
            volume_identity=lambda _source,job,stage:
            (job.check_cancel(),stages.append(stage),'same-volume')[-1],
            resident_crt_runner=lambda *_:commands.append(1),
            id_factory=lambda:next(self.ids))
        for record in (manual,bulk):
            reviewed=launch.prepare_launch(record.id).wait(5)
            self.assertEqual('succeeded',reviewed.state,reviewed.error)
            result=launch.execute_launch(reviewed.result.plan_id).wait(5)
            self.assertEqual('succeeded',result.state,result.error)
        expected=('game-launch-preparation-before',
                  'game-launch-preparation-after',
                  'game-launch-execution-before',
                  'game-launch-execution-after')
        self.assertEqual(expected,tuple(stages[:4]))
        self.assertEqual(expected,tuple(stages[4:]))
        self.assertEqual(2,len(commands))


if __name__ == '__main__':
    unittest.main()
