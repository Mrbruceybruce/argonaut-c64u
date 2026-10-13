"""PA-4.6B permanent bounded raw evidence and localhost ordering regressions."""
from dataclasses import replace, fields
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from c64u_browser.import_context_evidence import observation, CommandObservation, candidate_complete
from c64u_browser.import_execution_v5 import new_transaction, context_checkpoint
from c64u_browser.import_execution import ExecutionTransaction, validate_successor
from c64u_browser.import_execution_policy4 import encode_record
from c64u_browser.import_journal import encode, decode
from c64u_browser.import_capacity import reserve_capacity, _ReservedHistory
from c64u_browser.import_capacity_v5 import bound
from c64u_browser.import_transaction import TransactionError
from c64u_browser.import_execution_store import ExecutionJournalStore
from c64u_browser.c64u_ftp import C64UFtpClient
from c64u_browser.jobs import JobCancelled
from tests.test_import_evidence_prerequisites import transaction
from tests import test_import_staging as staging

FIXTURES = Path(__file__).parent/'fixtures'


def beige():
    old = decode((FIXTURES/'import_capacity_beige_schema4.json').read_bytes()).transaction
    base = ExecutionTransaction(**{f.name: 2 if f.name == 'execution_policy_version' else getattr(old, f.name)
                                   for f in fields(ExecutionTransaction)})
    return new_transaction(base)

CASES={
 '4096-body':(b'250 '+b'x'*4092+b'\r\n','CWD',True,'complete','accepted'),
 '4097-body':(b'250 '+b'x'*4093+b'\r\n','CWD',True,'complete','malformed'),
 'one-line-root':(b'257 "/"\r\n','PWD',True,'complete','accepted'),
 'two-lines':(b'257-start\r\n257 "/"\r\n','PWD',True,'complete','malformed'),
 '64-lines':(b'250-start\r\n'+b'x\r\n'*62+b'250 end\r\n','CWD',True,'complete','malformed'),
 '65-lines':(b'250-start\r\n'+b'x\r\n'*63+b'250 end\r\n','CWD',True,'complete','malformed'),
 '16384-complete':(b'250 '+b'x'*16378+b'\r\n','CWD',True,'complete','malformed'),
 '16384-partial':(b'250 '+b'x'*16380,'CWD',False,'partial','incomplete'),
 '16385-overflow':(b'250 '+b'x'*16379+b'\r\n','CWD',True,'truncated','incomplete'),
 'pwd-overflow':(b'257 \"'+b'x'*16377+b'\"\r\n','PWD',True,'truncated','incomplete'),
 'missing-final-LF':(b'257 "/"\r','PWD',False,'partial','incomplete'),
 'bare-LF':(b'250 OK\n','CWD',True,'complete','malformed'),
 'embedded-CR':(b'250 x\ry\r\n','CWD',True,'complete','malformed'),
 'embedded-LF':(b'250 x\ny\r\n','CWD',True,'complete','malformed'),
 'non-UTF8-comment':(b'250 \xff\r\n','CWD',True,'complete','malformed'),
 'non-UTF8-path':(b'257 "/\xff"\r\n','PWD',True,'complete','wrong-directory'),
 'partial-failure':(b'257 "/','PWD',False,'partial','incomplete'),
 'refusal':(b'550 Refused\r\n','CWD',True,'complete','refused'),
 'wrong-code':(b'200 OK\r\n','CWD',True,'complete','wrong-code'),
 'wrong-directory':(b'257 "//"\r\n','PWD',True,'complete','wrong-directory'),
 'doubled-quotes':(b'257 "/"""\r\n','PWD',True,'complete','malformed'),
}


class ContextEvidenceTests(unittest.TestCase):
    def test_all_retention_acceptance_boundaries(self):
        for name, (raw, verb, ended, availability, completion) in CASES.items():
            with self.subTest(name=name):
                o = observation(verb, raw, attempted=True, before=True, after=True)
                self.assertEqual((availability, completion), (o.availability, o.completion))
                self.assertEqual(raw[:16384].hex(), o.reply_wire_hex)
                self.assertEqual(min(len(raw),16384), o.reply_octets_retained)
                self.assertEqual(len(raw), o.reply_octets_observed)
                self.assertEqual(o, o.validate(verb))

    def test_forgery_rejected_and_frozen(self):
        o = observation('PWD', b'257 "/"\r\n', attempted=True, before=True, after=True)
        for kw in (dict(reply_code=True), dict(reply_octets_observed=1), dict(reply_octets_retained=1),
                   dict(parsed_directory_hex='2f2f'), dict(command_hex=''), dict(submission='not-attempted'),
                   dict(availability='truncated'), dict(completion='refused')):
            with self.subTest(kw=kw), self.assertRaises(TransactionError): replace(o, **kw).validate('PWD')
        with self.assertRaises(AttributeError): o.completion = 'refused'
        raw=b'250 '+b'x'*4093+b'\r\n'
        with self.assertRaises(TransactionError):
            replace(observation('CWD',raw,attempted=True,before=True,after=True),completion='accepted').validate('CWD')

    def test_unavailable_counts_and_non_submission(self):
        o = observation('CWD', b'', attempted=True, before=True, after=True)
        for count in (None, 0, 7, 16385): replace(o,reply_octets_observed=count).validate('CWD')
        for count in (-1, True, 16386):
            with self.assertRaises(TransactionError): replace(o,reply_octets_observed=count).validate('CWD')
        self.assertEqual('not-started',observation('PWD',b'',attempted=False,before=True,after=True).completion)
        raw=b'250 OK\r\n'
        o=observation('CWD',raw,attempted=True,before=True,after=False)
        self.assertEqual(('binding-invalid',raw.hex()),(o.completion,o.reply_wire_hex))
        self.assertEqual('incomplete',observation('CWD',raw,attempted=True,before=True,after=True,interrupted=True).completion)

    def test_actual_transport_capture_bounded_prefix(self):
        # Exercise production socket capture with finite fake recv, including EOF.
        for raw in (b'250 '+b'x'*17000, b'257-start\r\nx\r\n', b'250 x\nextra', b'250 '+b'x'*4093+b'\r\n'):
            for chunk in (7,4096):
                with self.subTest(length=len(raw),chunk=chunk):
                    class Stream:
                        def __init__(self): self.pending=raw; self.commands=[];self.requests=[]
                        def settimeout(self,t): pass
                        def sendall(self,data): self.commands.append(data)
                        def recv(self,n):
                            self.requests.append(n);block=self.pending[:min(n,chunk)];self.pending=self.pending[len(block):];return block
                    stream=Stream()
                    c=SimpleNamespace(_check=lambda:None,_buffer=b'',_control=stream,
                        _event=lambda *a,**k:None,_policy=SimpleNamespace(control_reply=1))
                    captured,attempted,error=C64UFtpClient._root_context_command(c,'CWD')
                    self.assertTrue(attempted);self.assertEqual(raw[:16385],captured)
                    self.assertEqual([b'CWD /\r\n'],stream.commands)
                    self.assertLessEqual(len(captured),16385)
                    self.assertTrue(all(0<n<=4096 for n in stream.requests))

    def test_canonical_format3_fixed_bytes_and_digest(self):
        expected=(FIXTURES/'import_record_format3.json').read_bytes()
        self.assertEqual(expected,encode_record(new_transaction(transaction())))
        self.assertEqual((FIXTURES/'import_record_format3.sha256').read_text().strip(),hashlib.sha256(expected).hexdigest())
        d=json.loads(expected)
        self.assertEqual((3,5,4,2),tuple(d[k] for k in ('format_version','journal_schema_version','execution_policy_version','policy_version')))
        self.assertNotIn('context',d)

    def test_capacity_actual_beige_exact_and_below(self):
        tx=beige();c=reserve_capacity(tx)
        self.assertEqual((37235,62000,23,881170),(c.continuing_bytes,c.checkpoint_bytes,c.revisions,c.aggregate_bytes))
        self.assertEqual(819170,(c.revisions-1)*c.continuing_bytes)
        exact=replace(tx,budgets=replace(tx.budgets,journal_bytes=881147))
        self.assertEqual(881147,reserve_capacity(exact).aggregate_bytes)
        with self.assertRaises(TransactionError): reserve_capacity(replace(tx,budgets=replace(tx.budgets,journal_bytes=881146)))
        for prefix in range(c.revisions): self.assertLessEqual(prefix*c.continuing_bytes+c.checkpoint_bytes,c.aggregate_bytes)
        self.assertEqual(167406,1048576-c.aggregate_bytes)

    def test_writer_enforces_both_envelopes_actual_consumption_and_revision_count(self):
        from c64u_browser.import_execution import initial_journal
        tx=beige();r=_ReservedHistory(tx);c=r.capacity
        # Abstract scalar boundary test; canonical real histories are tested below.
        initial=initial_journal(tx)
        r.check(initial,b'x'*c.continuing_bytes)
        with self.assertRaises(TransactionError):r.check(initial,b'x'*(c.continuing_bytes+1))
        r.used_revisions=c.revisions-1
        r.used_bytes=(c.revisions-1)*c.continuing_bytes
        terminal=replace(initial,state='failed',revision=c.revisions-1)
        r.check(terminal,b'x'*c.checkpoint_bytes)
        with self.assertRaises(TransactionError):r.check(terminal,b'x'*(c.checkpoint_bytes+1))
        r.used_bytes+=1
        with self.assertRaises(TransactionError):r.check(terminal,b'x'*c.checkpoint_bytes)
        r.used_revisions=c.revisions
        with self.assertRaises(TransactionError):r.check(replace(terminal,revision=c.revisions),b'x')

    def test_capacity_two_items_and_maximum_paths(self):
        tx=beige();i=tx.items[0];payload=i.size*2
        two=replace(tx,items=(i,replace(i,staged_path=tx.directory+'/item-0002.d64',final_path='games/second.d64',sha256='b'*64)),
            budgets=replace(tx.budgets,selected_payload_bytes=payload,planned_upload_bytes=payload,planned_readback_bytes=payload),
            limits=replace(tx.limits,snapshot_validation_reads=payload))
        self.assertEqual(1072716,bound(two)['reservation'])
        with self.assertRaises(TransactionError): reserve_capacity(two)
        for root,expected in (('/USB0',2754865),('/SD',2755509)):
            prefix=root+'/';suffix='/ARGONAUT_LIBRARY'
            long=replace(tx,library=replace(tx.library,root=root,path=prefix+'\U00010000'*(4096-len(prefix)-len(suffix))+suffix))
            self.assertEqual(expected,bound(long)['reservation'])
            with self.assertRaises(TransactionError):reserve_capacity(long)


class ContextStagingTests(unittest.TestCase):
    fixture=staging.StagingTests.fixture
    stage=staging.StagingTests.stage
    journal=staging.StagingTests.journal
    failure=staging.StagingTests.failure
    path=staging.StagingTests.path

    def root_override(self, reply, verb):
        active=False
        def hook(command,path):
            nonlocal active
            if command==b'CWD' and path==b'/': active=True
            if active and command==verb.encode(): return reply
        self.server.before_command=hook

    def test_different_initial_connection_directories(self):
        for path in (b'/',b'/USB0',b'/USB0/ARGONAUT_LIBRARY/games'):
            with self.subTest(path=path),self.fixture():
                self.server.initial_cwd=path
                self.stage()
                c=self.journal().operations[1].context
                self.assertEqual('2f',c.pwd.parsed_directory_hex)
                self.assertEqual(1,self.server.commands[self.start:].count((b'CWD',b'/')))

    def test_maximum_accepted_cwd_and_pwd_lines(self):
        for verb,raw in (('CWD',b'250 '+b'x'*4092+b'\r\n'),('PWD',b'257 "/" '+b'x'*4088+b'\r\n')):
            with self.subTest(verb=verb),self.fixture():
                # Only override the root verification, not subsequent navigation.
                active=False;used=False
                def hook(command,path):
                    nonlocal active,used
                    if command==b'CWD' and path==b'/':active=True
                    if active and not used and command==verb.encode():used=True;return raw
                    if active and used and verb=='CWD' and command==b'PWD':
                        active=False;return b'257 "/"\r\n'
                self.server.before_command=hook;self.stage()
                o=getattr(self.journal().operations[1].context,verb.lower())
                self.assertEqual(('accepted',4098),(o.completion,o.reply_octets_retained))

    def test_no_intervening_navigation_or_read_fallback(self):
        from c64u_browser.ftp_reads import _StagingContextGuard
        from c64u_browser.c64u_ftp_types import FtpOperationError
        original=_StagingContextGuard.observe
        with self.fixture():
            def observe(guard,verb,**kwargs):
                with self.assertRaises(FtpOperationError):guard.client.list_directory(b'/')
                with self.assertRaises(Exception):guard.adapter.end_read_attempt()
                return original(guard,verb,**kwargs)
            with patch.object(_StagingContextGuard,'observe',observe):self.stage()

    def test_all_failed_boundaries_block_mkd_and_stor(self):
        failures={k:v for k,v in CASES.items() if v[-1]!='accepted'}
        failures.update({'cwd-lost':(b'','CWD',False,'unavailable','incomplete'),
                         'pwd-lost':(b'','PWD',False,'unavailable','incomplete'),
                         'pwd-refused':(b'550 Refused\r\n','PWD',True,'complete','refused')})
        for name,(raw,verb,ended,availability,completion) in failures.items():
            with self.subTest(name=name),self.fixture():
                # Avoid waiting the real control deadline on deliberately missing tails.
                from c64u_browser.c64u_ftp_types import FtpPolicy
                self.core._ftp_manager._policy=FtpPolicy(control_reply=.15)
                self.root_override(raw,verb);self.failure()
                op=self.journal().operations[-1];o=getattr(op.context,verb.lower())
                self.assertEqual(raw[:16384].hex(),o.reply_wire_hex)
                self.assertEqual((availability,completion),(o.availability,o.completion))
                self.assertEqual(('stopped','not-started'),(op.context_phase,op.outcome))
                self.assertFalse({b'MKD',b'STOR'} & set(self.server.verbs[self.start:]))

    def test_order_same_lease_and_durable_barriers(self):
        with self.fixture():
            seen=[];lease=[]
            def hook(verb,path):
                if verb==b'CWD' and path==b'/' or seen and len(seen)<3:
                    op=self.journal().operations[-1]
                    self.assertEqual(('context-intent','cwd-observed','mkd-intent')[len(seen)],op.context_phase)
                    seen.append(verb)
                    client=next(iter(self.core._ftp_manager._leases.values()))
                    lease.append(client.identity.ftp_session_id)
                    self.assertFalse(client._operation_lock.acquire(blocking=False))
                if verb==b'STOR':
                    c=self.journal().operations[1].context
                    self.assertTrue(c.verified);self.assertEqual(c.ftp_session_id,c.mkd_lease_id)
            self.server.before_command=hook;self.stage()
            self.assertEqual([b'CWD',b'PWD',b'MKD'],seen);self.assertEqual(1,len(set(lease)))
            chain=[decode(p.read_bytes()) for p in sorted(self.folder.glob('*.execution-*'))]
            for old,new in zip(chain,chain[1:]):validate_successor(old,new)
            self.assertEqual(22,len(chain))
            prior=next(j for j in chain if j.operations and j.operations[-1].context_phase=='cwd-observed')
            following=chain[chain.index(prior)+1]
            c=following.operations[-1].context
            forged=replace(c,cwd=observation('CWD',b'250 other\r\n',attempted=True,before=True,after=True))
            bad=replace(following,operations=following.operations[:-1]+(replace(following.operations[-1],context=forged),))
            with self.assertRaises(TransactionError):validate_successor(prior,bad)
            for changed in (replace(c,operation_id='ffffffff-ffff-ffff-ffff-ffffffffffff'),replace(c,transaction_id='ffffffff-ffff-ffff-ffff-ffffffffffff'),replace(c,destination_hex='2f')):
                with self.assertRaises(TransactionError):changed.validate(self.tx,c.operation_id)
            with self.assertRaises(TransactionError):decode(encode(chain[-1])+b' ')
            d=json.loads(encode(chain[-1]));d['operations'][1]['context']['extra']=1
            with self.assertRaises(TransactionError):decode((json.dumps(d)+'\n').encode())
            with self.assertRaises(TransactionError):replace(chain[-1],transaction=replace(self.tx,execution_policy_version=3)).validate()

    def test_cancellation_after_each_durable_context_boundary(self):
        for phase in ('context-intent','cwd-observed','pwd-observed','mkd-intent','mkd-observed'):
            with self.subTest(phase=phase),self.fixture():
                canceled=False;append=ExecutionJournalStore._append
                def save(store,journal,*,previous):
                    nonlocal canceled
                    result=append(store,journal,previous=previous)
                    if journal.operations and journal.operations[-1].context_phase==phase:canceled=True
                    return result
                def check():
                    if canceled:raise JobCancelled()
                with patch.object(ExecutionJournalStore,'_append',save):self.failure(check_cancel=check)
                j=self.journal();self.assertEqual('canceled',j.state)
                c=j.operations[-1].context
                if phase!='context-intent':self.assertEqual('accepted',c.cwd.completion)
                if phase in ('pwd-observed','mkd-intent','mkd-observed'):self.assertEqual('accepted',c.pwd.completion)
                self.assertNotIn(b'STOR',self.server.verbs[self.start:])
                if phase!='mkd-observed':self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_persistence_failure_at_every_context_boundary(self):
        for phase in ('context-intent','cwd-observed','pwd-observed','mkd-intent','mkd-observed','stopped'):
            with self.subTest(phase=phase),self.fixture():
                if phase=='stopped':self.root_override(b'550 No\r\n','CWD')
                append=ExecutionJournalStore._append
                def save(store,journal,*,previous):
                    if journal.operations and journal.operations[-1].context_phase==phase:raise OSError('injected sync failure')
                    return append(store,journal,previous=previous)
                with patch.object(ExecutionJournalStore,'_append',save):e=self.failure()
                self.assertEqual('persistence-uncertain',e.staging_evidence.journal_state)
                self.assertNotIn(b'STOR',self.server.verbs[self.start:])
                if phase!='mkd-observed':self.assertNotIn(b'MKD',self.server.verbs[self.start:])
                if phase in ('cwd-observed','pwd-observed','stopped'):
                    self.assertIsNotNone(e.staging_evidence.unsaved_context.cwd)

    def test_binding_invalidated_between_context_steps(self):
        for phase in ('cwd-observed','pwd-observed','mkd-intent'):
            for change in ('session','owner','lease'):
                with self.subTest(phase=phase,change=change),self.fixture():
                    append=ExecutionJournalStore._append
                    def save(store,journal,*,previous):
                        result=append(store,journal,previous=previous)
                        if journal.operations and journal.operations[-1].context_phase==phase:
                            if change=='session':self.core._session_id='stale'
                            elif change=='owner':self.core._client._ftp_reads._owner_id='f'*32
                            else:self.core._ftp_manager._leases.clear()
                        return result
                    with patch.object(ExecutionJournalStore,'_append',save):self.failure()
                    self.assertFalse({b'MKD',b'STOR'} & set(self.server.verbs[self.start:]))
                    self.assertEqual('accepted',self.journal().operations[-1].context.cwd.completion)
                    self.assertEqual('not-started',self.journal().operations[-1].outcome)

    def test_cancellation_after_capture_cannot_erase_accepted_reply(self):
        from c64u_browser.ftp_reads import _StagingContextGuard
        original=_StagingContextGuard.observe
        for target in ('CWD','PWD'):
            with self.subTest(target=target),self.fixture():
                canceled=False
                def observe(guard,verb):
                    nonlocal canceled
                    result=original(guard,verb)
                    if verb==target:canceled=True
                    return result
                def check():
                    if canceled:raise JobCancelled()
                with patch.object(_StagingContextGuard,'observe',observe):self.failure(check_cancel=check)
                j=self.journal();o=getattr(j.operations[-1].context,target.lower())
                self.assertEqual(('canceled','accepted'),(j.state,o.completion))
                self.assertTrue(o.reply_wire_hex)
                self.assertFalse({b'MKD',b'STOR'} & set(self.server.verbs[self.start:]))

    def test_session_change_after_capture_preserves_raw_failure(self):
        from c64u_browser.ftp_reads import _StagingContextGuard
        original=_StagingContextGuard.observe
        for target in ('CWD','PWD'):
            with self.subTest(target=target),self.fixture():
                def observe(guard,verb):
                    result=original(guard,verb)
                    if verb==target:self.core._session_id='stale'
                    return result
                with patch.object(_StagingContextGuard,'observe',observe):self.failure()
                o=getattr(self.journal().operations[-1].context,target.lower())
                self.assertEqual('binding-invalid',o.completion);self.assertTrue(o.reply_wire_hex)
                self.assertFalse({b'MKD',b'STOR'} & set(self.server.verbs[self.start:]))

    def test_pa42_duplicated_mkd_path_remains_unqualified(self):
        with self.fixture(beige=True):
            reply=b'257 "'+self.tx.library.path.encode()+b'/games/'+self.path()+b'" created.\r\n'
            self.server.after_mutation[b'MKD']=lambda path:reply
            self.failure();op=self.journal().operations[-1]
            self.assertTrue(op.context.verified)
            self.assertEqual('unqualified',op.mkd_proof.decision)
            self.assertEqual(reply[:-2].hex(),op.mkd_proof.reply_lines_hex[0])
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_separate_physical_disk_space_gate(self):
        with self.fixture():
            with patch('c64u_browser.import_execution_store.os.fstatvfs',return_value=SimpleNamespace(f_bavail=0,f_frsize=4096)):
                self.failure()
            self.assertFalse(list(self.folder.glob('*.execution-*')))
            self.assertFalse({b'MKD',b'STOR'} & set(self.server.verbs[self.start:]))
