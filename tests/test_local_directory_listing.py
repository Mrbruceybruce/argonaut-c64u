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
                preferences=SimpleNamespace(app_options={'show_hidden_local': True}),
                llist=Mock(**{'get_selected_rows.return_value': ()}),
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

    def test_hidden_entries_are_filtered_by_default_and_can_be_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'ordinary.txt').write_text('visible')
            (tmp / '.secret').write_text('hidden')
            (tmp / '.folder').mkdir()
            fake = SimpleNamespace(
                local=tmp,
                preferences=SimpleNamespace(app_options={'show_hidden_local': False}),
                llist=Mock(**{'get_selected_rows.return_value': ()}), lpath=Mock(), drive_bars={True: Mock()},
                status=Mock(), populate=Mock())

            self.assertTrue(Browser.refresh_local(fake))
            entries = fake.populate.call_args.args[1]
            self.assertEqual([entry[0] for entry in entries], ['ordinary.txt'])

            fake.preferences.app_options['show_hidden_local'] = True
            self.assertTrue(Browser.refresh_local(fake))
            entries = fake.populate.call_args.args[1]
            self.assertEqual({entry[0] for entry in entries},
                             {'ordinary.txt', '.secret', '.folder'})

    def test_refresh_restores_surviving_selected_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'keep.txt').write_text('selected')
            (tmp / 'other.txt').write_text('unselected')
            selected = [SimpleNamespace(item=('keep.txt', False, 8)),
                        SimpleNamespace(item=('removed.txt', False, 0))]
            listing = Mock(**{'get_selected_rows.return_value': selected})
            rebuilt = []

            def populate(target, entries):
                self.assertIs(target, listing)
                rebuilt[:] = [Mock(item=entry) for entry in entries]
                for index, row in enumerate(rebuilt):
                    row.get_next_sibling.return_value = (
                        rebuilt[index + 1] if index + 1 < len(rebuilt) else None)
                listing.get_first_child.return_value = rebuilt[0]

            fake = SimpleNamespace(
                local=tmp, _local_listing_path=tmp,
                preferences=SimpleNamespace(app_options={'show_hidden_local': False}),
                llist=listing, lpath=Mock(), drive_bars={True: Mock()},
                status=Mock(), populate=Mock(side_effect=populate))

            self.assertTrue(Browser.refresh_local(fake))
            listing.get_selected_rows.assert_called_once_with()
            listing.unselect_all.assert_called_once_with()
            listing.select_row.assert_called_once_with(rebuilt[0])
            self.assertEqual(rebuilt[0].item[0], 'keep.txt')
            fake.status.set_text.assert_not_called()

    def test_directory_itself_unreadable_still_reports_status(self):
        # A genuine directory-level failure (permission denied, the path
        # having been removed out from under us, etc.) is a different
        # situation and should still surface to the status bar.
        missing = Path('/nonexistent-for-test/definitely-not-real')
        fake = SimpleNamespace(
            local=missing,
            preferences=SimpleNamespace(app_options={'show_hidden_local': False}),
            llist=Mock(**{'get_selected_rows.return_value': ()}),
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
