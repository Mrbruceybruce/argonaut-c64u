"""C1 policy boundaries, including non-GTK callers; no hardware."""
import unittest
from unittest.mock import Mock, patch
from c64u_browser.api import BrowserError, Entry, UltimateClient
from c64u_browser.storage import (recognized_root, storage_root, discover,
    browse_directory, initial_directory, root_presentation, require_file_operation)
from c64u_browser.file_service import FileService, FileLocation, CopyRequest
from c64u_browser.files import operate_managed
from c64u_browser.deletion import prepare
from c64u_browser.disk_image_io import read_remote_disk_image


class StorageC1(unittest.TestCase):
    def test_exact_mapping_and_no_authorization_inference(self):
        for name in ('USB0','USB1','USB20','SD','Flash','Temp'):
            for suffix in ('','/folder','/folder/a.txt'):
                path='/'+name+suffix
                self.assertEqual('/'+name,recognized_root(path))
                self.assertEqual(None if name in ('Flash','Temp') else '/'+name,storage_root(path))
        for path in ('Temp','/temp','/TEMP','/flash','/SD/../Flash','/Temp/./x',
                     '/Flash//x','//USB1/x','x/USB1/x','/USB1/','/USB1/..',
                     '/USB1/\\../Flash/x','/Temp/x\n','/USB1x/a','/TempExtra'):
            self.assertIsNone(recognized_root(path),path)
            with self.assertRaises(BrowserError):require_file_operation(path)

    def test_discovery_only_advertised_exact_directories(self):
        client=Mock()
        client.list_directory.return_value=('/',[Entry(n,k,None) for n,k in
            [('USB2','dir'),('SD','dir'),('Flash','dir'),('Temp','dir'),
             ('USB3','file'),('temp','dir'),('Other','dir'),('Flash/a','dir')]])
        self.assertEqual(['/Flash','/SD','/Temp','/USB2'],discover(client))
        client.list_directory.return_value=('/',[])
        self.assertEqual([],discover(client))

    def test_browsing_arbitrary_flash_and_temp_directories_without_mutation(self):
        client=Mock()
        for path in ('/Flash/html/assets','/Flash/other/sub','/Temp/downloads'):
            client.list_directory.return_value=(path,[Entry('item','file',3)])
            self.assertEqual(path,browse_directory(client,path)[0])
        self.assertEqual(['list_directory']*3,[call[0] for call in client.mock_calls])

    def test_inaccessible_and_redirected_roots_never_become_empty_success(self):
        client=Mock()
        for path in ('/USB1','/SD','/Flash','/Temp'):
            client.list_directory.side_effect=BrowserError('550 unavailable')
            with self.assertRaisesRegex(BrowserError,'unavailable'):browse_directory(client,path)
            client.list_directory.side_effect=None
            client.list_directory.return_value=('/',[])
            with self.assertRaisesRegex(BrowserError,'unavailable'):browse_directory(client,path)
        client.list_directory.side_effect=lambda path: ('/',[Entry('Temp','dir',None)]) if path=='/' else (_ for _ in ()).throw(BrowserError('Temp unavailable'))
        with self.assertRaisesRegex(BrowserError,'unavailable'):initial_directory(client)

    def test_startup_preserves_usb_preference_and_can_restore_internal_folder(self):
        client=Mock()
        client.list_directory.side_effect=lambda path:(path,[Entry(n,'dir',None) for n in ('Flash','Temp','USB1','SD')] if path=='/' else [])
        self.assertEqual('/SD',initial_directory(client)[0])
        self.assertEqual('/Temp/downloads',initial_directory(client,'/Temp/downloads')[0])

    def test_labels_icons_and_nonpermanence_description(self):
        expected={'/SD':('SD','argonaut-sd-symbolic'),'/USB2':('USB2','argonaut-usb-symbolic'),
                  '/Flash':('Flash','drive-harddisk-solidstate-symbolic'),'/Temp':('Temp','argonaut-ram-symbolic')}
        for path,values in expected.items():self.assertEqual(values,root_presentation(path)[:2])
        self.assertIn('Temporary storage; keep important files elsewhere.',root_presentation('/Temp/a')[2])
        self.assertIn('Internal Memory',root_presentation('/Flash')[2])

    def test_core_generic_permissions_refuse_before_client_access(self):
        provider=Mock(side_effect=AssertionError('No device access permitted'))
        service=FileService(provider,lambda:1)
        self.addCleanup(service._scheduler.close)
        for parent in ('/Flash','/Flash/roms','/Flash/html','/Temp','/Temp/downloads',
                       '/USB1/../Flash','/USB1//a','x/USB1'):
            source=FileLocation.core_host('/tmp/source')
            remote=FileLocation.c64u(parent)
            for call in (lambda:service.prepare_copy(CopyRequest(source,('a',),remote)),
                         lambda:service.prepare_copy(CopyRequest(remote,('a',),source)),
                         lambda:service.prepare_delete((FileLocation.c64u(parent+'/a'),)),
                         lambda:service.rename(FileLocation.c64u(parent+'/a'),'b'),
                         lambda:service.create_folder(remote,'child')):
                try:job=call()
                except BrowserError:continue  # Folder-name validation is synchronous.
                result=job.wait(3)
                self.assertEqual('failed',result.state)
                self.assertIn('USB/SD',result.error.message)
        provider.assert_not_called()

    def test_root_mutations_refuse_and_usb_children_remain_authorized(self):
        service=FileService(Mock(),lambda:1)
        self.addCleanup(service._scheduler.close)
        for path in ('/','/USB1','/SD','/Flash','/Temp'):
            self.assertEqual('failed',service.rename(FileLocation.c64u(path),'new').wait(3).state)
            self.assertEqual('failed',service.prepare_delete((FileLocation.c64u(path),)).wait(3).state)
            with self.assertRaises(BrowserError):require_file_operation(path)
        for path in ('/USB1/file','/SD/folder/file'):
            self.assertEqual(path,require_file_operation(path))
        self.assertEqual('/USB1',require_file_operation('/USB1',parent=True))

    def test_rest_create_mount_and_launch_cannot_bypass_policy(self):
        client=UltimateClient('offline')
        with patch.object(client,'_request_json') as send:
            for root in ('/Flash','/Temp','/USB1/../Flash','/temp','/SD//x'):
                for operation in (lambda:client.create_d64(root+'/a.d64','TEST'),
                                  lambda:client.mount_disk('a',root+'/a.d64'),
                                  lambda:client.run_crt(root+'/a.crt'),
                                  lambda:client.run_prg(root+'/a.prg'),
                                  lambda:client.play_sid(root+'/a.sid')):
                    with self.assertRaises(BrowserError):operation()
            send.assert_not_called()
