import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

# Importing GTK types does not create windows or connect to a device.
try:
    from c64u_browser.gui import Browser
except ImportError:
    Browser = None


@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class LocalDirectoryListing(unittest.TestCase):
    def test_dangling_symlink_does_not_abort_the_whole_listing(self):
        # Emacs lock files (e.g. ".#t.txt") are symlinks pointing at a
        # "user@host.pid:boot-time" string that was never a real path, so
        # they are permanently dangling. stat()-ing one raises ENOENT even
        # though the entry itself is perfectly real and lists fine with
        # lstat()/is_dir(). One such file must not take the rest of the
        # directory down with it.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'real.txt').write_bytes(b'hello')
            os.symlink('rix@host.12345:1758842000', tmp / '.#t.txt')

            fake = SimpleNamespace(
                local=tmp,
                llist=Mock(),
                lpath=Mock(),
                drive_bars={True: Mock()},
                status=Mock(),
                populate=Mock(),
            )

            self.assertTrue(Browser.refresh_local(fake))

            fake.status.set_text.assert_not_called()
            listing, entries = fake.populate.call_args.args
            by_name = {name: (directory, size) for name, directory, size in entries}
            self.assertEqual(by_name['real.txt'], (False, 5))
            self.assertEqual(by_name['.#t.txt'], (False, 0))

    def test_directory_itself_unreadable_still_reports_status(self):
        # A genuine directory-level failure (permission denied, the path
        # having been removed out from under us, etc.) is a different
        # situation and should still surface to the status bar.
        missing = Path('/nonexistent-for-test/definitely-not-real')
        fake = SimpleNamespace(
            local=missing,
            llist=Mock(),
            lpath=Mock(),
            drive_bars={True: Mock()},
            status=Mock(),
            populate=Mock(),
        )

        self.assertIsNone(Browser.refresh_local(fake))
        fake.status.set_text.assert_called_once()
        fake.populate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
