"""Synthetic media only: retained recording and asynchronous finalization."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import Gst, GstPbutils
from c64u_browser.recording import Recorder


class RecordingTests(unittest.TestCase):
    def record_clip(self, height, audio):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'recording.webm'
            recorder = Recorder(str(path), height, audio)
            self.addCleanup(lambda: recorder.pipeline.set_state(Gst.State.NULL))
            # Controlled timestamps; allow the encoder to consume bounded input.
            for index in range(30):
                with patch('c64u_browser.recording.time.monotonic',
                           return_value=recorder.started + (index + 1) / 30):
                    recorder.feed((height, bytes(384 * height * 3)),
                                  [bytes(768)] * 8 if audio else [])
                time.sleep(.005)
            recorder.stop()
            worker = recorder.thread
            recorder.stop()
            self.assertIs(recorder.thread, worker)
            worker.join(12)
            self.assertFalse(worker.is_alive())
            self.assertTrue(recorder.done)
            self.assertEqual(recorder.error, '')
            self.assertFalse(Path(recorder.temporary).exists())
            self.assertGreater(path.stat().st_size, 0)
            info = GstPbutils.Discoverer.new(5 * Gst.SECOND).discover_uri(path.as_uri())
            self.assertEqual(info.get_result(), GstPbutils.DiscovererResult.OK)
            self.assertGreater(info.get_duration(), 0)
            self.assertEqual(len(info.get_video_streams()), 1)
            self.assertEqual(info.get_video_streams()[0].get_height(), height)
            self.assertEqual(len(info.get_audio_streams()), int(audio))
            # EOS must produce a file a real decoder can consume.
            pipeline = Gst.parse_launch(
                'filesrc name=input ! matroskademux name=demux '
                'demux.video_0 ! queue ! vp8dec ! fakesink sync=false' +
                (' demux.audio_0 ! queue ! vorbisdec ! fakesink sync=false' if audio else ''))
            pipeline.get_by_name('input').set_property('location', str(path))
            try:
                pipeline.set_state(Gst.State.PLAYING)
                message = pipeline.get_bus().timed_pop_filtered(
                    5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
                self.assertIsNotNone(message)
                self.assertEqual(message.type, Gst.MessageType.EOS)
            finally:
                pipeline.set_state(Gst.State.NULL)

    def test_ntsc_recording_with_audio_finalizes_and_decodes(self):
        self.record_clip(240, True)

    def test_pal_video_only_recording_finalizes_and_decodes(self):
        self.record_clip(272, False)

    def test_initialization_failure_removes_only_owned_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'existing.webm'
            destination.write_bytes(b'original')
            with patch('c64u_browser.recording.Gst.parse_launch',
                       side_effect=RuntimeError('unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                    Recorder(str(destination), 240)
            self.assertEqual(list(Path(folder).iterdir()), [destination])
            self.assertEqual(destination.read_bytes(), b'original')

    def test_mode_change_is_reported_and_recording_still_finalizes(self):
        with tempfile.TemporaryDirectory() as folder:
            recorder = Recorder(str(Path(folder) / 'mode.webm'), 240, False)
            self.addCleanup(lambda: recorder.pipeline.set_state(Gst.State.NULL))
            recorder.feed((240, bytes(384 * 240 * 3)), [])
            with self.assertRaisesRegex(RuntimeError, 'Video mode changed'):
                recorder.feed((272, bytes(384 * 272 * 3)), [])
            recorder.stop('Video mode changed')
            recorder.thread.join(12)
            self.assertFalse(recorder.thread.is_alive())
            self.assertTrue(recorder.done)
            self.assertEqual(recorder.error, 'Video mode changed')
            self.assertTrue(Path(recorder.path).is_file())
