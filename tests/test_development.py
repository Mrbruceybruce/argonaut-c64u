import os
import unittest
from unittest.mock import patch
from c64u_browser.profiles import Preferences
from c64u_browser.credentials import Credentials, SessionCredentials
from c64u_browser.version import build_info

class DevelopmentTests(unittest.TestCase):
    def test_settings_are_separate_and_empty(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'0'}):
            stable=Preferences().path
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
            dev=Preferences().path
        self.assertNotEqual(stable,dev)
        self.assertEqual(dev.parent.name,'argonaut-development')
        self.assertEqual(stable.parent.name,'argonaut')

    def test_development_never_opens_keyring(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
            credentials=Credentials()
            self.assertIsInstance(credentials,SessionCredentials)
            self.assertEqual(credentials.get('stable-profile'),'')

    def test_about_identifies_development(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1','ARGONAUT_DEV_BUILD':'test-modified'}):
            self.assertEqual(build_info(),{'version':'0.1.4-dev','build':'test-modified'})
