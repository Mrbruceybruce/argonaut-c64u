# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from c64u_browser.core import CoreError
from c64u_browser.file_service import FileLocation
from c64u_browser.gui import Browser,configure_backup_destination_chooser


class UsbBackupPreferencePresentationTests(unittest.TestCase):
    def test_blank_root_preserves_native_chooser_default(self):
        chooser=Mock()
        configure_backup_destination_chooser(
            chooser,None,'/USB2',file_factory=lambda path:path)
        chooser.set_current_folder.assert_not_called()
        chooser.set_current_name.assert_called_once_with('Argonaut-USB2-backup')

    def test_chooser_starts_in_configured_core_host_root(self):
        chooser=Mock();root=FileLocation.core_host('/tmp/Argonaut Backups')
        configure_backup_destination_chooser(
            chooser,root,'/SD',file_factory=lambda path:'folder:'+path)
        chooser.set_current_folder.assert_called_once_with('folder:'+root.path)
        chooser.set_current_name.assert_called_once_with('Argonaut-SD-backup')

    def test_unavailable_configured_root_stops_before_chooser(self):
        core=Mock();core.usb_backup_root.side_effect=CoreError(
            'storage','The configured USB/SD backup root is unavailable.')
        app=SimpleNamespace(busy=False,client=object(),remote='/USB1',
            rlist=Mock(),core=core,status=Mock())
        app.rlist.get_selected_rows.return_value=[]
        Browser.backup_usb(app)
        app.status.set_text.assert_called_once_with(
            'The configured USB/SD backup root is unavailable.')


if __name__=='__main__':unittest.main()
