# SPDX-License-Identifier: GPL-3.0-or-later
import itertools
import os
from pathlib import Path
from threading import Event
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.jobs import CoreJob
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding
from c64u_browser.sid_jukebox import SidCatalogService, SidSource
from c64u_browser.sid_playback import (
    PlaylistContext, SidJukeboxError, SidJukeboxService,
)
from tests.test_sid_format import sid_bytes


class ReverseRandom:
    def shuffle(self, values):values.reverse()


class SidPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = [100.0]
        self.session = [DeviceSession('id:C64-A', 'session-1')]
        self.remote = {}
        self.media = ['media-1']
        self.scheduler = CoreScheduler(lambda:self.session[0], clock=lambda:self.now[0])
        self.addCleanup(self.scheduler.close)
        ids = itertools.count(1)
        self.catalog = SidCatalogService(
            self.root / 'sid-jukebox.json',
            remote_reader=lambda source:self.remote[source.path],
            session_provider=lambda:self.session[0], scheduler=self.scheduler,
            clock=lambda:self.now[0], id_factory=lambda:f'catalog-{next(ids)}')
        self.catalog.load()
        self.client = Mock(name='private-client')
        self.calls = []
        self.service = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0],
            self.scheduler,
            volume_identity=lambda source, check:(check(), self.media[0])[1],
            attached_runner=lambda client, data, song, source:
                self.calls.append(('attached', source.path, song, len(data))),
            resident_runner=lambda client, data, song, source:
                self.calls.append(('resident', source.path, song, len(data))),
            clock=lambda:self.now[0], id_factory=lambda:f'play-{next(ids)}',
            random_source=ReverseRandom())

    def local_tune(self, name='tune.sid', **kwargs):
        path = self.root / name; path.write_bytes(sid_bytes(**kwargs))
        result = self.catalog.add(SidSource.core_host(path)).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result.tune, path

    def remote_tune(self, path='/USB2/Music/tune.sid', **kwargs):
        self.remote[path] = sid_bytes(**kwargs)
        source = SidSource.c64u('id:C64-A', path)
        result = self.catalog.add(source).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result.tune

    def preview(self, tune, subtune=None, context=None):
        job = self.service.prepare_play(tune.id, subtune, context)
        result = job.wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def execute(self, preview):
        result = self.service.execute_play(preview.plan_id).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        return result.result

    def playlist(self, tunes):
        playlist = self.catalog.create_playlist('Test List')
        items = [self.catalog.add_playlist_item(
            playlist.id, tune.id, subtune) for tune, subtune in tunes]
        return self.catalog.get_playlist(playlist.id), items

    def authorize(self, playlist, item, tune):
        preview = self.preview(
            tune, item.subtune, PlaylistContext(playlist.id, item.id))
        self.execute(preview)
        return self.service.current_playback()

    def test_preview_default_explicit_and_serializable_schema(self):
        tune, _path = self.local_tune(
            songs=3, start=2, version=4, second=0x42, third=0xe0,
            flags=(1 << 2) | (1 << 4) | (2 << 6) | (3 << 8))
        default = self.preview(tune)
        self.assertEqual((2, 2, True, 'rest-attached-sid', 'unknown', None),
                         (default.selected_subtune, default.default_subtune,
                          default.used_file_default, default.mechanism,
                          default.duration_source, default.duration_ms))
        self.assertEqual((3, (0xd400, 0xd420, 0xde00)),
                         (default.sid_count, default.sid_addresses))
        self.assertIsInstance(default.as_dict(), dict)
        self.assertNotIn('data', default.as_dict())
        result = self.execute(default)
        self.assertEqual((3, default.sid_addresses, default.sid_models),
                         (result.sid_count, result.sid_addresses,
                          result.sid_models))
        explicit = self.preview(tune, 3)
        self.assertEqual((3, False),
                         (explicit.selected_subtune, explicit.used_file_default))

    def test_core_host_and_resident_routes_and_results(self):
        local, _path = self.local_tune()
        remote = self.remote_tune('/USB2/Music/remote.sid', title='Remote')
        local_result = self.execute(self.preview(local))
        remote_result = self.execute(self.preview(remote, 1))
        self.assertEqual(('attached', str(self.root / 'tune.sid'), None),
                         self.calls[0][:3])
        self.assertEqual(('resident', '/USB2/Music/remote.sid', 1),
                         self.calls[1][:3])
        for result in (local_result, remote_result):
            self.assertEqual('command-accepted', result.status)
            self.assertTrue(result.command_accepted)
            self.assertFalse(result.audible_playback_verified)

    def test_one_two_and_three_sid_requirements_propagate(self):
        cases = (
            ('one.sid', {}, (0xd400,)),
            ('two.sid', {'version':3, 'second':0x42, 'title':'Two SID'},
             (0xd400, 0xd420)),
            ('three.sid', {'version':4, 'second':0x42, 'third':0xe0,
                           'title':'Three SID'},
             (0xd400, 0xd420, 0xde00)),
        )
        for name, arguments, addresses in cases:
            with self.subTest(name=name):
                tune, _ = self.local_tune(name, **arguments)
                preview = self.preview(tune)
                result = self.execute(preview)
                self.assertEqual((len(addresses), addresses),
                                 (preview.sid_count, preview.sid_addresses))
                self.assertEqual((len(addresses), addresses),
                                 (result.sid_count, result.sid_addresses))

    def test_playback_blocked_tunes_never_create_plan(self):
        mus, _ = self.local_tune('mus.sid', flags=1)
        playsid, _ = self.local_tune('playsid.sid', flags=2, title='PlaySID')
        for tune in (mus, playsid):
            with self.subTest(tune=tune.title), self.assertRaisesRegex(
                    SidJukeboxError, 'external player|not compatible'):
                self.service.prepare_play(tune.id)
        self.assertEqual([], self.calls)

    def test_plan_expiration_consumption_and_subtune_bounds(self):
        tune, _ = self.local_tune(songs=2)
        expiring = self.preview(tune)
        self.now[0] += 301
        with self.assertRaisesRegex(SidJukeboxError, 'expired'):
            self.service.execute_play(expiring.plan_id)
        accepted = self.preview(tune, 2)
        self.execute(accepted)
        with self.assertRaisesRegex(SidJukeboxError, 'already used'):
            self.service.execute_play(accepted.plan_id)
        for invalid in (0, 3, True, '1'):
            with self.assertRaises(SidJukeboxError):
                self.service.prepare_play(tune.id, invalid)

    def test_source_and_record_change_after_preview(self):
        tune, path = self.local_tune()
        preview = self.preview(tune)
        path.write_bytes(sid_bytes(title='Changed'))
        result = self.service.execute_play(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'source-changed'),
                         (result.state, result.error.code))
        path.write_bytes(sid_bytes())
        self.catalog.validate_source(tune.id).wait(5)
        tune = self.catalog.get(tune.id)
        preview = self.preview(tune)
        self.catalog.set_notes(tune.id, 'Changed after review')
        result = self.service.execute_play(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'record-changed'),
                         (result.state, result.error.code))
        self.assertEqual([], self.calls)

    def test_device_session_and_media_change_reject_stale_plan(self):
        tune = self.remote_tune()
        preview = self.preview(tune)
        self.media[0] = 'media-2'
        result = self.service.execute_play(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'storage-changed'),
                         (result.state, result.error.code))
        self.media[0] = 'media-1'
        preview = self.preview(tune)
        self.session[0] = DeviceSession('id:C64-A', 'session-2')
        with self.assertRaisesRegex(SidJukeboxError, 'connection changed'):
            self.service.execute_play(preview.plan_id)
        self.session[0] = DeviceSession('id:C64-A', 'session-1')
        preview = self.preview(tune)
        self.session[0] = DeviceSession('id:C64-B', 'session-3')
        with self.assertRaisesRegex(SidJukeboxError, 'active C64U changed'):
            self.service.execute_play(preview.plan_id)
        self.assertEqual([], self.calls)

    def test_scheduler_order_and_queued_cancellation(self):
        tune, _ = self.local_tune()
        preview = self.preview(tune)
        entered = Event(); release = Event()
        blocker = self.scheduler.submit(
            CoreJob('blocker', lambda job:(entered.set(), release.wait(5))),
            JobBinding.device(self.session[0]))
        self.assertTrue(entered.wait(2))
        queued = self.service.execute_play(preview.plan_id)
        self.assertEqual('queued', queued.snapshot().state)
        self.assertTrue(queued.request_cancel())
        self.assertEqual([], self.calls)
        release.set(); blocker.wait(5)
        result = queued.wait(5)
        self.assertEqual('cancelled', result.state)
        self.assertEqual([], self.calls)

    def test_scheduler_runs_playback_after_prior_device_work(self):
        tune, _ = self.local_tune()
        preview = self.preview(tune)
        entered = Event(); release = Event(); order = []
        def block(_job):
            order.append('block-start'); entered.set(); release.wait(5)
            order.append('block-end')
        blocker = self.scheduler.submit(
            CoreJob('blocker', block), JobBinding.device(self.session[0]))
        self.assertTrue(entered.wait(2))
        queued = self.service.execute_play(preview.plan_id)
        self.assertEqual('queued', queued.snapshot().state)
        self.assertEqual([], self.calls)
        release.set(); blocker.wait(5)
        self.assertEqual('succeeded', queued.wait(5).state)
        self.assertEqual(['block-start', 'block-end'], order)
        self.assertEqual('attached', self.calls[0][0])

    def test_running_cancellation_before_command(self):
        tune = self.remote_tune()
        entered = Event(); release = Event()
        def identity(_source, check):
            entered.set(); release.wait(5); check(); return self.media[0]
        service = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0],
            self.scheduler,
            volume_identity=lambda _source, check:(check(), self.media[0])[1],
            resident_runner=lambda *args:self.calls.append(('unexpected',)))
        preview = service.prepare_play(tune.id).wait(5).result
        service._volume_identity = identity
        playback_job = service.execute_play(preview.plan_id)
        self.assertTrue(entered.wait(2))
        playback_job.request_cancel(); release.set()
        self.assertEqual('cancelled', playback_job.wait(5).state)
        self.assertEqual([], self.calls)

    def test_late_cancellation_does_not_relabel_completed_command(self):
        tune, _ = self.local_tune()
        preview = self.preview(tune)
        entered = Event(); release = Event()
        def runner(*_args):entered.set(); release.wait(5); self.calls.append(('ran',))
        service = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0],
            self.scheduler, attached_runner=runner)
        # Recreate the reviewed plan in the service that owns it.
        preview = service.prepare_play(tune.id).wait(5).result
        job = service.execute_play(preview.plan_id)
        self.assertTrue(entered.wait(2)); job.request_cancel(); release.set()
        result = job.wait(5)
        self.assertEqual('succeeded', result.state)
        self.assertTrue(result.result.command_accepted)

    def test_api_rejection_and_uncertain_outcome_are_structured_and_not_retried(self):
        tune, _ = self.local_tune()
        attempts = []
        def rejected(*_args):
            attempts.append('reject'); raise ConnectionFailure('api', 'private')
        service = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0],
            self.scheduler, attached_runner=rejected)
        preview = service.prepare_play(tune.id).wait(5).result
        result = service.execute_play(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'firmware-rejection', ['reject']),
                         (result.state, result.error.code, attempts))

        attempts.clear()
        def uncertain(*_args):
            attempts.append('network'); raise ConnectionFailure('network', 'private')
        service = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0],
            self.scheduler, attached_runner=uncertain)
        preview = service.prepare_play(tune.id).wait(5).result
        result = service.execute_play(preview.plan_id).wait(5)
        self.assertEqual(('failed', 'playback-outcome-unknown', ['network']),
                         (result.state, result.error.code, attempts))
        self.assertEqual('playback-outcome-unknown',
                         service.current_playback().status)

    def test_playlist_authorization_creation_session_and_playlist_invalidation(self):
        first, _ = self.local_tune('one.sid', title='One')
        second, _ = self.local_tune('two.sid', title='Two')
        playlist, items = self.playlist(((first, 1), (second, 1)))
        snapshot = self.authorize(playlist, items[0], first)
        self.assertTrue(snapshot.playlist_authorized)
        self.assertEqual(playlist.id, snapshot.playlist_id)
        self.session[0] = DeviceSession('id:C64-A', 'session-2')
        self.assertFalse(self.service.current_playback().playlist_authorized)

        self.session[0] = DeviceSession('id:C64-A', 'session-1')
        self.authorize(playlist, items[0], first)
        self.catalog.add_playlist_item(playlist.id, first.id, 1)
        with self.assertRaisesRegex(SidJukeboxError, 'playlist changed'):
            self.service.next()
        self.assertFalse(self.service.current_playback().playlist_authorized)

    def test_next_previous_boundaries_and_unavailable_target(self):
        first, _ = self.local_tune('one.sid', title='One')
        second, second_path = self.local_tune('two.sid', title='Two')
        playlist, items = self.playlist(((first, 1), (second, 1)))
        self.authorize(playlist, items[0], first)
        beginning = self.service.previous().wait(5).result
        self.assertEqual('boundary', beginning.status)
        next_result = self.service.next().wait(5).result
        self.assertEqual(('command-accepted', second.id),
                         (next_result.status, next_result.playback.tune_id))
        end = self.service.next().wait(5).result
        self.assertEqual('boundary', end.status)
        previous = self.service.previous().wait(5).result
        self.assertEqual(first.id, previous.playback.tune_id)

        # Start again, then make the next source unavailable.
        self.authorize(playlist, items[0], first)
        second_path.unlink()
        self.catalog.validate_source(second.id).wait(5)
        result = self.service.next().wait(5)
        self.assertEqual(('failed', 'target-unavailable'),
                         (result.state, result.error.code))

    def test_deterministic_shuffle_bag_previous_and_forward_history(self):
        one, _ = self.local_tune('one.sid', title='One')
        two, _ = self.local_tune('two.sid', title='Two')
        three, _ = self.local_tune('three.sid', title='Three')
        playlist, items = self.playlist(((one, 1), (two, 1), (three, 1)))
        self.authorize(playlist, items[0], one)
        self.service.set_shuffle(True)
        first = self.service.next().wait(5).result.playback.tune_id
        second = self.service.next().wait(5).result.playback.tune_id
        self.assertEqual((three.id, two.id), (first, second))
        back = self.service.previous().wait(5).result.playback.tune_id
        forward = self.service.next().wait(5).result.playback.tune_id
        self.assertEqual((three.id, two.id), (back, forward))
        new_cycle = self.service.next().wait(5).result.playback.tune_id
        self.assertNotEqual(two.id, new_cycle)

    def test_authorization_is_bounded_and_not_persisted_across_service_restart(self):
        tune, _ = self.local_tune()
        playlist, items = self.playlist(((tune, 1),))
        self.authorize(playlist, items[0], tune)
        self.now[0] += 1801
        self.assertFalse(self.service.current_playback().playlist_authorized)
        fresh = SidJukeboxService(
            self.catalog, lambda:self.client, lambda:self.session[0], self.scheduler)
        self.assertEqual('idle', fresh.current_playback().status)
        self.assertFalse(fresh.current_playback().playlist_authorized)

    def test_public_contract_is_headless_and_contains_no_sid_bytes_or_client(self):
        tune, _ = self.local_tune()
        preview = self.preview(tune)
        public = preview.as_dict()
        self.assertFalse(any(isinstance(value, bytes) for value in public.values()))
        self.assertNotIn(self.client, public.values())
        root = str(Path(__file__).resolve().parents[1]); env = dict(os.environ)
        env.pop('DISPLAY', None); env.pop('WAYLAND_DISPLAY', None)
        code = ("import sys; import c64u_browser.sid_playback as s; "
                "assert 'gi.repository.Gtk' not in sys.modules; "
                "assert 'UltimateClient' not in vars(s); "
                "assert 'Credentials' not in vars(s)")
        result = subprocess.run([sys.executable, '-c', code], cwd=root, env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':unittest.main()
