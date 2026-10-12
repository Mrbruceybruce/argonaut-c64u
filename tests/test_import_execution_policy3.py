"""PA-4F.3 offline proof, canonical history, capacity and version adversaries."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from c64u_browser.c64u_ftp_types import MutationEvidence, Outcome, DeviceIdentity, ConnectionBinding
from c64u_browser.import_mkd_proof import capture, RULE, destination, MkdObservation
from c64u_browser.import_execution_v4 import new_transaction, ExecutionJournalV4
from c64u_browser.import_execution import (ExecutionAccounting as A, transition, intent, outcome,
                                         validate_successor)
from c64u_browser.import_execution_policy3 import encode_record, validate_record, record_expectation, planned_operations
from c64u_browser.import_execution_store import ExecutionJournalStore
from c64u_browser.import_journal import encode, decode
from c64u_browser.import_capacity import reserve_capacity
from c64u_browser.import_transaction import TransactionError

FIXTURES = Path(__file__).parent/'fixtures'


def beige_transaction():
    old = decode((FIXTURES/'import_execution_policy1.jsonl').read_bytes().splitlines(keepends=True)[0]).transaction
    tx = new_transaction(old)
    size = 174848
    return replace(tx, session_id='a'*32, manifest_revision=0,
        library=replace(tx.library, device_id='id:25EA78', root='/USB0', path='/USB0/ARGONAUT_LIBRARY',
                        library_id='a3b6d459-a989-4224-a372-0a995628f7ce'),
        manifest_digest='485cd2d9f5310a200e43ad639c549faf9df60542fabc56c1cb093636e7b9aa8e',
        items=(replace(tx.items[0], format='D64', size=size, staged_path=tx.directory+'/item-0001.d64',
                       final_path='games/acceptance.d64',
                       sha256='78d99754a49326515d55f69fc7ac55e1984e0bb3b38b8a46466621e0add44d51'),),
        budgets=replace(tx.budgets, selected_payload_bytes=size, planned_upload_bytes=size, planned_readback_bytes=size),
        limits=replace(tx.limits, snapshot_validation_reads=size)).validate()


class Policy3Tests(unittest.TestCase):
    def setUp(self):
        self.tx = beige_transaction(); self.oid = str(uuid4())
        self.device = DeviceIdentity('id:25EA78','C64 Ultimate','1.1.0s2','0.1')
        self.binding = ConnectionBinding(self.device,self.tx.session_id,'127.0.0.1')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = ExecutionJournalStore(self.temp.name)

    def proof(self, line=None, *, wire=None, **kwargs):
        p = destination(self.tx,'utf-8')
        if wire is None:
            wire = MutationEvidence('MKD','MKD',Outcome.COMPLETED,True,True,257,
                acknowledged=(('MKD',257),), reply_lines=(line if line is not None else b'257 "//'+p+b'" created.',), requested_path=p)
        if isinstance(wire,MutationEvidence):
            wire=MkdObservation(wire.operation,wire.stage,wire.outcome.value,wire.stage_submitted,
                                wire.consequential_submitted,wire.reply_code,wire.acknowledged,wire.reply_lines,wire.requested_path)
        options = dict(encoding='utf-8', identity=self.device, binding=self.binding, binding_valid=True)
        options.update(kwargs)
        return capture(self.tx,self.oid,wire,**options)

    def start(self):
        w=self.store.create_reserved(self.tx)
        w.transition('awaiting-confirmation',previous=w.current); w.transition('staging',previous=w.current)
        w.intent(str(uuid4()),'snapshot-validation','',previous=w.current)
        w.outcome(w.current.operations[-1].id,'completed',previous=w.current,
                  size=self.tx.budgets.planned_upload_bytes,accounting=A(snapshot_validation_reads=self.tx.budgets.planned_upload_bytes))
        w.intent(self.oid,'mkdir',self.tx.directory,collision='absent',previous=w.current)
        return w

    def test_exact_qualified_reply_preserves_generic_invalid_and_raw(self):
        p=self.proof();self.assertEqual(('invalid','firmware-compatible',RULE),(p.path_status,p.decision,p.compatibility_rule))
        w=self.start();w.outcome(self.oid,'completed',previous=w.current,mkd_proof=p)
        loaded=self.store.load(self.tx.id)
        self.assertEqual(p,loaded.operations[-1].mkd_proof)
        self.assertEqual(encode(w.current),encode(loaded))
        self.assertEqual(bytes.fromhex(p.reply_lines_hex[0]),p.wire(self.tx).reply_lines[0])

    def test_strict_matching_does_not_require_qualified_firmware(self):
        p=destination(self.tx,'utf-8')
        proof=self.proof(b'257 "'+p+b'" created',identity=None)
        self.assertEqual('strict',proof.decision);self.assertIsNone(proof.compatibility_rule)

    def test_wrong_or_missing_identity_cannot_qualify(self):
        for field,values in (('physical_id',('id:25BE71','mac:25EA78','')),('product',('other','')),
                             ('firmware',('1.1.0','1.1.0s2 ','')),('api_version',('0.2',''))):
            for value in values:
                with self.subTest(field=field,value=value):
                    self.assertEqual('unqualified',self.proof(identity=replace(self.device,**{field:value})).decision)
        self.assertEqual('unqualified',self.proof(identity=None).decision)

    def test_identity_utf8_byte_bound_not_character_bound(self):
        self.assertEqual('unavailable',self.proof(identity=replace(self.device,product='é'*65)).provenance)
        p=self.proof()
        with self.assertRaises(TransactionError):replace(p,product='é'*65).validate(self.tx,self.oid)

    def test_profile_fallback_and_provenance_cannot_qualify(self):
        p=self.proof(identity=None)
        self.assertEqual('unqualified',p.decision)
        with self.assertRaises(TransactionError):replace(self.proof(),provenance='saved-profile').validate(self.tx,self.oid)

    def test_changed_binding_keeps_raw_but_cannot_accept(self):
        p=self.proof(binding_valid=False,binding=replace(self.binding,core_session_id='stale'))
        self.assertEqual('binding-invalid',p.reason);self.assertTrue(p.reply_lines_hex)
        w=self.start();w.outcome(self.oid,'unknown',previous=w.current,mkd_proof=p,reason='staging-stopped')
        self.assertEqual('uncertain',self.store.load(self.tx.id).state)

    def test_claimed_valid_wrong_session_is_rejected(self):
        with self.assertRaises(TransactionError):self.proof(binding=replace(self.binding,core_session_id='stale'))
        with self.assertRaises(TransactionError):replace(self.proof(),binding_device_id='other').validate(self.tx,self.oid)

    def test_wrong_transaction_operation_and_destination_rejected(self):
        proof=self.proof()
        for oid in (str(uuid4()),'bad'):
            with self.assertRaises(TransactionError):proof.validate(self.tx,oid)
        with self.assertRaises(TransactionError):replace(proof,request_hex=b'/USB0/wrong'.hex()).validate(self.tx,self.oid)
        with self.assertRaises(TransactionError):proof.validate(replace(self.tx,id=str(uuid4())),self.oid)

    def test_other_root_is_not_qualified(self):
        self.tx=replace(self.tx,library=replace(self.tx.library,root='/USB1',path='/USB1/ARGONAUT_LIBRARY'))
        self.assertEqual('unqualified',self.proof().decision)

    def test_wire_adversaries(self):
        p=destination(self.tx,'utf-8')
        returns=[b'/'+p,b'///'+p,p.lower(),b'//'+p.replace(b'/argonaut',b'//argonaut'),
                 b'//'+p+b'/..',b'//'+p.replace(b'/',b'%2F'),b'//'+p+b'\x00']
        lines=[b'257 "'+r+b'" created.' for r in returns]
        lines += [b'257 '+p,b'257 "//'+p+b'" created. extra',b'257 "//'+p+b'" created',b'257 "//'+p+b'" "oops"']
        for line in lines:
            with self.subTest(line=line):self.assertEqual('unqualified',self.proof(line).decision)
        wire=self.proof().wire(self.tx)
        self.assertEqual('unqualified',self.proof(wire=replace(wire,reply_lines=(b'257-first',b'257 done'))).decision)

    def test_negative_and_lost_replies(self):
        wire=self.proof().wire(self.tx)
        negative=replace(wire,outcome=Outcome.REJECTED,reply_code=550,acknowledged=(),reply_lines=(b'550 refused',))
        for evidence,status in ((negative,'rejected'),(replace(wire,outcome=Outcome.UNKNOWN,reply_code=None,acknowledged=(),reply_lines=()),'unknown')):
            with tempfile.TemporaryDirectory() as d:
                self.store=ExecutionJournalStore(d);p=self.proof(wire=evidence);w=self.start()
                w.outcome(self.oid,status,previous=w.current,mkd_proof=p,reason='staging-stopped')
                self.assertEqual(p,self.store.load(self.tx.id).operations[-1].mkd_proof)

    def test_missing_and_truncated_cannot_accept(self):
        wire=self.proof().wire(self.tx)
        for lines in ((),(b'x'*4097,),tuple(b'x' for _ in range(65)),(b'x'*4096,)*4):
            p=self.proof(wire=replace(wire,reply_lines=lines))
            self.assertEqual('unqualified',p.decision)
            self.assertIn(p.availability,('unavailable','truncated'))

    def test_bad_hex_and_bounds_rejected(self):
        proof=self.proof()
        for lines in (('AA',),('0',),('gg',),('00 '*4,),('00'*4097,),('00',)*65,('00'*4096,)*4):
            with self.subTest(lines=str(lines)[:30]),self.assertRaises(TransactionError):
                replace(proof,reply_lines_hex=lines).validate(self.tx,self.oid)

    def test_contradictory_transport_and_classification_rejected(self):
        p=self.proof()
        for changes in (dict(stage='STOR'),dict(stage_submitted=False),dict(consequential_submitted=False),
                        dict(acknowledgment='rejected'),dict(acknowledged=()),dict(reply_code=True),
                        dict(transport_outcome='rejected'),dict(path_status='matched'),dict(decision='strict'),
                        dict(compatibility_rule='global'),dict(reason='arbitrary'),dict(availability='unavailable')):
            with self.subTest(changes=changes),self.assertRaises(TransactionError):replace(p,**changes).validate(self.tx,self.oid)

    def test_proof_required_for_completion_and_forbidden_on_intent(self):
        w=self.start();j=w.current
        with self.assertRaises(TransactionError):w.outcome(self.oid,'completed',previous=j)
        with self.assertRaises(TransactionError):replace(j,operations=j.operations[:-1]+(replace(j.operations[-1],mkd_proof=self.proof()),)).validate()
        self.assertIs(j,w.current)

    def test_unqualified_cannot_advance(self):
        w=self.start();p=self.proof(binding_valid=False)
        with self.assertRaises(TransactionError):w.outcome(self.oid,'completed',previous=w.current,mkd_proof=p)
        w.outcome(self.oid,'unknown',previous=w.current,mkd_proof=p,reason='staging-stopped')
        with self.assertRaises(TransactionError):w.intent(str(uuid4()),'record-upload',self.tx.record_path,previous=w.current,collision='absent')

    def test_proof_immutable_through_successors(self):
        w=self.start();w.outcome(self.oid,'completed',previous=w.current,mkd_proof=self.proof());old=w.current
        w.intent(str(uuid4()),'record-upload',self.tx.record_path,previous=old,collision='absent')
        changed=replace(old.operations[-1].mkd_proof,encoding='latin-1') # valid same ASCII bytes, but different evidence
        ops=list(w.current.operations);ops[1]=replace(ops[1],mkd_proof=changed)
        with self.assertRaises(TransactionError):validate_successor(old,replace(w.current,operations=tuple(ops)))

    def test_codec_rejects_extra_fields_and_versions(self):
        w=self.start();w.outcome(self.oid,'completed',previous=w.current,mkd_proof=self.proof())
        original=json.loads(encode(w.current))
        for field,value in (('schema_version',3),('schema_version',True),('extra',1)):
            doc={**original,field:value}
            with self.assertRaises(TransactionError):decode(json.dumps(doc).encode())
        for policy in (1,2,4,True):
            doc=json.loads(encode(w.current));doc['transaction']['execution_policy_version']=policy
            with self.assertRaises(TransactionError):decode(json.dumps(doc).encode())
        doc=json.loads(encode(w.current));doc['operations'][1]['mkd_proof']['extra']='no'
        with self.assertRaises(TransactionError):decode(json.dumps(doc).encode())

    def test_capacity_one_item_and_exact_boundary(self):
        cap=reserve_capacity(self.tx)
        self.assertEqual((7,20),(len(planned_operations(self.tx)),cap.revisions));self.assertLessEqual(cap.aggregate_bytes,1048576)
        bound=cap.aggregate_bytes
        for _ in range(8):
            tx=replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=bound))
            new=reserve_capacity(tx).aggregate_bytes
            if bound==new:break
            bound=new
        self.assertEqual(bound,reserve_capacity(tx).aggregate_bytes)
        with self.assertRaises(TransactionError):reserve_capacity(replace(tx,budgets=replace(tx.budgets,journal_bytes=bound-1)))

    def test_two_payloads_conservatively_refused(self):
        i=self.tx.items[0];b=2*i.size
        tx=replace(self.tx,items=(i,replace(i,staged_path=self.tx.directory+'/item-0002.d64',final_path='games/second.d64',sha256='b'*64)),
                   budgets=replace(self.tx.budgets,selected_payload_bytes=b,planned_upload_bytes=b,planned_readback_bytes=b),
                   limits=replace(self.tx.limits,snapshot_validation_reads=b))
        with self.assertRaises(TransactionError):self.store.create_reserved(tx)
        self.assertFalse(list(Path(self.temp.name).iterdir()))

    def test_maximum_reply_dimensions_roundtrip_and_terminal_capacity(self):
        # 64 lines, each <=4096, exactly 16384 bytes including framing.
        lines=(b'257-'+b'x'*4092, b'x'*4096, b'x'*4096, b'x'*3963)+ (b'',)*59+(b'257 x',)
        self.assertEqual(16384,sum(len(x)+2 for x in lines))
        wire=self.proof().wire(self.tx);p=self.proof(wire=replace(wire,reply_lines=lines))
        w=self.start();w.outcome(self.oid,'unknown',previous=w.current,mkd_proof=p,reason='x'*256,
                               accounting=A(control_read_bytes=2**63-1))
        self.assertEqual(p,self.store.load(self.tx.id).operations[-1].mkd_proof)
        self.assertLessEqual(len(encode(w.current)),w._reservation.capacity.checkpoint_bytes)
        self.assertLessEqual(w._reservation.used_bytes,w._reservation.capacity.aggregate_bytes)
        self.assertEqual(w._reservation.used_bytes,sum(f.stat().st_size for f in Path(self.temp.name).glob('*.execution-*')))

    def test_durable_intent_survives_failed_proof_persistence(self):
        from unittest.mock import patch
        w=self.start();previous=w.current
        with patch.object(self.store,'_append',side_effect=OSError('sync')):
            with self.assertRaises(OSError):w.outcome(self.oid,'completed',previous=previous,mkd_proof=self.proof())
        self.assertTrue(w.blocked);self.assertEqual(previous,self.store.load(self.tx.id))
        with self.assertRaises(TransactionError):w.transition('uncertain',previous=previous,reason='stopped')

    def test_loaded_journals_have_no_resume_authority(self):
        w=self.start();w.outcome(self.oid,'completed',previous=w.current,mkd_proof=self.proof())
        loaded=self.store.load(self.tx.id)
        with self.assertRaises(ValueError):self.store.save(loaded)
        with self.assertRaises(TransactionError):self.store.create_reserved(self.tx)
        with self.assertRaises(TransactionError):w.transition('canceled',previous=loaded,reason='stopped')

    def test_fixed_format2_fixture_and_hash(self):
        from tests.test_import_evidence_prerequisites import transaction
        tx=new_transaction(transaction());raw=(FIXTURES/'import_record_format2.json').read_bytes()
        digest=(FIXTURES/'import_record_format2.sha256').read_text().strip()
        self.assertEqual(digest,hashlib.sha256(raw).hexdigest())
        self.assertEqual(raw,encode_record(tx));self.assertEqual((len(raw),digest),record_expectation(tx))
        self.assertEqual(raw,validate_record(raw,tx))
        self.assertNotIn(b'session',raw);self.assertNotIn(b'mkd',raw)
        for changed in (raw[:-1],raw+b'\n',b' '+raw):
            with self.assertRaises(TransactionError):validate_record(changed,tx)

    def test_unsupported_record_and_transaction_combinations(self):
        from c64u_browser.import_execution_policy2 import encode_record as old_record
        with self.assertRaises(TransactionError):old_record(self.tx)
        old=decode((FIXTURES/'import_execution_policy1.jsonl').read_bytes().splitlines(keepends=True)[0]).transaction
        with self.assertRaises(TransactionError):encode_record(replace(old,execution_policy_version=2))
        for v in (1,3,True,None):
            with self.assertRaises(TransactionError):encode_record(self.tx,format_version=v)
        with self.assertRaises(TransactionError):replace(old,execution_policy_version=3).validate()

    def test_historical_fixture_bytes_unchanged(self):
        lines=(FIXTURES/'import_execution_policy1.jsonl').read_bytes().splitlines(keepends=True)
        previous=None
        for raw in lines:
            j=decode(raw);self.assertEqual(raw,encode(j));self.assertEqual(3,j.schema_version)
            if previous is not None:validate_successor(previous,j)
            previous=j
        from tests.test_import_evidence_prerequisites import transaction
        from c64u_browser.import_execution_policy2 import encode_record as old_record
        self.assertEqual((FIXTURES/'import_record_format1.json').read_bytes(),old_record(transaction()))

    def test_versioned_path_parser_preserves_generic_classification(self):
        p=destination(self.tx,'utf-8')
        for lines in ((b'257 "'+p+b'" created',),(b'257 "//'+p+b'" created.',),
                      (b'257 "/wrong"',),(b'257 "relative"',),(b'257 no-path',),
                      (b'257-first',b'257 last')):
            wire=MutationEvidence('MKD','MKD',Outcome.COMPLETED,True,True,257,
                                  acknowledged=(('MKD',257),),reply_lines=lines,requested_path=p)
            proof=self.proof(wire=wire)
            self.assertEqual(wire.mkdir_path_status(p),proof.path_status)

    def contradictory_proof(self):
        # Exact PA-4F.3R reproduction, deliberately bypassing capture validation.
        return replace(self.proof(), transport_outcome='not-started',
                       decision='unqualified', compatibility_rule=None, reason='unqualified-reply')

    def contradictory_journal(self):
        w=self.start();previous=w.current
        op=replace(previous.operations[-1],outcome='unknown',mkd_proof=self.contradictory_proof())
        return replace(previous,operations=previous.operations[:-1]+(op,),state='uncertain',
                       reason='staging-stopped',revision=previous.revision+1,
                       previous_digest=hashlib.sha256(encode(previous)).hexdigest())

    def test_not_started_completed_reply_rejected_at_capture(self):
        wire=MkdObservation('MKD','MKD','not-started',True,True,257,(('MKD',257),),
                            (b'257 "//'+destination(self.tx,'utf-8')+b'" created.',),destination(self.tx,'utf-8'))
        with self.assertRaisesRegex(TransactionError,'transport/submission'):
            self.proof(wire=wire)

    def test_not_started_submission_and_acknowledgment_adversaries(self):
        p=destination(self.tx,'utf-8')
        wire=MkdObservation('MKD','MKD','not-started',False,False,None,(),(),p)
        cases=(dict(stage_submitted=True),dict(consequential_submitted=True),
               dict(stage_submitted=True,consequential_submitted=True),
               dict(reply_code=257,acknowledged=(('MKD',257),),reply_lines=(b'257 "'+p+b'"',)),
               dict(reply_code=257,reply_lines=(b'257 "'+p+b'"',)))
        for changes in cases:
            with self.subTest(changes=changes),self.assertRaises(TransactionError):
                self.proof(wire=replace(wire,**changes))
        legitimate=self.proof(wire=wire)
        with self.assertRaises(TransactionError):
            replace(legitimate,acknowledgment='completed').validate(self.tx,self.oid)

    def test_other_transport_submission_contradictions_rejected(self):
        p=destination(self.tx,'utf-8')
        cases=(('completed',True,True,550,(),(b'550 refused',)),
               ('rejected',True,True,257,(('MKD',257),),(b'257 "'+p+b'"',)),
               ('rejected',True,True,421,(),(b'421 closing',)),
               ('unknown',False,False,None,(),()),
               ('completed',True,False,257,(('MKD',257),),(b'257 "'+p+b'"',)))
        for state,stage,submitted,code,ack,lines in cases:
            with self.subTest(state=state,code=code,submitted=submitted),self.assertRaises(TransactionError):
                self.proof(wire=MkdObservation('MKD','MKD',state,stage,submitted,code,ack,lines,p))

    def test_legitimate_not_started_uncertain_and_rejected_remain_durable(self):
        p=destination(self.tx,'utf-8')
        cases=(('not-started',False,None,(),(),'not-started','not-started','failed'),
               ('unknown',True,None,(),(),'unknown','unknown','uncertain'),
               ('unknown',True,257,(('MKD',257),),(b'257 "//'+p+b'" created.',),'completed','unknown','uncertain'),
               ('unknown',True,421,(),(b'421 closing',),'unknown','unknown','uncertain'),
               ('rejected',True,550,(),(b'550 refused',),'rejected','rejected','failed'))
        for state,submitted,code,ack,lines,ack_status,status,terminal in cases:
            with self.subTest(state=state,code=code),tempfile.TemporaryDirectory() as folder:
                self.store=ExecutionJournalStore(folder)
                proof=self.proof(wire=MkdObservation('MKD','MKD',state,submitted,submitted,code,ack,lines,p))
                self.assertEqual('unqualified',proof.decision)
                self.assertEqual(ack_status,proof.acknowledgment)
                self.assertEqual(state,proof.transport_outcome)
                w=self.start();w.outcome(self.oid,status,previous=w.current,mkd_proof=proof,reason='staging-stopped')
                j=self.store.load(self.tx.id);self.assertEqual(terminal,j.state)
                self.assertEqual(proof,j.operations[-1].mkd_proof)
                with self.assertRaises(ValueError):self.store.save(j)
                total=sum(f.stat().st_size for f in Path(folder).glob('*.execution-*'))
                self.assertEqual(total,w._reservation.used_bytes)
                self.assertLessEqual(total,w._reservation.capacity.aggregate_bytes)
                self.assertLessEqual(w._reservation.used_revisions,20)

    def test_contradictory_proof_rejected_by_journal_validation(self):
        with self.assertRaisesRegex(TransactionError,'transport/submission'):
            self.contradictory_journal().validate()

    def test_contradictory_proof_rejected_by_canonical_encoder(self):
        with self.assertRaisesRegex(TransactionError,'transport/submission'):
            encode(self.contradictory_journal())

    def test_forged_canonical_contradiction_rejected_by_decode_and_reload(self):
        from c64u_browser.import_transaction import canonical
        j=self.contradictory_journal()
        # Canonical spelling is not validation. No production encoder is used to
        # manufacture this invalid checkpoint; all predecessor links are correct.
        raw=(json.dumps(canonical(j),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
        with self.assertRaises(TransactionError):decode(raw)
        name=Path(self.temp.name)/self.store._filename(self.tx.id,j.revision)
        name.write_bytes(raw);name.chmod(0o600)
        with self.assertRaises(TransactionError):self.store.load(self.tx.id)

    def test_invalid_proof_cannot_advance_live_writer(self):
        w=self.start();previous=w.current;consumed=w._reservation.used_bytes
        with self.assertRaises(TransactionError):
            w.outcome(self.oid,'unknown',previous=previous,mkd_proof=self.contradictory_proof(),reason='staging-stopped')
        self.assertIs(previous,w.current);self.assertEqual(consumed,w._reservation.used_bytes)
        self.assertEqual('intent',self.store.load(self.tx.id).operations[-1].outcome)
        with self.assertRaises(TransactionError):
            w.intent(str(uuid4()),'record-upload',self.tx.record_path,previous=previous,collision='absent')

    def test_capacity_binding_fields_use_four_byte_scalar_maxima(self):
        from c64u_browser.import_mkd_proof import maximum_document
        envelope=maximum_document(self.tx)
        for field in ('core_session_id','binding_device_id'):
            value=envelope[field]
            self.assertEqual(256,len(value));self.assertEqual(1024,len(value.encode('utf-8')))
            self.assertEqual(1026,len(json.dumps(value,ensure_ascii=False).encode('utf-8')))
        cap=reserve_capacity(self.tx)
        # Independently reviewed fixture constants, not values derived from a
        # second call to the same sizing helper.
        self.assertEqual((42978,20,859560),(cap.checkpoint_bytes,cap.revisions,cap.aggregate_bytes))
        self.assertLess(cap.aggregate_bytes,1048576)

    def test_corrected_capacity_exact_limit_and_one_byte_below(self):
        # The captured journal_bytes changes from 7 to 6 decimal digits, reducing
        # every maximum checkpoint by one byte: (42978-1)*20 = 859540.
        tx=replace(self.tx,budgets=replace(self.tx.budgets,journal_bytes=859540))
        cap=reserve_capacity(tx);self.assertEqual((42977,20,859540),(cap.checkpoint_bytes,cap.revisions,cap.aggregate_bytes))
        w=self.store.create_reserved(tx);self.assertEqual('prepared',w.current.state)
        with self.assertRaises(TransactionError):reserve_capacity(replace(tx,budgets=replace(tx.budgets,journal_bytes=859539)))

    def test_maximum_valid_proof_scalar_envelope_and_terminal_history(self):
        from c64u_browser.import_mkd_proof import maximum_document, IDENTITY_FIELDS
        from c64u_browser.import_transaction import canonical
        lines=(b'257-'+b'x'*4092,b'x'*4096,b'x'*4096,b'x'*3963)+(b'',)*59+(b'257 x',)
        self.assertEqual(64,len(lines));self.assertEqual(16384,sum(len(x)+2 for x in lines))
        self.assertEqual(4096,max(map(len,lines)))
        p=destination(self.tx,'latin-1')
        proof=self.proof(wire=MkdObservation('MKD','MKD','completed',True,True,257,(('MKD',257),),lines,p),encoding='latin-1')
        proof=replace(proof,**{f:'\\'*128 for f in IDENTITY_FIELDS},core_session_id='\U00010000'*256,
                      binding_device_id='\U00010000'*256,binding_valid=False,reason='binding-invalid')
        proof.validate(self.tx,self.oid)
        envelope=maximum_document(self.tx)
        def length(value):return len(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))
        for field,value in canonical(proof).items():
            self.assertLessEqual(length(value),length(envelope[field]),field)
        for field in IDENTITY_FIELDS:self.assertEqual(258,length(getattr(proof,field)))
        w=self.start();w.outcome(self.oid,'unknown',previous=w.current,mkd_proof=proof,reason='x'*256,
                               accounting=A(control_read_bytes=2**63-1))
        self.assertEqual(proof,self.store.load(self.tx.id).operations[-1].mkd_proof)
        self.assertLessEqual(len(encode(w.current)),42978)
        self.assertEqual(w._reservation.used_bytes,sum(f.stat().st_size for f in Path(self.temp.name).glob('*.execution-*')))
        self.assertLessEqual(w._reservation.used_bytes,859560)

    def test_request_envelope_covers_maximum_utf8_library_path(self):
        from c64u_browser.import_mkd_proof import maximum_document
        prefix='/USB0/';suffix='/ARGONAUT_LIBRARY'
        library=replace(self.tx.library,path=prefix+'\U00010000'*(4096-len(prefix)-len(suffix))+suffix)
        tx=replace(self.tx,library=library).validate()
        path=destination(tx,'utf-8')
        self.assertEqual(4096,len(tx.library.path))
        self.assertEqual(2*len(path),len(maximum_document(tx)['request_hex']))
        self.assertEqual(len(path.hex()),len(maximum_document(tx)['request_hex']))
        with self.assertRaises(TransactionError):reserve_capacity(tx)

    def test_reserved_history_rejects_excess_encoded_bytes_and_slots(self):
        from c64u_browser.import_capacity import _ReservedHistory
        r=_ReservedHistory(self.tx);j=ExecutionJournalV4(self.tx)
        with self.assertRaises(TransactionError):r.check(j,b'x'*42979)
        self.assertEqual((0,0),(r.used_bytes,r.used_revisions))
        for revision in range(20):
            r.check(replace(j,revision=revision),b'x'*42978);r.charge(b'x'*42978)
        self.assertEqual((859560,20),(r.used_bytes,r.used_revisions))
        with self.assertRaises(TransactionError):r.check(replace(j,revision=20),b'x')
