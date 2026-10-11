# SPDX-License-Identifier: GPL-3.0-or-later
"""PA-3F safety boundaries through real managed localhost FTP evidence."""
import hashlib
import json
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from c64u_ftp_server import FakeC64UFtp
import test_ftp_reads as reads
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.jobs import CoreJob, JobCancelled
from c64u_browser.scheduler import JobBinding
from c64u_browser.picker_model import PickerSelection
from c64u_browser.c64u_ftp_types import Outcome

ROOT='/USB0/ARGONAUT_LIBRARY'
MUTATIONS={b'MKD',b'STOR',b'RMD',b'DELE',b'RNFR',b'RNTO'}


class CreationSafetyTests(TestCase):
    @contextmanager
    def fixture(self,**options):
        replies={b'MKD':lambda p:b'257 "'+p+b'" created\r\n'}
        replies.update(options.pop('after_mutation',{}))
        with FakeC64UFtp(directories={b'/':b'',b'/USB1':b'',b'/USB0':b''},
                mutation_tree=True,after_mutation=replies,**options) as server:
            f=reads.ReadMigrationTests()
            try:
                core,_=f.connect(server)
                session=core.device_session()
                target=core.prepare_library_creation(PickerSelection('c64u','/USB0','USB0','/USB0',
                    session.device_id,session.session_id,'library-root','dir'))
                yield server,core,target
                self.assertEqual(0,core._ftp_manager.active_count)
                self.assertFalse(core._session_gate.locked())
                probe=core.scheduler.submit(CoreJob('test.release',lambda _:True),JobBinding.device(session))
                self.assertEqual('succeeded',probe.wait(5).state)
                with self.assertRaises(Exception):core.create_managed_library(target)
            finally:f.doCleanups()

    def execute(self,core,target):
        result=core.create_managed_library(target).wait(10)
        self.assertIn(result.state,('succeeded','failed','cancelled'))
        json.dumps(result.as_dict())
        return result

    def invalid_mkd(self,reply):
        with self.fixture(after_mutation={b'MKD':reply}) as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('failed',result.state)
            recovery=result.result
            self.assertTrue(recovery.uncertain)
            self.assertEqual((),recovery.removed)
            self.assertEqual((),recovery.retained)
            self.assertEqual((ROOT,),recovery.possible_paths)
            self.assertEqual(Outcome.UNKNOWN,recovery.observations[-1].outcome)
            self.assertEqual([(b'MKD',ROOT.encode())],[(v,p) for v,p in server.commands if v in MUTATIONS])
            self.assertIn(ROOT.encode(),server.directories)
            self.assertIsNone(core.preferences.game_library_location)
            return recovery

    def test_wrong_mkd_path(self):
        recovery=self.invalid_mkd(b'257 "/unexpected" created\r\n')
        self.assertEqual(b'/unexpected'.hex(),recovery.observations[0].evidence['created_path_hex'])
        self.assertEqual((b'257 "/unexpected" created'.hex(),),recovery.observations[0].evidence['reply_lines_hex'])
        json.dumps(recovery.observations[0].evidence)
    def test_missing_mkd_path(self):self.invalid_mkd(b'257 Created\r\n')
    def test_relative_mkd_path(self):self.invalid_mkd(b'257 "ARGONAUT_LIBRARY" created\r\n')
    def test_case_mismatch(self):self.invalid_mkd(b'257 "/USB0/argonaut_library" created\r\n')
    def test_spelling_mismatch(self):self.invalid_mkd(b'257 "/USB0/ARGONAUT_LIBRAR" created\r\n')
    def test_malformed_mkd_reply(self):self.invalid_mkd(b'257 "/USB0/ARGONAUT_LIBRARY\r\n')
    def test_ambiguous_mkd_reply(self):self.invalid_mkd(b'257 "/USB0/ARGONAUT_LIBRARY" or "/other"\r\n')
    def test_generic_200_not_directory_ack(self):self.invalid_mkd(b'200 OK\r\n')
    def test_lost_mkd_reply(self):self.invalid_mkd(None)

    def test_each_child_requires_exact_reply(self):
        for count,name in enumerate(('games','metadata','artwork'),2):
            with self.subTest(name=name):
                path=(ROOT+'/'+name).encode()
                reply=lambda p:b'257 "/unexpected" created\r\n' if p==path else b'257 "'+p+b'" created\r\n'
                with self.fixture(after_mutation={b'MKD':reply}) as (server,core,target):
                    result=self.execute(core,target)
                    self.assertEqual('failed',result.state)
                    self.assertTrue(result.result.uncertain)
                    self.assertEqual(count,server.verbs.count(b'MKD'))
                    self.assertFalse(set(server.verbs)&{b'STOR',b'RMD',b'RNFR',b'RNTO'})
                    self.assertIn(path.decode(),result.result.possible_paths)
                    self.assertNotIn(path.decode(),result.result.retained)

    def test_valid_creation_preserves_exact_evidence(self):
        with self.fixture() as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('succeeded',result.state,result.error)
            payload=server.files[(ROOT+'/manifest.json').encode()]
            doc=json.loads(payload)
            self.assertEqual((1,0,[],target.token),(doc['schema_version'],doc['revision'],doc['games'],doc['library_id']))
            observations=result.result.observations
            self.assertEqual(['MKD']*4+['STOR','RNTO'],[o.operation for o in observations])
            for o in observations[:4]:self.assertEqual(o.path.encode().hex(),o.evidence['created_path_hex'])
            self.assertEqual(hashlib.sha256(payload).hexdigest(),observations[4].evidence['sha256'])
            self.assertTrue(all(o.outcome==Outcome.COMPLETED for o in observations))
            self.assertEqual(3,server.verbs.count(b'RETR'))

    def test_lost_stor_completion_retains_all_evidence(self):
        with self.fixture(transfer_completion=lambda v,p:None if v==b'STOR' else b'226 done\r\n') as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('failed',result.state)
            recovery=result.result
            self.assertTrue(recovery.uncertain)
            pending=ROOT+'/manifest.pending-'+target.token
            self.assertIn(pending.encode(),server.files)
            self.assertIn(pending,recovery.possible_paths)
            self.assertEqual((ROOT,ROOT+'/games',ROOT+'/metadata',ROOT+'/artwork'),recovery.retained)
            self.assertEqual(Outcome.UNKNOWN,recovery.observations[-1].outcome)
            self.assertGreater(recovery.observations[-1].evidence['transferred'],0)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})
            self.assertEqual(1,server.verbs.count(b'STOR'))

    def test_definite_mkd_refusal_no_ownership(self):
        with self.fixture(before_command=lambda v,p:b'550 Refused\r\n' if v==b'MKD' else None) as (server,core,target):
            result=self.execute(core,target)
            self.assertFalse(result.result.uncertain)
            self.assertEqual(Outcome.REJECTED,result.result.observations[-1].outcome)
            self.assertEqual((),result.result.retained)
            self.assertNotIn(ROOT.encode(),server.directories)
            self.assertFalse(set(server.verbs)&{b'RMD',b'STOR'})

    def test_definite_stor_refusal_cleans_owned_empty_directories(self):
        with self.fixture(before_command=lambda v,p:b'550 Refused\r\n' if v==b'STOR' else None) as (server,core,target):
            server.files[b'/USB0/keep.txt']=b'untouched'
            result=self.execute(core,target)
            self.assertFalse(result.result.uncertain)
            self.assertEqual((ROOT+'/artwork',ROOT+'/metadata',ROOT+'/games',ROOT),result.result.removed)
            self.assertEqual(Outcome.REJECTED,result.result.observations[4].outcome)
            self.assertEqual({b'/file':b'abc',b'/USB0/keep.txt':b'untouched'},server.files)
            self.assertNotIn(ROOT.encode(),server.directories)

    def test_uncertain_cleanup_stops_at_first_command(self):
        with self.fixture(before_command=lambda v,p:b'550 Refused\r\n' if v==b'STOR' else None,
                after_mutation={b'RMD':None}) as (server,core,target):
            result=self.execute(core,target)
            recovery=result.result
            self.assertTrue(recovery.uncertain)
            self.assertEqual(1,server.verbs.count(b'RMD'))
            self.assertEqual((),recovery.removed)
            self.assertIn(ROOT+'/artwork',recovery.possible_paths)
            self.assertTrue(recovery.cleanup_error)
            self.assertEqual(Outcome.UNKNOWN,recovery.observations[-1].outcome)

    def test_lost_or_ambiguous_rename_reply(self):
        for verb,reply in ((b'RNFR',None),(b'RNTO',None),(b'RNTO',b'200 Done\r\n')):
            with self.subTest(verb=verb,reply=reply):
                with self.fixture(after_mutation={verb:reply}) as (server,core,target):
                    result=self.execute(core,target)
                    self.assertTrue(result.result.uncertain)
                    self.assertEqual('failed',result.state)
                    self.assertFalse(set(server.verbs)&{b'RMD',b'DELE'})
                    self.assertEqual(Outcome.UNKNOWN,result.result.observations[-1].outcome)
                    self.assertIn(ROOT+'/manifest.json',result.result.possible_paths)

    def test_pending_and_final_readback_failures_retain_artifacts(self):
        for final in (False,True):
            with self.subTest(final=final):
                def corrupt(path,payload):
                    return b'x'*len(payload) if (path.endswith(b'manifest.json')==final) else payload
                with self.fixture(readback_data=corrupt) as (server,core,target):
                    result=self.execute(core,target)
                    self.assertEqual('failed',result.state)
                    self.assertTrue(result.result.uncertain)
                    self.assertFalse(set(server.verbs)&{b'RMD',b'DELE'})
                    self.assertEqual(int(final),server.verbs.count(b'RNTO'))

    def test_failure_after_pending_verification(self):
        def inject(v,p):
            if v==b'RETR' and b'manifest.pending-' in p:
                server.files[(ROOT+'/manifest.json').encode()]=b'foreign'
        with self.fixture(transfer_hook=inject) as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('failed',result.state)
            self.assertTrue(result.result.uncertain)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})

    def test_failure_after_final_verification_retains_observations(self):
        with self.fixture() as (server,core,target):
            with patch.object(core.preferences,'save',side_effect=OSError('disk full')):
                result=self.execute(core,target)
            self.assertEqual('registration',result.result.phase)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(6,len(result.result.observations))
            self.assertIn((ROOT+'/manifest.json').encode(),server.files)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE'})

    def test_partial_stor_local_failure_is_uncertain(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.write_from
            def partial(path,source,length):
                class Broken:
                    count=0
                    def read(self,size):
                        self.count+=1
                        if self.count>1:raise OSError('local read failed')
                        return source.read(1)
                return original(path,Broken(),length)
            with patch.object(adapter,'write_from',side_effect=partial):result=self.execute(core,target)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(1,result.result.observations[-1].evidence['transferred'])
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})

    def test_cancellation_after_mkd_allows_only_safe_cleanup(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.list_directory
            def cancel(path):
                if path==ROOT and not cancelled[0]:
                    cancelled[0]=True;raise JobCancelled()
                return original(path)
            cancelled=[False]
            with patch.object(adapter,'list_directory',side_effect=cancel):result=self.execute(core,target)
            self.assertEqual('cancelled',result.state)
            self.assertFalse(result.result.uncertain)
            self.assertEqual((ROOT,),result.result.removed)
            self.assertNotIn(b'STOR',server.verbs)

    def test_cancellation_after_stor_preserves_artifacts(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client)
            with patch.object(adapter,'read',side_effect=JobCancelled()):result=self.execute(core,target)
            self.assertEqual('cancelled',result.state)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(Outcome.COMPLETED,result.result.observations[-1].outcome)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})

    def test_ambiguous_rnfr_stops_before_rnto(self):
        with self.fixture(after_mutation={b'RNFR':b'399 Continue?\r\n'}) as (server,core,target):
            result=self.execute(core,target)
            self.assertEqual('failed',result.state)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(1,server.verbs.count(b'RNFR'))
            self.assertFalse(set(server.verbs)&{b'RNTO',b'RMD',b'DELE'})

    def test_multiline_mkd_path_is_ambiguous(self):
        self.invalid_mkd(b'257-"/USB0/ARGONAUT_LIBRARY"\r\n257 End\r\n')

    def test_definite_cleanup_refusal_preserves_exact_outcome(self):
        with self.fixture(before_command=lambda v,p:b'550 Refused\r\n' if v in (b'STOR',b'RMD') else None) as (server,core,target):
            result=self.execute(core,target)
            recovery=result.result
            self.assertFalse(recovery.uncertain)
            self.assertEqual(1,server.verbs.count(b'RMD'))
            self.assertEqual((),recovery.removed)
            self.assertEqual(4,len(recovery.retained))
            self.assertTrue(recovery.cleanup_error)
            self.assertEqual(Outcome.REJECTED,recovery.observations[-1].outcome)

    def test_unknown_adapter_failure_never_authorizes_cleanup(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client)
            with patch.object(adapter,'write_from',side_effect=RuntimeError('unknown')):
                result=self.execute(core,target)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(Outcome.UNKNOWN,result.result.observations[-1].outcome)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})

    def test_cancellation_during_stor_retains_wire_evidence(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.write_from
            def partial(path,source,length):
                def cancel(count):raise JobCancelled()
                return original(path,source,length,progress=cancel)
            with patch.object(adapter,'write_from',side_effect=partial):result=self.execute(core,target)
            self.assertEqual('cancelled',result.state)
            self.assertTrue(result.result.uncertain)
            self.assertGreater(result.result.observations[-1].evidence['transferred'],0)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE',b'RNFR',b'RNTO'})

    def test_cancellation_after_rename_does_not_cleanup(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.list_directory
            def cancel(path):
                if (ROOT+'/manifest.json').encode() in server.files:raise JobCancelled()
                return original(path)
            with patch.object(adapter,'list_directory',side_effect=cancel):result=self.execute(core,target)
            self.assertEqual('cancelled',result.state)
            self.assertTrue(result.result.uncertain)
            self.assertEqual(Outcome.COMPLETED,result.result.observations[-1].outcome)
            self.assertFalse(set(server.verbs)&{b'RMD',b'DELE'})

    def test_changed_listing_path_after_mkd_stops_all_mutations(self):
        with self.fixture() as (server,core,target):
            adapter=adapter_for(core._client);original=adapter.list_directory
            def changed(path):
                actual,entries=original(path)
                return ('/unexpected',entries) if path==ROOT else (actual,entries)
            with patch.object(adapter,'list_directory',side_effect=changed):result=self.execute(core,target)
            self.assertTrue(result.result.uncertain)
            self.assertEqual([(b'MKD',ROOT.encode())],[(v,p) for v,p in server.commands if v in MUTATIONS])

    def test_definite_child_refusal_cleans_only_created_prefix(self):
        with self.fixture(before_command=lambda v,p:b'550 Refused\r\n' if v==b'MKD' and p.endswith(b'/metadata') else None) as (server,core,target):
            result=self.execute(core,target)
            self.assertFalse(result.result.uncertain)
            self.assertEqual((ROOT+'/games',ROOT),result.result.removed)
            self.assertEqual([(b'RMD',(ROOT+'/games').encode()),(b'RMD',ROOT.encode())],
                [(v,p) for v,p in server.commands if v==b'RMD'])
            self.assertNotIn(b'STOR',server.verbs)
