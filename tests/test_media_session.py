import threading,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from c64u_browser.media_session import MediaDelivery

class Media(unittest.TestCase):
    def wait(self,predicate):
        until=time.monotonic()+3
        while not predicate() and time.monotonic()<until:time.sleep(.01)
        self.assertTrue(predicate())
    def test_recording_continues_without_ui_draining_frames(self):
        receiver=Mock();receiver.take.side_effect=lambda video=True: (((240,bytes(384*240//2)) if video else None),[bytes(768)])
        session=SimpleNamespace(with_audio=True,receiver=receiver,stopping=threading.Event(),thread=Mock())
        session.thread.is_alive.return_value=True
        output=Mock(dropped=0)
        class Writer:
            def __init__(self,*args,**kwargs):
                self.frames=0;self.started=time.monotonic();self.finishing=False;self.done=False;self.error='';self.path='test'
            def feed(self,frame,samples):
                if frame:self.frames+=1
            def stop(self,*args):
                if self.finishing:return
                self.finishing=True
                self.thread=threading.Thread(target=lambda:setattr(self,'done',True));self.thread.start()
        delivery=MediaDelivery(session,lambda:output,Writer)
        try:
            self.assertTrue(delivery.start_recording('test',240))
            self.assertFalse(delivery.start_recording('second',240))
            self.wait(lambda:delivery.snapshot()['recorded']>=5)
            self.assertEqual(delivery.snapshot()['displayed'],0)
            self.assertGreater(delivery.snapshot()['display_superseded'],0)
            self.assertIsNotNone(delivery.take_frame())
            delivery.stop_recording();self.wait(lambda:delivery.snapshot()['recording_state']=='saved')
            self.assertTrue(delivery.thread.is_alive())
        finally:delivery.stop();delivery.thread.join(3)
        self.assertTrue(delivery.done);output.close.assert_called_once()
    def test_stop_before_worker_start_cancels_recording(self):
        entered=threading.Event();release=threading.Event();output=Mock(dropped=0)
        def factory():entered.set();release.wait(2);return output
        session=SimpleNamespace(with_audio=True,receiver=None,stopping=threading.Event(),thread=Mock())
        writer=Mock();delivery=MediaDelivery(session,factory,writer)
        self.assertTrue(entered.wait(1));delivery.start_recording('test',240);delivery.stop();release.set();delivery.thread.join(3)
        writer.assert_not_called();self.assertTrue(delivery.done)

    def test_audio_is_delivered_before_slow_video_conversion(self):
        entered=threading.Event();release=threading.Event();heard=threading.Event()
        receiver=Mock();receiver.take.side_effect=lambda video=True: (((240,bytes(384*240//2)) if video else None),[bytes(768)])
        session=SimpleNamespace(with_audio=True,receiver=receiver,stopping=threading.Event(),thread=Mock())
        session.thread.is_alive.return_value=True
        output=Mock(dropped=0);output.push.side_effect=lambda samples:heard.set()
        def slow(packed):
            entered.set();release.wait(2);return bytes(384*240*3)
        with patch('c64u_browser.media_session.rgb_frame',side_effect=slow):
            delivery=MediaDelivery(session,lambda:output)
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(heard.is_set(),'Sound waited behind video conversion')
            finally:release.set();delivery.stop();delivery.thread.join(3)
        self.assertTrue(delivery.done)

    def test_audio_drains_between_video_deadlines(self):
        receiver=Mock();receiver.take.side_effect=lambda video=True: (((240,bytes(384*240//2)) if video else None),[bytes(768)])
        session=SimpleNamespace(with_audio=True,receiver=receiver,stopping=threading.Event(),thread=Mock())
        session.thread.is_alive.return_value=True
        output=Mock(dropped=0);delivery=MediaDelivery(session,lambda:output)
        try:self.wait(lambda:any(call.kwargs.get('video') is False for call in receiver.take.call_args_list))
        finally:delivery.stop();delivery.thread.join(3)
        self.assertGreaterEqual(output.push.call_count,2)
