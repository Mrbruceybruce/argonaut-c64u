import unittest
from c64u_browser.configuration import Setting
from c64u_browser.dependencies import enabled,LED_MODES
class LEDTests(unittest.TestCase):
 def test_confirmed_modes(self):
  expected={'Default':(False,True,False,False),'Off':(False,False,False,False),'Fixed Color':(False,True,True,True),'Rainbow':(True,True,False,True),'Rainbow Sparkle':(True,True,False,True),'SID Music':(True,True,False,True),'Sparkle':(False,True,True,True)}
  for mode,flags in expected.items():
   settings={'LED Strip Settings':[Setting('LedStrip Mode',mode,'')]}
   self.assertEqual(tuple(enabled('LED Strip Settings',name,settings,{}) for name in LED_MODES),flags)
   self.assertTrue(enabled('LED Strip Settings','LedStrip Auto SID Mode',settings,{}))
 def test_pending_mode_and_other_hardware(self):
  settings={'LED Strip Settings':[Setting('LedStrip Mode','Off','')]}
  self.assertTrue(enabled('LED Strip Settings','Fixed Color',settings,{('LED Strip Settings','LedStrip Mode'):'Fixed Color'}))
  self.assertTrue(enabled('Keyboard Lighting','Fixed Color',settings,{}))
