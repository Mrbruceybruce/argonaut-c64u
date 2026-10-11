# SPDX-License-Identifier: GPL-3.0-or-later
"""PA-3E.2: live identity propagation and initializer evidence over localhost."""
import copy
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from c64u_ftp_server import FakeC64UFtp
from c64u_browser.api import UltimateClient
from c64u_browser.core import ArgonautCore
from c64u_browser.profiles import Preferences, Profile
from c64u_browser.picker_model import PickerSelection
from c64u_browser.ftp_reads import adapter_for, creation_outcome
from c64u_browser.ftp_reads import CREATION_MKD_RULE as RULE, CREATION_MKD_PATHS as PATHS
from test_core import INFO, FakeCredentials

ROOT='/USB0/ARGONAUT_LIBRARY'
MUTATIONS={b'MKD',b'STOR',b'RNFR',b'RNTO',b'RMD',b'DELE'}

def triple(path):return b'257 "//'+path+b'" created.\r\n'

class CreationPathEvidenceTests(TestCase):
    @contextmanager
    def fixture(self, *, reply=triple, info=None, root='/USB0', profile_id='25EA78'):
        live=copy.deepcopy(INFO)
        live['info'].update(unique_id='25EA78',firmware_version='1.1.0s2')
        if info:
            for section,values in info.items():live[section].update(values)
        with tempfile.TemporaryDirectory() as tmp, FakeC64UFtp(
                directories={b'/':b'',b'/USB0':b'',b'/USB1':b''},mutation_tree=True,
                after_mutation={b'MKD':reply}) as server:
            def factory(host,password,port,http_port):
                client=UltimateClient(host,password,port=server.port,http_port=http_port,timeout=2)
                client.test_connection=lambda:copy.deepcopy(live)
                return client
            core=ArgonautCore(preferences=Preferences(Path(tmp)/'config.json'),
                              credentials=FakeCredentials(),client_factory=factory)
            profile=Profile.new('fixture','127.0.0.1',device_id=profile_id,
                                device_mac=INFO['network_mac'])
            try:
                core.connect(profile,require_bound=True,initial_browse=False)
                session=core.device_session()
                target=core.prepare_library_creation(PickerSelection('c64u',root,root[1:],root,
                    session.device_id,session.session_id,'library-root','dir'))
                yield server,core,target
            finally:
                self.assertEqual(0,core._ftp_manager.active_count)
                core.close()

    def execute(self,core,target):
        result=core.create_managed_library(target).wait(5)
        self.assertIn(result.state,('succeeded','failed','cancelled'))
        with self.assertRaises(Exception):core.create_managed_library(target)
        return result

    def unknown(self,server,result,count=1):
        self.assertEqual('failed',result.state)
        self.assertTrue(result.result.uncertain)
        self.assertEqual((),result.result.removed)
        self.assertEqual([b'MKD']*count,[v for v in server.verbs if v in MUTATIONS])
        self.assertIsNone(result.result.observations[-1].evidence['compatibility_rule'])

    def test_qualified_four_paths_raw_evidence_and_rule(self):
        with self.fixture() as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('succeeded',result.state,result.error)
            for observation,path in zip(result.result.observations[:4],PATHS):
                wire=observation.evidence
                self.assertEqual('completed',observation.outcome)
                self.assertEqual(RULE,wire['compatibility_rule'])
                self.assertEqual('firmware-compatibility',wire['path_acceptance_rule'])
                self.assertEqual('invalid',wire['path_status'])
                self.assertEqual((triple(path)[:-2].hex(),),wire['reply_lines_hex'])
                self.assertEqual((b'//'+path).hex(),wire['created_path_hex'])
                self.assertEqual(path.hex(),wire['requested_path_hex'])
            self.assertEqual([b'MKD']*4+[b'STOR',b'RNFR',b'RNTO'],[v for v in server.verbs if v in MUTATIONS])
            self.assertEqual(3,server.verbs.count(b'RETR'))

    def test_single_slash_ordinary_rule_on_unqualified_firmware(self):
        with self.fixture(reply=lambda p:b'257 "'+p+b'" created\r\n',
                          info={'info':{'firmware_version':'other'}}) as (server,core,target):
            result=self.execute(core,target);self.assertEqual('succeeded',result.state)
            for observation in result.result.observations[:4]:
                self.assertEqual('exact-path',observation.evidence['path_acceptance_rule'])
                self.assertIsNone(observation.evidence['compatibility_rule'])

    def test_wrong_or_missing_live_identity_firmware_api_product(self):
        cases=[({'info':{'firmware_version':v}},'25EA78') for v in ('1.1.0','', '1.1.0s2 ')]
        cases += [({'version':{'version':v}},'25EA78') for v in ('0.2','')]
        cases += [({'info':{'product':'other'}},'25EA78'),
                  ({'info':{'unique_id':'25BE71'}},'25BE71'),
                  ({'info':{'unique_id':''}},'25EA78')]
        for info,profile_id in cases:
            with self.subTest(info=info),self.fixture(info=info,profile_id=profile_id) as (server,core,target):
                self.unknown(server,self.execute(core,target))

    def test_wrong_selected_root(self):
        with self.fixture(root='/USB1') as (server,core,target):
            self.unknown(server,self.execute(core,target))

    def test_rejected_variants_at_every_creation_path(self):
        variants=[lambda p:b'/'+p,lambda p:b'///'+p,
          lambda p:b'//'+p.replace(b'USB0',b'USB1'),
          lambda p:b'//'+p.replace(b'ARGONAUT_LIBRARY',b'argonaut_library'),
          lambda p:b'//'+p+b'x',lambda p:b'//'+p.replace(b'/ARGONAUT',b'//ARGONAUT'),
          lambda p:b'//'+p.replace(b'/ARGONAUT',b'/../ARGONAUT'),
          lambda p:p[1:],lambda p:b'//'+p+b'\x00',lambda p:b'//'+p+b'\t',
          lambda p:b'//'+p.replace(b'USB0/',b'USB0%2f'),
          lambda p:b'//'+p.replace(b'USB0/',b'USB0\xc0\xaf'),lambda p:b'//'+p+b'/']
        for index,path in enumerate(PATHS):
            for variant in variants:
                bad=b'257 "'+variant(path)+b'" created.\r\n'
                with self.subTest(path=path,bad=bad),self.fixture(reply=lambda p:bad if p==path else triple(p)) as (server,core,target):
                    self.unknown(server,self.execute(core,target),index+1)

    def test_malformed_reply_shapes(self):
        p=PATHS[0]
        replies=[b'257 "//'+p+b' created.\r\n',
          b'257 "//'+p+b'" "other"\r\n',b'257 missing\r\n',
          b'257-first\r\n257 "//'+p+b'" created.\r\n',
          triple(p)[:-2]+b' extra\r\n',b'257 "//'+p+b'" created\r\n',
          b'257 "//'+p+b'" created.\x7f\r\n']
        for reply in replies:
            with self.subTest(reply=reply),self.fixture(reply=reply) as (server,core,target):
                self.unknown(server,self.execute(core,target))

    def test_lost_and_negative_reply(self):
        for reply in (None,b'550 denied\r\n',b'299 "///USB0/ARGONAUT_LIBRARY" created.\r\n'):
            with self.subTest(reply=reply),self.fixture(reply=reply) as (server,core,target):
                result=self.execute(core,target)
                self.assertEqual('failed',result.state)
                self.assertEqual([b'MKD'],[v for v in server.verbs if v in MUTATIONS])
                self.assertIsNone(result.result.observations[0].evidence['compatibility_rule'])
                self.assertEqual('rejected' if reply and reply.startswith(b'550') else 'unknown',result.result.observations[0].outcome)

    def test_changed_session_after_reply_is_unknown(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.mutate_evidence
            def changed(*args,**kwargs):
                result=original(*args,**kwargs);core._session_id='changed';return result
            with patch.object(adapter,'mutate_evidence',changed):
                self.unknown(server,self.execute(core,target))

    def test_missing_session_or_live_context_is_not_qualified(self):
        for field in ('session','live'):
            with self.subTest(field=field),self.fixture() as (server,core,target):
                adapter=adapter_for(core._client);original=adapter.mutate_evidence
                def missing(*args,**kwargs):
                    result=original(*args,**kwargs)
                    if field=='session':adapter.binding=replace(adapter.binding,core_session_id='')
                    else:adapter._creation_identity=None
                    return result
                with patch.object(adapter,'mutate_evidence',missing):
                    self.unknown(server,self.execute(core,target))

    def test_generic_mkdir_and_classifier_remain_strict(self):
        with self.fixture() as (server,core,target):
            evidence=adapter_for(core._client).mutate_evidence('mkdir',ROOT)
            self.assertEqual('invalid',evidence.mkdir_path_status(ROOT.encode()))
            outcome,wire=creation_outcome('MKD',ROOT,result=evidence)
            self.assertEqual('unknown',outcome)
            self.assertNotIn('compatibility_rule',dict(wire))

    def test_recorded_request_and_acknowledgment_cannot_be_substituted(self):
        from c64u_browser.c64u_ftp_types import Outcome
        variants=[{'requested_path':b'/USB0/OTHER'}, {'stage_submitted':False},
                  {'consequential_submitted':False}, {'acknowledged':()},
                  {'outcome':Outcome.UNKNOWN}, {'stage':'RNTO'}]
        for changes in variants:
            with self.subTest(changes=changes),self.fixture() as (server,core,target):
                adapter=adapter_for(core._client);original=adapter.mutate_evidence
                def altered(*args,**kwargs):return replace(original(*args,**kwargs),**changes)
                with patch.object(adapter,'mutate_evidence',altered):
                    self.unknown(server,self.execute(core,target))

    def test_changed_session_before_submission_cannot_mutate(self):
        with self.fixture() as (server,core,target):
            core._session_id='new-session'
            result=self.execute(core,target)
            self.assertNotEqual('succeeded',result.state)
            self.assertFalse(set(server.verbs)&MUTATIONS)
