import unittest
from c64u_browser.stream_diagnostics import report,advice
from c64u_browser.streaming import AudioDecoder
from c64u_browser.video_geometry import fit
import struct

class Diagnostics(unittest.TestCase):
    def test_secrets_are_not_serialized(self):
        secret='SENSITIVE-token-password'
        data=dict(peer=secret,address='127.0.0.1',frames=secret,error=secret,
                  password=secret,stream_key=secret,recording_state=secret,path=secret)
        self.assertNotIn(secret,report(data,True))
        self.assertNotIn('127.0.0.1',report(data))
        self.assertIn('127.0.0.1',report(data,True))
    def test_explanations_do_not_diagnose_firewall_as_fact(self):
        self.assertIn('may be blocked',advice({'video_packets':0}))
        self.assertIn('no complete',advice({'video_packets':10,'frames':0}))
        self.assertIn('audio is not',advice({'video_packets':10,'frames':2,'with_audio':True}))
    def test_sequence_reset_and_reordering_do_not_explode_loss(self):
        d=AudioDecoder()
        for seq in [40000,0,1,0,2]:d.feed(struct.pack('<H',seq)+bytes(768))
        self.assertEqual(d.missing,0)
        self.assertGreater(d.resets,0)
    def test_geometry_preserves_raster_and_letterboxes(self):
        self.assertEqual(fit(384,272,1000,800,True),(116,128,768,544))
        self.assertEqual(fit(384,240,768,480),(0,0,768,480))
        x,y,w,h=fit(384,272,200,100,True)
        self.assertLessEqual(w,200);self.assertLessEqual(h,100)
        self.assertLess(abs(w/h-384/272),.02)
