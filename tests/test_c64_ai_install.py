from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import BrowserError, Entry
from c64u_browser.c64_ai_bridge_config import C64BridgeConfig
from c64u_browser.c64_ai_install import (
    ClientInstallResult, build_c64_ai_client, install_and_pair_c64_ai,
    install_c64_ai_client,
)


CONFIG = C64BridgeConfig(
    'gemma3:4b', '192.168.68.80', 6464, ('192.168.68.69',), 'A' * 64)


class C64AIInstallTests(unittest.TestCase):
    def test_built_in_tokenizer_matches_verified_petcat_fixture(self):
        program = build_c64_ai_client(CONFIG)
        self.assertEqual(len(program), 1532)
        self.assertEqual(
            sha256(program).hexdigest(),
            '03824eabf37ad745bdd21d5b27f3844249e926c42819d787880cd79d4f8a9c79')
        self.assertEqual(program[:2], b'\x01\x08')
        self.assertEqual(program[-2:], b'\x00\x00')

    @patch('c64u_browser.c64_ai_install.upload')
    @patch('c64u_browser.c64_ai_install.inspect', return_value=None)
    def test_missing_client_is_generated_uploaded_and_verified(self, _inspect, upload):
        program = build_c64_ai_client(CONFIG)

        def uploaded(_client, local, parent):
            self.assertEqual(parent, '/USB2')
            self.assertEqual(Path(local).read_bytes(), program)
            return {'path': '/USB2/argonaut-ai.prg', 'bytes': len(program),
                    'sha256': sha256(program).hexdigest(), 'verified': True}

        upload.side_effect = uploaded
        result = install_c64_ai_client(Mock(), CONFIG)
        self.assertTrue(result.installed)
        self.assertEqual(result.size, 1532)

    @patch('c64u_browser.c64_ai_install.download')
    @patch('c64u_browser.c64_ai_install.inspect',
           return_value=Entry('argonaut-ai.prg', 'file', 1532))
    def test_identical_existing_client_is_kept(self, _inspect, download):
        program = build_c64_ai_client(CONFIG)
        download.side_effect = lambda _client, _source, destination: Path(
            destination).write_bytes(program)
        result = install_c64_ai_client(Mock(), CONFIG)
        self.assertFalse(result.installed)

    @patch('c64u_browser.c64_ai_install.upload')
    @patch('c64u_browser.c64_ai_install.download')
    @patch('c64u_browser.c64_ai_install.inspect',
           return_value=Entry('argonaut-ai.prg', 'file', 10))
    def test_different_existing_client_is_never_overwritten(
            self, _inspect, download, upload):
        download.side_effect = lambda _client, _source, destination: Path(
            destination).write_bytes(b'different')
        with self.assertRaises(BrowserError):
            install_c64_ai_client(Mock(), CONFIG)
        upload.assert_not_called()

    @patch('c64u_browser.c64_ai_install.pair_bridge_address')
    @patch('c64u_browser.c64_ai_install.install_c64_ai_client')
    @patch('c64u_browser.c64_ai_install.load_bridge_config', return_value=CONFIG)
    def test_provision_installs_then_pairs_without_exposing_token(
            self, _load, install, pair):
        installed = ClientInstallResult(
            '/USB2/argonaut-ai.prg', True, 1526, 'd' * 64)
        install.return_value = installed
        pair.return_value = Mock(state='ready')
        runner = Mock()
        result = install_and_pair_c64_ai(
            Mock(), '/private/bridge.json', '192.168.68.70', runner)
        self.assertIs(result.client, installed)
        pair.assert_called_once_with(
            '/private/bridge.json', '192.168.68.70', runner)
        self.assertFalse(hasattr(result, 'token'))


if __name__ == '__main__':
    unittest.main()
