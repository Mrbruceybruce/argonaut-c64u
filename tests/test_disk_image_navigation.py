import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

try:
    from c64u_browser.api import BrowserError
    from c64u_browser.disk_image_dialog import DiskImageDialog
    from c64u_browser.drives_tab import DrivesTab
    from c64u_browser.gui import Browser
except ImportError:
    Browser = DiskImageDialog = DrivesTab = None


@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class DiskImageNavigationTests(unittest.TestCase):
    def test_pointer_activates_remote_pane_without_focusing_and_scrolling_list(self):
        app = SimpleNamespace(set_active_file_pane=Mock(), rlist=Mock())
        Browser.activate_file_pane_pointer(app, False)
        app.set_active_file_pane.assert_called_once_with(False)
        app.rlist.grab_focus.assert_not_called()

    def test_double_click_opens_d64_instead_of_treating_it_as_folder(self):
        app = SimpleNamespace(menu_token='old', open_disk_image=Mock(), navigate=Mock())
        row = SimpleNamespace(item=('GAME.D64', False))
        Browser.activate_row(app, True, row)
        app.open_disk_image.assert_called_once_with(True, 'GAME.D64')
        app.navigate.assert_not_called()

    def test_double_click_opens_d71_instead_of_treating_it_as_folder(self):
        app = SimpleNamespace(menu_token='old', open_disk_image=Mock(), navigate=Mock())
        row = SimpleNamespace(item=('DOUBLE.D71', False))
        Browser.activate_row(app, False, row)
        app.open_disk_image.assert_called_once_with(False, 'DOUBLE.D71')
        app.navigate.assert_not_called()

    def test_double_click_opens_d81_instead_of_treating_it_as_folder(self):
        app = SimpleNamespace(menu_token='old', open_disk_image=Mock(), navigate=Mock())
        row = SimpleNamespace(item=('THREE.D81', False))
        Browser.activate_row(app, True, row)
        app.open_disk_image.assert_called_once_with(True, 'THREE.D81')
        app.navigate.assert_not_called()

    def test_other_files_are_not_opened_as_disk_images(self):
        app = SimpleNamespace(menu_token='old', open_disk_image=Mock(), navigate=Mock())
        Browser.activate_row(app, True, SimpleNamespace(item=('GAME.PRG', False)))
        app.open_disk_image.assert_not_called()
        app.navigate.assert_not_called()

    def test_remote_mount_prepares_drive_a_and_opens_drives(self):
        drives = SimpleNamespace(box=object(), select_image=Mock())
        tabs = Mock()
        tabs.page_num.return_value = 2
        app = SimpleNamespace(client=object(), remote='/USB2/GAMES',
                              drives_tab=drives, tabs=tabs)
        Browser.open_mount_in_drives(app, 'DEMO.D81')
        drives.select_image.assert_called_once_with('/USB2/GAMES/DEMO.D81', 'a')
        tabs.set_current_page.assert_called_once_with(2)

    def test_mount_rejects_a_non_disk_file(self):
        app = SimpleNamespace(client=object(), remote='/USB2',
                              drives_tab=Mock(), tabs=Mock())
        with self.assertRaisesRegex(BrowserError, 'D64, G64, D71, G71 or D81'):
            Browser.open_mount_in_drives(app, 'README.TXT')

    def test_extract_refreshes_and_selects_a_visible_local_result(self):
        with tempfile.TemporaryDirectory() as folder:
            app = SimpleNamespace(local=Path(folder), refresh_local=Mock())
            dialog = SimpleNamespace(app=app)
            DiskImageDialog.refresh_local_destination(
                dialog, Path(folder) / 'EXTRACTED.PRG')
            app.refresh_local.assert_called_once_with(('EXTRACTED.PRG',))

    def test_drive_selection_prepares_path_without_mounting(self):
        path = Mock()
        message = Mock()
        tab = SimpleNamespace(cards={'a': {'path': path}}, message=message)
        DrivesTab.select_image(tab, '/USB2/GAME.D64', 'a')
        path.set_text.assert_called_once_with('/USB2/GAME.D64')
        path.grab_focus.assert_called_once_with()
        self.assertIn('selected for Drive A', message.set_text.call_args.args[0])

    def test_disk_close_focuses_parent_on_the_next_ui_turn(self):
        window = Mock()
        dialog = SimpleNamespace(app=SimpleNamespace(window=window))
        self.assertFalse(DiskImageDialog.restore_parent_focus(dialog))
        window.present.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
