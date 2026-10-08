import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from c64u_browser.api import BrowserError
from c64u_browser.platform_support import config_base
from c64u_browser.macos_credentials import MacOSCredentials

class MacSupport(unittest.TestCase):
    def test_native_preferences_location(self):
        with patch.object(sys, 'platform', 'darwin'):
            self.assertEqual(config_base(), Path.home()/'Library'/'Application Support')

    def backend(self):
        credentials = object.__new__(MacOSCredentials)
        credentials.error = None
        credentials.backend = Mock()
        return credentials

    def test_keychain_operations_are_scoped_by_profile(self):
        c = self.backend()
        c.backend.get_password.return_value = 'value'
        self.assertEqual(c.get('profile'), 'value')
        c.set('profile', 'replacement')
        with patch.object(c,'exists',return_value=True) as exists:
            c.delete('profile')
        exists.assert_called_once_with('profile')
        c.backend.set_password.assert_called_once_with(c.service, 'profile', 'replacement')
        c.backend.delete_password.assert_called_once_with(c.service, 'profile')

    def test_missing_password_and_keychain_failure(self):
        c = self.backend()
        c.backend.get_password.return_value = None
        self.assertEqual(c.get('absent'), '')
        with patch.object(c,'exists',return_value=False) as exists:
            c.delete('absent')
        exists.assert_called_once_with('absent')
        c.backend.delete_password.assert_not_called()
        c.backend.set_password.side_effect = RuntimeError('denied')
        with self.assertRaises(BrowserError):
            c.set('profile', 'value')
