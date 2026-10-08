"""Deterministic credential and discovery contracts; never use native stores or LANs."""
import ctypes
import os
import threading
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_core
import gi
gi.require_version("Gtk", "4.0")
from c64u_browser.api import BrowserError, ConnectionFailure
from c64u_browser.credentials import Credentials, SessionCredentials
from c64u_browser.core import CoreError
from c64u_browser.discovery import Candidate, subnet_scan, validate_subnet, standard_scan
from c64u_browser.connection_dialog import ConnectionDialog
from c64u_browser.macos_credentials import MacOSCredentials
from c64u_browser.windows_credentials import WindowsCredentials


class CredentialContract(unittest.TestCase):
    setUp=test_core.CoreTests.setUp
    tearDown=test_core.CoreTests.tearDown

    def test_test_never_saves_profile_or_credential(self):
        self.core.test_profile(self.profile,'typed')
        self.assertEqual([],self.prefs.profiles)
        self.assertEqual({},self.credentials.values)
        self.assertEqual({},self.core._session_passwords)

    def test_connect_never_changes_store_regardless_of_remember(self):
        for remember in (False,True):
            self.credentials.values[self.profile.id]='old'
            self.core.connect(self.profile,entered_password='replacement',remember=remember,persist=True,initial_browse=False)
            self.assertEqual('old',self.credentials.values[self.profile.id])
            self.assertEqual('replacement',self.created[-1].password)
            self.assertEqual(self.profile.id,self.prefs.selected_id)
            self.assertEqual('replacement',self.core._session_passwords[self.profile.id])

    def test_save_remember_is_explicit_offline_update(self):
        self.core._client_factory=Mock(side_effect=AssertionError('Must not authenticate'))
        self.core.save_profile(self.profile,'unverified',True)
        self.core.save_profile(self.profile,'replacement',True)
        self.assertEqual('replacement',self.credentials.values[self.profile.id])
        self.core.save_profile(self.profile,'',True)
        self.assertEqual('replacement',self.credentials.values[self.profile.id])

    def test_unchecked_save_deletes_exact_store_keeps_session(self):
        self.credentials.values={'other':'other',self.profile.id:'old'}
        self.core.save_profile(self.profile,'typed',False)
        self.assertEqual({'other':'other'},self.credentials.values)
        self.core.test_profile(self.profile)
        self.assertEqual('typed',self.created[-1].password)
        self.core.save_profile(self.profile,'',False)
        self.assertEqual('typed',self.core._session_passwords[self.profile.id])

    def test_forget_keeps_connection_profile_and_clears_fallback(self):
        self.core.save_profile(self.profile,'typed',True)
        self.core.connect(self.profile,initial_browse=False)
        client=self.core._client;session=self.core.device_session()
        self.core.forget_credential(self.profile.id)
        self.assertIs(client,self.core._client)
        self.assertEqual(session,self.core.device_session())
        self.assertEqual(self.profile.id,self.prefs.selected_id)
        self.core.test_profile(self.profile)
        self.assertEqual('',self.created[-1].password)
        self.assertEqual({},self.credentials.values)

    def test_exists_is_boolean_exact_binding_without_get(self):
        self.prefs.profiles=[self.profile]
        self.credentials.exists=Mock(return_value=True)
        self.credentials.get=Mock(side_effect=AssertionError('Secret lookup'))
        self.assertIs(True,self.core.has_saved_credential(self.profile))
        for changes in ({'id':'other'},{'host':'192.0.2.21'},{'http_port':8080},{'ftp_port':2121}):
            self.assertIs(False,self.core.has_saved_credential(replace(self.profile,**changes)))
        self.credentials.exists.assert_called_once_with(self.profile.id)
        self.credentials.get.assert_not_called()

    def test_rename_and_endpoint_change_preserve_existing_identity_rules(self):
        self.core.save_profile(self.profile,'old',True)
        renamed=self.core.save_profile(replace(self.profile,name='Renamed'),'',True)
        self.assertEqual(self.profile.id,renamed.id)
        changed=self.core.save_profile(replace(renamed,host='192.0.2.21'),'new',False)
        self.assertNotEqual(renamed.id,changed.id)
        self.assertEqual({self.profile.id:'old'},self.credentials.values)

    def test_session_modes_never_call_persistence_backend(self):
        for mode in ('Development','Portable'):
            store=SessionCredentials(mode)
            for name in ('get','set','delete','exists'):
                setattr(store,name,Mock(side_effect=AssertionError('Native store path')))
            self.core._credentials=store
            self.assertEqual(mode,self.core.credential_mode)
            self.assertIs(False,self.core.has_saved_credential(self.profile))
            self.core.save_profile(self.profile,'typed',True)
            self.core.save_profile(self.profile,'typed',False)
            self.core.forget_credential(self.profile.id)

    def test_close_clears_sessions_even_on_teardown_failure(self):
        self.core.save_profile(self.profile,'session')
        self.core.disconnect()
        self.assertEqual('session',self.core._session_passwords[self.profile.id])
        with patch.object(self.core.ai,'close',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.core.close()
        self.assertEqual({},self.core._session_passwords)

    def test_profile_write_failure_does_not_change_store(self):
        self.credentials.values[self.profile.id]='old'
        with patch.object(self.prefs,'save',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.core.save_profile(self.profile,'new',True)
        self.assertEqual('old',self.credentials.values[self.profile.id])
        self.assertEqual([],self.prefs.profiles)

    def test_store_failure_reports_partial_profile_save(self):
        self.credentials.set=Mock(side_effect=BrowserError('Store locked'))
        with self.assertRaisesRegex(CoreError,'Profile saved, but'):self.core.save_profile(self.profile,'new',True)
        self.assertEqual(self.profile.id,self.prefs.selected_id)
        self.assertEqual({},self.credentials.values)

    def test_403_remains_visible(self):
        self.core._client_factory=Mock(return_value=Mock(test_connection=Mock(side_effect=ConnectionFailure('authentication','HTTP 403 Forbidden'))))
        with self.assertRaisesRegex(CoreError,'403'):self.core.test_profile(self.profile,'wrong')

    def test_core_discovery_checks_scope_and_forwards_progress(self):
        self.core._networks=lambda:['192.168.68.0/24']
        self.core._subnet_discovery=Mock(return_value=[])
        progress=Mock();found=Mock()
        self.core.discover(subnet='192.168.68.42/24',progress=progress,found=found)
        self.core._subnet_discovery.assert_called_once_with('192.168.68.0/24',progress=progress,found=found)
        self.core._subnet_discovery.reset_mock()
        with self.assertRaises(ValueError):self.core.discover(subnet='192.168.0.0/16')
        self.core._subnet_discovery.assert_not_called()

    def test_core_normal_discovery_uses_saved_addresses_not_subnet_scanner(self):
        self.prefs.profiles=[self.profile]
        self.core._standard_discovery=Mock(return_value=([],['standard']))
        self.core._subnet_discovery=Mock()
        self.core._networks=lambda:['192.168.68.0/24']
        self.core.discover()
        self.core._standard_discovery.assert_called_once_with(known_hosts=[(self.profile.host,self.profile.http_port)])
        self.core._subnet_discovery.assert_not_called()


class BackendExistence(unittest.TestCase):
    def test_linux_search_does_not_load_or_unlock_secret(self):
        store=object.__new__(Credentials);store.error=None;store.schema=object()
        store.secret=Mock();store.secret.SearchFlags.NONE=0
        store.secret.password_search_sync.return_value=[object()]
        self.assertIs(True,store.exists('fixture'))
        store.secret.password_search_sync.assert_called_once_with(store.schema,{'profile-id':'fixture'},0,None)
        store.secret.password_lookup_sync.assert_not_called()
        store.secret.password_search_sync.return_value=[]
        self.assertIs(False,store.exists('fixture'))

    def test_windows_success_frees_opaque_pointer_without_dereferencing(self):
        store=object.__new__(WindowsCredentials);store.dll=Mock()
        store.dll.CredReadW.return_value=True
        # The native fixture leaves a NULL pointer: touching contents would raise.
        with patch('ctypes.string_at',side_effect=AssertionError('Secret materialized')):
            self.assertIs(True,store.exists('fixture'))
        store.dll.CredFree.assert_called_once()
        self.assertEqual(('Argonaut/profile/fixture',1,0),store.dll.CredReadW.call_args.args[:3])

    def test_windows_missing_and_errors_are_distinct(self):
        store=object.__new__(WindowsCredentials);store.dll=Mock()
        store.dll.CredReadW.return_value=False
        with patch('ctypes.get_last_error',return_value=1168,create=True):
            self.assertIs(False,store.exists('fixture'))
        with patch('ctypes.get_last_error',return_value=5,create=True):
            with self.assertRaises(BrowserError):store.exists('fixture')
        store.dll.CredFree.assert_not_called()

    def test_macos_requests_no_password_outputs(self):
        store=object.__new__(MacOSCredentials);store.error=None
        native=Mock();native.SecKeychainFindGenericPassword.return_value=0
        with patch('ctypes.CDLL',return_value=native):
            self.assertIs(True,store.exists('fixture'))
            args=native.SecKeychainFindGenericPassword.call_args.args
            self.assertEqual((None,None,None),args[-3:])
            self.assertEqual((b'org.argonaut.c64u',7,b'fixture'),args[2:5])
            native.SecKeychainFindGenericPassword.return_value=-25300
            self.assertIs(False,store.exists('fixture'))
            native.SecKeychainFindGenericPassword.return_value=-1
            with self.assertRaises(BrowserError):store.exists('fixture')

    def test_factory_separates_development_and_portable_without_native_access(self):
        for dev,portable,mode in ((True,None,'Development'),(False,'/fixture','Portable')):
            with patch('c64u_browser.credentials.development.enabled',return_value=dev),patch('c64u_browser.credentials.portable_root',return_value=portable),patch.object(Credentials,'__init__',side_effect=AssertionError('Native init')):
                store=Credentials()
                self.assertEqual(mode,store.mode)
                self.assertFalse(store.exists('fixture'))


class DiscoveryContract(unittest.TestCase):
    def test_cidr_normalization_and_existing_bounds(self):
        self.assertEqual('192.168.68.0/24',str(validate_subnet('192.168.68.42/24',['192.168.68.0/22'])))
        self.assertEqual(1024,validate_subnet('192.168.68.0/22',['192.168.68.0/22']).num_addresses)
        for value in ('','192.168.68.','192.168.68.1','192.168.68.0/','192.168.68.0/33','192.168.68.0/255.255.255.0','0.0.0.0/0','192.168.64.0/21','::1/128','8.8.8.0/24','10.0.0.0/24'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_subnet(value,['192.168.68.0/22'])

    def test_invalid_scan_never_opens_a_socket(self):
        with patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/24']),patch('c64u_browser.discovery.socket.create_connection') as connect:
            with self.assertRaises(ValueError):subnet_scan('192.168.68.0/16')
        connect.assert_not_called()

    def test_progress_counts_all_completed_probes_including_failures(self):
        events=[];found=[];main=threading.get_ident();threads=set()
        def connect(address,timeout):
            threads.add(threading.get_ident())
            if address[0].endswith('.1'):raise OSError('fixture')
            return Mock(__enter__=Mock(),__exit__=Mock())
        with patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/24']),patch('c64u_browser.discovery.socket.create_connection',side_effect=connect),patch('c64u_browser.discovery.verify',side_effect=lambda c:c):
            result=subnet_scan('192.168.68.0/30',progress=lambda n,t:events.append((n,t)),found=found.append)
        self.assertEqual([(0,2),(1,2),(2,2)],events)
        self.assertEqual(result,found);self.assertEqual(1,len(found))
        self.assertNotIn(main,threads)

    def test_incremental_result_precedes_last_probe_completion(self):
        release=threading.Event();seen=threading.Event()
        def verify(c):
            if c.host.endswith('.2'):
                if not release.wait(2):raise AssertionError('Incremental callback missing')
            return c
        def found(c):
            if c.host.endswith('.1'):seen.set();release.set()
        with patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/24']),patch('c64u_browser.discovery.socket.create_connection',return_value=Mock(__enter__=Mock(),__exit__=Mock())),patch('c64u_browser.discovery.verify',side_effect=verify):
            result=subnet_scan('192.168.68.0/30',found=found)
        self.assertTrue(seen.is_set());self.assertEqual(2,len(result))

    def test_24_31_and_32_progress_denominators_match_host_policy(self):
        for cidr,total in (('192.168.68.0/24',254),('192.168.68.0/31',2),('192.168.68.1/32',1)):
            events=[]
            with patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/24']),patch('c64u_browser.discovery.socket.create_connection',side_effect=OSError('fixture')):
                subnet_scan(cidr,progress=lambda n,t:events.append((n,t)))
            self.assertEqual((total,total),events[-1]);self.assertEqual(total+1,len(events))


class Widget:
    def __init__(self,text='',**kwargs):
        self.text=text;self.active=False;self.sensitive=True;self.visible=True;self.children=[];self.placeholder='';self.fraction=0
    def get_text(self):return self.text
    def set_text(self,text):self.text=text
    def set_property(self,name,text):
        assert name == 'placeholder-text'
        self.placeholder=text
    def get_active(self):return self.active
    def set_active(self,value):self.active=value
    def set_inconsistent(self,value):self.inconsistent=value
    def set_sensitive(self,value):self.sensitive=value
    def set_visible(self,value):self.visible=value
    def set_fraction(self,value):self.fraction=value
    def append(self,value):self.children.append(value)
    def set_child(self,value):self.child=value
    def get_first_child(self):return next(iter(self.children),None)
    def remove(self,value):self.children.remove(value)


class DialogContract(unittest.TestCase):
    def setUp(self):
        self.d=ConnectionDialog.__new__(ConnectionDialog)
        d=self.d
        d.app=SimpleNamespace(busy=False,core=Mock(credentials_session_only=False),pool=Mock())
        d._closed=False;d._credential_generation=0;d._credential_state='ABSENT';d._credential_pending=False
        d._scanning=False;d._scan_generation=0;d._candidate_rows={};d._networks=('192.168.68.0/24',)
        d.current_id='fixture'
        for name in ('password','remember','retry_credential_button','forget_button','credential_status','subnet','subnet_validation','scan_subnet_button','scan_progress','devices','status','controls'):
            setattr(d,name,Widget())
        d.fields={'host':Widget('192.168.68.1')}
        d.profile=Mock(return_value=SimpleNamespace(id='fixture'))
        d._saved_fields=((),False,'',False)
        self.timers=[]
        patcher=patch('c64u_browser.connection_dialog.GLib.timeout_add',side_effect=lambda _,fn:self.timers.append(fn));patcher.start();self.addCleanup(patcher.stop)
        patcher=patch('c64u_browser.connection_dialog.GLib.idle_add',side_effect=lambda fn:fn());patcher.start();self.addCleanup(patcher.stop)

    def test_saved_placeholder_never_becomes_authentication_input(self):
        d=self.d;d._credential_state='PRESENT';d.paint_credential_state()
        self.assertEqual('••••••••',d.password.placeholder);self.assertEqual('',d.password.get_text())
        d.password.set_text('typed');d.paint_credential_state()
        self.assertNotEqual('••••••••',d.password.placeholder)
        d.password.set_text('');d.paint_credential_state()
        self.assertEqual('••••••••',d.password.placeholder)
        submitted=[];d.submit=lambda task,done:submitted.append(task)
        d.app.core.test_profile.return_value=SimpleNamespace(device_info=test_core.INFO)
        d.test();submitted[0]()
        d.app.core.test_profile.assert_called_once_with(d.profile.return_value,'')

    def test_async_saved_state_reconstruction_and_stale_result_discard(self):
        d=self.d;callbacks=[];d._background=lambda task,done:callbacks.append((task,done))
        d.refresh_credential_state();self.timers[-1]()
        d.refresh_credential_state();self.timers[-1]()
        callbacks[0][1](True)
        self.assertNotEqual('PRESENT',d._credential_state)
        callbacks[1][1](True)
        self.assertTrue(d.remember.active);self.assertEqual('••••••••',d.password.placeholder)
        self.assertEqual('',d.password.get_text())

    def test_forget_immediately_clears_typed_saved_and_remember(self):
        d=self.d;d._credential_state='PRESENT';d.password.text='typed';d.remember.active=True
        d.app.run=lambda task,done:done(task())
        d.forget()
        d.app.core.forget_credential.assert_called_once_with('fixture')
        self.assertNotEqual('PRESENT',d._credential_state);self.assertFalse(d.remember.active)
        self.assertEqual('',d.password.text);self.assertNotEqual('••••••••',d.password.placeholder)

    def test_session_mode_text_is_distinct(self):
        d=self.d;d.app.core.credentials_session_only=True
        for mode in ('Development','Portable'):
            d.app.core.credential_mode=mode;d.paint_credential_state()
            self.assertEqual(mode+' mode — passwords are session-only.',d.credential_status.text)

    def test_validation_controls_scan_and_normalizes_without_touching_credentials(self):
        d=self.d;d.password.text='typed';d.remember.active=True
        for value in ('','192.168.68.','192.168.68.0/0','8.8.8.0/24'):
            d.subnet.text=value;d.validate_subnet_field()
            self.assertFalse(d.scan_subnet_button.sensitive)
            d.scan(True)
        d.app.core.discover.assert_not_called()
        d.subnet.text='192.168.68.42/24'
        self.assertEqual('192.168.68.0/24',d.validate_subnet_field())
        self.assertTrue(d.scan_subnet_button.sensitive)
        self.assertEqual('typed',d.password.text);self.assertTrue(d.remember.active)

    def test_incremental_dedup_and_connection_count_progress(self):
        d=self.d;d.subnet.text='192.168.68.42/24';observed=[]
        c1=Candidate('192.168.68.1',info={'info':{'unique_id':'same'}})
        c2=Candidate('192.168.68.2',info={'info':{'unique_id':'same'}})
        def discover(**kwargs):
            self.assertEqual('192.168.68.0/24',kwargs['subnet'])
            kwargs['found'](c1);kwargs['found'](c1);kwargs['found'](c2)
            kwargs['progress'](127,254)
            observed.append((len(d.devices.children),d.scan_progress.fraction))
            return (c1,c2),(),()
        d.app.core.discover.side_effect=discover;d.app.run=lambda task,done:done(task())
        with patch('c64u_browser.connection_dialog.Gtk.ListBoxRow',Widget),patch('c64u_browser.connection_dialog.Gtk.Label',Widget):d.scan(True)
        self.assertEqual([(2,.5)],observed)
        self.assertEqual(1,d.scan_progress.fraction)
        self.assertIn('100%',d.scan_progress.text)
        self.assertIn('2 network connections found',d.status.text)
        self.assertEqual(2,len(d.devices.children))

    def test_discover_keeps_normal_mechanism_separate_from_subnet(self):
        d=self.d;d.subnet.text='invalid';d.app.core.discover.return_value=((),('normal',),d._networks)
        d.app.run=lambda task,done:done(task())
        d.scan(False)
        d.app.core.discover.assert_called_once_with(subnet='')
        self.assertIn('0 network connections found',d.status.text)

    def test_existing_network_prepopulation_never_overwrites_user_text(self):
        d=self.d;d.subnet.text='192.168.68.42/24';d.networks_loaded(['192.168.68.0/24'])
        self.assertEqual('192.168.68.42/24',d.subnet.text)
        d.subnet.text='';d.networks_loaded(['192.168.68.0/24'])
        self.assertEqual('192.168.68.0/24',d.subnet.text)

    def test_background_dispatches_worker_and_posts_ui_completion(self):
        d=self.d;f=Future();d.app.pool.submit.return_value=f;done=Mock();queue=[]
        task=Mock()
        with patch('c64u_browser.connection_dialog.GLib.idle_add',side_effect=lambda callback:queue.append(callback)):
            d._background(task,done);task.assert_not_called();f.set_result(True)
            done.assert_not_called();queue[0]()
        d.app.pool.submit.assert_called_once_with(task);done.assert_called_once_with(True)

    def test_close_request_keeps_callbacks_alive_until_window_actually_closes(self):
        d=self.d
        self.assertFalse(d.close_requested())
        self.assertFalse(d._closed)  # Parent Preferences can still choose Keep editing.
        d.app.busy=True;self.assertTrue(d.close_requested())
        self.assertFalse(d._closed)
        d.window_closed();self.assertTrue(d._closed)

    def test_constructor_labels_and_session_controls(self):
        for mode in ('Installed','Development','Portable'):
            app=SimpleNamespace(core=Mock(credentials_session_only=mode!='Installed'),busy=False)
            app.button=Mock(side_effect=lambda *args:Mock())
            with patch('c64u_browser.connection_dialog.Gtk') as gtk,patch.object(ConnectionDialog,'reload'),patch.object(ConnectionDialog,'_background'):
                gtk.CheckButton.side_effect=lambda **kwargs:Mock()
                d=ConnectionDialog(app,window=Mock())
                labels=[c.args[1] for c in app.button.call_args_list]
                self.assertIn('Discover',labels);self.assertIn('Scan Subnet',labels)
                self.assertNotIn('Scan again',labels);self.assertNotIn('Scan subnet',labels)
                self.assertIn('Save Profile',labels);self.assertIn('Forget Password',labels)
                self.assertIn('Remember password',[c.kwargs['label'] for c in gtk.CheckButton.call_args_list])
                if mode != 'Installed':
                    d.remember.set_visible.assert_called_once_with(False)
                    d.remember.set_sensitive.assert_called_once_with(False)
                    d.forget_button.set_visible.assert_called_once_with(False)
                    d.forget_button.set_sensitive.assert_called_once_with(False)

    def test_partial_save_failure_keeps_typed_edit_and_saved_id_for_retry(self):
        d=self.d;d.password.text='typed';d.remember.active=True
        d.app.update_connection_header=Mock();d.app.run=lambda task,done:done(task())
        error=CoreError('credentials','Profile saved, but store failed');error.saved_profile_id='saved-id'
        def fail():raise error
        d.submit(fail,Mock())
        self.assertEqual('saved-id',d.current_id)
        self.assertEqual('typed',d.password.text);self.assertTrue(d.remember.active)
        self.assertIn('Profile saved, but',d.status.text)

    def test_ui_connect_ignores_remember_and_reports_connection(self):
        d=self.d;d.password.text='typed';d.remember.active=True
        d.profile.return_value=SimpleNamespace(id='fixture',device_id='bound',device_mac='')
        d.app.preferences=SimpleNamespace(app_options={'remember_folders':False})
        d.app.core.test_profile.return_value=SimpleNamespace(device_info={},reported_device_id='bound')
        d.app.core.connect.return_value=SimpleNamespace(profile=d.profile.return_value)
        d.window=SimpleNamespace(pages=Mock());d.reload=Mock();d.app.activate_connection=Mock()
        d.app.run=lambda task,done:done(task())
        d.connect()
        self.assertIs(False,d.app.core.connect.call_args.kwargs['remember'])
        self.assertEqual('typed',d.app.core.connect.call_args.kwargs['entered_password'])
        self.assertTrue(d.status.text.startswith('Connected'))
        self.assertIn('password storage unchanged',d.status.text)

    def check_failed_lookup_retry(self, exists):
        fixture=test_core.CoreTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        d=self.d;d.app.core=fixture.core
        profile=replace(fixture.profile,name='Deliberate edited name')
        fixture.prefs.profiles=[fixture.profile]
        fixture.credentials.values[profile.id]='existing-fixture-secret'
        fixture.credentials.exists=Mock(side_effect=[BrowserError('private backend details'),exists])
        fixture.credentials.set=Mock(wraps=fixture.credentials.set)
        fixture.credentials.delete=Mock(wraps=fixture.credentials.delete)
        fixture.prefs.save=Mock(wraps=fixture.prefs.save)
        d.profile=Mock(return_value=profile);d.current_id=profile.id
        d.fields['name']=Widget(profile.name);d.password.text='typed-fixture-replacement'
        d.app.run=lambda task,done:done(task())
        d.app.update_connection_header=Mock();d.reload=Mock()
        d._background=lambda task,done:done(task())
        # Match the real asynchronous helper's exception-as-result boundary.
        def background(task,done):
            try:value=task()
            except Exception as exc:value=exc
            done(value)
        d._background=background
        d.refresh_credential_state();self.timers[-1]()
        self.assertEqual('UNKNOWN',d._credential_state)
        self.assertFalse(d.remember.sensitive);self.assertTrue(d.remember.inconsistent)
        self.assertTrue(d.retry_credential_button.visible)
        self.assertNotIn('private backend details',d.credential_status.text)
        after=Mock()
        for checked in (False,True):
            d.remember.active=checked
            d.save(after)
        fixture.prefs.save.assert_not_called()
        fixture.credentials.set.assert_not_called();fixture.credentials.delete.assert_not_called()
        self.assertEqual([fixture.profile],fixture.prefs.profiles)
        self.assertEqual('existing-fixture-secret',fixture.credentials.values[profile.id])
        self.assertEqual('typed-fixture-replacement',d.password.text)
        self.assertEqual(profile.name,d.fields['name'].text)
        after.assert_not_called()
        # Deliberate retry: no automatic replay of either blocked save.
        d.refresh_credential_state();self.timers[-1]()
        self.assertEqual('PRESENT' if exists else 'ABSENT',d._credential_state)
        self.assertEqual(exists,d.remember.active)
        self.assertFalse(d.remember.inconsistent);self.assertTrue(d.remember.sensitive)
        self.assertFalse(d.retry_credential_button.visible)
        fixture.prefs.save.assert_not_called()
        fixture.credentials.set.assert_not_called();fixture.credentials.delete.assert_not_called()
        self.assertEqual('typed-fixture-replacement',d.password.text)
        d.password.text='';d.paint_credential_state()
        self.assertEqual('••••••••' if exists else 'Network password',d.password.placeholder)
        self.assertEqual('',d.password.get_text())
        d.password.text='typed-fixture-replacement'
        d.save(after)
        fixture.prefs.save.assert_called_once();after.assert_called_once()
        if exists:
            fixture.credentials.set.assert_called_once_with(profile.id,'typed-fixture-replacement')
            fixture.credentials.delete.assert_not_called()
        else:
            fixture.credentials.set.assert_not_called()
            fixture.credentials.delete.assert_called_once_with(profile.id)

    def test_unknown_blocks_all_persistence_then_deliberate_retry_present(self):
        self.check_failed_lookup_retry(True)

    def test_unknown_blocks_all_persistence_then_deliberate_retry_absent(self):
        self.check_failed_lookup_retry(False)

    def test_save_waits_for_initial_credential_state(self):
        d=self.d;d._credential_pending=True;d.submit=Mock()
        d.save();d.submit.assert_not_called()
        self.assertIn('Checking',d.status.text)


if __name__=='__main__':unittest.main()
