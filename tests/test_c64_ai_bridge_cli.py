import os
from pathlib import Path
import unittest
from unittest.mock import patch

from c64u_browser.c64_ai_bridge_cli import default_config_path


class C64AIBridgeCLITests(unittest.TestCase):
    def test_default_private_path_follows_app_identity(self):
        root = Path('/private/config')
        with patch('c64u_browser.c64_ai_bridge_cli.config_base',
                   return_value=root):
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': '1'}):
                self.assertEqual(
                    default_config_path(),
                    root / 'argonaut-development/test-lab/c64-ai-bridge.json')
            with patch.dict(os.environ, {'ARGONAUT_DEVELOPMENT': ''}):
                self.assertEqual(
                    default_config_path(),
                    root / 'argonaut/test-lab/c64-ai-bridge.json')


if __name__ == '__main__':
    unittest.main()
