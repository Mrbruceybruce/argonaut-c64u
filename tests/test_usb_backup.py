# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import posixpath
import subprocess
import sys
import tempfile
import shutil
from threading import Event
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError, Entry, IdentityEntry
from c64u_browser.file_service import FileLocation, FileService
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.profiles import Preferences
from c64u_browser.scheduler import CoreScheduler, DeviceSession, JobBinding
from c64u_browser.usb_backup import (
    BackupRequest, MANIFEST_NAME, UsbBackupService)


class MemoryFTP:
    def __init__(self,client):self.client=client
    def close(self):pass
    def size(self,path):return len(self.client.files[path]) if path in self.client.files else None
    def retrbinary(self,command,callback):
        path=command[5:]
        if path in self.client.fail_paths:raise OSError('simulated transfer failure')
        if self.client.block_path==path:
            self.client.transfer_started.set();self.client.transfer_release.wait(3)
        data=self.client.files[path]
        for offset in range(0,len(data),3):callback(data[offset:offset+3])
        if not data:callback(b'')
    def storbinary(self,command,stream,callback=None):
        path=command[5:];data=stream.read();self.client._ensure_parent(path)
        self.client.store_count+=1
        if self.client.block_store:
            self.client.store_started.set();self.client.store_release.wait(3)
        if self.client.fail_store_on==self.client.store_count:
            raise OSError('simulated upload failure')
        self.client.files[path]=data
        if callback:callback(data)
    def mkd(self,path):self.client._ensure_parent(path);self.client.dirs.add(path)
    def rename(self,source,destination):
        self.client._ensure_parent(destination)
        if source in self.client.files:self.client.files[destination]=self.client.files.pop(source)
        elif source in self.client.dirs:
            self.client.dirs.remove(source);self.client.dirs.add(destination)
        else:raise OSError('missing source')
    def delete(self,path):del self.client.files[path]
    def rmd(self,path):self.client.dirs.remove(path)


class MemoryClient:
    credentials_encapsulated=True
    def __init__(self):
        self.dirs={'/','/USB2'};self.files={};self.fail_paths=set()
        self.list_calls=[]
        self.block_path=None;self.transfer_started=Event();self.transfer_release=Event()
        self.store_count=0;self.fail_store_on=None;self.block_store=False
        self.store_started=Event();self.store_release=Event()
    def open_ftp(self):return MemoryFTP(self)
    def _ensure_parent(self,path):
        parent=posixpath.dirname(path)
        if parent not in self.dirs:raise OSError('missing parent '+parent)
    def add_dir(self,path):
        parent=posixpath.dirname(path);self.dirs.add(parent);self.dirs.add(path)
    def add_file(self,path,data):self.dirs.add(posixpath.dirname(path));self.files[path]=data
    def list_directory(self,path):
        self.list_calls.append(path)
        if path not in self.dirs:raise BrowserError('missing directory '+path)
        prefix=path.rstrip('/')+'/' if path!='/' else '/';rows=[]
        for directory in self.dirs:
            if directory in ('/',path):continue
            rest=directory[len(prefix):] if directory.startswith(prefix) else ''
            if rest and '/' not in rest:rows.append(Entry(rest,'dir',None))
        for filename,data in self.files.items():
            rest=filename[len(prefix):] if filename.startswith(prefix) else ''
            if rest and '/' not in rest:rows.append(Entry(rest,'file',len(data)))
        return path,sorted(rows,key=lambda row:(row.kind!='dir',row.name.casefold()))


class RawIdentityClient:
    """Minimal byte-path tree used to verify storage identity semantics."""
    def __init__(self,tree):self.tree=tree;self.calls=[]
    def list_directory_identity(self,path):
        self.calls.append(path)
        if path not in self.tree:raise BrowserError('missing raw directory')
        return path,tuple(self.tree[path])


class UsbBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.client=MemoryClient()
        self.client.add_dir('/USB2/GAMES');self.client.add_dir('/USB2/EMPTY')
        self.client.add_file('/USB2/GAMES/A.PRG',b'alpha')
        self.client.add_file('/USB2/ZERO',b'')
        self.session=DeviceSession('c64u-abc','session-1')
        self.scheduler=CoreScheduler(lambda:self.session)
        self.addCleanup(self.scheduler.close)
        self.service=UsbBackupService(lambda:self.client,lambda:self.session,self.scheduler)
        self.files=FileService(lambda:self.client,lambda:self.session,
                               scheduler=self.scheduler)

    def backup_request(self,name='backup',paths=()):
        return BackupRequest(FileLocation.c64u('/USB2'),tuple(paths),
                             FileLocation.core_host(self.root/name))

    def create_backup(self,name='backup'):
        preview=self.service.prepare_backup(self.backup_request(name)).wait(5).result
        result=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('succeeded',result.state)
        return self.root/name,result.result

    def test_successful_backup_manifest_preview_progress_and_empty_data(self):
        events=[];prepare=self.service.prepare_backup(self.backup_request())
        prepare.add_listener(events.append);preview_job=prepare.wait(5)
        self.assertEqual('succeeded',preview_job.state)
        json.dumps(preview_job.as_dict())
        preview=preview_job.result
        self.assertEqual(('EMPTY','GAMES','ZERO'),preview.selected_paths)
        self.assertEqual(2,preview.directories);self.assertEqual(2,preview.files)
        job=self.service.execute_backup(preview.plan_id);job.add_listener(events.append)
        result=job.wait(5)
        self.assertEqual('complete',result.result.state)
        self.assertEqual(b'alpha',(self.root/'backup/GAMES/A.PRG').read_bytes())
        self.assertEqual(b'',(self.root/'backup/ZERO').read_bytes())
        self.assertTrue((self.root/'backup/EMPTY').is_dir())
        manifest=json.loads((self.root/'backup'/MANIFEST_NAME).read_text())
        self.assertEqual('complete',manifest['state'])
        self.assertEqual('c64u-abc',manifest['source']['device_id'])
        self.assertTrue(any(event.kind=='progress' for event in events))
        self.assertNotIn('MemoryClient',repr(preview));self.assertFalse(hasattr(preview,'client'))

    def test_backup_retains_recursive_volume_fingerprint_safety(self):
        preview = self.service.prepare_backup(self.backup_request()).wait(5).result
        preparation_calls = tuple(self.client.list_calls)
        self.assertIn('/USB2', preparation_calls)
        self.assertIn('/USB2/GAMES', preparation_calls)
        self.client.list_calls.clear()
        result = self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('succeeded', result.state, result.error)
        self.assertIn('/USB2', self.client.list_calls)
        self.assertIn('/USB2/GAMES', self.client.list_calls)

    def test_raw_filename_fingerprint_is_complete_deterministic_and_order_independent(self):
        side_1=b'Schatzj\x84ger [Side 1] [Ariolasoft] [TWG].d64'
        side_2=b'Schatzj\x84ger [Side 2] [Ariolasoft] [TWG].d64'
        files=(IdentityEntry(side_2,'file',174848),
               IdentityEntry(side_1,'file',174848))
        first=RawIdentityClient({
            b'/USB1':(IdentityEntry(b'games','dir',None),),
            b'/USB1/games':(IdentityEntry(b's','dir',None),),
            b'/USB1/games/s':files,
        })
        second=RawIdentityClient({
            b'/USB1':(IdentityEntry(b'games','dir',None),),
            b'/USB1/games':(IdentityEntry(b's','dir',None),),
            b'/USB1/games/s':tuple(reversed(files)),
        })
        observed=[]
        digest=UsbBackupService._volume_fingerprint(
            first,'/USB1',progress=lambda directories,entries:
            observed.append((directories,entries)))
        self.assertEqual(digest,UsbBackupService._volume_fingerprint(second,'/USB1'))
        self.assertEqual((3,4),observed[-1])
        self.assertIn(b'/USB1/games/s',first.calls)
        removed=RawIdentityClient({**second.tree,
            b'/USB1/games/s':(IdentityEntry(side_1,'file',174848),)})
        self.assertNotEqual(digest,UsbBackupService._volume_fingerprint(removed,'/USB1'))

    def test_raw_identity_digest_changes_for_name_type_size_and_hierarchy(self):
        def fingerprint(tree):
            return UsbBackupService._volume_fingerprint(
                RawIdentityClient(tree),'/USB1')
        baseline={
            b'/USB1':(IdentityEntry(b'folder','dir',None),),
            b'/USB1/folder':(IdentityEntry(b'game\x84.d64','file',10),),
        }
        expected=fingerprint(baseline)
        variants=(
            {b'/USB1':(IdentityEntry(b'folder','dir',None),),
             b'/USB1/folder':(IdentityEntry(b'game\x85.d64','file',10),)},
            {b'/USB1':(IdentityEntry(b'folder','file',None),)},
            {b'/USB1':(IdentityEntry(b'folder','dir',None),),
             b'/USB1/folder':(IdentityEntry(b'game\x84.d64','file',11),)},
            {b'/USB1':(IdentityEntry(b'other','dir',None),),
             b'/USB1/other':(IdentityEntry(b'game\x84.d64','file',10),)},
        )
        for tree in variants:
            with self.subTest(tree=tree):self.assertNotEqual(expected,fingerprint(tree))

    def test_raw_identity_bounds_and_cancellation_fail_instead_of_truncating(self):
        items=RawIdentityClient({b'/USB1':(
            IdentityEntry(b'a','file',1),IdentityEntry(b'b','file',1))})
        with patch('c64u_browser.usb_backup.MAX_ITEMS',1), \
                self.assertRaisesRegex(BrowserError,'item'):
            UsbBackupService._volume_fingerprint(items,'/USB1')
        deep=RawIdentityClient({
            b'/USB1':(IdentityEntry(b'a','dir',None),),
            b'/USB1/a':(IdentityEntry(b'b','dir',None),),
            b'/USB1/a/b':(),
        })
        with patch('c64u_browser.usb_backup.MAX_DEPTH',1), \
                self.assertRaisesRegex(BrowserError,'level'):
            UsbBackupService._volume_fingerprint(deep,'/USB1')
        checks=[0]
        def cancel():
            checks[0]+=1
            if checks[0]>1:raise JobCancelled('cancelled')
        with self.assertRaises(JobCancelled):
            UsbBackupService._volume_fingerprint(items,'/USB1',cancel)

    def test_usb_safety_fingerprint_includes_non_utf8_entries(self):
        raw_size={'value':174848}
        def raw_listing(path):
            actual,entries=self.client.list_directory(path.decode('utf-8'))
            rows=[IdentityEntry(entry.name.encode(),entry.kind,entry.size)
                  for entry in entries]
            if path==b'/USB2':
                rows.append(IdentityEntry(b'Schatzj\x84ger.d64','file',raw_size['value']))
            return actual.encode(),tuple(rows)
        self.client.list_directory_identity=raw_listing
        preview=self.service.prepare_backup(self.backup_request('raw')).wait(5).result
        result=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        preview=self.service.prepare_backup(self.backup_request('raw-change')).wait(5).result
        raw_size['value']+=1
        failed=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('failed',failed.state)
        self.assertEqual('storage',failed.error.code)

    def test_backup_root_change_does_not_nest_or_invalidate_existing_backup(self):
        first_root=self.root/'first-root';second_root=self.root/'second-root'
        first_root.mkdir();second_root.mkdir()
        preferences=Preferences(self.root/'preferences.json')
        preferences.usb_backup_root=str(first_root);preferences.save()
        folder,_=self.create_backup('first-root/backup-one')
        self.assertTrue((folder/MANIFEST_NAME).is_file())
        self.assertFalse((folder/'backup-one').exists())
        preferences.usb_backup_root=str(second_root);preferences.save()
        loaded=Preferences(preferences.path).load()
        self.assertEqual(str(second_root),loaded.usb_backup_root)
        self.client.files.clear();self.client.dirs={'/','/USB2'}
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        restored=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('succeeded',restored.state)
        self.assertEqual(b'alpha',self.client.files['/USB2/GAMES/A.PRG'])

    def test_selected_nested_source_preserves_volume_relative_path(self):
        preview=self.service.prepare_backup(self.backup_request(
            paths=('/USB2/GAMES/A.PRG',))).wait(5).result
        result=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual(b'alpha',(self.root/'backup/GAMES/A.PRG').read_bytes())

    def test_successful_restore_add_replace_unchanged_conflict_and_no_delete(self):
        folder,_=self.create_backup()
        self.client.files.clear();self.client.dirs={'/','/USB2','/USB2/GAMES'}
        self.client.add_file('/USB2/GAMES/A.PRG',b'other')
        self.client.add_dir('/USB2/ZERO')
        self.client.add_file('/USB2/EXTRA',b'keep')
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        json.dumps(preview.__dict__,default=lambda value:value.__dict__)
        self.assertIn('GAMES/A.PRG',preview.replacements)
        self.assertIn('ZERO',preview.conflicts)
        self.assertFalse(preview.extra_destination_files_deleted)
        events=[];job=self.service.execute_restore(preview.plan_id,replace=True)
        job.add_listener(events.append);result=job.wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual(b'alpha',self.client.files['/USB2/GAMES/A.PRG'])
        self.assertEqual(b'keep',self.client.files['/USB2/EXTRA'])
        self.assertIn('ZERO',result.result.conflicts)
        self.assertTrue(any(event.kind=='progress' for event in events))

    def test_restore_skips_replacement_without_explicit_decision(self):
        folder,_=self.create_backup();self.client.files['/USB2/GAMES/A.PRG']=b'other'
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        result=self.service.execute_restore(preview.plan_id,replace=False).wait(5)
        self.assertEqual('succeeded',result.state)
        self.assertEqual(b'other',self.client.files['/USB2/GAMES/A.PRG'])
        self.assertIn('GAMES/A.PRG',result.result.skipped)

    def test_source_destination_and_session_changes_fail_safely(self):
        preview=self.service.prepare_backup(self.backup_request()).wait(5).result
        self.client.files['/USB2/GAMES/A.PRG']=b'bravo'
        failed=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('failed',failed.state)
        self.assertEqual('backup',failed.error.code)
        self.assertEqual('incomplete',failed.result.state)

        preview=self.service.prepare_backup(self.backup_request('appeared')).wait(5).result
        (self.root/'appeared').mkdir()
        self.assertEqual('failed',self.service.execute_backup(preview.plan_id).wait(5).state)

        preview=self.service.prepare_backup(self.backup_request('session')).wait(5).result
        self.session=DeviceSession('c64u-abc','session-2')
        changed=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('failed',changed.state);self.assertEqual('session',changed.error.code)

    def test_restore_revalidates_local_bytes_and_remote_destination(self):
        folder,_=self.create_backup()
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        (folder/'GAMES/A.PRG').write_bytes(b'tampered')
        failed=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('backup-invalid',failed.error.code)

        (folder/'GAMES/A.PRG').write_bytes(b'alpha')
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        self.client.files['/USB2/GAMES/A.PRG']=b'bravo'
        failed=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('changed',failed.error.code)

    def test_missing_payload_blocks_restore_and_replaced_local_storage_is_detected(self):
        folder,_=self.create_backup();payload=folder/'GAMES/A.PRG'
        payload.unlink()
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        self.assertFalse(preview.can_restore);self.assertTrue(preview.missing)
        failed=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('backup-invalid',failed.error.code)

        payload.parent.mkdir(parents=True,exist_ok=True);payload.write_bytes(b'alpha')
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        moved=self.root/'moved';folder.rename(moved);shutil.copytree(moved,folder)
        failed=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('storage',failed.error.code)

    def test_backup_plan_expiration_and_consumption(self):
        now=[100.0]
        service=UsbBackupService(lambda:self.client,lambda:self.session,self.scheduler,
                                 plan_ttl=5,clock=lambda:now[0])
        expired=service.prepare_backup(self.backup_request('expired')).wait(5).result
        now[0]+=6
        with self.assertRaisesRegex(BrowserError,'expired'):
            service.execute_backup(expired.plan_id)
        fresh=service.prepare_backup(self.backup_request('fresh')).wait(5).result
        self.assertEqual('succeeded',service.execute_backup(fresh.plan_id).wait(5).state)
        with self.assertRaisesRegex(BrowserError,'already used'):
            service.execute_backup(fresh.plan_id)

    def test_queued_and_running_cancellation_and_followup_recovery(self):
        gate=Event();entered=Event()
        blocker=self.scheduler.submit(CoreJob('block',lambda _:(entered.set(),gate.wait(3))),
                                              JobBinding.device(self.session))
        self.assertTrue(entered.wait(1))
        queued=self.service.prepare_backup(self.backup_request('queued'))
        self.assertTrue(self.service.cancel(queued.id));gate.set();blocker.wait(3)
        self.assertEqual('cancelled',queued.wait(3).state)
        self.assertFalse((self.root/'queued').exists())

        preview=self.service.prepare_backup(self.backup_request('running')).wait(5).result
        self.client.block_path='/USB2/GAMES/A.PRG'
        running=self.service.execute_backup(preview.plan_id)
        self.assertTrue(self.client.transfer_started.wait(1));self.service.cancel(running.id)
        self.client.transfer_release.set();cancelled=running.wait(5)
        self.assertEqual('cancelled',cancelled.state)
        self.assertEqual('incomplete',cancelled.result.state)
        manifest=json.loads((self.root/'running'/MANIFEST_NAME).read_text())
        self.assertEqual('incomplete',manifest['state'])
        self.client.block_path=None
        self.assertEqual('succeeded',self.service.prepare_backup(
            self.backup_request('after-cancel')).wait(5).state)

    def test_partial_backup_is_reported_and_manifest_remains_reviewable(self):
        self.client.add_file('/USB2/ZFAIL',b'failure')
        preview=self.service.prepare_backup(self.backup_request('partial')).wait(5).result
        self.client.fail_paths.add('/USB2/ZFAIL')
        failed=self.service.execute_backup(preview.plan_id).wait(5)
        self.assertEqual('failed',failed.state);self.assertEqual('backup',failed.error.code)
        self.assertEqual('incomplete',failed.result.state)
        self.assertTrue(failed.result.completed_files)
        manifest=json.loads((self.root/'partial'/MANIFEST_NAME).read_text())
        self.assertEqual('incomplete',manifest['state']);self.assertTrue(manifest['failure'])

    def test_partial_restore_running_cancel_and_failure_recovery(self):
        folder,_=self.create_backup();self.client.files.clear()
        self.client.dirs={'/','/USB2'}
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        self.client.fail_store_on=2
        failed=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('failed',failed.state);self.assertEqual('restore',failed.error.code)
        self.assertTrue(failed.result.added);self.assertTrue(failed.result.remaining)

        self.client.fail_store_on=None;self.client.store_count=0
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        recovered=self.service.execute_restore(preview.plan_id,replace=True).wait(5)
        self.assertEqual('succeeded',recovered.state)

        self.client.files.clear();self.client.dirs={'/','/USB2'}
        preview=self.service.prepare_restore(FileLocation.core_host(folder),
                    FileLocation.c64u('/USB2')).wait(5).result
        self.client.block_store=True;self.client.store_started.clear();self.client.store_release.clear()
        running=self.service.execute_restore(preview.plan_id,replace=True)
        self.assertTrue(self.client.store_started.wait(1));self.service.cancel(running.id)
        self.client.store_release.set();cancelled=running.wait(5)
        self.assertEqual('cancelled',cancelled.state)
        partial=cancelled.result.partial_upload
        self.assertIsNotNone(partial)
        self.assertEqual(self.session.device_id,partial.device_id)
        self.assertEqual(self.session.session_id,partial.session_id)
        self.assertIn(partial.location.path,self.client.files)
        reviewed=self.files.prepare_partial_delete(partial).wait(5)
        self.assertEqual('succeeded',reviewed.state)
        deleted=self.files.execute_delete(reviewed.result.plan_id).wait(5)
        self.assertEqual('succeeded',deleted.state)
        self.assertNotIn(partial.location.path,self.client.files)

    def test_partial_restore_cleanup_rejects_filename_only_and_changed_session(self):
        from c64u_browser.file_service import PartialUpload
        arbitrary=FileLocation.c64u('/USB2/c64u-part-arbitrary')
        with self.assertRaisesRegex(BrowserError,'did not identify'):
            self.files.prepare_partial_delete(arbitrary)
        claim=PartialUpload(arbitrary,self.session.device_id,self.session.session_id)
        self.client.add_file(arbitrary.path,b'partial')
        reviewed=self.files.prepare_partial_delete(claim).wait(5).result
        self.session=DeviceSession(self.session.device_id,'session-2')
        changed=self.files.execute_delete(reviewed.plan_id).wait(5)
        self.assertEqual('failed',changed.state)
        self.assertEqual('session',changed.error.code)
        self.assertIn(arbitrary.path,self.client.files)
        with self.assertRaisesRegex(BrowserError,'connection changed'):
            self.files.prepare_partial_delete(claim)

    def test_client_upload_is_rejected_and_import_is_headless(self):
        request=BackupRequest(FileLocation.c64u('/USB2'),(),
                              FileLocation.client_upload('future','backup'))
        with self.assertRaises(BrowserError):self.service.prepare_backup(request)
        root=str(Path(__file__).resolve().parents[1]);env=dict(os.environ)
        env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None)
        code=("import sys; import c64u_browser.usb_backup; "
              "assert 'gi.repository.Gtk' not in sys.modules")
        result=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,
                              capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)


if __name__=='__main__':unittest.main()
