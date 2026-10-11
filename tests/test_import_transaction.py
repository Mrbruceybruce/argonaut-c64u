"""Offline transaction contracts and durable host evidence; no network fixtures."""
from dataclasses import FrozenInstanceError, replace
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from c64u_browser.import_transaction import (Budgets, Journal, OperationEvidence, TransactionError,
    MAX_FILES, MAX_JOURNAL_BYTES, MAX_OPERATIONS, MAX_SNAPSHOT_BYTES, prepare_transaction)
from c64u_browser.import_journal import JournalStore, encode, decode
from c64u_browser.import_plan import MAX_SOURCE_BYTES
from tests import test_import_plan as planner_tests
from tests.test_game_library import crt_bytes


class TransactionFixture:
    def setUp(self):
        self.f=planner_tests.ImportPlanTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        source=self.f.source()
        self.first=self.f.prepare(source);self.second=self.f.prepare(source)
        self.tx=self.make()

    def make(self,first=None,second=None,**overrides):
        kwargs=dict(library=self.f.library.identity,session=self.f.session,revision=0,
                    manifest_digest=self.second.manifest_sha256)
        kwargs.update(overrides)
        return prepare_transaction(first or self.first,second or self.second,**kwargs)

    def pair(self,**changes):
        return replace(self.first,**changes),replace(self.second,**changes)

    def active(self):
        return Journal(self.tx).transition('awaiting-confirmation')

    def uploaded(self):
        ops=(OperationEvidence(1,'mkdir',self.tx.directory,'completed'),
             OperationEvidence(2,'record',self.tx.record_path,'completed',32,'a'*64))
        for item in self.tx.items:
            ops+=(OperationEvidence(len(ops)+1,'upload',item.staged_path,'completed',item.size,item.sha256),)
        return Journal(self.tx,'failed',ops,len(ops),'disconnected').validate()


class TransactionTests(TransactionFixture, unittest.TestCase):
    def test_uuid_identity_paths_and_no_remote_operations(self):
        calls=list(self.f.calls)
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            other=self.make()
        self.assertNotEqual(self.tx.id,other.id);self.assertEqual(str(UUID(self.tx.id)),self.tx.id)
        self.assertEqual(calls,self.f.calls)
        self.assertEqual(self.tx.directory+'/item-0001.crt',self.tx.items[0].staged_path)
        self.assertEqual(self.tx.library.path+'/'+self.tx.directory,self.tx.recovery_location)

    def test_deep_immutability(self):
        for obj,name in ((self.tx,'id'),(self.tx.items[0],'size'),(self.tx.budgets,'files')):
            with self.assertRaises(FrozenInstanceError):setattr(obj,name,1)
        with self.assertRaises(TransactionError):replace(self.tx,items=list(self.tx.items)).validate()

    def test_revalidation_is_required_and_changed_evidence_rejected(self):
        with self.assertRaises(TransactionError):self.make(second=self.first)
        with self.assertRaises(TransactionError):self.make(second=replace(self.second,manifest_sha256='f'*64))
        with self.assertRaises(TransactionError):self.make(*self.pair(completion='partial'))

    def test_all_context_mismatches(self):
        for kwargs in (dict(library=replace(self.tx.library,library_id=str(uuid4()))),
                       dict(library=replace(self.tx.library,root='/USB1')),
                       dict(library=replace(self.tx.library,path='/USB1/ARGONAUT_LIBRARY')),
                       dict(session=replace(self.f.session,device_id='other')),
                       dict(session=replace(self.f.session,session_id='other')),
                       dict(revision=1),dict(manifest_digest='f'*64)):
            with self.subTest(kwargs=kwargs),self.assertRaises(TransactionError):self.make(**kwargs)

    def test_invalid_conflicting_unverified_candidates_block(self):
        for kind in ('invalid','conflict','unverified','invented'):
            items=(replace(self.first.items[0],classification=kind),)
            with self.subTest(kind=kind),self.assertRaises(TransactionError):self.make(*self.pair(items=items,transfer_bytes=0))

    def test_missing_hash_size_format_read_evidence(self):
        for change in (dict(sha256=''),dict(size=0),dict(size=True),dict(format='PRG')):
            with self.subTest(change=change),self.assertRaises(TransactionError):
                self.make(*self.pair(items=(replace(self.first.items[0],**change),)))
        for size in (0,MAX_SOURCE_BYTES+1):
            with self.assertRaises(TransactionError):self.make(*self.pair(source_bytes_read=size))

    def test_forged_duplicate_classification_rejected(self):
        for kind in ('same-name-duplicate','content-duplicate','batch-duplicate'):
            with self.assertRaises(TransactionError):self.make(*self.pair(
                items=(replace(self.first.items[0],classification=kind),),transfer_bytes=0))

    def test_mixed_new_and_batch_duplicate(self):
        sources=(self.f.source('a.crt'),self.f.source('b.crt'))
        first=self.f.prepare(*sources);second=self.f.prepare(*sources)
        tx=self.make(first,second)
        self.assertEqual(1,len(tx.items));self.assertEqual(1,tx.skipped_duplicates)

    def test_catalog_duplicate_only_rejected_and_mixed_skipped(self):
        self.f.existing()
        sources=(self.f.source('a.crt'),)
        first=self.f.prepare(*sources);second=self.f.prepare(*sources)
        with self.assertRaises(TransactionError):self.make(first,second,manifest_digest=second.manifest_sha256)
        sources+=(self.f.source('new.crt',crt_bytes(name='Different')),)
        first=self.f.prepare(*sources);second=self.f.prepare(*sources)
        tx=self.make(first,second,manifest_digest=second.manifest_sha256)
        self.assertEqual(1,len(tx.items));self.assertEqual(1,tx.skipped_duplicates)

    def test_paths_refuse_traversal_alias_absolute_and_collision(self):
        item=self.tx.items[0]
        for path in ('/USB1/evil','../evil',self.tx.directory+'/../evil',self.tx.directory+'//item-0001.crt',
                     self.tx.directory+'/item-0001.CRT'):
            with self.assertRaises(TransactionError):replace(self.tx,items=(replace(item,staged_path=path),)).validate()
        for path in ('games/../evil','/games/a.crt','games//a.crt','metadata/a.crt'):
            with self.assertRaises(TransactionError):replace(self.tx,items=(replace(item,final_path=path),)).validate()
        self.tx.require_absent(())
        for name in (self.tx.directory,self.tx.directory.upper()):
            with self.assertRaises(TransactionError):self.tx.require_absent((name,))

    def test_remote_source_and_session_validation(self):
        source=self.f.source(remote=True)
        first=self.f.prepare(source);second=self.f.prepare(source)
        tx=self.make(first,second);self.assertEqual((),tx.items[0].local_identity)
        item=replace(tx.items[0],source=replace(source,session_id='stale'))
        with self.assertRaises(TransactionError):replace(tx,items=(item,)).validate()

    def test_source_alias_and_missing_local_identity(self):
        item=self.tx.items[0]
        for path in ('/tmp/../a.crt','/tmp//a.crt'):
            bad=replace(item,source=replace(item.source,path=path))
            with self.assertRaises(TransactionError):replace(self.tx,items=(bad,)).validate()
        with self.assertRaises(TransactionError):replace(self.tx,items=(replace(item,local_identity=()),)).validate()

    def test_budget_boundaries_are_independent(self):
        size=self.tx.items[0].size
        for field in ('snapshot_bytes','spool_bytes','upload_bytes','readback_bytes'):
            self.make(budgets=replace(Budgets(),**{field:size}))
            with self.assertRaises(TransactionError):self.make(budgets=replace(Budgets(),**{field:size-1}))
        self.assertEqual(268435456,MAX_SOURCE_BYTES)
        self.assertEqual(134217728,MAX_SNAPSHOT_BYTES)
        for kwargs in (dict(files=65),dict(files=True),dict(journal_bytes=MAX_JOURNAL_BYTES+1),
                       dict(operations=MAX_OPERATIONS+1),dict(spool_bytes=0)):
            with self.assertRaises(TransactionError):replace(Budgets(),**kwargs).validate()

    def test_item_count_limit(self):
        with self.assertRaises(TransactionError):self.make(*self.pair(items=self.first.items*(MAX_FILES+1)))

    def test_valid_state_and_verified_evidence(self):
        waiting=self.active()
        self.assertEqual('awaiting-confirmation',decode(encode(waiting)).state)
        self.assertEqual('canceled',waiting.transition('canceled').state)
        for state in ('staging','verifying','verified-staged','published'):
            with self.subTest(state=state),self.assertRaises(TransactionError):waiting.transition(state)
            with self.assertRaises(TransactionError):replace(waiting,state=state).validate()

    def test_invalid_transitions_and_unverified_success(self):
        for state in ('staging','verifying','verified-staged','published','uncertain'):
            with self.assertRaises(TransactionError):Journal(self.tx).transition(state)
        raw=json.loads(encode(Journal(self.tx)))
        for state in ('staging','verifying','verified-staged','published','invalid'):
            raw['state']=state
            with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())

    def test_cancel_before_and_during_mutation_retains_intent(self):
        self.assertEqual('canceled',Journal(self.tx).transition('canceled',reason='user-request').state)
        op=OperationEvidence(1,'mkdir',self.tx.directory)
        j=Journal(self.tx,'canceled',(op,),0,'user-request').validate()
        self.assertEqual(j,decode(encode(j)));self.assertTrue(j.requires_inspection)
        with self.assertRaises(TransactionError):j.transition('staging')
        with self.assertRaises(TransactionError):j.outcome('completed')

    def test_partial_batch_failure_retains_completed_evidence(self):
        j=self.uploaded()
        self.assertEqual('completed',j.operations[-1].outcome)
        self.assertEqual(j,decode(encode(j)))
        with self.assertRaises(TransactionError):j.transition('verified-staged')

    def test_unknown_outcome_blocks_retry(self):
        op=OperationEvidence(1,'mkdir',self.tx.directory,'unknown')
        j=Journal(self.tx,'uncertain',(op,),0,'lost-reply').validate()
        self.assertTrue(j.requires_inspection)
        with self.assertRaises(TransactionError):j.intent('mkdir',self.tx.directory)
        self.assertEqual(j,decode(encode(j)))

    def test_readback_mismatch_and_operation_path_bounds(self):
        j=self.uploaded();item=self.tx.items[0]
        for size,sha in ((item.size-1,item.sha256),(item.size,'f'*64)):
            op=OperationEvidence(len(j.operations)+1,'readback',item.staged_path,'completed',size,sha)
            with self.assertRaises(TransactionError):replace(j,operations=j.operations+(op,),checkpoint=op.sequence).validate()
        for kind,path in (('delete',item.staged_path),('upload','games/a.crt'),('mkdir','../escape')):
            with self.assertRaises(TransactionError):Journal(self.tx,'failed',(OperationEvidence(1,kind,path),)).validate()

    def test_multi_file_partial_cancel_and_readback_cancel(self):
        sources=(self.f.source('a.crt'),self.f.source('b.crt',crt_bytes(name='Other')))
        self.tx=self.make(self.f.prepare(*sources),self.f.prepare(*sources))
        j=self.uploaded();first,second=self.tx.items
        partial=replace(j,state='canceled',operations=j.operations[:-1]+(
            OperationEvidence(4,'upload',second.staged_path),),checkpoint=3)
        self.assertEqual(partial,decode(encode(partial)))
        readback=OperationEvidence(5,'readback',first.staged_path,'completed',first.size,first.sha256)
        partial=replace(j,state='canceled',operations=j.operations+(readback,),checkpoint=5)
        self.assertEqual(partial,decode(encode(partial)))

    def test_record_count_and_unresolved_intent_boundaries(self):
        self.tx=replace(self.tx,budgets=replace(self.tx.budgets,operations=1))
        ops=(OperationEvidence(1,'mkdir',self.tx.directory),OperationEvidence(2,'record',self.tx.record_path))
        with self.assertRaises(TransactionError):Journal(self.tx,'failed',ops).validate()
        tx=replace(self.tx,budgets=Budgets())
        with self.assertRaises(TransactionError):Journal(tx,'failed',ops).validate()

    def test_rejected_record_cannot_claim_ownership_or_success(self):
        op=OperationEvidence(1,'mkdir',self.tx.directory,'rejected')
        j=Journal(self.tx,'failed',(op,),0,'destination-collision').validate()
        with self.assertRaises(TransactionError):replace(j,operations=j.operations+(
            OperationEvidence(2,'record',self.tx.record_path),)).validate()
        with self.assertRaises(TransactionError):j.transition('verified-staged')


class JournalTests(TransactionFixture, unittest.TestCase):
    # Inherit fixture helpers without duplicating the contract test suite below.
    def setUp(self):
        super().setUp()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.store=JournalStore(self.directory)
        self.journal=Journal(self.tx)

    def test_journal_roundtrip_and_restart(self):
        self.assertTrue(self.store.save(self.journal))
        self.assertEqual(self.journal,JournalStore(self.directory).load(self.tx.id))
        self.assertEqual(0o600,(self.directory/(self.tx.id+'.json')).stat().st_mode&0o777)
        next_=self.journal.transition('awaiting-confirmation')
        self.store.save(next_,previous=self.journal)
        self.assertEqual(next_,self.store.load(self.tx.id))
        with self.assertRaises(TransactionError):self.store.save(self.journal)
        with self.assertRaises(TransactionError):self.store.save(next_,previous=self.journal)

    def test_corrupt_truncated_duplicate_unknown_fields(self):
        data=encode(self.journal)
        for corrupt in (b'',data[:-2],b'{}',b'{"state":1,"state":2}',b'x'*(MAX_JOURNAL_BYTES+1)):
            with self.assertRaises(TransactionError):decode(corrupt)
        raw=json.loads(data);raw['password']='secret'
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())
        raw=json.loads(data);raw['transaction']['items'][0]['source']['credentials']='secret'
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())
        self.assertNotIn(b'password',data);self.assertNotIn(b'credentials',data)

    def test_journal_byte_limit(self):
        small=replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=1))
        with self.assertRaises(TransactionError):encode(Journal(small))

    def test_fsync_replace_order_and_failure_preserves_previous(self):
        self.store.save(self.journal);next_=self.journal.transition('awaiting-confirmation')
        calls=[];real_sync=os.fsync;real_replace=os.replace
        def sync(fd):calls.append('sync');return real_sync(fd)
        def rename(*a,**kw):calls.append('replace');return real_replace(*a,**kw)
        with patch('c64u_browser.import_journal.os.fsync',side_effect=sync),patch('c64u_browser.import_journal.os.replace',side_effect=rename):
            self.store.save(next_,previous=self.journal)
        self.assertEqual(['sync','replace','sync'],calls)
        failed=next_.transition('canceled')
        with patch('c64u_browser.import_journal.os.replace',side_effect=OSError('failure')):
            with self.assertRaises(OSError):self.store.save(failed,previous=next_)
        self.assertEqual(next_,self.store.load(self.tx.id))
        self.assertEqual([],list(self.directory.glob('journal-write-*')))

    def test_directory_sync_failure_is_not_silenced(self):
        real=os.fsync;calls=[]
        def sync(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError(errno.EIO,'disk error')
            return real(fd)
        with patch('c64u_browser.import_journal.os.fsync',side_effect=sync):
            with self.assertRaises(OSError):self.store.save(self.journal)
        self.assertEqual(self.journal,self.store.load(self.tx.id))

    def test_directory_sync_unsupported_is_reported(self):
        real=os.fsync;calls=[]
        def sync(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError(errno.EINVAL,'unsupported')
            return real(fd)
        with patch('c64u_browser.import_journal.os.fsync',side_effect=sync):
            self.assertFalse(self.store.save(self.journal))

    def test_execution_evidence_cannot_be_saved_as_authorization(self):
        self.store.save(self.journal)
        waiting=self.journal.transition('awaiting-confirmation');self.store.save(waiting,previous=self.journal)
        for state in ('staging','verifying','verified-staged'):
            with self.assertRaises(TransactionError):self.store.save(replace(waiting,state=state),previous=waiting)
        with self.assertRaises(TransactionError):self.store.save(self.uploaded(),previous=waiting)
        with self.assertRaises(TransactionError):waiting.intent('mkdir',self.tx.directory)
        self.assertEqual(waiting,self.store.load(self.tx.id))

    def test_symlink_private_directory_and_file_identity(self):
        link=self.directory/'other';link.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(OSError):JournalStore(link).save(self.journal)
        self.store.save(self.journal)
        target=self.directory/(self.tx.id+'.json');target.unlink();target.symlink_to('/dev/null')
        with self.assertRaises(OSError):self.store.load(self.tx.id)
        target.unlink();self.directory.chmod(0o755)
        with self.assertRaises(TransactionError):self.store.save(self.journal)
        self.directory.chmod(0o700)

    def test_recovery_count_quota_and_updates_at_limit(self):
        self.store.save(self.journal)
        with patch('c64u_browser.import_journal.MAX_RECOVERY_JOURNALS',1):
            with self.assertRaises(TransactionError):self.store.save(Journal(self.make()))
            self.store.save(self.journal.transition('canceled'),previous=self.journal)

    def test_file_sync_failure_does_not_publish(self):
        with patch('c64u_browser.import_journal.os.fsync',side_effect=OSError(errno.EIO,'disk error')):
            with self.assertRaises(OSError):self.store.save(self.journal)
        self.assertFalse((self.directory/(self.tx.id+'.json')).exists())
        self.assertEqual([],list(self.directory.glob('journal-write-*')))

    def test_exact_journal_size_and_one_byte_over(self):
        j=Journal(replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=4096)))
        data=encode(j);exact=data+b' '*(4096-len(data))
        self.assertEqual(j,decode(exact))
        with self.assertRaises(TransactionError):decode(exact+b' ')

    def test_restart_rejects_wrong_identity_and_corrupt_evidence(self):
        self.store.save(self.journal)
        other=str(uuid4());(self.directory/(self.tx.id+'.json')).rename(self.directory/(other+'.json'))
        with self.assertRaises(TransactionError):self.store.load(other)
        raw=json.loads(encode(self.journal));raw['state']='verified-staged'
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())
        raw['state']='prepared';raw['schema_version']=True
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())


class SafetyCorrectionTests(TransactionFixture, unittest.TestCase):
    def assert_invalid(self,journal):
        with self.assertRaises(TransactionError):journal.validate()
        from c64u_browser.import_transaction import canonical
        with self.assertRaises(TransactionError):decode(json.dumps(canonical(journal)).encode())

    def test_each_reserved_transition_and_constructor(self):
        for base in (Journal(self.tx),self.active(),self.uploaded()):
            for state in ('staging','verifying','verified-staged','published'):
                with self.subTest(base=base.state,state=state):
                    with self.assertRaises(TransactionError):base.transition(state)
                    self.assert_invalid(replace(base,state=state))

    def test_forged_persisted_confirmation_is_not_authorization(self):
        for field in ('confirmed','authorized','admission','execution_token'):
            raw=json.loads(encode(self.active()));raw[field]=True
            with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())
        with self.assertRaises(TransactionError):self.active().intent('upload',self.tx.items[0].staged_path)
        with self.assertRaises(TransactionError):self.active().outcome('completed')

    def test_staging_readback_and_terminal_success_contradictions(self):
        j=self.uploaded();item=self.tx.items[0]
        op=OperationEvidence(4,'readback',item.staged_path,'completed',item.size,item.sha256)
        for state in ('staging','verifying','verified-staged','canceled','failed','uncertain'):
            self.assert_invalid(replace(j,state=state,operations=j.operations+(op,),checkpoint=4))

    def test_ordering_checkpoint_and_malformed_evidence(self):
        j=self.uploaded()
        self.assert_invalid(replace(j,checkpoint=0))
        self.assert_invalid(replace(j,operations=j.operations[1:],checkpoint=2))
        self.assert_invalid(replace(j,operations=(replace(j.operations[0],sequence=True),)+j.operations[1:]))
        self.assert_invalid(replace(j,operations=j.operations[:-1]+(replace(j.operations[-1],outcome='verified'),)))
        self.assert_invalid(Journal(self.tx,'canceled',(OperationEvidence(1,'mkdir',self.tx.directory),),1))
        self.assert_invalid(Journal(self.tx,'uncertain'))

    def test_readback_requires_all_uploads_and_no_later_upload(self):
        sources=(self.f.source('a.crt'),self.f.source('b.crt',crt_bytes(name='Other')))
        self.tx=self.make(self.f.prepare(*sources),self.f.prepare(*sources));j=self.uploaded()
        item=self.tx.items[0]
        read=OperationEvidence(4,'readback',item.staged_path,'completed',item.size,item.sha256)
        self.assert_invalid(replace(j,operations=j.operations[:3]+(read,),checkpoint=4))

    def test_large_timestamp_rejected_before_encoder(self):
        for timestamp in ('2026-10-11T00:00:00.'+'0'*100+'+00:00','x'*(2*1024*1024)):
            bad=Journal(replace(self.tx,created_at=timestamp))
            with patch('c64u_browser.import_journal.canonical',side_effect=AssertionError('conversion reached')):
                with self.assertRaises(TransactionError):encode(bad)

    def test_oversized_paths_filenames_and_identifiers(self):
        item=self.tx.items[0]
        candidates=(replace(self.tx,session_id='s'*257),
                    replace(self.tx,library=replace(self.tx.library,path='/'+'p'*4096)),
                    replace(self.tx,items=(replace(item,source=replace(item.source,path='/'+'p'*4096)),)),
                    replace(self.tx,items=(replace(item,source=replace(item.source,filename='x'*256+'.crt')),)),
                    replace(self.tx,id='i'*5000))
        for tx in candidates:
            with self.assertRaises(TransactionError):encode(Journal(tx))

    def test_oversized_reason_recovery_fields_and_evidence(self):
        with self.assertRaises(TransactionError):encode(Journal(self.tx,'failed',reason='e'*257))
        raw=json.loads(encode(Journal(self.tx)));raw['recovery_notes']='n'*5000
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())
        ops=(OperationEvidence(1,'mkdir',self.tx.directory),)*257
        with self.assertRaises(TransactionError):encode(Journal(self.tx,'failed',ops))
        bad=replace(self.uploaded(),operations=(OperationEvidence(1,'mkdir','x'*5000),))
        with self.assertRaises(TransactionError):encode(bad)

    def test_nested_collections_rejected_before_conversion_and_parsing(self):
        nested=()
        for _ in range(20):nested=(nested,)
        with self.assertRaises(TransactionError):encode(replace(Journal(self.tx),operations=nested))
        with patch('c64u_browser.import_journal.json.loads',side_effect=AssertionError('parser reached')):
            with self.assertRaises(TransactionError):decode(b'['*20+b'0'+b']'*20)

    def test_strict_utf8_and_unicode_roundtrip(self):
        j=Journal(self.tx,'failed',reason='échec')
        self.assertEqual(j,decode(encode(j)))
        with self.assertRaises(TransactionError):decode(b'\xff')
        with self.assertRaises(TransactionError):encode(Journal(replace(self.tx,session_id='\ud800')))
        raw=json.loads(encode(Journal(self.tx)));raw['transaction']['session_id']='\ud800'
        with self.assertRaises(TransactionError):decode(json.dumps(raw).encode())

    def test_bounded_encoder_exact_limit_and_one_byte_short(self):
        from c64u_browser.import_journal import canonical
        def raw_size(j):return len((json.dumps(canonical(j),sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode())
        j=Journal(self.tx)
        for _ in range(8):j=replace(j,transaction=replace(j.transaction,budgets=replace(j.transaction.budgets,journal_bytes=raw_size(j))))
        self.assertEqual(j.transaction.budgets.journal_bytes,len(encode(j)))
        with self.assertRaises(TransactionError):encode(replace(j,transaction=replace(j.transaction,
            budgets=replace(j.transaction.budgets,journal_bytes=j.transaction.budgets.journal_bytes-1))))
        with patch('c64u_browser.import_journal.json.dumps',side_effect=AssertionError('full JSON allocation')):
            self.assertEqual(j,decode(encode(j)))

    def test_truthful_over_budget_failure_evidence_survives(self):
        j=self.uploaded();item=self.tx.items[0]
        tx=replace(self.tx,budgets=replace(self.tx.budgets,upload_bytes=item.size))
        op=replace(j.operations[-1],outcome='unknown',size=item.size+1,sha256='')
        observed=Journal(tx,'uncertain',j.operations[:-1]+(op,),2,'lost-reply')
        self.assertEqual(item.size+1,decode(encode(observed)).operations[-1].size)
        with self.assertRaises(TransactionError):observed.transition('staging')

    def test_unsubmitted_intent_cannot_claim_bytes_or_checkpoint(self):
        j=self.uploaded()
        for op in (replace(j.operations[-1],outcome='intent'),
                   replace(j.operations[-1],outcome='intent',size=0)):
            self.assert_invalid(replace(j,operations=j.operations[:-1]+(op,),checkpoint=2))

    def test_recovery_load_is_inspection_only_and_not_resavable_as_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=JournalStore(tmp)
            for j in (self.uploaded(),Journal(self.tx,'canceled',
                      (OperationEvidence(1,'mkdir',self.tx.directory),)),
                      Journal(self.tx,'uncertain',(OperationEvidence(1,'mkdir',self.tx.directory,'unknown'),))):
                path=Path(tmp)/(self.tx.id+'.json');path.write_bytes(encode(j));path.chmod(0o600)
                with patch('socket.socket',side_effect=AssertionError('remote operation')):
                    loaded=store.load(self.tx.id)
                self.assertEqual(j,loaded);self.assertTrue(loaded.requires_inspection)
                with self.assertRaises(TransactionError):loaded.transition('awaiting-confirmation')
                with self.assertRaises(TransactionError):store.save(loaded)
