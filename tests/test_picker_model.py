"""Offline contracts: picker references grant no operation authority."""
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from c64u_browser.picker_model import (
    PickerModel, PickerMode, PickerError, PickerEntry as E, SID, DRIVES, GAMES)


class PickerContracts(unittest.TestCase):
    def setUp(self):
        self.session = NS(device_id='founders', session_id='connection-1')
        self.model = PickerModel()

    def load(self, path='/USB0', entries=None, scope='c64u'):
        token = self.model.begin(scope, path, self.session)
        self.assertTrue(self.model.complete(token, token.path,
            entries if entries is not None else [E('music.sid', 'file'), E('folder', 'dir')], self.session))
        return token

    def test_remote_immutable_reference(self):
        self.load()
        result, = self.model.choose(['music.sid'], self.session)
        self.assertEqual(('c64u', '/USB0/music.sid', 'music.sid', '/USB0',
                          'founders', 'connection-1', 'sid', 'file'), tuple(vars(result).values()))
        with self.assertRaises(FrozenInstanceError):result.path = 'other'
        self.assertNotIn('client', vars(result))
        self.assertNotIn('password', vars(result))
        result.validate_session(self.session)
        with self.assertRaises(PickerError):result.validate_session(NS(device_id='founders', session_id='new'))

    def test_local_result_and_listing(self):
        with TemporaryDirectory() as tmp:
            (Path(tmp) / 'music.sid').write_bytes(b'fixture')
            (Path(tmp) / 'folder').mkdir()
            path, entries = self.model.local_listing(tmp)
            self.load(path, entries, 'core-host')
            result, = self.model.choose(['music.sid'], self.session)
            self.assertEqual('core-host', result.scope)
            self.assertEqual(str(Path(tmp) / 'music.sid'), result.path)
            self.assertEqual(('', '', ''), (result.device_id, result.session_id, result.storage_root))

    def test_exact_filters_and_case(self):
        for profile, accepted, rejected in [(SID, 'MUSIC.SID', 'music.prg'),
                (DRIVES, 'disk.G71', 'disk.crt'), (GAMES, 'game.CRT', 'game.d81')]:
            self.model = PickerModel(filter=profile)
            self.load(entries=[E(accepted, 'file'), E(rejected, 'file'), E('folder.xyz', 'dir')])
            self.assertEqual({'folder.xyz', accepted}, {e.name for e in self.model.entries})
            with self.assertRaises(PickerError):self.model.choose([rejected], self.session)

    def test_multiple_count_limit(self):
        self.model = PickerModel(mode=PickerMode.OPEN_FILES, limit=2)
        self.load(entries=[E(n + '.sid', 'file') for n in 'abc'])
        self.assertEqual(2, len(self.model.choose(['a.sid', 'b.sid'], self.session)))
        for names in ([], ['a.sid'] * 2, ['a.sid', 'b.sid', 'c.sid']):
            with self.assertRaises(PickerError):self.model.choose(names, self.session)

    def test_folder_mode_current_or_child(self):
        self.model = PickerModel(mode=PickerMode.OPEN_FOLDER)
        self.load()
        self.assertEqual(['folder'], [e.name for e in self.model.entries])
        self.assertEqual('/USB0', self.model.choose([], self.session)[0].path)
        self.assertEqual('/USB0/folder', self.model.choose(['folder'], self.session)[0].path)

    def test_parent_and_navigation_clear(self):
        self.load('/USB0/folder')
        self.assertEqual('/USB0', self.model.parent())
        self.assertEqual('/USB0/folder/folder', self.model.child('folder'))
        self.model.begin('c64u', '/SD', self.session)
        with self.assertRaises(PickerError):self.model.choose(['music.sid'], self.session)

    def test_root_discovery_exact_and_parent_not_an_entry(self):
        self.load('/', [E(n, 'dir') for n in ['USB0', 'SD', 'Flash', 'Temp', 'USBfake', '..', 'USB0/../SD']])
        self.assertEqual({'USB0', 'SD', 'Flash', 'Temp'}, {e.name for e in self.model.entries})
        self.assertEqual('/', self.model.parent())

    def test_flash_temp_browse_only(self):
        for root in ('/Flash', '/Temp'):
            self.load(root)
            self.assertEqual(2, len(self.model.entries))
            with self.assertRaises(PickerError):self.model.choose(['music.sid'], self.session)

    def test_traversal_and_alias_refused(self):
        for path in ('USB0', '/USB0/../SD', '/USB0//dir', '/USB0/./dir', '/usb0', '/USBfake', '/SD\\x'):
            with self.subTest(path=path), self.assertRaises(PickerError):
                self.model.begin('c64u', path, self.session)
        self.load(entries=[E(n, 'file') for n in ('../x.sid', '..', 'x/y.sid', 'x\\y.sid', 'bad\ns.sid')])
        self.assertFalse(self.model.entries)
        with self.assertRaises(PickerError):self.model.child('..')

    def test_unavailable_not_false_empty(self):
        token = self.model.begin('c64u', '/SD', self.session)
        with self.assertRaises(PickerError):self.model.complete(token, '/', [], self.session)
        self.assertIsNone(self.model.loaded)

    def test_empty_folder_is_success(self):
        self.load(entries=[])
        self.assertIsNotNone(self.model.loaded)
        self.assertFalse(self.model.entries)

    def test_disconnect_reconnect_and_replacement(self):
        for device, session in [('', ''), ('founders', 'connection-2'), ('other', 'connection-1')]:
            self.load()
            with self.assertRaises(PickerError):
                self.model.choose(['music.sid'], NS(device_id=device, session_id=session))
            self.assertIsNone(self.model.loaded)

    def test_delayed_result_cannot_replace_new_root(self):
        old = self.model.begin('c64u', '/USB0', self.session)
        new = self.load('/SD')
        self.assertFalse(self.model.complete(old, '/USB0', [], self.session))
        self.assertEqual(new, self.model.loaded)

    def test_reconnect_rejects_delayed_listing(self):
        old = self.model.begin('c64u', '/USB0', self.session)
        self.session.session_id = 'new'
        self.assertFalse(self.model.complete(old, '/USB0', [], self.session))

    def test_scope_restriction(self):
        self.model = PickerModel(scopes=('core-host',))
        with self.assertRaises(PickerError):self.load()

    def test_no_mutation_interface(self):
        for name in ('upload', 'download', 'rename', 'delete', 'mount', 'launch', 'overwrite'):
            self.assertFalse(hasattr(self.model, name))
