import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from c64u_browser.profiles import Preferences,Profile
from c64u_browser.app_preferences import validate,defaults
from c64u_browser.storage import initial_directory
from c64u_browser.api import Entry,BrowserError

class AppPreferencesTests(unittest.TestCase):
    def test_roundtrip_preserves_profiles_and_options(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.json';p=Preferences(path)
            p.profiles=[Profile.new('Test','test')];p.selected_id=p.profiles[0].id
            p.app_options.update(preview_scale=175,preview_audio=False,remote_folders={p.selected_id:'/USB2/Games'})
            p.save();loaded=Preferences(path).load()
            self.assertEqual(loaded.app_options,p.app_options)
            loaded.app_options=defaults();loaded.save()
            self.assertEqual(Preferences(path).load().selected_id,p.selected_id)

    def test_invalid_sizes_rejected(self):
        for value in (49,201,True,'150'):
            with self.assertRaises(ValueError):validate({'preview_scale':value})
        self.assertEqual(validate({})['preview_scale'],150)

    def test_missing_remote_folder_falls_back_to_drive(self):
        client=Mock();client.list_directory.side_effect=[('/',[Entry('USB2','dir',0)]),BrowserError('Gone'),('/USB2',[])]
        self.assertEqual(initial_directory(client,'/USB2/Gone'),('/USB2',[]))
