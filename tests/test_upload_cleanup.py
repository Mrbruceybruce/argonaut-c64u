import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from c64u_browser.file_service import FileLocation,PartialUpload
from c64u_browser.gui import Browser
from c64u_browser.transfers import upload,UploadFailure
from c64u_browser.usb_backup import RestoreResult
class CleanupTests(unittest.TestCase):
 def test_only_staged_path_offered_after_failure(self):
  with TemporaryDirectory() as d,patch('c64u_browser.files.inspect',return_value=None),patch('c64u_browser.transfers.connect') as connect:
   p=Path(d)/'original.bin';p.write_bytes(b'abc');ftp=connect.return_value;ftp.storbinary.side_effect=OSError('disconnected')
   with self.assertRaises(UploadFailure) as caught:upload(Mock(),p)
   self.assertEqual(caught.exception.partial_path,ftp.storbinary.call_args.args[0][5:])
   self.assertNotEqual(caught.exception.partial_path,'/USB2/original.bin');ftp.delete.assert_not_called()
 def test_no_cleanup_before_upload_started(self):
  with patch('c64u_browser.files.inspect',return_value=object()):
   with self.assertRaises(UploadFailure) as caught:upload(Mock(),'original.bin')
   self.assertIsNone(caught.exception.partial_path)
 def test_cancelled_usb_restore_enables_owned_partial_cleanup(self):
  partial=PartialUpload(FileLocation.c64u('/USB1/c64u-part-owned'),'device','session')
  result=RestoreResult((),(),(),(),(),('movie.webm',),0,
                       partial.location.path,'Operation cancelled by request.',partial)
  app=SimpleNamespace(status=Mock(),partial_upload=None,partial_button=Mock(),
                      client=None,refresh_remote=Mock(),usb_report=Mock())
  Browser.usb_restore_finished(app,SimpleNamespace(
      result=result,state='cancelled',error=SimpleNamespace(
          message='Operation cancelled by request.')))
  self.assertIs(app.partial_upload,partial)
  app.partial_button.set_sensitive.assert_called_once_with(True)
  report=app.usb_report.call_args.args
  self.assertIn(partial.location.path,report[2])
