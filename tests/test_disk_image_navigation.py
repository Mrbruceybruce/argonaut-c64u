import unittest
from types import SimpleNamespace
from unittest.mock import Mock

try:
    from c64u_browser.gui import Browser
except ImportError:
    Browser = None


@unittest.skipIf(Browser is None, 'GTK runtime unavailable')
class DiskImageNavigationTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
