import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from c64u_browser.profiles import Preferences,Profile
from c64u_browser.api import BrowserError

class FavoritesTests(TestCase):
    def test_round_trip_preserves_profiles_folders_and_exact_keys(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'prefs.json';prefs=Preferences(path)
            profile=Profile.new('Test','192.168.68.66');prefs.profiles=[profile];prefs.selected_id=profile.id
            prefs.screenshot_folder='/tmp/screens';prefs.recording_folder='/tmp/video'
            prefs.setting_favorites={('Drive A Settings','Drive'),('Drive B Settings','Drive')}
            prefs.save();loaded=Preferences(path).load()
            self.assertEqual(loaded.setting_favorites,prefs.setting_favorites)
            self.assertEqual(loaded.selected_id,profile.id)
            self.assertEqual(loaded.screenshot_folder,'/tmp/screens');self.assertEqual(loaded.recording_folder,'/tmp/video')
            loaded.setting_favorites.remove(('Drive A Settings','Drive'));loaded.save()
            self.assertEqual(Preferences(path).load().setting_favorites,{('Drive B Settings','Drive')})
    def test_old_preferences_and_invalid_favorites(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'prefs.json';data={'schema_version':1,'profiles':[],'selected_id':None}
            path.write_text(json.dumps(data));self.assertFalse(Preferences(path).load().setting_favorites)
            for bad in ('bad',[['one']],[[1,'name']],[['','name']]):
                data['setting_favorites']=bad;path.write_text(json.dumps(data))
                with self.assertRaises(BrowserError):Preferences(path).load()
                self.assertEqual(json.loads(path.read_text()),data)
