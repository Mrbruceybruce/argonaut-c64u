"""Independent byte fixture and policy-2 capacity proof boundaries; no transport."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from c64u_browser.import_execution import (ExecutionJournal, ExecutionOperation, ExecutionAccounting as A,
    ExecutionItem, ExecutionLimits, ExecutionTransaction, intent, outcome, transition)
from c64u_browser.import_execution_policy2 import encode_record, validate_record, record_expectation
from c64u_browser.import_capacity import reserve_capacity, planned_operations
from c64u_browser.import_journal import encode, decode
from c64u_browser.import_policy import ImportPolicy
from c64u_browser.import_transaction import TransactionError, MiB
from c64u_browser.managed_library import LibraryIdentity

FIXTURES = Path(__file__).parent/'fixtures'


def transaction(n=1, maximum=False):
    txid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    directory = 'argonaut-import-'+txid
    library = LibraryIdentity('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'fixture-é', '/SD', '/SD/Library 雪/ARGONAUT_LIBRARY')
    items = tuple(ExecutionItem(f'{directory}/item-{i:04d}.crt',
        'games/café "雪".crt' if n == 1 else f'games/game-{i}.crt', 'CRT', 8272, f'{i:064x}') for i in range(1,n+1))
    if n == 1:items = (replace(items[0], sha256='d'*64),)
    size = 8272*n
    tx = ExecutionTransaction(txid, 'e'*64, library, 'offline-session', 7, 'c'*64, 'a'*64,
        ImportPolicy(128*MiB, 512*MiB, size, size, size, 256*MiB, 256*MiB, 256*MiB),
        ExecutionLimits(size, MiB, 16*MiB), items, execution_policy_version=2)
    if maximum:
        tx = replace(tx, library=replace(library, device_id='"'*256, path='/SD/'+'雪'*4075+'/ARGONAUT_LIBRARY'),
            session_id='"'*256, manifest_revision=2**63-1,
            items=tuple(replace(i, final_path='games/'+str(k).zfill(3)+'雪"'*124+'.crt') for k,i in enumerate(items)))
    return tx.validate()


def independent_plan(tx):
    return [('snapshot-validation',''), ('mkdir',tx.directory), ('record-upload',tx.record_path)] + [
        ('upload',i.staged_path) for i in tx.items] + [('record-readback',tx.record_path)] + [
        ('readback',i.staged_path) for i in tx.items] + [('final-validation',tx.directory)]


def envelope(tx):
    # Specification oracle: explicit serialized keys/constants, no production
    # capacity, canonical conversion, operation factory or planner calls.
    maximum = 9223372036854775807
    account = dict(snapshot_validation_reads=maximum, attempted_upload_bytes=maximum,
        confirmed_sender_bytes=maximum, uncertain_send_bytes=maximum, readback_bytes=maximum,
        control_upload_bytes=maximum, control_read_bytes=maximum)
    ops = [dict(id='ffffffff-ffff-ffff-ffff-ffffffffffff', sequence=i, kind=k, path=p,
        outcome='not-started', size=maximum, sha256='f'*64, collision='not-applicable', accounting=account)
        for i,(k,p) in enumerate(independent_plan(tx),1)]
    doc = dict(transaction=asdict(tx), state='awaiting-confirmation', operations=ops,
        checkpoint=len(ops), reason='x'*256, revision=519, previous_digest='f'*64, schema_version=3)
    return len(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode())+1


def completed_values(tx, kind, path):
    if kind == 'snapshot-validation':return dict(size=tx.budgets.planned_upload_bytes, accounting=A(snapshot_validation_reads=tx.budgets.planned_upload_bytes))
    if kind in ('mkdir','final-validation'):return dict(accounting=A(control_read_bytes=1))
    if kind.startswith('record-'):
        size,digest=record_expectation(tx)
        return dict(size=size,sha256=digest,accounting=A(control_upload_bytes=size) if kind=='record-upload' else A(control_read_bytes=size))
    item=next(i for i in tx.items if i.staged_path==path)
    return dict(size=item.size,sha256=item.sha256,accounting=A(attempted_upload_bytes=item.size,confirmed_sender_bytes=item.size) if kind=='upload' else A(readback_bytes=item.size))


class EvidencePrerequisitesTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket', side_effect=AssertionError('network forbidden'))
        guard.start();self.addCleanup(guard.stop)

    def test_fixed_independent_record_bytes_length_hash_and_allowlist(self):
        raw=(FIXTURES/'import_record_format1.json').read_bytes();tx=transaction()
        self.assertEqual(783,len(raw))
        self.assertEqual('976046bb07cd1026167af565bec1fb2c36023c60754c8987d4462ade0ac17535',hashlib.sha256(raw).hexdigest())
        self.assertEqual(raw,encode_record(tx));self.assertEqual(raw,validate_record(raw,tx))
        self.assertEqual((783,hashlib.sha256(raw).hexdigest()),record_expectation(tx))
        self.assertEqual(1,raw.count(b'\n'));self.assertTrue(raw.endswith(b'\n'))
        self.assertIn('雪'.encode(),raw);self.assertIn(b'\\"',raw)
        doc=json.loads(raw)
        self.assertEqual({'directory','execution_policy_version','format_version','items','journal_schema_version','library','manifest','plan_digest','policy_version','transaction_id'},set(doc))
        self.assertEqual({'final_path','format','sha256','size','staged_path'},set(doc['items'][0]))
        self.assertEqual({'device_id','library_id','path','root'},set(doc['library']))
        self.assertEqual({'revision','sha256'},set(doc['manifest']))
        for bad in (raw[:-1],raw+b'\n',b' '+raw,json.dumps(doc).encode(),
                    raw.replace(b'8272',b'8273'),raw.replace(b'item-0001',b'item-0002'),
                    raw.replace(b'{',b'{"extra":0,',1),raw.replace('雪'.encode(),b'\\u96ea')):
            with self.subTest(bad=bad[:40]),self.assertRaises(TransactionError):validate_record(bad,tx)

    def test_all_counts_and_maximum_dimensions_against_independent_envelope(self):
        for n in range(1,65):
            for maximum in (False,True):
                with self.subTest(n=n,maximum=maximum):
                    tx=transaction(n,maximum);k=2*n+5;r=4*n+16;b=envelope(tx)
                    self.assertEqual(k,len(planned_operations(tx)))
                    self.assertEqual(independent_plan(tx),list(planned_operations(tx)))
                    if b*r <= MiB:
                        c=reserve_capacity(tx)
                        self.assertEqual((b,r,b*r),(c.checkpoint_bytes,c.revisions,c.aggregate_bytes))
                    else:
                        # Structural validity does not imply execution admission.
                        tx.validate()
                        with self.assertRaises(TransactionError):reserve_capacity(tx)
                    if maximum:
                        self.assertEqual(4096,len(tx.library.path));self.assertEqual(261,len(tx.items[0].final_path))
                        self.assertEqual(256,len(tx.session_id));self.assertEqual(256,len(tx.library.device_id))

    def test_exact_allowance_and_one_byte_below(self):
        for n in range(1,65):
            tx=transaction(n)
            if envelope(tx)*(4*n+16)>MiB:continue
            # Captured allowance itself changes serialized width; solve that
            # small fixed point using the independent oracle, never reservation.
            for _ in range(8):tx=replace(tx,budgets=replace(tx.budgets,journal_bytes=envelope(tx)*(4*n+16)))
            total=envelope(tx)*(4*n+16)
            self.assertEqual(total,tx.budgets.journal_bytes)
            self.assertEqual(total,reserve_capacity(tx).aggregate_bytes)
            with self.assertRaises(TransactionError):reserve_capacity(replace(tx,budgets=replace(tx.budgets,journal_bytes=total-1)))

    def test_every_operation_prefix_and_terminal_boundary(self):
        # Capacity tests construct checkpoints independently of transition/hash
        # helpers. History validity is covered separately by the chain suites.
        for n in (1,2,10,32,64):
            tx=transaction(n,True);bound=envelope(tx);r=4*n+16
            j=ExecutionJournal(tx);sizes=[len(encode(j))]
            def check(value):
                raw=encode(value);self.assertLessEqual(len(raw),bound)
                return len(raw)
            for state in ('awaiting-confirmation','staging'):
                for end in ('canceled','failed'):
                    check(replace(j,state=end,reason='x'*256,revision=519,previous_digest='f'*64))
                j=replace(j,state=state,revision=519,previous_digest='f'*64);sizes.append(check(j))
            for index,(kind,path) in enumerate(independent_plan(tx),1):
                if kind=='record-readback':j=replace(j,state='verifying');sizes.append(check(j))
                for end in ('canceled','failed','uncertain'):check(replace(j,state=end,reason='x'*256))
                oid=f'00000000-0000-4000-8000-{index:012d}'
                op=ExecutionOperation(oid,index,kind,path,collision='absent' if kind in ('mkdir','record-upload','upload') else 'not-applicable')
                pending=replace(j,operations=j.operations+(op,))
                sizes.append(check(pending));check(replace(pending,state='uncertain',reason='x'*256))
                for status in ('not-started','rejected','unknown'):
                    for end in (('uncertain',) if status=='unknown' else ('failed','canceled')):
                        check(replace(pending,operations=j.operations+(replace(op,outcome=status),),state=end,reason='x'*256))
                done=replace(op,outcome='completed',**completed_values(tx,kind,path))
                j=replace(j,operations=j.operations+(done,),checkpoint=index)
                for end in ('failed','canceled','uncertain'):check(replace(j,state=end,reason='x'*256))
                sizes.append(check(j))
            j=replace(j,state='verified-staged');sizes.append(check(j))
            self.assertEqual(r-1,len(sizes));self.assertLessEqual(sum(sizes)+bound,bound*r)

    def test_maximum_valid_counter_exposure_and_hash_reason_width(self):
        tx=transaction();maximum=2**63-1;j=transition(transition(ExecutionJournal(tx),'awaiting-confirmation'),'staging')
        # Each applicable counter reaches its maximum on an isolated terminal
        # observation. Earlier observations must leave room for aggregate sums.
        for index,(kind,path) in enumerate(independent_plan(tx),1):
            if kind=='record-readback':j=transition(j,'verifying')
            oid=f'00000000-0000-4000-8000-{index:012d}'
            p=intent(j,oid,kind,path,collision='absent' if kind in ('mkdir','record-upload','upload') else 'not-applicable')
            current=j.accounting
            account=A(control_read_bytes=maximum-current.control_read_bytes)
            size=0;digest=''
            if kind=='snapshot-validation':size=maximum;account=A(snapshot_validation_reads=maximum)
            elif kind=='record-upload':size=maximum;digest='f'*64;account=A(control_upload_bytes=maximum)
            elif kind=='upload':size=maximum;digest='f'*64;account=A(attempted_upload_bytes=maximum,confirmed_sender_bytes=maximum)
            elif kind=='readback':size=maximum;digest='f'*64;account=A(readback_bytes=maximum)
            elif kind=='record-readback':size=maximum-current.control_read_bytes;digest='f'*64
            observed=outcome(p,oid,'unknown',size=size,sha256=digest,accounting=account,reason='x'*256)
            self.assertLessEqual(len(encode(observed)),envelope(tx))
            if kind=='upload':
                uncertain=outcome(p,oid,'unknown',accounting=A(attempted_upload_bytes=maximum,uncertain_send_bytes=maximum),reason='x'*256)
                self.assertLessEqual(len(encode(uncertain)),envelope(tx))
            j=outcome(p,oid,'completed',**completed_values(tx,kind,path))

    def test_policy1_historical_fixture_unchanged(self):
        raw=(FIXTURES/'import_execution_policy1.jsonl').read_bytes()
        self.assertEqual('59e519f173fd0c06f57b14ef0e8014162c40151d3af12d624aee5cc601969aa8',hashlib.sha256(raw).hexdigest())
        c=reserve_capacity(decode(raw.splitlines(keepends=True)[0]).transaction)
        self.assertEqual((4688,16,75008),(c.checkpoint_bytes,c.revisions,c.aggregate_bytes))
