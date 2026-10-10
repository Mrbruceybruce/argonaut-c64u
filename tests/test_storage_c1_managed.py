"""Actual managed FTP listing on loopback, never a physical device."""
import unittest
import tempfile
from unittest.mock import patch
from c64u_ftp_server import FakeC64UFtp
from c64u_browser.storage import discover, browse_directory
from c64u_browser.api import BrowserError
from c64u_browser.file_service import FileLocation
import test_ftp_reads as reads


class StorageC1Managed(unittest.TestCase):
    def test_existing_core_adapter_browses_flash_html_and_temp(self):
        directories={b'/':b'type=dir; USB1\r\ntype=dir; SD\r\ntype=dir; Flash\r\ntype=dir; Temp\r\n',
            b'/USB1':b'',b'/SD':b'',b'/Flash':b'type=dir; html\r\n',
            b'/Flash/html':b'type=file;size=3; index.html\r\n',
            b'/Temp':b'type=dir; downloads\r\n',b'/Temp/downloads':b''}
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        with FakeC64UFtp(directories=directories) as server:
            with patch('ftplib.FTP',side_effect=AssertionError('Legacy FTP forbidden')):
                core,_=fixture.connect(server)
                self.assertEqual(['/Flash','/SD','/Temp','/USB1'],discover(core.device_operations))
                for path in ('/Flash','/Flash/html','/Temp','/Temp/downloads'):
                    self.assertEqual(path,browse_directory(core.device_operations,path)[0])
                    result=core.list_directory(path).wait(3)
                    self.assertEqual('succeeded',result.state)
                    self.assertEqual(path,result.result[0])
                self.assertEqual(0,core._ftp_manager.active_count)
                forbidden={b'STOR',b'DELE',b'RMD',b'MKD',b'RNFR',b'RNTO'}
                self.assertFalse(forbidden.intersection(server.verbs))
                with tempfile.TemporaryDirectory() as folder:
                    for root in ('/Flash','/Temp'):
                        with self.assertRaisesRegex(BrowserError,'USB or SD'):
                            core.usb.prepare_restore(FileLocation.core_host(folder),FileLocation.c64u(root))
                self.assertFalse(forbidden.intersection(server.verbs))
                core.close()
