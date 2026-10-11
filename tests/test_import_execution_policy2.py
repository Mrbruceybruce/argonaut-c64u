"""Offline policy isolation, canonical record and checkpoint contract adversaries."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from c64u_browser.import_execution import (ExecutionJournal, ExecutionOperation, ExecutionAccounting as A,
    intent, outcome, transition, validate_successor)
from c64u_browser.import_execution_policy2 import encode_record, record_expectation, validate_record
from c64u_browser.import_capacity import planned_operations, reserve_capacity
from c64u_browser.import_execution_store import ExecutionJournalStore
from c64u_browser.import_journal import encode, decode
from c64u_browser.import_transaction import TransactionError, MAX_JOURNAL_BYTES

FIXTURE = Path(__file__).parent/'fixtures'/'import_execution_policy1.jsonl'


class Policy2Tests(unittest.TestCase):
    def setUp(self):
        self.socket = patch('socket.socket', side_effect=AssertionError('network forbidden'))
        self.socket.start(); self.addCleanup(self.socket.stop)
        self.old = decode(FIXTURE.read_bytes().splitlines(keepends=True)[0]).transaction
        self.tx = replace(self.old, execution_policy_version=2)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = ExecutionJournalStore(self.root)

    def start(self, tx=None):
        w = self.store.create_reserved(tx or self.tx)
        w.transition('awaiting-confirmation', previous=w.current)
        w.transition('staging', previous=w.current)
        return w

    def values(self, tx, kind, path):
        if kind == 'snapshot-validation':
            size = tx.budgets.planned_upload_bytes
            return dict(size=size, accounting=A(snapshot_validation_reads=size))
        if kind in ('mkdir', 'final-validation'):return dict(accounting=A(control_read_bytes=7))
        if kind.startswith('record-'):
            size, digest = record_expectation(tx)
            return dict(size=size, sha256=digest, accounting=(A(control_upload_bytes=size) if kind == 'record-upload' else A(control_read_bytes=size)))
        item = next(i for i in tx.items if i.staged_path == path)
        return dict(size=item.size, sha256=item.sha256, accounting=(
            A(attempted_upload_bytes=item.size, confirmed_sender_bytes=item.size) if kind == 'upload' else A(readback_bytes=item.size)))

    def begin(self, w, kind, path):
        oid = str(uuid4())
        w.intent(oid, kind, path, previous=w.current,
                 collision='absent' if kind in ('mkdir', 'record-upload', 'upload') else 'not-applicable')
        return oid

    def prefix(self, w, count):
        plan = planned_operations(w.current.transaction)
        for kind, path in plan[len(w.current.operations):count]:
            if kind == 'record-readback':w.transition('verifying', previous=w.current)
            oid = self.begin(w, kind, path)
            w.outcome(oid, 'completed', previous=w.current, **self.values(w.current.transaction, kind, path))
        return w

    def test_policy1_golden_bytes_chain_and_capacity_unchanged(self):
        previous = None
        lines = FIXTURE.read_bytes().splitlines(keepends=True)
        self.assertEqual(15, len(lines))
        self.assertEqual(36581, sum(map(len, lines)))
        for raw in lines:
            j = decode(raw); self.assertEqual(raw, encode(j))
            self.assertEqual(1, j.transaction.execution_policy_version)
            if previous is not None:validate_successor(previous, j)
            target = self.root/self.store._filename(j.transaction.id, j.revision)
            target.write_bytes(raw); target.chmod(0o600)
            previous = j
        self.assertEqual(previous, self.store.load(self.old.id))
        c = reserve_capacity(self.old)
        self.assertEqual((4688, 16, 75008), (c.checkpoint_bytes, c.revisions, c.aggregate_bytes))
        with self.assertRaises(ValueError):self.store.save(previous)

    def test_complete_chain_crash_reload_at_every_checkpoint(self):
        w = self.start(); tx = w.current.transaction
        for n in range(1, len(planned_operations(tx))+1):
            self.prefix(w, n)
            self.assertEqual(w.current, self.store.load(tx.id))
        w.transition('verified-staged', previous=w.current)
        files = sorted(self.root.glob('*.execution-*')); previous = None
        for p in files:
            j = decode(p.read_bytes()); self.assertEqual(p.read_bytes(), encode(j))
            if previous is not None:validate_successor(previous, j)
            # A process crash can leave precisely this prefix; load never grants authority.
            with tempfile.TemporaryDirectory() as folder:
                store = ExecutionJournalStore(folder)
                for earlier in files[:j.revision+1]:
                    target = Path(folder, earlier.name)
                    target.write_bytes(earlier.read_bytes()); target.chmod(0o600)
                loaded = store.load(tx.id); self.assertEqual(j, loaded)
                with self.assertRaises(ValueError):store.save(loaded)
                with self.assertRaises(TransactionError):store.create_reserved(tx)
                self.assertFalse(hasattr(loaded, 'outcome'))
            previous = j
        reservation = w._reservation
        self.assertEqual(2*len(planned_operations(tx))+5, len(files))
        self.assertEqual(sum(p.stat().st_size for p in files), reservation.used_bytes)
        self.assertLessEqual(reservation.used_bytes, reservation.capacity.aggregate_bytes)
        with self.assertRaises(TransactionError):w.transition('staging', previous=w.current)

    def test_record_upload_acknowledged_with_readback_pending(self):
        w = self.prefix(self.start(), 3)
        op = w.current.operations[-1]
        self.assertEqual('record-upload', op.kind); self.assertEqual('completed', op.outcome)
        self.assertEqual(0, op.accounting.control_read_bytes)
        self.assertEqual('staging', w.current.state)
        self.assertEqual(w.current, decode(encode(w.current)))
        with self.assertRaises(TransactionError):w.transition('verified-staged', previous=w.current)

    def test_cancel_immediately_after_each_acknowledged_mutation(self):
        for count in (2, 3, 4):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                self.store = ExecutionJournalStore(directory)
                w = self.prefix(self.start(), count-1)
                kind, path = planned_operations(self.tx)[count-1]; oid = self.begin(w, kind, path)
                w.outcome(oid, 'completed', previous=w.current, terminal_state='canceled', reason='user-canceled', **self.values(self.tx, kind, path))
                self.assertEqual('completed', w.current.operations[-1].outcome)
                self.assertEqual('canceled', self.store.load(self.tx.id).state)
                with self.assertRaises(TransactionError):w.transition('staging', previous=w.current)

    def test_cancellation_between_upload_and_verification(self):
        w = self.prefix(self.start(), 4); w.transition('canceled', previous=w.current, reason='user-canceled')
        self.assertEqual(4, w.current.checkpoint)
        self.assertFalse(any(o.kind == 'readback' for o in w.current.operations))

    def test_final_validation_required(self):
        w = self.prefix(self.start(), len(planned_operations(self.tx))-1)
        with self.assertRaises(TransactionError):w.transition('verified-staged', previous=w.current)
        oid = self.begin(w, 'final-validation', self.tx.directory)
        with self.assertRaises(TransactionError):w.transition('verified-staged', previous=w.current)
        w.outcome(oid, 'completed', previous=w.current, accounting=A(control_read_bytes=19))
        w.transition('verified-staged', previous=w.current)
        self.assertEqual(19, w.current.operations[-1].accounting.control_read_bytes)

    def test_early_verifying_and_published_rejected(self):
        w = self.prefix(self.start(), 3)
        for state in ('verifying', 'verified-staged', 'published'):
            with self.assertRaises(TransactionError):w.transition(state, previous=w.current)

    def test_unknown_policies_and_policy_change_rejected(self):
        for value in (None, True, 0, 3, '2', 2.0):
            with self.subTest(value=value), self.assertRaises(TransactionError):replace(self.tx, execution_policy_version=value).validate()
        old = ExecutionJournal(self.old)
        changed = transition(ExecutionJournal(self.tx), 'awaiting-confirmation')
        with self.assertRaises(TransactionError):validate_successor(old, changed)

    def test_mixed_operation_names_rejected(self):
        for policy, forbidden in ((1, 'record-upload'), (2, 'record')):
            with tempfile.TemporaryDirectory() as directory:
                self.store = ExecutionJournalStore(directory); tx = replace(self.tx, execution_policy_version=policy)
                w = self.prefix(self.start(tx), 2)
                with self.assertRaises(TransactionError):self.begin(w, forbidden, tx.record_path)

    def test_wrong_kind_path_ordinal_duplicate_uuid_and_intent_io(self):
        w = self.prefix(self.start(), 2); oid = self.begin(w, 'record-upload', self.tx.record_path)
        j = w.current; op = j.operations[-1]
        for changes in (dict(kind='upload'), dict(path='games/other.crt'), dict(sequence=2),
                        dict(id=j.operations[0].id), dict(size=1), dict(accounting=A(control_read_bytes=1))):
            with self.subTest(changes=changes), self.assertRaises(TransactionError):
                replace(j, operations=j.operations[:-1]+(replace(op, **changes),)).validate()
        with self.assertRaises(TransactionError):self.begin(w, 'upload', self.tx.items[0].staged_path)

    def two_items(self):
        first = self.tx.items[0]
        second = replace(first, staged_path=self.tx.directory+'/item-0002.'+first.format.lower(),
                         final_path='games/second.'+first.format.lower(), sha256='d'*64)
        size = first.size+second.size
        budgets = replace(self.tx.budgets, selected_payload_bytes=size, planned_upload_bytes=size, planned_readback_bytes=size)
        return replace(self.tx, items=(first, second), budgets=budgets,
                       limits=replace(self.tx.limits, snapshot_validation_reads=size)).validate()

    def test_payload_order_and_verification_order(self):
        tx = self.two_items(); w = self.prefix(self.start(tx), 3)
        with self.assertRaises(TransactionError):self.begin(w, 'upload', tx.items[1].staged_path)
        self.prefix(w, 6)  # two uploads and record readback
        with self.assertRaises(TransactionError):self.begin(w, 'readback', tx.items[1].staged_path)
        with self.assertRaises(TransactionError):self.begin(w, 'final-validation', tx.directory)
        self.prefix(w, len(planned_operations(tx))); w.transition('verified-staged', previous=w.current)

    def test_verification_intent_requires_verifying(self):
        w = self.prefix(self.start(), 4)
        with self.assertRaises(TransactionError):self.begin(w, 'record-readback', self.tx.record_path)
        w.transition('verifying', previous=w.current)
        with self.assertRaises(TransactionError):self.begin(w, 'upload', self.tx.items[0].staged_path)

    def test_record_exact_bytes_allowlist_and_digest(self):
        raw = encode_record(self.tx); document = json.loads(raw)
        self.assertEqual(raw, encode_record(self.tx)); self.assertEqual(b'\n', raw[-1:])
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), record_expectation(self.tx))
        self.assertEqual(raw, validate_record(raw, self.tx))
        self.assertEqual({'format_version','journal_schema_version','execution_policy_version','policy_version','transaction_id','plan_digest','library','manifest','directory','items'}, set(document))
        self.assertEqual(self.tx.library.root, document['library']['root'])
        self.assertNotIn('session_id', document); self.assertNotIn('snapshot_evidence_sha256', document)
        self.assertEqual({'staged_path','final_path','format','size','sha256'}, set(document['items'][0]))
        for forbidden in ('source', 'credentials', 'authorization', 'runtime'):
            altered = dict(document); altered[forbidden] = 'not-allowed'
            with self.assertRaises(TransactionError):validate_record(json.dumps(altered).encode(), self.tx)
        for altered in (raw[:-1], raw+b'\n', b' '+raw, json.dumps(document, indent=2).encode(), b'{}', bytearray(raw)):
            with self.assertRaises(TransactionError):validate_record(altered, self.tx)

    def test_record_rejects_invalid_version_transaction_and_oversize(self):
        for version in (0, 2, True, None, '1'):
            with self.assertRaises(TransactionError):encode_record(self.tx, format_version=version)
        with self.assertRaises(TransactionError):encode_record(self.old)
        with self.assertRaises(TransactionError):encode_record({'id': self.tx.id})
        with self.assertRaises(TransactionError):encode_record(replace(self.tx, id='invalid'))
        with self.assertRaises(TransactionError):validate_record(b'x'*(MAX_JOURNAL_BYTES+1), self.tx)
        size = len(encode_record(self.tx))
        for field in ('control_upload_bytes', 'control_read_bytes'):
            with self.assertRaises(TransactionError):encode_record(replace(self.tx, limits=replace(self.tx.limits, **{field:size-1})))
        with self.assertRaises(TransactionError):encode_record(replace(self.tx, budgets=replace(self.tx.budgets, journal_bytes=size-1)))
        self.assertEqual(size, len(encode_record(replace(self.tx, limits=replace(self.tx.limits, control_upload_bytes=size)))))

    def test_canonical_record_utf8_and_immutable_identity(self):
        item = replace(self.tx.items[0], final_path='games/café.crt')
        tx = replace(self.tx, items=(item,))
        self.assertIn('café'.encode(), encode_record(tx))
        with self.assertRaises(TransactionError):validate_record(encode_record(self.tx), tx)

    def test_record_and_payload_completed_hash_and_length_are_exact(self):
        for ordinal in (3, 4, 5, 6):
            with tempfile.TemporaryDirectory() as directory:
                self.store = ExecutionJournalStore(directory); w = self.prefix(self.start(), ordinal-1)
                kind, path = planned_operations(self.tx)[ordinal-1]
                if kind == 'record-readback':w.transition('verifying', previous=w.current)
                oid = self.begin(w, kind, path); original = w.current
                valid = self.values(self.tx, kind, path)
                for digest in ('e'*64, '', None, False, True, 0, -1, 1.0, [], {}, 'A'*64, 'aA'*32, 'a'*63, ' '*64):
                    with self.subTest(kind=kind, digest=digest), self.assertRaises(TransactionError):
                        w.outcome(oid, 'completed', previous=original, **{**valid, 'sha256':digest})
                    self.assertIs(original, w.current); self.assertFalse(w.blocked)
                for size in (0, valid['size']-1, valid['size']+1):
                    with self.assertRaises(TransactionError):w.outcome(oid, 'completed', previous=original, **{**valid, 'size':size})

    def test_failed_readbacks_preserve_actual_short_overlong_mismatch(self):
        for ordinal in (5, 6):
            for delta in (-1, 0, 1):
                with tempfile.TemporaryDirectory() as directory:
                    self.store = ExecutionJournalStore(directory); w = self.prefix(self.start(), ordinal-1)
                    kind, path = planned_operations(self.tx)[ordinal-1]
                    if kind == 'record-readback':w.transition('verifying', previous=w.current)
                    oid = self.begin(w, kind, path); expected = self.values(self.tx, kind, path)['size']; size=expected+delta
                    accounting = A(control_read_bytes=size) if kind == 'record-readback' else A(readback_bytes=size)
                    w.outcome(oid, 'rejected', previous=w.current, size=size, sha256='e'*64, accounting=accounting, reason='content-mismatch')
                    self.assertEqual(size, self.store.load(self.tx.id).operations[-1].size)
                    self.assertEqual('failed', w.current.state)
                    with self.assertRaises(TransactionError):w.transition('verified-staged', previous=w.current)

    def test_lost_reply_retains_payload_sender_partition(self):
        w = self.prefix(self.start(), 3); item=self.tx.items[0]; oid=self.begin(w, 'upload', item.staged_path)
        w.outcome(oid, 'unknown', previous=w.current, size=3, accounting=A(attempted_upload_bytes=8, confirmed_sender_bytes=3, uncertain_send_bytes=5), reason='lost-reply')
        self.assertEqual('uncertain', self.store.load(self.tx.id).state)
        with self.assertRaises(TransactionError):self.begin(w, 'record-readback', self.tx.record_path)

    def test_control_exposure_distinct_from_payload_accounting(self):
        w=self.prefix(self.start(),2);oid=self.begin(w,'record-upload',self.tx.record_path)
        with self.assertRaises(TransactionError):w.outcome(oid,'unknown',previous=w.current,size=9,accounting=A(control_upload_bytes=8),reason='lost-reply')
        w.outcome(oid,'unknown',previous=w.current,size=3,accounting=A(control_upload_bytes=8),reason='lost-reply')
        op=w.current.operations[-1]
        self.assertEqual(5,op.accounting.control_upload_bytes-op.size)
        self.assertEqual(0,w.current.accounting.attempted_upload_bytes)

    def test_disallowed_accounting_and_nonzero_final_fields(self):
        w=self.prefix(self.start(),6);oid=self.begin(w,'final-validation',self.tx.directory)
        for kwargs in (dict(size=1),dict(sha256='a'*64),dict(accounting=A(control_upload_bytes=1)),dict(accounting=A(readback_bytes=1))):
            with self.assertRaises(TransactionError):w.outcome(oid,'completed',previous=w.current,**kwargs)
        with self.assertRaises(TransactionError):A(attempted_upload_bytes=9,confirmed_sender_bytes=3,uncertain_send_bytes=5).validate()

    def test_collision_and_not_started_cannot_claim_writes(self):
        w=self.prefix(self.start(),2);oid=self.begin(w,'record-upload',self.tx.record_path)
        for status,extra in (('not-started',{}),('rejected',{'collision':'present'})):
            with self.assertRaises(TransactionError):w.outcome(oid,status,previous=w.current,accounting=A(control_upload_bytes=1),**extra)
        w.outcome(oid,'rejected',previous=w.current,collision='present',accounting=A(control_read_bytes=9))
        self.assertEqual('failed',w.current.state)

    def test_intent_and_outcome_persistence_failure_blocks_writer(self):
        for boundary in ('intent','outcome'):
            with tempfile.TemporaryDirectory() as directory:
                self.store=ExecutionJournalStore(directory);w=self.prefix(self.start(),2)
                if boundary=='outcome':oid=self.begin(w,'record-upload',self.tx.record_path)
                previous=w.current
                with patch.object(self.store,'_append',side_effect=OSError('sync failure')):
                    with self.assertRaises(OSError):
                        if boundary=='intent':self.begin(w,'record-upload',self.tx.record_path)
                        else:w.outcome(oid,'completed',previous=previous,**self.values(self.tx,'record-upload',self.tx.record_path))
                self.assertTrue(w.blocked);self.assertIs(previous,w.current)
                self.assertEqual(previous,self.store.load(self.tx.id))
                with self.assertRaises(TransactionError):w.transition('uncertain',previous=previous,reason='persistence-failed')

    def test_failure_after_durable_outcome_is_inspection_only(self):
        w=self.prefix(self.start(),2);oid=self.begin(w,'record-upload',self.tx.record_path);previous=w.current
        append=self.store._append
        def fail(journal,*,previous):append(journal,previous=previous);raise OSError('post-sync uncertainty')
        with patch.object(self.store,'_append',fail):
            with self.assertRaises(OSError):w.outcome(oid,'completed',previous=previous,**self.values(self.tx,'record-upload',self.tx.record_path))
        self.assertTrue(w.blocked);self.assertIs(previous,w.current)
        loaded=self.store.load(self.tx.id);self.assertEqual('completed',loaded.operations[-1].outcome)
        with self.assertRaises(ValueError):self.store.save(loaded)

    def test_capacity_formula_exact_boundary_and_one_byte_short(self):
        self.assertEqual(7,len(planned_operations(self.tx)))
        capacity=reserve_capacity(self.tx);self.assertEqual(20,capacity.revisions)
        bound=capacity.aggregate_bytes
        for _ in range(8):
            tx=replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=bound))
            new=reserve_capacity(tx).aggregate_bytes
            if new==bound:break
            bound=new
        self.assertEqual(bound,reserve_capacity(tx).aggregate_bytes)
        short=replace(tx,budgets=replace(tx.budgets,journal_bytes=bound-1))
        with self.assertRaises(TransactionError):self.store.create_reserved(short)
        self.assertFalse(list(self.root.iterdir()))
        with self.assertRaises(TransactionError):reserve_capacity(replace(self.tx,budgets=replace(self.tx.budgets,operations=6)))
        self.assertEqual(24,reserve_capacity(self.two_items()).revisions)

    def test_maximal_terminal_evidence_fits_reservation(self):
        w=self.prefix(self.start(),2);oid=self.begin(w,'record-upload',self.tx.record_path)
        maximum=2**63-1
        w.outcome(oid,'unknown',previous=w.current,size=maximum,sha256='f'*64,
                  accounting=A(control_upload_bytes=maximum,control_read_bytes=maximum-w.current.accounting.control_read_bytes),reason='x'*256)
        self.assertLessEqual(len(encode(w.current)),w._reservation.capacity.checkpoint_bytes)
        self.assertLessEqual(w._reservation.used_bytes,w._reservation.capacity.aggregate_bytes)

    def test_serialized_corruption_and_chain_policy_switch_rejected(self):
        w=self.prefix(self.start(),3);raw=json.loads(encode(w.current))
        for change in ('policy','field','hash','kind'):
            altered=json.loads(json.dumps(raw))
            if change=='policy':altered['transaction']['execution_policy_version']=99
            elif change=='field':altered['authorization']='not-authority'
            elif change=='hash':altered['operations'][-1]['sha256']=False
            else:altered['operations'][-1]['kind']='record'
            with self.assertRaises(TransactionError):decode(json.dumps(altered).encode())
        first=self.root/self.store._filename(self.tx.id,0)
        j=decode(first.read_bytes());first.write_bytes(encode(replace(j,transaction=self.old)))
        with self.assertRaises(TransactionError):self.store.load(self.tx.id)


if __name__ == '__main__':unittest.main()
