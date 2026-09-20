# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from c64u_browser.api import BrowserError
from c64u_browser.file_service import CopyRequest, FileLocation, FileService


class FileServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.destination=self.root/'destination'
        self.source.mkdir();self.destination.mkdir();self.session=1
        self.service=FileService(lambda:(_ for _ in ()).throw(
            AssertionError('local copy must not request a device client')),
            lambda:self.session)

    def request(self,*names):
        return CopyRequest(FileLocation.core_host(self.source),tuple(names),
                           FileLocation.core_host(self.destination))

    def test_success_and_progress_are_headless(self):
        (self.source/'large.bin').write_bytes(b'x'*(1024*1024+16))
        prepared=self.service.prepare_copy(self.request('large.bin')).run()
        self.assertEqual('succeeded',prepared.state)
        events=[];job=self.service.execute_copy(prepared.result.plan_id)
        job.add_listener(events.append);result=job.run()
        self.assertEqual('succeeded',result.state)
        self.assertEqual(('large.bin',),result.result.completed)
        self.assertEqual((self.source/'large.bin').read_bytes(),
                         (self.destination/'large.bin').read_bytes())
        self.assertTrue(any(event.kind=='progress' and
                            event.job.progress.unit=='bytes' for event in events))

    def test_cancel_removes_staging_file_and_does_not_publish(self):
        (self.source/'large.bin').write_bytes(b'x'*(3*1024*1024))
        preview=self.service.prepare_copy(self.request('large.bin')).run().result
        job=self.service.execute_copy(preview.plan_id)
        def cancel_on_progress(event):
            if event.kind=='progress':self.service.cancel(job.id)
        job.add_listener(cancel_on_progress);result=job.run()
        self.assertEqual('cancelled',result.state)
        self.assertFalse((self.destination/'large.bin').exists())
        self.assertEqual((),result.result.completed)

    def test_conflict_preview_skip_replace_and_revalidation(self):
        (self.source/'a').write_text('new');(self.destination/'a').write_text('old')
        preview=self.service.prepare_copy(self.request('a')).run().result
        self.assertEqual(('a',),preview.conflicts)
        self.assertEqual(('a',),preview.replaceable)
        skipped=self.service.execute_copy(preview.plan_id,'skip').run()
        self.assertEqual('succeeded',skipped.state)
        self.assertEqual('old',(self.destination/'a').read_text())
        self.assertEqual(('a',),skipped.result.skipped)

        preview=self.service.prepare_copy(self.request('a')).run().result
        (self.destination/'a').write_text('changed after review')
        failed=self.service.execute_copy(preview.plan_id,'replace').run()
        self.assertEqual('failed',failed.state)
        self.assertEqual('transfer',failed.error.code)
        self.assertIn('changed',failed.result.failure)
        self.assertEqual('changed after review',(self.destination/'a').read_text())

    def test_delete_preview_revalidates_before_consequential_work(self):
        folder=self.destination/'folder';folder.mkdir();(folder/'a').write_text('a')
        preview=self.service.prepare_delete((FileLocation.core_host(folder),)).run().result
        (folder/'new').write_text('new')
        result=self.service.execute_delete(preview.plan_id).run()
        self.assertEqual('failed',result.state)
        self.assertEqual('delete',result.error.code)
        self.assertFalse(result.result.removed)
        self.assertTrue((folder/'a').exists())

    def test_categorized_failure_and_client_path_semantics(self):
        failed=self.service.prepare_copy(self.request('missing')).run()
        self.assertEqual('failed',failed.state)
        self.assertEqual('operation',failed.error.code)
        request=CopyRequest(FileLocation.client_upload('future-id','a'),('a',),
                            FileLocation.core_host(self.destination))
        with self.assertRaises(BrowserError):self.service.prepare_copy(request)

    def test_contract_never_returns_transport_or_secret(self):
        (self.source/'a').write_text('data')
        preview=self.service.prepare_copy(self.request('a')).run().result
        text=repr(preview)
        self.assertNotIn('UltimateClient',text);self.assertNotIn('password',text)
        self.assertFalse(hasattr(preview,'client'))

    def test_remote_plan_is_invalid_after_session_changes(self):
        client=SimpleNamespace(list_directory=lambda path:(path,[
            SimpleNamespace(name='a',kind='file',size=4)]))
        service=FileService(lambda:client,lambda:self.session)
        request=CopyRequest(FileLocation.c64u('/USB2'),('a',),
                            FileLocation.core_host(self.destination))
        preview=service.prepare_copy(request).run().result
        self.session+=1
        result=service.execute_copy(preview.plan_id).run()
        self.assertEqual('failed',result.state)
        self.assertEqual('session',result.error.code)
        self.assertFalse((self.destination/'a').exists())

    def test_native_upload_uses_private_reviewed_data(self):
        rom=self.source/'kernal.bin';rom.write_bytes(b'rom-data')
        preview=self.service.prepare_native_upload(
            FileLocation.core_host(rom),'/Flash/roms',rom.name).run().result
        self.assertEqual(8,preview.size)
        self.assertFalse(hasattr(preview,'data'))
        fake=object();self.service._client_provider=lambda:fake
        with patch('c64u_browser.file_service.upload_flash',
                   return_value='/Flash/roms/kernal.bin') as upload:
            result=self.service.execute_native_upload(preview.plan_id).run()
        self.assertEqual('succeeded',result.state)
        upload.assert_called_once_with(fake,'/Flash/roms','kernal.bin',b'rom-data')

    def test_import_without_gtk_or_display(self):
        root=str(Path(__file__).resolve().parents[1]);env=dict(os.environ)
        env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None)
        code="import sys; import c64u_browser.file_service, c64u_browser.jobs; assert 'gi.repository.Gtk' not in sys.modules"
        result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,
                              capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)


if __name__=='__main__':unittest.main()
