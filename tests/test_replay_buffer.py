import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from c64u_browser.replay_buffer import (
    ReplayBuffer, export_space_required, require_export_space)


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance_frame(self):
        self.value += 1 / 30


class ReplayBufferTests(unittest.TestCase):
    def test_export_space_check_is_deterministic(self):
        self.assertEqual(export_space_required(100), 4 * 1024 * 1024 + 100)
        usage = Mock(return_value=shutil._ntuple_diskusage(100, 99, 1))
        with self.assertRaisesRegex(OSError, 'Not enough free space'):
            require_export_space('/example', 100, usage)

    def test_bounded_encoded_history_exports_playable_webm_and_cleans_up(self):
        clock = Clock()
        frame = (240, bytes(384 * 240 * 3))
        with tempfile.TemporaryDirectory() as folder:
            replay = ReplayBuffer(
                240, audio=True, seconds=5, fragment_seconds=.5,
                clock=clock, workspace=folder)
            workspace = replay.root
            for _ in range(180):
                replay.feed(frame, [bytes(768)] * 8)
                clock.advance_frame()
                time.sleep(.002)
            destination = Path(folder) / 'recent.webm'
            result = []
            failure = []

            def save():
                try:
                    result.append(replay.export(destination))
                except Exception as exc:
                    failure.append(exc)

            thread = threading.Thread(target=save)
            thread.start()
            for _ in range(90):
                replay.feed(frame, [bytes(768)] * 8)
                clock.advance_frame()
                time.sleep(.003)
                if not thread.is_alive():
                    break
            thread.join(15)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failure, [])
            self.assertTrue(destination.is_file())
            self.assertGreater(destination.stat().st_size, 0)
            self.assertGreater(result[0]['seconds'], 0)
            self.assertLessEqual(result[0]['seconds'], 6.0)
            self.assertLessEqual(
                len(list(workspace.glob('fragment-*.webm'))), replay.max_files)
            replay.close()
            self.assertFalse(workspace.exists())

    def test_validation_rejects_unbounded_or_wrong_video_modes(self):
        with self.assertRaisesRegex(ValueError, '240- or 272-line'):
            ReplayBuffer(200)
        with self.assertRaisesRegex(ValueError, 'between 5 and 300'):
            ReplayBuffer(240, seconds=0)

    def test_failed_export_removes_its_immutable_snapshot(self):
        replay=ReplayBuffer.__new__(ReplayBuffer)
        snapshot=Path(tempfile.mkdtemp(prefix='argonaut-replay-failed-test-'))
        (snapshot/'fragment-00000.webm').write_bytes(b'encoded')
        with patch.object(replay,'_snapshot_fragments',return_value=(snapshot,7)), \
                patch.object(replay,'_remux',side_effect=OSError('full')):
            with self.assertRaisesRegex(OSError,'full'):
                replay.export('/unused/recent.webm')
        self.assertFalse(snapshot.exists())


if __name__ == '__main__':
    unittest.main()
