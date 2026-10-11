"""Offline versioned policy compatibility; no device or transfer fixtures."""
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from c64u_browser.api import BrowserError
from c64u_browser.app_preferences import defaults, validate
from c64u_browser.profiles import Preferences
from c64u_browser.import_transaction import Budgets, Journal, Transaction, TransactionError, MiB
from c64u_browser.import_policy import (ImportPolicy, TransactionV2, JournalV2,
    ResourceAccounting, prepare_transaction_v2)
from c64u_browser.import_journal import encode, decode, JournalStore
from c64u_browser.import_plan import MAX_SOURCE_BYTES
from tests.test_import_transaction import TransactionFixture


class PolicyTests(TransactionFixture, unittest.TestCase):
    def v2(self, options=None, first=None, second=None):
        return prepare_transaction_v2(first or self.first, second or self.second,
            library=self.f.library.identity, session=self.f.session, revision=0,
            manifest_digest=self.second.manifest_sha256, app_options=options or {})

    def test_v1_roundtrip_retains_original_contract(self):
        raw=encode(Journal(self.tx)); restored=decode(raw)
        self.assertIs(type(restored),Journal)
        self.assertIs(type(restored.transaction),Transaction)
        self.assertIs(type(restored.transaction.budgets),Budgets)
        self.assertEqual(raw,encode(restored)); self.assertEqual(1,restored.schema_version)
        for key in ('snapshot_bytes','spool_bytes','upload_bytes','readback_bytes'):
            self.assertEqual(128*MiB,getattr(restored.transaction.budgets,key))
            replace(Budgets(),**{key:128*MiB}).validate()
            with self.assertRaises(TransactionError):replace(Budgets(),**{key:128*MiB+1}).validate()
            with self.assertRaises(TransactionError):replace(Budgets(),**{key:0}).validate()

    def test_v1_invalid_records_still_rejected(self):
        for change in ({'schema_version':0},{'state':'staging'},{'authorized':True}):
            data=json.loads(encode(Journal(self.tx)));data.update(change)
            with self.assertRaises(TransactionError):decode(json.dumps(data).encode())
        data=json.loads(encode(Journal(self.tx)))
        data['transaction']['budgets']['upload_bytes']=129*MiB
        with self.assertRaises(TransactionError):decode(json.dumps(data).encode())

    def test_policy_capture_is_immutable_and_no_network(self):
        options={'import_batch_mib':256,'import_temp_mib':1024}
        calls=list(self.f.calls)
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):tx=self.v2(options)
        options['import_batch_mib']=1
        self.assertEqual(256*MiB,tx.budgets.batch_payload_limit)
        self.assertEqual(1024*MiB,tx.budgets.temporary_disk_limit)
        self.assertEqual(512*MiB,tx.budgets.upload_allowance)
        self.assertEqual(calls,self.f.calls)
        for obj,key in ((tx,'id'),(tx.budgets,'batch_payload_limit')):
            with self.assertRaises(FrozenInstanceError):setattr(obj,key,0)
        self.assertEqual(256*MiB,MAX_SOURCE_BYTES)

    def test_payload_excludes_verification_rereads(self):
        tx=self.v2();size=sum(i.size for i in tx.items)
        self.assertEqual(size,tx.budgets.selected_payload_bytes)
        self.assertEqual(size,tx.budgets.planned_upload_bytes)
        self.assertEqual(size,tx.budgets.planned_readback_bytes)
        self.assertGreater(self.second.source_bytes_read,size)
        self.assertEqual(ResourceAccounting(),JournalV2(tx).accounting)

    def test_duplicate_selection_counts_payload_once_per_selected_source(self):
        sources=(self.f.source('a.crt'),self.f.source('b.crt'))
        tx=self.v2(first=self.f.prepare(*sources),second=self.f.prepare(*sources))
        self.assertEqual(1,tx.skipped_duplicates)
        self.assertEqual(2*tx.items[0].size,tx.budgets.selected_payload_bytes)
        self.assertEqual(tx.items[0].size,tx.budgets.planned_upload_bytes)

    def test_policy_limits_exact_and_over(self):
        for batch,disk in ((1,1),(128,512),(4096,8192)):
            policy=ImportPolicy(batch*MiB,disk*MiB,MiB,MiB,MiB,MiB,MiB,MiB)
            policy.validate()
            for key,value in (('batch_payload_limit',4096*MiB+1),('temporary_disk_limit',8192*MiB+1),
                ('selected_payload_bytes',batch*MiB+1),('planned_upload_bytes',MiB+1),
                ('planned_readback_bytes',MiB+1),('upload_allowance',8192*MiB+1),
                ('readback_allowance',MiB-1),('snapshot_read_allowance',True),('files',65),
                ('journal_bytes',1048577),('operations',257)):
                with self.subTest(key=key),self.assertRaises(TransactionError):replace(policy,**{key:value}).validate()
        policy=ImportPolicy(256*MiB,256*MiB,256*MiB,256*MiB,256*MiB,256*MiB,256*MiB,256*MiB)
        policy.validate()
        with self.assertRaises(TransactionError):replace(policy,temporary_disk_limit=256*MiB-1).validate()

    def test_v2_identity_paths_and_evidence_not_weakened(self):
        tx=self.v2()
        for changes in ({'session_id':''},{'manifest_digest':'bad'},{'plan_id':tx.revalidated_plan_id},
                        {'items':(replace(tx.items[0],staged_path='../bad'),)},
                        {'budgets':replace(tx.budgets,planned_upload_bytes=tx.items[0].size+1)}):
            with self.subTest(changes=changes),self.assertRaises(TransactionError):replace(tx,**changes).validate()
        with self.assertRaises(TransactionError):self.v2(second=self.first)

    def test_v2_roundtrip_and_inspection_only_store(self):
        journal=JournalV2(self.v2())
        with tempfile.TemporaryDirectory() as folder:
            store=JournalStore(folder);store.save(journal)
            restored=store.load(journal.transaction.id)
            self.assertEqual(journal,restored);self.assertIs(type(restored),JournalV2)
            next_record=journal.transition('awaiting-confirmation')
            store.save(next_record,previous=journal)
            self.assertEqual(next_record,store.load(journal.transaction.id))
            with self.assertRaises(TransactionError):store.save(journal,previous=journal)
        self.assertEqual(journal,decode(encode(journal)))

    def test_no_automatic_version_conversion(self):
        v1=Journal(self.tx);v2=JournalV2(replace(self.v2(),id=self.tx.id,
            items=tuple(replace(i,staged_path=self.tx.items[n].staged_path) for n,i in enumerate(self.v2().items))))
        with tempfile.TemporaryDirectory() as folder:
            store=JournalStore(folder);store.save(v1)
            with self.assertRaises(TransactionError):store.save(v2,previous=v1)
            self.assertEqual(v1,store.load(self.tx.id))
        for journal,version in ((v1,2),(JournalV2(self.v2()),1)):
            data=json.loads(encode(journal));data['schema_version']=version
            with self.assertRaises(TransactionError):decode(json.dumps(data).encode())

    def test_execution_states_remain_reserved(self):
        for journal in (Journal(self.tx),JournalV2(self.v2())):
            for state in ('staging','verifying','verified-staged','published'):
                with self.assertRaises(TransactionError):replace(journal,state=state).validate()
                with self.assertRaises(TransactionError):journal.transition(state)
                data=json.loads(encode(journal));data['state']=state
                with self.assertRaises(TransactionError):decode(json.dumps(data).encode())
            with self.assertRaises(TransactionError):journal.intent('mkdir',journal.transaction.directory)
            data=json.loads(encode(journal));data['authorization']='confirmed'
            with self.assertRaises(TransactionError):decode(json.dumps(data).encode())

    def test_accounting_is_evidence_not_allowance(self):
        journal=JournalV2(self.v2())
        observation=ResourceAccounting(upload_bytes=journal.transaction.budgets.upload_allowance+1)
        with self.assertRaises(TransactionError):replace(journal,accounting=observation).validate()
        failed=replace(journal,state='failed',reason='uncertain-prior-observation',accounting=observation)
        self.assertEqual(failed,decode(encode(failed)))
        for value in (-1,True,2**63):
            with self.assertRaises(TransactionError):replace(observation,upload_bytes=value).validate()

    def test_bounded_encoding_corruption_and_utf8(self):
        journal=JournalV2(self.v2());raw=encode(journal)
        for payload in (raw[:-2],raw+b'x',b'\xff',b' '*1048577):
            with self.assertRaises(TransactionError):decode(payload)
        for value in ('x'*4097,'\ud800'):
            with self.assertRaises(TransactionError):encode(replace(journal,state='failed',reason=value))
        exact=replace(journal,transaction=replace(journal.transaction,
            budgets=replace(journal.transaction.budgets,journal_bytes=len(raw))))
        # Encoding the smaller ceiling changes its decimal width; find the exact fixed point.
        for unused in range(3):
            size=len(encode(exact))
            exact=replace(exact,transaction=replace(exact.transaction,
                budgets=replace(exact.transaction.budgets,journal_bytes=size)))
        self.assertEqual(len(encode(exact)),exact.transaction.budgets.journal_bytes)
        with self.assertRaises(TransactionError):encode(replace(exact,transaction=replace(exact.transaction,
            budgets=replace(exact.transaction.budgets,journal_bytes=size-1))))


class ImportPreferenceTests(unittest.TestCase):
    def test_defaults_bounds_and_invalid_values(self):
        self.assertEqual(128,defaults()['import_batch_mib']);self.assertEqual(512,defaults()['import_temp_mib'])
        for key,maximum in (('import_batch_mib',4096),('import_temp_mib',8192)):
            for value in (1,maximum):self.assertEqual(value,validate({key:value})[key])
            for value in (0,-1,maximum+1,True,None,'128',1.0):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):validate({key:value})

    def test_persistence_corruption_and_failed_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prefs.json';prefs=Preferences(path)
            prefs.app_options.update(import_batch_mib=4096,import_temp_mib=8192);prefs.save()
            self.assertEqual(prefs.app_options,Preferences(path).load().app_options)
            original=path.read_bytes();prefs.app_options['import_batch_mib']=0
            with self.assertRaises(ValueError):prefs.save()
            self.assertEqual(original,path.read_bytes())
            prefs.app_options['import_batch_mib']=1
            with patch('c64u_browser.profiles.os.replace',side_effect=OSError('disk')):
                with self.assertRaises(OSError):prefs.save()
            self.assertEqual(original,path.read_bytes());self.assertEqual(['prefs.json'],[p.name for p in path.parent.iterdir()])
            data=json.loads(original);data['app_options']['import_temp_mib']=None
            path.write_text(json.dumps(data));corrupt=path.read_bytes()
            with self.assertRaises(BrowserError):Preferences(path).load()
            self.assertEqual(corrupt,path.read_bytes())
