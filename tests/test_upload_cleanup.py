import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock,patch
from c64u_browser.transfers import upload,UploadFailure
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
