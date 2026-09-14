import threading,unittest
from collections import deque
from c64u_browser.streaming import Receiver,rgb_frame,PIXELS

class StreamTiming(unittest.TestCase):
    def test_optimized_conversion_preserves_every_packed_pixel(self):
        for packed in (b'',bytes(range(256)),bytes(range(256))*204):
            self.assertEqual(rgb_frame(packed),b''.join(PIXELS[n] for n in packed))

    def test_audio_only_take_retains_latest_video(self):
        receiver=Receiver.__new__(Receiver)
        receiver.lock=threading.Lock();receiver.latest=(240,b'frame')
        receiver.samples=deque([b'audio'],maxlen=24)
        self.assertEqual(receiver.take(video=False),(None,[b'audio']))
        self.assertEqual(receiver.take(),((240,b'frame'),[]))
        self.assertEqual(receiver.take(),(None,[]))
