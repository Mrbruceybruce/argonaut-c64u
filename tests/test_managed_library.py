"""Read-only managed-library contracts and fake-Core integration."""
import json
from dataclasses import replace
from types import SimpleNamespace as E
from unittest import TestCase
from unittest.mock import Mock, patch
from c64u_browser.managed_library import (
    APPLICATION, MAX_MANIFEST_BYTES, LibraryError, LibraryIdentity,
    ManagedLibraryReader, location, parse_manifest)
from c64u_browser.scheduler import DeviceSession

ID='11111111-1111-4111-8111-111111111111'
GAME='22222222-2222-4222-8222-222222222222'
PATH='/SD/ARGONAUT_LIBRARY'


def manifest(**changes):
    doc=dict(schema_version=1,library_id=ID,created_at='2026-10-10T10:00:00Z',
             application=APPLICATION,revision=0,games=[])
    doc.update(changes);return json.dumps(doc).encode()


def game(**changes):
    value=dict(id=GAME,path='games/a.crt',format='CRT',size=80,sha256='a'*64,title='A game')
    value.update(changes);return value


class ManifestTests(TestCase):
    def test_valid_empty_and_populated_manifest(self):
        self.assertEqual((),parse_manifest(manifest(),'device',PATH).games)
        result=parse_manifest(manifest(games=[game()]),'device',PATH)
        self.assertEqual(LibraryIdentity(ID,'device','/SD',PATH),result.identity)
        self.assertEqual('A game',result.games[0].title)

    def test_invalid_json_schema_identity_and_types(self):
        cases=[b'',b'{',b'[]',b'\xff',manifest(schema_version=2),manifest(schema_version=True),
            manifest(library_id='bad'),manifest(library_id='00000000-0000-0000-0000-000000000000'),
            manifest(created_at='2026-01-01'),manifest(application='other'),manifest(revision=-1),
            manifest(revision=True),manifest(games=None),b'{' + b' '*MAX_MANIFEST_BYTES,
            manifest().replace(b'"revision": 0',b'"revision": 0,"revision": 1')]
        for data in cases:
            with self.subTest(data=data[:90]),self.assertRaises(LibraryError):parse_manifest(data,'device',PATH)

    def test_traversal_paths_formats_and_duplicate_entries(self):
        for path in ('../a.crt','/games/a.crt','games/../a.crt','games//a.crt','games/./a.crt',
                     'games/a\\b.crt','games/a\n.crt','other/a.crt'):
            with self.subTest(path=path),self.assertRaises(LibraryError):
                parse_manifest(manifest(games=[game(path=path)]),'device',PATH)
        for entries in ([game(),game(path='games/b.crt')],
                        [game(),game(id='33333333-3333-4333-8333-333333333333',path='games/A.crt')],
                        [game(format='SID')],[game(metadata_path='../metadata/a.json')],
                        [game(artwork_path='/artwork/a.png')],[game(size=True)],[game(sha256='bad')]):
            with self.subTest(entries=entries),self.assertRaises(LibraryError):
                parse_manifest(manifest(games=entries),'device',PATH)

    def test_location_root_and_boundary_validation(self):
        valid=dict(device_id='device',root='/SD',path=PATH,library_id=ID)
        self.assertEqual(valid,location(valid))
        self.assertIsNone(location(None))
        for changes in (dict(root='/USB0'),dict(path='/SD/../ARGONAUT_LIBRARY'),
                        dict(path='/Flash/ARGONAUT_LIBRARY',root='/Flash'),
                        dict(path='/Temp/ARGONAUT_LIBRARY',root='/Temp'),
                        dict(path='/SD/not-library'),dict(device_id=''),dict(library_id='bad')):
            with self.subTest(changes=changes),self.assertRaises(LibraryError):location({**valid,**changes})


class DiscoveryTests(TestCase):
    def setUp(self):
        self.tree={'/':[E(name='SD',kind='dir'),E(name='USB0',kind='dir'),
                       E(name='Flash',kind='dir'),E(name='Temp',kind='dir')],'/SD':[], '/USB0':[]}
        self.data={};self.calls=[]
        self.session=DeviceSession('device','one')
        def listing(path):
            self.calls.append(path)
            if path not in self.tree:raise LibraryError('Unavailable folder.')
            return path,self.tree[path]
        self.read=Mock(side_effect=lambda path,limit:self.data[path])
        self.check=Mock()
        self.reader=ManagedLibraryReader(listing,self.read,self.session,self.check)

    def library(self,root='/SD',data=None):
        path=root+'/ARGONAUT_LIBRARY'
        self.tree[root]=[E(name='ARGONAUT_LIBRARY',kind='dir'),E(name='other',kind='dir')]
        self.tree[path]=[E(name='manifest.json',kind='file')]+[E(name=n,kind='dir') for n in ('games','metadata','artwork')]
        self.data[path+'/manifest.json']=manifest() if data is None else data
        return dict(device_id='device',root=root,path=path,library_id=ID)

    def test_zero_nonrecursive_and_approved_roots_only(self):
        result=self.reader.discover()
        self.assertEqual('none',result.status)
        self.assertEqual(['/','/SD','/USB0'],self.calls);self.read.assert_not_called()

    def test_one_loads_only_manifest_and_never_game_bytes(self):
        self.library(data=manifest(games=[game()]))
        result=self.reader.discover();self.assertEqual('valid',result.status)
        self.assertEqual(1,len(result.libraries[0].games))
        self.read.assert_called_once_with(PATH+'/manifest.json',MAX_MANIFEST_BYTES)
        self.assertNotIn(PATH+'/games',self.calls)

    def test_multiple_and_copied_uuid_require_selection(self):
        self.library();self.library('/USB0')
        result=self.reader.discover();self.assertEqual('multiple',result.status)
        self.assertIn('Copied',result.message);self.assertEqual(2,len(result.libraries))
        self.data['/USB0/ARGONAUT_LIBRARY/manifest.json']=manifest(library_id=GAME)
        self.assertEqual('multiple',self.reader.discover().status)

    def test_configured_priority_without_discovery(self):
        configured=self.library();self.library('/USB0')
        self.assertEqual('valid',self.reader.discover(configured).status)
        self.assertEqual([PATH],self.calls)

    def test_configured_missing_or_identity_changed_no_fallback(self):
        configured=self.library();self.library('/USB0');del self.tree[PATH]
        self.assertEqual('unavailable',self.reader.discover(configured).status)
        self.assertEqual([PATH],self.calls)
        self.library(data=manifest(library_id=GAME));self.calls.clear()
        self.assertEqual('unavailable',self.reader.discover(configured).status)
        self.assertEqual([PATH],self.calls)

    def test_device_mismatch_has_no_reads(self):
        configured=self.library();configured['device_id']='other'
        self.assertEqual('unavailable',self.reader.discover(configured).status)
        self.assertEqual([],self.calls)

    def test_missing_corrupt_manifest_never_counts_as_empty_library(self):
        self.library();self.tree[PATH]=[]
        self.assertEqual('unavailable',self.reader.discover().status)
        self.library(data=b'broken')
        self.assertEqual('unavailable',self.reader.discover().status)

    def test_manifest_alone_or_wrong_directory_type_is_incomplete(self):
        self.library()
        self.tree[PATH]=[E(name='manifest.json',kind='file')]
        self.assertEqual('unavailable',self.reader.discover().status)
        self.library()
        self.tree[PATH][-1]=E(name='artwork',kind='file')
        self.assertEqual('unavailable',self.reader.discover().status)

    def test_visible_legacy_marker_and_pending_manifest_refuse_loading(self):
        for name in ('.argonaut-creation-'+ID,'manifest.pending-'+ID):
            self.library();self.tree[PATH].append(E(name=name,kind='file'))
            result=self.reader.discover()
            self.assertEqual('unavailable',result.status)
            self.assertIn('incomplete',result.message)

    def test_inaccessible_root_and_redirect_fail_closed(self):
        self.library();del self.tree['/USB0']
        with self.assertRaises(LibraryError):self.reader.discover()
        self.reader.listing=lambda path:('/USB0',[])
        with self.assertRaises(LibraryError):self.reader.discover()

    def test_cancellation_propagates(self):
        from c64u_browser.jobs import JobCancelled
        self.check.side_effect=JobCancelled()
        with self.assertRaises(JobCancelled):self.reader.discover()
        self.assertEqual([],self.calls)


class ManagedCoreTests(TestCase):
    def setUp(self):
        from tests.test_core import CoreTests
        self.fixture=CoreTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
        self.core=self.fixture.core;self.core.connect(self.fixture.profile)
        self.client=self.fixture.created[-1]
        self.client.list_directory=Mock(side_effect=lambda path:(path,
            [E(name='SD',kind='dir')] if path=='/' else
            [E(name='ARGONAUT_LIBRARY',kind='dir')] if path=='/SD' else
            [E(name='manifest.json',kind='file')]+[E(name=n,kind='dir') for n in ('games','metadata','artwork')]))
        self.patch=patch('c64u_browser.native_files.read_remote_game',return_value=manifest())
        self.read=self.patch.start();self.addCleanup(self.patch.stop)

    def test_core_readonly_loading_and_preference_roundtrip(self):
        from c64u_browser.profiles import Preferences
        self.core.configure_game_library(PATH)
        saved=Preferences(self.core.preferences.path).load()
        self.assertEqual(self.core.device_session().device_id,saved.game_library_location['device_id'])
        self.assertEqual(PATH,saved.game_library_location['path'])
        result=self.core.load_managed_library().wait(5)
        self.assertEqual('succeeded',result.state,result.error)
        self.assertEqual('valid',result.result.status)
        self.client.list_directory.assert_called_once_with(PATH)
        self.assertFalse(self.core.game_library.path.exists())

    def test_core_device_mismatch_no_io_and_clear(self):
        self.core.configure_game_library(PATH)
        self.core.preferences.game_library_location['device_id']='other'
        with self.assertRaises(Exception):self.core.load_managed_library()
        self.client.list_directory.assert_not_called();self.read.assert_not_called()
        self.core.configure_game_library('');self.assertIsNone(self.core.preferences.game_library_location)

    def test_reconnect_during_read_rejects_result(self):
        def read(*args,**kwargs):
            self.core.connect(self.fixture.profile)
            return manifest()
        self.read.side_effect=read
        result=self.core.load_managed_library().wait(5)
        self.assertEqual('failed',result.state);self.assertEqual('session',result.error.code)

    def test_selection_binds_copied_library_location_and_session(self):
        session=self.core.device_session()
        identity=LibraryIdentity(ID,session.device_id,'/SD',PATH)
        self.core.configure_game_library(PATH,identity=identity,expected_session=session)
        self.assertEqual(identity.preference(),self.core.preferences.game_library_location)
        self.core.connect(self.fixture.profile)
        with self.assertRaises(Exception):self.core.configure_game_library(PATH,identity=identity,expected_session=session)
        self.assertEqual(identity.preference(),self.core.preferences.game_library_location)

    def test_general_save_preserves_location_and_old_preferences_default(self):
        from c64u_browser.profiles import Preferences
        self.core.preferences.save()
        self.assertIsNone(Preferences(self.core.preferences.path).load().game_library_location)
        self.core.configure_game_library(PATH)
        self.core.preferences.app_options['width']=1300;self.core.preferences.save()
        self.assertEqual(PATH,Preferences(self.core.preferences.path).load().game_library_location['path'])
