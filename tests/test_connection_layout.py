"""Offline widget-tree/controller qualification; no desktop or native store required."""
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_core
import gi
gi.require_version("Gtk", "4.0")
from c64u_browser.api import BrowserError
from c64u_browser.connection_dialog import ConnectionDialog
from c64u_browser.credentials import SessionCredentials
from c64u_browser.discovery import Candidate


class Node:
    """Signal-capable GTK stand-in: setters emit the changes the controller uses."""
    def __init__(self, kind='Box', **props):
        self.kind=kind;self.props=props;self.children=[];self.signals={};self.items={}
        self.text=props.get('text',props.get('label',''));self.active=False
        self.visible=True;self.sensitive=True;self.active_id=None;self.fraction=0
        self.placeholder=props.get('placeholder_text','');self.inconsistent=False
    def connect(self, signal, callback):self.signals.setdefault(signal,[]).append(callback)
    def emit(self, signal, *args):
        for callback in self.signals.get(signal,[]):callback(self,*args)
    def append(self, *args):
        if len(args)==2:self.items[args[0]]=args[1]
        else:self.children.append(args[0])
    def set_child(self, child):self.children=[child]
    def get_first_child(self):return next(iter(self.children),None)
    def remove(self, child):self.children.remove(child)
    def remove_all(self):self.items.clear();self.set_active_id(None)
    def set_active_id(self, value):
        self.active_id=value if value in self.items else None;self.emit('changed')
    def get_active_id(self):return self.active_id
    def set_active(self, value):
        if self.kind=='ComboBoxText':self.set_active_id(None)
        else:self.active=value
    def get_active(self):return self.active
    def set_text(self, text):
        changed=self.text!=text;self.text=text
        if changed:self.emit('changed')
    def get_text(self):return self.text
    def set_property(self, key, value):
        if key=='placeholder-text':self.placeholder=value
        else:self.props[key]=value
    def set_sensitive(self, value):self.sensitive=value
    def set_visible(self, value):self.visible=value
    def set_inconsistent(self, value):self.inconsistent=value
    def set_fraction(self, value):self.fraction=value
    def __getattr__(self, name):
        if name.startswith('set_') or name in ('add_css_class','present','destroy'):
            return lambda *args:self.props.update({name:args})
        raise AttributeError(name)


def descendants(node):
    yield node
    for child in node.children:yield from descendants(child)


class ConnectionLayoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_core.CoreTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f=self.fixture
        self.first=replace(f.profile,name='Ethernet',serial_number='serial fixture')
        self.second=replace(f.profile,id='wifi-fixture',name='Wi-Fi',host='192.0.2.21')
        f.prefs.profiles=[self.first,self.second];f.prefs.selected_id=self.first.id
        f.credentials.values[self.first.id]='fixture-secret'
        f.credentials.exists=lambda key:key in f.credentials.values
        f.credentials.get=Mock(side_effect=AssertionError('No secret reads in layout'))
        self.timers=[]
        gtk=SimpleNamespace(Orientation=SimpleNamespace(VERTICAL=1,HORIZONTAL=0),Align=SimpleNamespace(START=0,END=1))
        for kind in ('Window','Box','ScrolledWindow','ComboBoxText','Label','Entry','PasswordEntry','CheckButton','ProgressBar','ListBox','ListBoxRow','Separator'):
            setattr(gtk,kind,lambda _kind=kind,**kwargs:Node(_kind,**kwargs))
        for target,value in [('c64u_browser.connection_dialog.Gtk',gtk),
                             ('c64u_browser.connection_dialog.GLib.timeout_add',lambda _,fn:self.timers.append(fn)),
                             ('c64u_browser.connection_dialog.GLib.idle_add',lambda fn:fn()),
                             ('c64u_browser.connection_dialog.ConnectionDialog._background',staticmethod(self.background))]:
            patcher=patch(target,value);patcher.start();self.addCleanup(patcher.stop)
        self.app=SimpleNamespace(core=f.core,preferences=f.prefs,busy=False,active_profile=None,
                                 update_connection_header=Mock(),activate_connection=Mock(),disconnect_device=Mock())
        self.app.run=lambda task,done:done(task())
        self.app.button=self.button
        f.core.discovery_networks=Mock(return_value=('192.0.2.0/24',))
        self.window=Node('Window');self.window.pages=Node()
        self.d=ConnectionDialog(self.app,self.window);self.drain()
    @staticmethod
    def background(task, done):
        try:result=task()
        except Exception as exc:result=exc
        done(result)
    @staticmethod
    def button(box, label, callback):
        button=Node('Button',label=label);button.connect('clicked',lambda _:callback());box.append(button)
        return button
    def drain(self):
        while self.timers:
            pending,self.timers=self.timers,[]
            for fn in pending:fn()
    def click(self, label):
        matches=[n for n in descendants(self.d.controls) if n.kind=='Button' and n.text==label]
        self.assertEqual(1,len(matches));matches[0].emit('clicked')
    def test_sections_and_distinct_action_groups(self):
        d=self.d
        self.assertEqual([d.identity_section,d.credentials_section,d.status,d.discovery_section,
                          d.controls.children[4],d.profiles_section,d.connection_actions],d.controls.children)
        self.assertEqual('Separator',d.controls.children[4].kind)
        self.assertEqual(['New','Save Profile','Delete Profile'],[n.text for n in d.profile_actions.children])
        self.assertEqual(['Test','Connect'],[n.text for n in d.connection_actions.children])
        labels=[n.text for n in descendants(d.controls) if n.kind=='Label']
        for label in ('Saved Network Connections','Connection','Network Discovery','Credentials','Connection name'):
            self.assertIn(label,labels)
        self.assertNotIn('Machines',labels);self.assertNotIn('FTP Connection',labels)
        self.assertNotIn('Save Password',[n.text for n in descendants(d.controls)])
    def test_saved_only_selector_and_unsaved_discovery_state(self):
        d=self.d;original=dict(d.saved.items)
        self.assertEqual({self.first.id:'Ethernet',self.second.id:'Wi-Fi'},original)
        self.fixture.prefs.save=Mock()
        candidate=Candidate('192.0.2.22',info={'info':{'hostname':'Discovered'}})
        d.add_candidate(candidate);row=d._candidate_rows[candidate.host,candidate.port]
        d.devices.emit('row-selected',row);self.drain()
        self.assertEqual(original,d.saved.items);self.assertIsNone(d.current_id)
        self.assertIsNone(d.saved.get_active_id());self.assertIn('Discovered connection',d.selection_status.text)
        self.assertEqual(candidate.host,d.fields['host'].text)
        self.assertEqual('Saved device ID: Not bound',d.device_identity.text)
        self.fixture.prefs.save.assert_not_called()
    def test_switch_reconstructs_credentials_and_exact_saved_binding(self):
        d=self.d
        self.assertEqual('PRESENT',d._credential_state);self.assertTrue(d.remember.active)
        self.assertEqual('••••••••',d.password.placeholder)
        d.password.set_text('fixture replacement');d.saved.set_active_id(self.second.id)
        self.assertEqual('UNKNOWN',d._credential_state);self.assertEqual('',d.password.text)
        self.assertEqual(self.second.host,d.fields['host'].text)
        self.assertIn(self.second.name,d.selection_status.text)
        self.drain();self.assertEqual('ABSENT',d._credential_state);self.assertFalse(d.remember.active)
        d.saved.set_active_id(self.first.id);self.drain()
        self.assertEqual('PRESENT',d._credential_state);self.assertTrue(d.remember.active)
        self.assertEqual('serial fixture',d.fields['serial_number'].text)
        self.assertEqual('Saved device ID: ABC123',d.device_identity.text)
        self.assertEqual(self.first.device_id,d.profile().device_id)
        self.fixture.credentials.get.assert_not_called()
    def test_relocated_save_cannot_bypass_unknown_after_switch(self):
        d=self.d;f=self.fixture
        f.credentials.exists=Mock(side_effect=BrowserError('fixture private error'))
        f.prefs.save=Mock();f.credentials.set=Mock();f.credentials.delete=Mock()
        d.saved.set_active_id(self.second.id);self.drain()
        d.fields['name'].set_text('Unfinished edit');d.password.set_text('fixture replacement')
        self.assertEqual('UNKNOWN',d._credential_state)
        self.assertTrue(d.remember.inconsistent);self.assertFalse(d.remember.sensitive)
        for value in (False,True):
            d.remember.set_active(value);self.click('Save Profile')
        f.prefs.save.assert_not_called();f.credentials.set.assert_not_called();f.credentials.delete.assert_not_called()
        self.assertEqual('fixture replacement',d.password.text)
        self.assertEqual('Unfinished edit',d.fields['name'].text)
        self.assertNotIn('fixture private error',d.credential_status.text)

    def test_relocated_new_save_delete_preserve_profile_semantics(self):
        d=self.d
        d.fields['name'].set_text('Renamed Ethernet');self.click('Save Profile');self.drain()
        self.assertEqual(self.first.id,d.current_id)
        self.assertEqual('Renamed Ethernet',self.fixture.prefs.profiles[0].name)
        self.click('New');self.drain();self.assertIsNone(d.current_id)
        self.assertEqual('',d.password.text);self.assertIn('not saved',d.selection_status.text)
        d.fields['name'].set_text('New fixture');d.fields['host'].set_text('192.0.2.23');self.drain()
        self.click('Save Profile');self.drain();new_id=d.current_id
        self.assertNotIn(new_id,(self.first.id,self.second.id));self.assertEqual(3,len(self.fixture.prefs.profiles))
        self.click('Delete Profile');self.drain()
        self.assertEqual([self.first.id,self.second.id],[p.id for p in self.fixture.prefs.profiles])
        self.assertIsNone(d.current_id)
    def test_test_connect_and_password_enter_do_not_route_to_save(self):
        d=self.d;core=self.fixture.core
        core.save_profile=Mock(side_effect=AssertionError('Implicit Save'))
        core.test_profile=Mock(return_value=SimpleNamespace(device_info=test_core.INFO,reported_device_id='ABC123'))
        core.connect=Mock(return_value=SimpleNamespace(profile=self.first))
        d.password.set_text('fixture typed');self.click('Test')
        core.test_profile.assert_called_once_with(d.profile(),'fixture typed')
        self.assertIn('Success',d.status.text);core.connect.assert_not_called()
        self.click('Connect');self.drain()
        self.assertFalse(core.connect.call_args.kwargs['remember'])
        self.assertEqual('fixture typed',core.connect.call_args.kwargs['entered_password'])
        self.assertIn('password storage unchanged',d.status.text)
        d.password.set_text('second fixture');d.password.emit('activate');self.drain()
        self.assertEqual(2,core.connect.call_count);core.save_profile.assert_not_called()
        self.assertNotIn('set_default_widget',self.window.props)
        for field in d.fields.values():self.assertNotIn('activate',field.signals)
    def test_discovery_controls_progress_and_results_after_relocation(self):
        d=self.d;core=self.fixture.core
        core.discover=Mock(return_value=((),(),('192.0.2.0/24',)))
        d.subnet.set_text('invalid');self.click('Scan Subnet');core.discover.assert_not_called()
        self.click('Discover');core.discover.assert_called_once_with(subnet='')
        observed=[];candidate=Candidate('192.0.2.22')
        def scan(**kwargs):
            kwargs['found'](candidate);kwargs['progress'](127,254)
            observed.append((d.scan_progress.fraction,len(d.devices.children)))
            return (candidate,),(),()
        core.discover=Mock(side_effect=scan)
        d.subnet.set_text('192.0.2.0/24');self.assertTrue(d.scan_subnet_button.sensitive)
        self.click('Scan Subnet')
        self.assertEqual([(.5,1)],observed);self.assertEqual(1,d.scan_progress.fraction)
        self.assertIn('1 network connections found',d.status.text)
    def test_session_modes_keep_controls_hidden_and_password_private(self):
        for mode in ('Development','Portable'):
            self.fixture.core._credentials=SessionCredentials(mode)
            d=ConnectionDialog(self.app,Node('Window'));self.drain()
            self.assertEqual(mode+' mode — passwords are session-only.',d.credential_status.text)
            self.assertFalse(d.remember.visible);self.assertFalse(d.remember.sensitive)
            self.assertFalse(d.forget_button.visible);self.assertFalse(d.forget_button.sensitive)
            d.password.set_text('never display this fixture')
            self.assertNotIn('never display this fixture',' '.join(n.text for n in descendants(d.controls) if n.kind=='Label'))
            self.assertEqual('PasswordEntry',d.password.kind)


if __name__=='__main__':unittest.main()
