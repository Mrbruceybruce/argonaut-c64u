import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from c64u_browser.file_service import FileLocation,PartialUpload
from c64u_browser.transfers import upload_managed,UploadFailure
from c64u_browser.usb_backup import RestoreResult
class CleanupTests(unittest.TestCase):
 def test_only_staged_path_offered_after_failure(self):
  from c64u_browser.simulated_ftp_reads import MemoryFilesystem
  peer=MemoryFilesystem()
  peer.interrupted=True
  with TemporaryDirectory() as d:
   p=Path(d)/'original.bin';p.write_bytes(b'abc')
   with self.assertRaises(UploadFailure) as caught:upload_managed(peer.attach(),p)
   staged=next(c[1] for c in peer.calls if c[0]=='write')
   self.assertEqual(caught.exception.partial_path,staged.decode())
   self.assertNotEqual(caught.exception.partial_path,'/USB2/original.bin')
   self.assertFalse(any(c[0]=='delete' for c in peer.calls))
   self.assertEqual(0,peer.active)
 def test_no_cleanup_before_upload_started(self):
  from c64u_browser.simulated_ftp_reads import MemoryFilesystem
  peer=MemoryFilesystem(files={b'/USB2/original.bin':b'keep'})
  with self.assertRaises(UploadFailure) as caught:upload_managed(peer.attach(),'original.bin')
  self.assertIsNone(caught.exception.partial_path)
  self.assertFalse(any(c[0]=='write' for c in peer.calls))
 def test_cancelled_usb_restore_retains_owned_partial_evidence(self):
  partial=PartialUpload(FileLocation.c64u('/USB1/c64u-part-owned'),'device','session')
  result=RestoreResult((),(),(),(),(),('movie.webm',),0,
                       partial.location.path,'Operation cancelled by request.',partial)
  self.assertIs(result.partial_upload,partial)
  self.assertIn(partial.location.path,result.details())
  self.assertIn('movie.webm',result.details())
