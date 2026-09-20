import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from c64u_browser.profiles import Preferences
from c64u_browser.credentials import Credentials, SessionCredentials
from c64u_browser.version import build_info
from c64u_browser import development

class DevelopmentTests(unittest.TestCase):
    def test_settings_are_separate_and_empty(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'0'}):
            stable=Preferences().path
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
            dev=Preferences().path
        self.assertNotEqual(stable,dev)
        self.assertEqual(dev.parent.name,'argonaut-development')
        self.assertEqual(stable.parent.name,'argonaut')

    def test_backup_root_persists_in_separate_stable_and_development_configs(self):
        with tempfile.TemporaryDirectory() as folder, patch(
                'c64u_browser.profiles.config_base',return_value=Path(folder)):
            with patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'0'}):
                stable=Preferences();stable.usb_backup_root='/stable/backups';stable.save()
            with patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'1'}):
                development_prefs=Preferences()
                self.assertEqual('',development_prefs.usb_backup_root)
                development_prefs.usb_backup_root='/development/backups';development_prefs.save()
                self.assertEqual('/development/backups',Preferences().load().usb_backup_root)
            with patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'0'}):
                self.assertEqual('/stable/backups',Preferences().load().usb_backup_root)

    def test_config_and_service_names_follow_package_identity(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': '1'}):
            self.assertEqual(development.config_name(), 'argonaut-development')
            self.assertEqual(
                development.service_name('c64-ai-test.timer'),
                'argonaut-development-c64-ai-test.timer')
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': '0'}):
            self.assertEqual(development.config_name(), 'argonaut')
            self.assertEqual(
                development.service_name('c64-ai-test.timer'),
                'argonaut-c64-ai-test.timer')

    def test_development_never_opens_keyring(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1'}):
            credentials=Credentials()
            self.assertIsInstance(credentials,SessionCredentials)
            self.assertEqual(credentials.get('stable-profile'),'')

    def test_about_identifies_development(self):
        with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT':'1','ARGONAUT_DEV_BUILD':'test-modified'}):
            self.assertEqual(build_info(),{'version':'1.8-dev','build':'test-modified'})
