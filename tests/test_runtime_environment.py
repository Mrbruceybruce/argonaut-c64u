"""Signed macOS bundles must not receive GStreamer registry writes."""
import builtins
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from c64u_browser.runtime_environment import configure_gstreamer_registry


class RuntimeEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.bundle = self.home / 'relocated/Argonaut.app/Contents/Frameworks'
        self.bundle.mkdir(parents=True)
        for mock in (patch('sys.platform', 'darwin'),
                     patch.object(sys, 'frozen', True, create=True),
                     patch.object(sys, '_MEIPASS', str(self.bundle), create=True),
                     patch.object(Path, 'home', return_value=self.home),
                     patch.dict(os.environ, {'GST_REGISTRY': str(self.bundle / 'registry.bin'),
                                             'GST_REGISTRY_1_0': '/explicit/registry',
                                             'GST_PLUGIN_PATH': str(self.bundle),
                                             'GST_PLUGIN_SYSTEM_PATH': ''}, clear=True)):
            mock.start()
            self.addCleanup(mock.stop)

    def test_channels_override_explicit_registry_only_and_write_outside_bundle(self):
        for development, channel in ((False, 'argonaut'), (True, 'argonaut-development')):
            configure_gstreamer_registry(development=development)
            expected = self.home / 'Library/Caches' / channel / 'gstreamer/registry.bin'
            registry = Path(os.environ['GST_REGISTRY']).resolve()
            self.assertEqual(registry, expected.resolve())
            self.assertEqual(Path(os.environ['GST_REGISTRY_1_0']).resolve(), expected.resolve())
            self.assertFalse(registry.is_relative_to(self.bundle.resolve()))
            self.assertFalse(registry.is_relative_to(self.bundle.parents[1].resolve()))
            expected.write_bytes(b'simulated GStreamer cache')
            self.assertFalse(list(self.bundle.parents[1].rglob('registry.bin')))
            self.assertEqual(os.environ['GST_PLUGIN_PATH'], str(self.bundle))
            self.assertEqual(os.environ['GST_PLUGIN_SYSTEM_PATH'], '')

    def test_other_platforms_and_unfrozen_environment_unchanged(self):
        before = dict(os.environ)
        for platform, frozen in (('win32', True), ('linux', True), ('darwin', False)):
            with patch('sys.platform', platform), patch.object(sys, 'frozen', frozen):
                configure_gstreamer_registry()
            self.assertEqual(dict(os.environ), before)
        self.assertFalse((self.home / 'Library').exists())

    def test_cache_creation_failure_does_not_fall_back(self):
        with patch.object(Path, 'mkdir', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                configure_gstreamer_registry()

    def test_symlink_into_app_is_rejected(self):
        (self.home / 'Library').mkdir()
        (self.home / 'Library/Caches').symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            configure_gstreamer_registry()

    def test_launcher_configures_before_both_consumers(self):
        import c64u_browser
        launcher = Path(__file__).resolve().parents[1] / 'packaging/windows/launch.py'
        fake_package = self.home / 'package'
        fake_package.mkdir()
        (fake_package / '_build.json').write_text('{"development": true, "build": "test"}')
        for self_test in (False, True):
            consumer = types.ModuleType('fake_consumer')
            observed = []
            def consume(*args):
                observed.append(os.environ['GST_REGISTRY'])
                self.assertIn('/argonaut-development/gstreamer/', observed[-1])
            consumer.main = consume
            consumer.run = consume
            original_import = builtins.__import__
            def checked_import(name, *args, **kwargs):
                if name in ('c64u_browser.gui', 'c64u_browser.package_self_test'):
                    self.assertIn('/argonaut-development/gstreamer/', os.environ['GST_REGISTRY'])
                return original_import(name, *args, **kwargs)
            os.environ['GST_REGISTRY'] = str(self.bundle / 'registry.bin')
            with patch.object(c64u_browser, '__file__', str(fake_package / '__init__.py')), \
                    patch.dict(sys.modules, {'c64u_browser.gui': consumer,
                                             'c64u_browser.package_self_test': consumer}), \
                    patch.object(sys, 'argv', ['Argonaut'] + (['--self-test', 'result'] if self_test else [])), \
                    patch('os.chdir'), patch('builtins.__import__', side_effect=checked_import):
                runpy.run_path(str(launcher))
            self.assertEqual(len(observed), 1)


if __name__ == '__main__':
    unittest.main()
