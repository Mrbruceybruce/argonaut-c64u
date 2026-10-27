"""Offline dependency contracts: real Core/controllers, synthetic transport only."""
import copy
from itertools import permutations
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import UltimateClient
from c64u_browser.configuration import Configuration
from c64u_browser.configuration_policy import ConfigurationRefused, validate, enabled, DEPENDENCIES
from c64u_browser.core import ArgonautCore
from c64u_browser.config_history import history_path
from c64u_browser.backups import read_backup, write_backup
from c64u_browser.profiles import Preferences, Profile
from test_core import FakeClient, FakeCredentials

CATEGORIES = ('LED Strip Settings', 'Keyboard Lighting')
MODES = ('Off', 'Fixed Color', 'SID Music', 'Rainbow', 'Rainbow Sparkle', 'Default')
# Independent oracle transcribed from official update_menu, not policy constants.
FLAGS = {'Off': (0,0,0,0), 'Default': (0,1,0,0), 'Fixed Color': (0,1,1,1),
         'SID Music': (1,1,0,0), 'Rainbow': (1,1,0,1),
         'Rainbow Sparkle': (1,1,0,1), 'Sparkle': (0,1,0,0)}
FIELDS = ('LedStrip Pattern', 'Strip Intensity', 'Fixed Color', 'Color tint')
VALUES = ('Left to Right', 15, 'Red', 'Bright')


def metadata(category, mode='Fixed Color'):
    return {
        'LedStrip Mode': {'current': mode, 'values': list(MODES) + (['Sparkle'] if category == CATEGORIES[0] else [])},
        'LedStrip Auto SID Mode': {'current': 'Disabled', 'values': ['Disabled','Enabled']},
        'LedStrip SID Select': {'current':'UltiSID1-A','values':['UltiSID1-A','UltiSID1-B']},
        'LedStrip Pattern': {'current':'Left to Right','values':['Left to Right','Right to Left']},
        'Strip Intensity': {'current':10,'min':0,'max':31},
        'Fixed Color': {'current':'Blue','values':['Blue','Red']},
        'Color tint': {'current':'Pure','values':['Pure','Bright']},
    }


class RecordingClient(FakeClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata = {c:metadata(c) for c in CATEGORIES}
        self.metadata['Other'] = {'Value':{'current':'old'}}
        self.writes = []; self.reads = []; self.info = {'product':'C64 Ultimate','firmware_version':'1.1.0'}
    def read_configuration(self, category=None):
        self.reads.append(category)
        if category is None:return {'categories':list(self.metadata)}
        return {category:copy.deepcopy(self.metadata.get(category, {}))}
    def read_about(self, route):return copy.deepcopy(self.info)
    def _apply_configuration_validated(self, values):
        self.writes.append(copy.deepcopy(values))
        for c, items in values.items():
            for n, v in items.items():self.metadata[c][n]['current']=v
    apply_configuration = UltimateClient.apply_configuration


class Offline:
    def setUp(self):
        self.addCleanup(patch.stopall)
        for method in ('connect','connect_ex','sendto'):
            patch.object(socket.socket,method,side_effect=AssertionError('OFFLINE')).start()
        patch('socket.create_connection',side_effect=AssertionError('OFFLINE')).start()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.core=ArgonautCore(preferences=Preferences(Path(self.temp.name)/'prefs.json'),
                               credentials=FakeCredentials(),client_factory=RecordingClient)
        self.addCleanup(self.core.close)
        self.profile=Profile.new('Synthetic','192.0.2.20',device_id='ABC123')
        self.core.connect(self.profile,initial_browse=False)
        self.client=self.core._client;self.ops=self.core.device_operations
        self.history=history_path(self.core.preferences,self.profile,self.ops)
    def settings(self):return Configuration(self.ops).all_settings(list(self.client.metadata))
    def refused(self,payload,**kwargs):
        before=copy.deepcopy(self.client.writes)
        with self.assertRaises(ConfigurationRefused):self.ops.apply_configuration(payload,**kwargs)
        self.assertEqual(before,self.client.writes)


class CoreDependencies(Offline,unittest.TestCase):
    def test_all_category_modes_fields_and_ui_agreement(self):
        for category in CATEGORIES:
            for mode in MODES + (('Sparkle',) if category == CATEGORIES[0] else ()):
                self.client.metadata[category] = metadata(category, mode)
                settings = self.settings()
                # Retained firmware dependency rules are not rewritten by containment.
                self.assertEqual(tuple(mode in DEPENDENCIES[(category, name)].allowed for name in FIELDS), tuple(bool(flag) for flag in FLAGS[mode]))
                for name, meta in self.client.metadata[category].items():
                    for value in (meta['current'], (15 if name == 'Strip Intensity' else meta['values'][-1])):
                        with self.subTest(category=category, mode=mode, field=name, value=value):
                            self.assertFalse(enabled(category, name, settings, {}))
                            before = copy.deepcopy(self.client.metadata)
                            with patch.object(self.client, 'read_configuration', side_effect=AssertionError('read')) as read, patch.object(self.client, 'read_about', side_effect=AssertionError('info')) as info:
                                self.refused({category: {name: value}}, history_path=self.history)
                            read.assert_not_called(); info.assert_not_called()
                            self.assertEqual(self.client.metadata, before)
                            self.assertFalse(self.history.exists())

    def test_final_state_all_orders_reject_whole_mixed_batch(self):
        for category in CATEGORIES:
            for mode in ('Rainbow','SID Music') + (('Sparkle',) if category==CATEGORIES[0] else ()):
                for fields in permutations((('LedStrip Mode',mode),('Fixed Color','Red'))):
                    for categories in permutations(((category,dict(fields)),('Other',{'Value':'new'}))):
                        self.refused(dict(categories),history_path=self.history)
        self.assertFalse(self.history.exists())

    def test_enabling_transition_also_refused_in_every_field_order(self):
        for category in CATEGORIES:
            for fields in permutations((('Fixed Color','Red'),('LedStrip Mode','Fixed Color'))):
                self.client.metadata[category]=metadata(category,'Rainbow')
                self.refused({category:dict(fields)},history_path=self.history)
        self.assertFalse(self.history.exists())

    def test_stale_unedited_controller_rejected_before_history(self):
        expected={(c,s.name):s.current for c,rows in self.settings().items() for s in rows}
        self.client.metadata[CATEGORIES[0]]['LedStrip Mode']['current']='Rainbow'
        self.refused({CATEGORIES[0]:{'Color tint':'Bright'}},expected=expected,history_path=self.history)
        self.assertFalse(self.history.exists())

    def test_fresh_controller_without_ui_snapshot_is_authoritative(self):
        self.client.metadata[CATEGORIES[1]]['LedStrip Mode']['current']='Rainbow'
        self.refused({CATEGORIES[1]:{'Fixed Color':'Red'}})
        self.refused({CATEGORIES[1]:{'Color tint':'Bright'}})

    def test_unknown_firmware_and_product_do_not_block_non_led(self):
        for info in ({}, {'firmware_version':'1.1.0s2','product':'C64 Ultimate'},
                     {'firmware_version':'1.1.0','product':'Unknown'},
                     {'firmware_version':'1.2.0','product':'C64 Ultimate'}):
            self.client.info=info
            self.refused({CATEGORIES[0]:{'Strip Intensity':15},'Other':{'Value':'new'}})
            self.ops.apply_configuration({'Other':{'Value':'new'}})

    def test_unknown_missing_and_malformed_capabilities(self):
        category=CATEGORIES[0]
        cases=[{}, {'LedStrip Mode':{'current':'Fixed Color'}}, metadata(category,'Future')]
        for mutate in (lambda m:m['LedStrip Mode'].update(values=['Fixed Color','Future']),
                       lambda m:m['Fixed Color'].pop('values'),
                       lambda m:m['Fixed Color'].update(readonly=True),
                       lambda m:m.update({'fixed color':m['Fixed Color']})):
            m=metadata(category);mutate(m);cases.append(m)
        for m in cases:
            self.client.metadata[category]=m
            self.refused({category:{'Fixed Color':'Red'}})
        self.client.metadata[category]=metadata(category)
        self.client.metadata[category]['Future field']={'current':'old'}
        self.refused({category:{'Future field':'new'}})
        self.refused({CATEGORIES[1]:{'LedStrip Mode':'Sparkle'}})

    def test_malformed_payloads_cannot_bypass_identity_or_value_checks(self):
        for payload in ({},[], {'Other':{}}, {'Other':{'Value':float('nan')}},
                        {'LED Strip Settings*':{'Fixed Color':'Red'}},
                        {'Other':{'Value':'new','value':'old'}},
                        {'Other':{'Value':'new'},'other':{'Value':'old'}},
                        {CATEGORIES[0]:{'Strip Intensity':True}},
                        {CATEGORIES[0]:{'Strip Intensity':32}}):
            self.refused(payload)

    def test_case_variants_cannot_bypass_mode_dependency(self):
        for transform in (str.lower,str.upper,str.swapcase):
            self.refused({transform(CATEGORIES[0]):{transform('LedStrip Mode'):'Rainbow',transform('Fixed Color'):'Red'}})

    def test_raw_client_public_apply_has_same_boundary(self):
        with self.assertRaises(ConfigurationRefused):
            self.client.apply_configuration({CATEGORIES[1]:{'LedStrip Mode':'Rainbow'}})
        self.assertEqual(self.client.writes,[])
        for category in CATEGORIES:
            for value in ('Rainbow', 'Fixed Color'):
                with self.assertRaises(ConfigurationRefused):
                    self.client.apply_configuration({category:{'LedStrip Mode':value}})
        self.assertEqual(self.client.writes,[])

    def test_existing_history_preserved_on_invalid_mixed_batch(self):
        self.history.parent.mkdir();self.history.write_bytes(b'prior')
        self.refused({'Other':{'Value':'new'},CATEGORIES[0]:{'LedStrip Mode':'Sparkle','Color tint':'Bright'}},history_path=self.history)
        self.assertEqual(self.history.read_bytes(),b'prior')

    def test_detached_intent_survives_caller_mutation_during_read(self):
        values={'Other':{'Value':'new'}}
        read=self.client.read_configuration
        def mutate(category=None):
            values[CATEGORIES[0]]={'Strip Intensity':15}
            values['Other']['Value']='injected'
            return read(category)
        with patch.object(self.client,'read_configuration',side_effect=mutate):self.ops.apply_configuration(values)
        self.assertEqual(self.client.writes,[{'Other':{'Value':'new'}}])

    def test_failed_reads_and_stale_session_have_zero_writes(self):
        with patch.object(self.client,'read_configuration',side_effect=TimeoutError):
            self.refused({'Other':{'Value':'new'}},history_path=self.history)
        session=self.ops.configuration_session
        self.core.reconnect();self.client=self.core._client
        self.refused({'Other':{'Value':'new'}},session=session,history_path=self.history)
        self.assertFalse(self.history.exists())

    def test_history_precedes_valid_dispatch_and_timeout_not_retried(self):
        def fail(payload):
            self.assertEqual(read_backup(self.history)['settings'],{'Other':{'Value':'old'}})
            raise TimeoutError('uncertain')
        with patch.object(self.client,'_apply_configuration_validated',side_effect=fail) as dispatch:
            with self.assertRaises(TimeoutError):
                self.ops.apply_configuration({'Other':{'Value':'new'}},history_path=self.history)
            self.assertEqual(dispatch.call_count,1)

    def test_all_85_mode_pairs_refused_including_same_value(self):
        pairs = 0
        for category in CATEGORIES:
            modes=MODES + (('Sparkle',) if category==CATEGORIES[0] else ())
            for old in modes:
                for new in modes:
                    with self.subTest(category=category, old=old, new=new):
                        self.client.metadata[category]=metadata(category,old)
                        before=copy.deepcopy(self.client.metadata)
                        self.refused({category:{'LedStrip Mode':new}},history_path=self.history)
                        self.assertEqual(self.client.metadata,before)
                        self.assertFalse(self.history.exists())
                        pairs += 1
        self.assertEqual(pairs,85)

    def test_mode_refusal_without_metadata_and_case_bypasses(self):
        # Presentation must not add identity errors for unrelated metadata.
        self.assertTrue(enabled('Other/Legacy', 'Value', {}, {}))
        for category in CATEGORIES:
            for transform in (str, str.lower, str.upper, str.swapcase):
                payload={transform(category):{transform('LedStrip Mode'):'Fixed Color'}}
                with self.assertRaisesRegex(ConfigurationRefused,'blocked by Argonaut'):
                    validate(payload,{})
                with patch.object(self.client,'read_configuration',side_effect=AssertionError('no read needed')) as read:
                    self.refused(payload,history_path=self.history)
                read.assert_not_called()
        self.assertFalse(self.history.exists())

    def test_mode_mixed_with_valid_parameters_preserves_existing_history(self):
        self.history.parent.mkdir(); self.history.write_bytes(b'prior')
        for category in CATEGORIES:
            for mode in ('Fixed Color','Rainbow','Off'):
                for fields in permutations((('LedStrip Mode',mode),('Strip Intensity',15))):
                    for categories in permutations(((category,dict(fields)),('Other',{'Value':'new'}))):
                        self.refused(dict(categories),history_path=self.history)
                        self.assertEqual(self.history.read_bytes(),b'prior')

    def test_invalid_second_led_category_prevents_first_category_write(self):
        for order in permutations(((CATEGORIES[0],{'Strip Intensity':15}),
                                   (CATEGORIES[1],{'LedStrip Mode':'Rainbow'}))):
            self.refused(dict(order),history_path=self.history)
        self.assertFalse(self.history.exists())

    def test_dhcp_dependency_is_shared_and_order_independent(self):
        category='Ethernet Settings'
        self.client.metadata[category]={'Use DHCP':{'current':'Enabled','values':['Disabled','Enabled']},
                                        'Static IP':{'current':'192.0.2.1'}}
        self.refused({category:{'Static IP':'192.0.2.2'},'Other':{'Value':'new'}})
        for fields in permutations((('Static IP','192.0.2.2'),('Use DHCP','Disabled'))):
            self.client.metadata[category]['Use DHCP']['current']='Enabled'
            self.ops.apply_configuration({category:dict(fields)})
            self.assertEqual(list(self.client.writes[-1][category]),['Use DHCP','Static IP'])
        self.refused({category:{'Static IP':'192.0.2.3','Use DHCP':'Enabled'}})

    def test_unknown_enum_vocabulary_and_intensity_bounds_refused(self):
        category=CATEGORIES[0]
        for name in ('Fixed Color','Color tint','LedStrip Pattern','LedStrip Auto SID Mode','LedStrip SID Select'):
            original=copy.deepcopy(self.client.metadata[category])
            self.client.metadata[category][name]['values'].append('Future')
            self.refused({category:{name:'Future'}})
            self.client.metadata[category]=original
        self.client.metadata[category]['Strip Intensity']['max']=255
        self.refused({category:{'Strip Intensity':15}})

    def test_real_transport_dispatch_is_zero_for_rejection_one_for_valid_batch(self):
        client=UltimateClient('192.0.2.20')
        category=CATEGORIES[0]
        with patch.object(client,'read_configuration',side_effect=self.client.read_configuration), patch.object(client,'read_about',side_effect=self.client.read_about), patch.object(client,'_request_json') as request:
            with self.assertRaises(ConfigurationRefused):
                client.apply_configuration({'Other':{'Value':'new'},category:{'LedStrip Mode':'Rainbow'}})
            request.assert_not_called()
            client.apply_configuration({'Other':{'Value':'new'}})
            request.assert_called_once_with('POST','/v1/configs',{'Other':{'Value':'new'}})

    def test_all_led_fields_case_variants_unknown_fields_and_mixed_batches(self):
        self.history.parent.mkdir(); self.history.write_bytes(b'prior')
        for category in CATEGORIES:
            fields = [(name, meta['current']) for name, meta in metadata(category).items()]
            fields += [('Future field', 'unknown')]
            for name, value in fields:
                for transform in (str, str.lower, str.upper, str.swapcase):
                    for order in permutations(((transform(category), {transform(name): value}), ('Other', {'Value': 'new'}))):
                        payload = dict(order)
                        with self.subTest(category=category, name=name, payload=payload):
                            with patch.object(self.client, 'read_configuration', side_effect=AssertionError('read')) as read, patch.object(self.client, 'read_about', side_effect=AssertionError('info')) as info:
                                self.refused(payload, history_path=self.history)
                                with self.assertRaises(ConfigurationRefused):self.client.apply_configuration(payload)
                            read.assert_not_called(); info.assert_not_called()
                            with self.assertRaises(ConfigurationRefused):validate(payload, {})
                            self.assertEqual(self.history.read_bytes(), b'prior')
                            self.assertEqual(self.client.writes, [])
        for category in CATEGORIES:
            for fields in permutations((('Strip Intensity', 10), ('LedStrip Auto SID Mode', 'Enabled'))):
                with patch.object(self.client, 'read_configuration', side_effect=AssertionError('read')) as read, patch.object(self.client, 'read_about', side_effect=AssertionError('info')) as info:
                    self.refused({category:dict(fields), 'Other':{'Value':'new'}}, history_path=self.history)
                read.assert_not_called(); info.assert_not_called()
                self.assertEqual(self.history.read_bytes(), b'prior')
        client = UltimateClient('192.0.2.20')
        with patch.object(client, '_request_json', side_effect=AssertionError('transport')) as request:
            for category in CATEGORIES:
                for name, meta in metadata(category).items():
                    with self.assertRaises(ConfigurationRefused):client.apply_configuration({category:{name:meta['current']}})
            request.assert_not_called()

    def test_led_values_still_readable_and_unrelated_mode_names_writable(self):
        settings = self.settings()
        for category in CATEGORIES:
            self.assertEqual({s.name for s in settings[category]}, set(metadata(category)))
            self.assertEqual(next(s.current for s in settings[category] if s.name == 'Strip Intensity'), '10')
        self.client.metadata['Other']['LedStrip Mode'] = {'current':'old'}
        self.ops.apply_configuration({'Other': {'LedStrip Mode':'new'}})
        self.assertEqual(self.client.writes, [{'Other': {'LedStrip Mode':'new'}}])

    def test_headless_core_does_not_import_gtk(self):
        import subprocess,sys
        result=subprocess.run([sys.executable,'-c',"import sys; from c64u_browser.core import ArgonautCore; from c64u_browser.configuration_policy import validate; sys.exit(1 if 'gi' in sys.modules else 0)"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


class Widget:
    def __init__(self,*args,**kwargs):self.active=kwargs.get('active',False);self.callbacks={}
    def connect(self,signal,callback):self.callbacks[signal]=callback
    def response(self,code):self.callbacks['response'](self,code)
    def get_active(self):return self.active
    def set_active(self,value):self.active=value
    def add_button(self,*args):return Widget()
    def get_content_area(self):return self
    def __getattr__(self,name):return lambda *args,**kwargs:None


class UIDependencies(Offline,unittest.TestCase):
    def setUp(self):
        super().setUp()
        from c64u_browser.settings_tab import SettingsTab
        from c64u_browser.backup_dialog import BackupActions
        from c64u_browser import settings_tab,backup_dialog
        gtk=SimpleNamespace(Dialog=Widget,Label=Widget,Box=Widget,ScrolledWindow=Widget,
                            CheckButton=Widget,Orientation=SimpleNamespace(VERTICAL=1),
                            ResponseType=SimpleNamespace(OK=1,CANCEL=0))
        patch.object(settings_tab,'Gtk',gtk).start();patch.object(backup_dialog,'Gtk',gtk).start()
        tab=self.tab=SettingsTab.__new__(SettingsTab)
        tab.app=SimpleNamespace(busy=False,window=None,status=Mock(),preferences=self.core.preferences,
                                active_profile=self.profile,run=lambda task,done:done(task()))
        tab.client=self.ops;tab.pending={};tab.drafts={};tab.errors={};tab.requires_refresh=False
        tab.all_settings=self.settings();tab.loaded=True
        tab.render=Mock();tab.update_edit_buttons=Mock();tab.rows=Mock();tab.backups=BackupActions(tab)
        self.history.parent.mkdir();self.history.write_bytes(b'prior')
    def stage(self,values):
        self.tab.pending={(c,n):v for c,items in values.items() for n,v in items.items()}
        self.tab.drafts={k:str(v) for k,v in self.tab.pending.items()}
    def test_apply_refuses_invalid_full_batch_and_retains_edits(self):
        self.stage({'Other':{'Value':'new'},CATEGORIES[1]:{'Strip Intensity':15}})
        pending=dict(self.tab.pending);drafts=dict(self.tab.drafts)
        self.assertIsNone(self.tab.apply());self.tab.apply_reviewed(pending)
        self.assertEqual(self.tab.pending,pending);self.assertEqual(self.tab.drafts,drafts)
        self.assertEqual(self.client.writes,[]);self.assertEqual(self.history.read_bytes(),b'prior')
    def test_both_categories_all_fields_stage_refused_preserves_unrelated_draft(self):
        self.stage({'Other': {'Value': 'new'}})
        before = (dict(self.tab.pending), dict(self.tab.drafts))
        for category in CATEGORIES:
            for row in self.tab.all_settings[category]:
                self.tab.stage(category, row, '15' if row.name == 'Strip Intensity' else 'Rainbow')
                self.assertEqual((self.tab.pending, self.tab.drafts), before)
                self.assertEqual(self.client.writes, [])

    def test_ui_bypass_still_rejected_by_core(self):
        payload={CATEGORIES[0]:{'Strip Intensity':10}}
        self.stage(payload)
        with patch.object(self.tab,'admit_changes',return_value=payload):self.tab.apply_reviewed(dict(self.tab.pending))
        self.assertEqual(self.client.writes,[]);self.assertEqual(self.history.read_bytes(),b'prior')
        self.assertIn('not sent',self.tab.app.status.set_text.call_args.args[0])
    def test_value_changes_after_review_preserve_history(self):
        self.stage({'Other':{'Value':'new'}})
        dialog=self.tab.apply()
        self.client.metadata['Other']['Value']['current']='external'
        dialog.response(1)
        self.assertEqual(self.client.writes,[]);self.assertEqual(self.history.read_bytes(),b'prior')

    def test_restore_and_undo_preview_reject_invalid_selected_set(self):
        for title in ('Restore preview','Undo last apply preview','Native configuration preview'):
            data={'settings':{CATEGORIES[1]:{'LedStrip Auto SID Mode':'Enabled'},'Other':{'Value':'new'}}}
            dialog,checks=self.tab.backups.preview(data,self.tab.all_settings,title=title)
            for check in checks:check.set_active(True)
            dialog.response(1)
            self.assertFalse(self.tab.pending);self.assertFalse(self.tab.drafts)
            self.assertEqual(self.client.writes,[]);self.assertEqual(self.history.read_bytes(),b'prior')
    def test_valid_restore_stages_unrelated_batch_and_applies(self):
        dialog,checks=self.tab.backups.preview({'settings':{'Other':{'Value':'new'}}},self.tab.all_settings)
        for check in checks:check.set_active(True)
        dialog.response(1);self.assertEqual(len(self.tab.pending),1)
        self.tab.apply().response(1)
        self.assertEqual(self.client.writes,[{'Other':{'Value':'new'}}])
        self.assertFalse(self.tab.pending)

    def test_actual_undo_history_uses_dependency_validation(self):
        write_backup(self.history,{'format':'argonaut-settings','version':1,'settings':{CATEGORIES[0]:{'LedStrip SID Select':'UltiSID1-B'}}})
        before=self.history.read_bytes();captured=[];original=self.tab.backups.preview
        def preview(*args,**kwargs):
            result=original(*args,**kwargs);captured.append(result);return result
        with patch.object(self.tab.backups,'preview',side_effect=preview):self.tab.undo_apply()
        dialog,checks=captured[0]
        for check in checks:check.set_active(True)
        dialog.response(1)
        self.assertFalse(self.tab.pending);self.assertEqual(self.client.writes,[])
        self.assertEqual(self.history.read_bytes(),before)
    def test_native_cfg_actual_preview_refuses_invalid_combination(self):
        from c64u_browser.flash_dialog import FlashFiles
        native=FlashFiles.__new__(FlashFiles);native.tab=self.tab;native.client=self.ops
        native.dialog=Widget();native.folder=lambda:'/Flash/configs'
        native.listing=SimpleNamespace(get_selected_row=lambda:SimpleNamespace(name='test.cfg'))
        native.run=lambda task,done:done(task())
        captured=[];original=self.tab.backups.preview
        def preview(*args,**kwargs):
            result=original(*args,**kwargs);captured.append(result);return result
        with patch('c64u_browser.flash_dialog.read_remote',return_value=b'[Keyboard Lighting]\nStrip Intensity=15\n'), patch.object(self.tab.backups,'preview',side_effect=preview):
            native.preview()
        dialog,checks=captured[0]
        for check in checks:check.set_active(True)
        dialog.response(1)
        self.assertFalse(self.tab.pending);self.assertEqual(self.client.writes,[])
        self.assertEqual(self.history.read_bytes(),b'prior')

    def test_stale_preview_cannot_clear_reload_gate(self):
        dialog,checks=self.tab.backups.preview({'settings':{'Other':{'Value':'new'}}},self.tab.all_settings)
        checks[0].set_active(True);self.tab.require_fresh_settings();dialog.response(1)
        self.assertTrue(self.tab.requires_refresh);self.assertFalse(self.tab.pending)
    def test_cancel_confirmation_writes_nothing(self):
        self.stage({'Other':{'Value':'new'}})
        self.tab.apply().response(0)
        self.assertEqual(self.client.writes,[]);self.assertEqual(self.history.read_bytes(),b'prior')
