# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy configuration remains usable by Core after backup UI retirement."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from c64u_browser.core import ArgonautCore, CoreError
from c64u_browser.file_service import CORE_HOST
from c64u_browser.profiles import Preferences

class UsbBackupPreferenceCompatibilityTests(unittest.TestCase):
    def test_blank_legacy_root_remains_optional(self):
        self.assertIsNone(ArgonautCore.usb_backup_root(SimpleNamespace(
            preferences=SimpleNamespace(usb_backup_root=''))))

    def test_saved_root_round_trips_and_resolves_in_core(self):
        with TemporaryDirectory() as tmp:
            prefs=Preferences(Path(tmp)/'config.json')
            prefs.usb_backup_root=tmp; prefs.save()
            loaded=Preferences(prefs.path).load()
            root=ArgonautCore.usb_backup_root(SimpleNamespace(preferences=loaded))
            self.assertEqual(CORE_HOST,root.scope)
            self.assertEqual(tmp,root.path)

    def test_unavailable_legacy_root_is_still_refused_by_core(self):
        with TemporaryDirectory() as tmp:
            app=SimpleNamespace(preferences=SimpleNamespace(usb_backup_root=str(Path(tmp)/'missing')))
            with self.assertRaises(CoreError):ArgonautCore.usb_backup_root(app)
