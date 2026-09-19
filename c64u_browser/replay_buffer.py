# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Bounded encoded instant-replay history for the live C64U preview."""
from collections import deque
import math
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst


MIN_EXPORT_HEADROOM = 4 * 1024 * 1024


def export_space_required(encoded_bytes):
    """Allow for the remuxed output plus a small filesystem safety margin."""
    return max(MIN_EXPORT_HEADROOM, int(encoded_bytes) + MIN_EXPORT_HEADROOM)


def require_export_space(folder, encoded_bytes, disk_usage=shutil.disk_usage):
    required = export_space_required(encoded_bytes)
    available = disk_usage(folder).free
    if available < required:
        raise OSError(
            f'Not enough free space to save replay: {required} bytes required; '
            f'{available} bytes available.')


class ReplayBuffer:
    """Continuously encode a bounded ring of WebM fragments.

    Only encoded VP8/Vorbis fragments persist between calls. Raw RGB and PCM
    buffers remain bounded inside the same GStreamer queues used for recording.
    """

    def __init__(self, height, audio=True, seconds=30, fragment_seconds=2,
                 clock=time.monotonic, workspace=None):
        if height not in (240, 272):
            raise ValueError('Replay requires a 240- or 272-line C64 frame.')
        if not 5 <= seconds <= 300:
            raise ValueError('Replay duration must be between 5 and 300 seconds.')
        if not .25 <= fragment_seconds <= 5:
            raise ValueError('Replay fragment duration must be between 0.25 and 5 seconds.')
        Gst.init(None)
        self.height = height
        self.audio = bool(audio)
        self.seconds = int(seconds)
        self.fragment_seconds = float(fragment_seconds)
        self.clock = clock
        self.started = clock()
        self.last_video = -1
        self.audio_pts = None
        self.latest_pts = 0
        self.error = ''
        self.closed = False
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.closed_fragments = deque(maxlen=512)
        self.closed_generation = 0
        self.root = Path(tempfile.mkdtemp(
            prefix='.argonaut-replay-', dir=workspace))
        self.pattern = str(self.root / 'fragment-%05d.webm')
        # Keep one current fragment in addition to the requested closed history.
        self.max_files = math.ceil(seconds / fragment_seconds) + 1
        self.pipeline = None
        try:
            frame_count = max(1, round(fragment_seconds * 30))
            description = (
                'splitmuxsink name=sink muxer-factory=webmmux '
                'async-finalize=true send-keyframe-requests=true '
                f'location="{self.pattern}" '
                f'max-size-time={round(fragment_seconds * Gst.SECOND)} '
                f'max-files={self.max_files} '
                'appsrc name=video is-live=true format=time block=false '
                'max-bytes=4194304 '
                f'caps="video/x-raw,format=RGB,width=384,height={height},framerate=30/1" '
                '! queue max-size-buffers=8 max-size-bytes=0 max-size-time=0 '
                '! videoconvert '
                f'! vp8enc deadline=1 cpu-used=8 keyframe-max-dist={frame_count} '
                '! queue ! sink.video ')
            if audio:
                description += (
                    'appsrc name=audio is-live=true format=time block=false '
                    'max-bytes=262144 '
                    'caps="audio/x-raw,format=S16LE,rate=48000,channels=2,layout=interleaved" '
                    '! queue max-size-buffers=64 max-size-bytes=0 max-size-time=0 '
                    '! audioconvert ! audioresample ! vorbisenc ! queue ! sink.audio_0')
            self.pipeline = Gst.parse_launch(description)
            self.sink = self.pipeline.get_by_name('sink')
            self.video = self.pipeline.get_by_name('video')
            self.sound = self.pipeline.get_by_name('audio') if audio else None
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Replay encoding pipeline could not start.')
        except Exception:
            self.close()
            raise

    @property
    def retained_seconds(self):
        return min(float(self.seconds), self.latest_pts / Gst.SECOND)

    def _drain_bus(self):
        if not self.pipeline:
            return
        bus = self.pipeline.get_bus()
        while True:
            message = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.ELEMENT)
            if not message:
                break
            if message.type == Gst.MessageType.ERROR:
                self.error = message.parse_error()[0].message
                raise RuntimeError(self.error)
            structure = message.get_structure()
            if not structure or structure.get_name() != 'splitmuxsink-fragment-closed':
                continue
            location = structure.get_string('location')
            running_time = structure.get_value('running-time')
            if location:
                self.closed_fragments.append((int(running_time or 0), Path(location)))
                self.closed_generation += 1
                self.condition.notify_all()

    def _push(self, source, data, pts, duration):
        if source.get_property('current-level-bytes') > source.get_property('max-bytes'):
            raise RuntimeError('Replay encoding could not keep up with incoming data.')
        buffer = Gst.Buffer.new_allocate(None, len(data), None)
        buffer.fill(0, data)
        buffer.pts = pts
        buffer.duration = duration
        if source.emit('push-buffer', buffer) != Gst.FlowReturn.OK:
            raise RuntimeError('Replay encoding input failed.')

    def feed(self, frame, samples):
        with self.lock:
            if self.closed:
                return
            self._drain_bus()
            now = int((self.clock() - self.started) * Gst.SECOND)
            if frame:
                height, rgb = frame
                if height != self.height:
                    raise RuntimeError('Video mode changed; replay history was restarted.')
                pts = max(now, self.last_video + 1)
                self.last_video = pts
                self.latest_pts = max(self.latest_pts, pts)
                self._push(self.video, rgb, pts, Gst.SECOND // 30)
            if self.sound and samples:
                duration = len(samples) * 192 * Gst.SECOND // 48000
                if self.audio_pts is None:
                    self.audio_pts = max(0, now - duration)
                if now - self.audio_pts > 250000000:
                    self.audio_pts = max(0, now - duration)
                for sample in samples:
                    length = 192 * Gst.SECOND // 48000
                    self._push(self.sound, sample, self.audio_pts, length)
                    self.audio_pts += length
                    self.latest_pts = max(self.latest_pts, self.audio_pts)

    def _wait_for_split(self, generation, timeout=8):
        deadline = time.monotonic() + timeout
        while self.closed_generation <= generation:
            self._drain_bus()
            if self.closed_generation > generation:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('Timed out finalizing replay history.')
            self.condition.wait(min(.05, remaining))

    def _snapshot_fragments(self):
        with self.condition:
            if self.closed or not self.pipeline:
                raise RuntimeError('Replay history is not running.')
            generation = self.closed_generation
            self.sink.emit('split-now')
            self._wait_for_split(generation)
            # Locations are cyclically reused. Retain only the newest closure for
            # each surviving path and order those closures by running time.
            latest = {}
            for running_time, path in self.closed_fragments:
                if path.is_file() and path.stat().st_size:
                    latest[path] = (running_time, path)
            ordered = [entry[1] for entry in sorted(latest.values())]
            if not ordered:
                raise RuntimeError('Replay history is not ready yet.')
            # Keep the immutable export snapshot outside the live ring so a
            # preview stop or video-mode restart can clean the ring immediately
            # without disrupting an export already in progress.
            snapshot = Path(tempfile.mkdtemp(prefix='.argonaut-replay-export-'))
            total = sum(path.stat().st_size for path in ordered)
            require_export_space(self.root, total)
            for index, source in enumerate(ordered):
                shutil.copyfile(source, snapshot / f'fragment-{index:05d}.webm')
            return snapshot, total

    @staticmethod
    def _remux(snapshot, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fragments = list(snapshot.glob('fragment-*.webm'))
        encoded_bytes = sum(path.stat().st_size for path in fragments)
        require_export_space(destination.parent, encoded_bytes)
        fd, temporary = tempfile.mkstemp(
            prefix='.argonaut-replay-', suffix='.webm', dir=destination.parent)
        os.close(fd)
        pipeline = Gst.Pipeline.new('argonaut-replay-export')
        reader = Gst.ElementFactory.make('splitmuxsrc', 'reader')
        mux = Gst.ElementFactory.make('webmmux', 'mux')
        output = Gst.ElementFactory.make('filesink', 'output')
        if not all((pipeline, reader, mux, output)):
            os.unlink(temporary)
            raise RuntimeError('Required GStreamer replay elements are unavailable.')
        reader.set_property('location', str(snapshot / 'fragment-*.webm'))
        output.set_property('location', temporary)
        pipeline.add(reader); pipeline.add(mux); pipeline.add(output)
        if not mux.link(output):
            os.unlink(temporary)
            raise RuntimeError('Could not connect the replay output pipeline.')
        link_errors = []

        def pad_added(_reader, pad):
            template = ('video_%u' if pad.get_name().startswith('video') else
                        'audio_%u' if pad.get_name().startswith('audio') else '')
            target = mux.request_pad_simple(template) if template else None
            if target is None or pad.link(target) != Gst.PadLinkReturn.OK:
                link_errors.append('Could not connect a replay media stream.')

        reader.connect('pad-added', pad_added)
        try:
            if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Could not start replay export.')
            message = pipeline.get_bus().timed_pop_filtered(
                20 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if not message:
                raise RuntimeError('Timed out saving replay.')
            if message.type == Gst.MessageType.ERROR:
                raise RuntimeError(message.parse_error()[0].message)
            if link_errors:
                raise RuntimeError(link_errors[0])
            pipeline.set_state(Gst.State.NULL)
            os.replace(temporary, destination)
            return {'path': str(destination), 'bytes': destination.stat().st_size,
                    'fragments': len(fragments)}
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise
        finally:
            pipeline.set_state(Gst.State.NULL)

    def export(self, destination):
        snapshot = None
        try:
            snapshot, _ = self._snapshot_fragments()
            result = self._remux(snapshot, destination)
            try:
                gi.require_version('GstPbutils', '1.0')
                from gi.repository import GstPbutils
                info = GstPbutils.Discoverer.new(5 * Gst.SECOND).discover_uri(
                    Path(result['path']).absolute().as_uri())
                result['seconds'] = info.get_duration() / Gst.SECOND
            except Exception:
                result['seconds'] = self.retained_seconds
            return result
        finally:
            if snapshot:
                shutil.rmtree(snapshot, ignore_errors=True)

    def close(self):
        with getattr(self, 'lock', threading.RLock()):
            if getattr(self, 'closed', False):
                return
            self.closed = True
            pipeline = getattr(self, 'pipeline', None)
            if pipeline:
                pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
        root = getattr(self, 'root', None)
        if root:
            shutil.rmtree(root, ignore_errors=True)
