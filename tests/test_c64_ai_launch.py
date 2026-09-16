import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import BrowserError, Entry
from c64u_browser.c64_ai_launch import launch_c64_ai
from c64u_browser.configuration import Setting


class C64AILaunchTests(unittest.TestCase):
    def test_identity_file_runtime_setting_then_run(self):
        client = Mock()
        profile = Mock()
        with patch('c64u_browser.c64_ai_launch.inspect',
                   return_value=Entry('argonaut-ai.prg', 'file', 1526)), patch(
                'c64u_browser.c64_ai_launch.Configuration') as configuration:
            configuration.return_value.settings.return_value = [Setting(
                'Command Interface', 'Disabled', '', ('Disabled', 'Enabled'))]
            result = launch_c64_ai(client, profile)
        profile.verify_identity.assert_called_once_with(
            client.test_connection.return_value, require_bound=True)
        client.apply_configuration.assert_called_once_with({
            'C64 and Cartridge Settings': {'Command Interface': 'Enabled'}})
        client.run_prg.assert_called_once_with('/USB2/argonaut-ai.prg')
        self.assertEqual(result, {
            'path': '/USB2/argonaut-ai.prg',
            'command_interface_changed': True, 'saved_to_flash': False})

    def test_missing_client_does_not_change_device(self):
        client = Mock()
        profile = Mock()
        with patch('c64u_browser.c64_ai_launch.inspect', return_value=None):
            with self.assertRaises(BrowserError):
                launch_c64_ai(client, profile)
        client.apply_configuration.assert_not_called()
        client.run_prg.assert_not_called()


if __name__ == '__main__':
    unittest.main()
