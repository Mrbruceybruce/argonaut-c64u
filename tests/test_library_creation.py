"""Deterministic creation with an in-memory managed-adapter double."""
import hashlib
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from c64u_browser.library_creation import create_empty_library,CreationTarget,CreationError
from c64u_browser.managed_library import ManagedLibraryReader,LibraryError,parse_manifest
from c64u_browser.picker_model import PickerSelection
from c64u_browser.scheduler import DeviceSession
from tests.test_managed_library import ID,PATH,manifest


class MemoryAdapter:
    def __init__(self):
        self.dirs={'/','/SD','/USB0'};self.files={};self.calls=[];self.before=lambda *args:None
    def list_directory(self,path):
        if path not in self.dirs:raise LibraryError('Missing directory')
        prefix=path.rstrip('/')+'/'
        names=[NS(name=p[len(prefix):],kind='dir') for p in self.dirs
               if p.startswith(prefix) and p!=path and '/' not in p[len(prefix):]]
        names += [NS(name=p[len(prefix):],kind='file') for p in self.files
                  if p.startswith(prefix) and '/' not in p[len(prefix):]]
        return path,names
    def mutate(self,action,path,destination=None):
        self.calls.append((action,path,destination));self.before(action,path)
        if action=='mkdir':
            if path in self.dirs or path in self.files:raise LibraryError('Exists')
            self.dirs.add(path)
        elif action=='rmdir':
            if self.list_directory(path)[1]:raise LibraryError('Not empty')
            self.dirs.remove(path)
        elif action=='rename':
            if destination in self.files or destination in self.dirs:raise LibraryError('Exists')
            self.files[destination]=self.files.pop(path)
        elif action=='delete':del self.files[path]
        else:raise AssertionError(action)
        return {'outcome':'acknowledged'}
    def write_from(self,path,stream,size):
        self.calls.append(('write',path,None));self.before('write',path)
        if path in self.files:raise LibraryError('Overwrite forbidden')
        data=stream.read();self.files[path]=data
        return NS(transferred=len(data),sha256=hashlib.sha256(data).hexdigest())
    def read(self,path,maximum):
        data=self.files[path]
        if len(data)>maximum:raise LibraryError('Too large')
        return data


class CreationTests(TestCase):
    def setUp(self):
        self.adapter=MemoryAdapter()
        self.target=CreationTarget(ID,'device','one','/SD',PATH)
        self.session=DeviceSession('device','one')
    def create(self):return create_empty_library(self.adapter,self.target,lambda:None,lambda:None)
    def test_success_structure_manifest_and_rediscovery(self):
        library=self.create()
        self.assertEqual(ID,library.identity.library_id);self.assertEqual((),library.games)
        self.assertEqual({PATH+'/manifest.json'},set(self.adapter.files))
        self.assertTrue({PATH,PATH+'/games',PATH+'/metadata',PATH+'/artwork'}<=self.adapter.dirs)
        reader=ManagedLibraryReader(self.adapter.list_directory,self.adapter.read,self.session,lambda:None)
        result=reader.discover();self.assertEqual('valid',result.status)
        self.assertEqual(library,result.libraries[0])
    def test_dot_entries_omitted_creation_and_rediscovery_succeed(self):
        listing=self.adapter.list_directory
        def hide_dot_files(path):
            actual,entries=listing(path)
            return actual,[e for e in entries if not e.name.startswith('.')]
        self.adapter.list_directory=hide_dot_files
        library=self.create()
        self.assertEqual(ID,library.identity.library_id)
        self.assertFalse(any('/.' in path for _,path,_ in self.adapter.calls))
        reader=ManagedLibraryReader(hide_dot_files,self.adapter.read,self.session,lambda:None)
        self.assertEqual(library,reader.discover().libraries[0])

    def test_missing_staged_manifest_reports_missing_evidence(self):
        listing=self.adapter.list_directory
        def omit_manifest(path):
            actual,entries=listing(path)
            return actual,[e for e in entries if not e.name.startswith('manifest.pending-')]
        self.adapter.list_directory=omit_manifest
        with self.assertRaisesRegex(CreationError,'Missing expected creation evidence'):
            self.create()
        self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
        reader=ManagedLibraryReader(listing,self.adapter.read,self.session,lambda:None)
        self.assertEqual('unavailable',reader.discover().status)

    def test_user_file_reports_unexpected_content_without_publication(self):
        def inject(action,path):
            if action=='write':self.adapter.files[PATH+'/user.txt']=b'keep'
        self.adapter.before=inject
        with self.assertRaisesRegex(CreationError,'Unexpected content.*user.txt'):
            self.create()
        self.assertEqual(b'keep',self.adapter.files[PATH+'/user.txt'])
        self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
        self.assertFalse(any(action=='delete' for action,_,_ in self.adapter.calls))

    def test_missing_directory_blocks_publication_and_rediscovery(self):
        def remove(action,path):
            if action=='write':self.adapter.dirs.remove(PATH+'/artwork')
        self.adapter.before=remove
        with self.assertRaisesRegex(CreationError,'Missing expected creation evidence: artwork'):
            self.create()
        self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
        self.adapter.files[PATH+'/manifest.json']=manifest()
        del self.adapter.files[next(p for p in self.adapter.files if 'manifest.pending-' in p)]
        reader=ManagedLibraryReader(self.adapter.list_directory,self.adapter.read,self.session,lambda:None)
        result=reader.discover()
        self.assertEqual('unavailable',result.status)
        self.assertIn('Invalid/incomplete library structure: artwork',result.message)

    def test_nonatomic_rename_leaving_pending_evidence_is_not_valid(self):
        mutate=self.adapter.mutate
        def copy_rename(action,path,destination=None):
            payload=self.adapter.files.get(path)
            result=mutate(action,path,destination)
            if action=='rename':self.adapter.files[path]=payload
            return result
        self.adapter.mutate=copy_rename
        with self.assertRaisesRegex(CreationError,'Unexpected content.*manifest.pending-'):
            self.create()
        reader=ManagedLibraryReader(self.adapter.list_directory,self.adapter.read,self.session,lambda:None)
        self.assertEqual('unavailable',reader.discover().status)

    def test_manifest_is_published_only_after_complete_structure(self):
        def at_publication(action,path):
            if action=='rename':
                self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
                self.assertTrue({PATH+'/'+n for n in ('games','metadata','artwork')}<=self.adapter.dirs)
                self.assertEqual(ID,parse_manifest(self.adapter.files[path],'device',PATH).identity.library_id)
        self.adapter.before=at_publication
        self.create()

    def test_duplicate_existing_folder_or_file_refused_without_mutations(self):
        for kind in ('dir','file'):
            self.adapter=MemoryAdapter()
            if kind=='dir':self.adapter.dirs.add(PATH)
            else:self.adapter.files[PATH]=b'user'
            with self.assertRaises(CreationError):self.create()
            self.assertEqual([],self.adapter.calls)
    def test_creation_boundary_refuses_flash_temp_and_redirected_destination(self):
        for root,path in (('/Flash','/Flash/ARGONAUT_LIBRARY'),('/Temp','/Temp/ARGONAUT_LIBRARY'),
                          ('/SD','/USB0/ARGONAUT_LIBRARY')):
            self.target=replace(self.target,root=root,path=path)
            with self.assertRaises(CreationError):self.create()
            self.assertEqual([],self.adapter.calls)
    def test_missing_root_refused(self):
        self.adapter.dirs.remove('/SD')
        with self.assertRaises(CreationError):self.create()
        self.assertEqual([],self.adapter.calls)
    def test_failure_before_manifest_cleans_only_acknowledged_empty_directories(self):
        self.adapter.files['/SD/user.crt']=b'keep'
        def fail(action,path):
            if action=='write':raise LibraryError('write refused before transfer')
        self.adapter.before=fail
        with self.assertRaises(CreationError) as caught:self.create()
        self.assertEqual((PATH+'/artwork',PATH+'/metadata',PATH+'/games',PATH),caught.exception.result.removed)
        self.assertNotIn(PATH,self.adapter.dirs)
        self.assertEqual({'/SD/user.crt':b'keep'},self.adapter.files)
    def test_partial_creation_without_manifest_never_appears_valid(self):
        def fail(action,path):
            if action=='mkdir' and path.endswith('/metadata'):
                self.adapter.files[PATH+'/games/foreign.txt']=b'keep'
                raise LibraryError('fail')
        self.adapter.before=fail
        with self.assertRaises(CreationError) as caught:self.create()
        self.assertIn('Recovery required',str(caught.exception))
        reader=ManagedLibraryReader(self.adapter.list_directory,self.adapter.read,self.session,lambda:None)
        self.assertEqual('unavailable',reader.discover().status)
        self.assertFalse(any(c[0]=='delete' for c in self.adapter.calls))
    def test_foreign_content_prevents_cleanup(self):
        def fail(action,path):
            if action=='write':
                self.adapter.files[PATH+'/user.txt']=b'keep'
                raise LibraryError('fail')
        self.adapter.before=fail
        with self.assertRaises(CreationError):self.create()
        self.assertEqual(b'keep',self.adapter.files[PATH+'/user.txt'])
        self.assertIn(PATH,self.adapter.dirs)
    def test_corrupt_readback_keeps_manifest_unpublished(self):
        read=self.adapter.read
        self.adapter.read=lambda path,limit:b'bad' if 'manifest.pending-' in path else read(path,limit)
        with self.assertRaises(CreationError):self.create()
        self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
        self.assertTrue(any('manifest.pending-' in p for p in self.adapter.files))
    def test_uncertain_completion_never_removes_verified_structure(self):
        mutate=self.adapter.mutate
        def uncertain(action,path,destination=None):
            result=mutate(action,path,destination)
            if action=='rename':raise LibraryError('Reply lost')
            return result
        self.adapter.mutate=uncertain
        with self.assertRaises(CreationError):self.create()
        self.assertTrue({PATH+'/games',PATH+'/metadata',PATH+'/artwork'}<=self.adapter.dirs)
        parse_manifest(self.adapter.files[PATH+'/manifest.json'],'device',PATH)
        self.assertFalse(any(c[0]=='rmdir' for c in self.adapter.calls))

    def test_cancellation_reports_partial_state_without_deleting_files(self):
        from c64u_browser.jobs import JobCancelled
        def check():
            if self.adapter.files:raise JobCancelled()
        with self.assertRaises(JobCancelled) as caught:
            create_empty_library(self.adapter,self.target,check,lambda:None)
        self.assertIn('Recovery required',caught.exception.result.message)
        self.assertNotIn(PATH+'/manifest.json',self.adapter.files)
        self.assertFalse(any(c[0]=='delete' for c in self.adapter.calls))


class CreationCoreTests(TestCase):
    def setUp(self):
        from tests.test_core import CoreTests
        self.fixture=CoreTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.adapter=MemoryAdapter()
        patcher=patch('c64u_browser.core.adapter_for',return_value=self.adapter)
        patcher.start();self.addCleanup(patcher.stop)
        session=self.core.device_session()
        self.selected=PickerSelection('c64u','/SD','SD','/SD',session.device_id,session.session_id,'library-root','dir')
    def target(self):return self.core.prepare_library_creation(self.selected)
    def test_prepare_no_mutation_and_success_registration_once(self):
        target=self.target();self.assertEqual([],self.adapter.calls)
        result=self.core.create_managed_library(target).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual(target.token,self.core.preferences.game_library_location['library_id'])
        self.assertFalse(self.core.game_library.path.exists())
        with self.assertRaises(Exception):self.core.create_managed_library(target)
    def test_missing_device_and_wrong_roots(self):
        for path in ('/Flash','/Temp','/SD/folder','/USB0/../SD'):
            with self.assertRaises(Exception):self.core.prepare_library_creation(replace(self.selected,path=path,storage_root=path))
        self.core.disconnect()
        with self.assertRaises(Exception):self.target()
        self.assertEqual([],self.adapter.calls)
    def test_disconnect_and_reconnect_after_confirmation_refused(self):
        for action in ('disconnect','reconnect'):
            with self.subTest(action=action):
                self.core.connect(self.fixture.profile)
                session=self.core.device_session()
                self.selected=replace(self.selected,session_id=session.session_id)
                target=self.target()
                self.core.disconnect() if action=='disconnect' else self.core.connect(self.fixture.profile)
                result=self.core.create_managed_library(target).wait(5)
                self.assertEqual('failed',result.state)
                self.assertEqual([],self.adapter.calls)
    def test_guard_prevents_reconnect_during_writes(self):
        from c64u_browser.core import CoreError
        def attempted(action,path):
            self.assertTrue(self.core._session_gate.locked())
            with self.assertRaises(CoreError):self.core.connect(self.fixture.profile)
        self.adapter.before=attempted
        result=self.core.create_managed_library(self.target()).wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertFalse(self.core._session_gate.locked())
    def test_session_loss_stops_and_never_cleans_replacement(self):
        def lost(action,path):
            if action=='write':self.core._session_id='lost'
        self.adapter.before=lost
        result=self.core.create_managed_library(self.target()).wait(5)
        self.assertEqual('failed',result.state)
        self.assertIsNone(self.core.preferences.game_library_location)
        self.assertFalse(any(c[0] in ('rmdir','delete') for c in self.adapter.calls))
    def test_tampered_target_and_cancel_refuse(self):
        target=self.target()
        with self.assertRaises(Exception):self.core.create_managed_library(replace(target,root='/USB0'))
        target=self.target();self.core.discard_library_creation(target.token)
        with self.assertRaises(Exception):self.core.create_managed_library(target)
        self.assertEqual([],self.adapter.calls)
    def test_registration_failure_retains_verified_library(self):
        with patch.object(self.core.preferences,'save',side_effect=OSError('disk full')):
            result=self.core.create_managed_library(self.target()).wait(5)
        self.assertEqual('failed',result.state)
        self.assertEqual('registration',result.result.phase)
        self.assertIsNone(self.core.preferences.game_library_location)
        parse_manifest(self.adapter.files[PATH+'/manifest.json'],self.selected.device_id,PATH)


class ManagedWireCreationTests(TestCase):
    def test_real_managed_adapter_creation_and_readonly_rediscovery(self):
        from c64u_ftp_server import FakeC64UFtp
        import test_ftp_reads as reads
        fixture=reads.ReadMigrationTests();self.addCleanup(fixture.doCleanups)
        with FakeC64UFtp(directories={b'/':b'',b'/USB1':b''},mutation_tree=True) as server:
            with patch('ftplib.FTP',side_effect=AssertionError('Legacy transport forbidden')):
                core,profile=fixture.connect(server)
                session=core.device_session()
                selection=PickerSelection('c64u','/USB1','USB1','/USB1',
                    session.device_id,session.session_id,'library-root','dir')
                target=core.prepare_library_creation(selection)
                result=core.create_managed_library(target).wait(10)
                self.assertEqual('succeeded',result.state,result.error)
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertIn(b'/USB1/ARGONAUT_LIBRARY/manifest.json',server.files)
                self.assertFalse(any(b'argonaut-creation-' in p or b'manifest.pending-' in p for p in server.files))
                mutations={b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'}
                self.assertTrue(all(arg.startswith(b'/USB1/ARGONAUT_LIBRARY')
                    for verb,arg in server.commands if verb in mutations))
                count=len(server.commands)
                loaded=core.load_managed_library().wait(10)
                self.assertEqual('succeeded',loaded.state,loaded.error)
                self.assertEqual('valid',loaded.result.status)
                self.assertEqual(target.token,loaded.result.libraries[0].identity.library_id)
                self.assertFalse(any(command[0] in
                    {b'STOR',b'MKD',b'DELE',b'RMD',b'RNFR',b'RNTO'} for command in server.commands[count:]))
