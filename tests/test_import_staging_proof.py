"""Real Core/admission/adapter/journal ordering with loopback-only FTP."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from tests import test_import_staging as staging
from c64u_browser.import_execution_store import ExecutionJournalStore
from c64u_browser.import_mkd_proof import RULE
from c64u_browser.jobs import JobCancelled


class StagingProofTests(TestCase):
    fixture=staging.StagingTests.fixture
    stage=staging.StagingTests.stage
    journal=staging.StagingTests.journal
    failure=staging.StagingTests.failure
    path=staging.StagingTests.path

    def triple(self):
        self.server.after_mutation[b'MKD']=lambda p:b'257 "//'+p+b'" created.\r\n'

    def test_beige_raw_proof_durable_before_every_stor(self):
        with self.fixture(beige=True):
            self.triple();seen=[]
            def hook(verb,path):
                if verb==b'MKD':
                    self.assertEqual('intent',self.journal().operations[-1].outcome)
                    self.assertIsNone(self.journal().operations[-1].mkd_proof)
                if verb==b'STOR':
                    op=self.journal().operations[1]
                    self.assertEqual('completed',op.outcome)
                    self.assertEqual(RULE,op.mkd_proof.compatibility_rule)
                    self.assertEqual('invalid',op.mkd_proof.path_status)
                    self.assertEqual('25EA78',op.mkd_proof.physical_id)
                    self.assertEqual('live-rest',op.mkd_proof.provenance)
                    self.assertEqual(self.tx.session_id,op.mkd_proof.core_session_id)
                    seen.append(path)
            self.server.before_command=hook
            self.assertEqual('verified-staged',self.stage().state)
            j=self.journal();self.assertEqual((4,3),(j.schema_version,j.transaction.execution_policy_version))
            self.assertEqual(2,len(seen));self.assertEqual(19,len(list(self.folder.glob('*.execution-*'))))
            self.assertEqual((b'257 "//'+self.path()+b'" created.').hex(),j.operations[1].mkd_proof.reply_lines_hex[0])

    def test_unqualified_device_triple_slash_has_no_stor(self):
        with self.fixture():
            self.triple();self.failure();j=self.journal()
            self.assertEqual('uncertain',j.state);self.assertEqual('unqualified',j.operations[-1].mkd_proof.decision)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_live_rest_missing_or_changed_after_connect(self):
        for change in ('missing','firmware','binding'):
            with self.subTest(change=change),self.fixture(beige=True):
                self.triple();adapter=self.core._client._ftp_reads
                if change=='missing':adapter._creation_identity=None
                elif change=='firmware':adapter._creation_identity=replace(adapter._creation_identity,firmware='1.1.0')
                else:adapter.binding=replace(adapter.binding,core_session_id='stale')
                self.failure();self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_binding_changes_after_ack_keeps_positive_wire_uncertain(self):
        with self.fixture(beige=True):
            self.triple();adapter=self.core._client._ftp_reads;original=adapter.classify_staging_mkdir
            def changed(*args,**kwargs):
                self.core._session_id='stale'
                return original(*args,**kwargs)
            with patch.object(adapter,'classify_staging_mkdir',changed):self.failure()
            j=self.journal();self.assertEqual('uncertain',j.state)
            proof=j.operations[-1].mkd_proof
            self.assertEqual(257,proof.reply_code);self.assertTrue(proof.reply_lines_hex)
            self.assertFalse(proof.binding_valid);self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_cancel_after_ack_persists_accepted_proof_first(self):
        with self.fixture(beige=True):
            self.triple();cancelled=False
            def hook(verb,path):
                nonlocal cancelled
                if verb==b'MKD':cancelled=True
            def check():
                if cancelled:raise JobCancelled()
            self.server.mutation_hook=hook;self.failure(check_cancel=check)
            j=self.journal();self.assertEqual('canceled',j.state)
            self.assertEqual('completed',j.operations[-1].outcome)
            self.assertEqual(RULE,j.operations[-1].mkd_proof.compatibility_rule)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_qualified_outcome_sync_failure_prevents_stor(self):
        with self.fixture(beige=True):
            self.triple();original=ExecutionJournalStore._append
            def fail(store,journal,*,previous):
                if journal.operations and journal.operations[-1].kind=='mkdir' and journal.operations[-1].outcome=='completed':
                    self.assertEqual(RULE,journal.operations[-1].mkd_proof.compatibility_rule)
                    raise OSError('sync failure')
                return original(store,journal,previous=previous)
            with patch.object(ExecutionJournalStore,'_append',fail):self.failure()
            self.assertEqual('intent',self.journal().operations[-1].outcome)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_two_item_capacity_refusal_is_before_lease(self):
        with self.fixture(beige=True,count=2):
            before=self.server.connections;self.failure()
            self.assertEqual(before,self.server.connections)
            self.assertFalse(list(self.folder.iterdir()))
            self.assertNotIn(b'MKD',self.server.verbs[self.start:])

    def test_wire_reply_rejections_retain_raw_and_stop(self):
        replies=(lambda p:b'257 "/'+p+b'" created.\r\n',
                 lambda p:b'257 "///'+p+b'" created.\r\n',
                 lambda p:b'257 "//'+p+b'" created. extra\r\n',
                 lambda p:b'257-first\r\n257 "//'+p+b'" created.\r\n',
                 lambda p:b'257 "'+p+b'" bad\x00comment\r\n')
        for reply in replies:
            with self.subTest(reply=reply),self.fixture(beige=True):
                self.server.after_mutation[b'MKD']=reply;self.failure()
                self.assertEqual('uncertain',self.journal().state)
                self.assertTrue(self.journal().operations[-1].mkd_proof.reply_lines_hex)
                self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_adapter_replaced_after_ack_cannot_authorize_upload(self):
        with self.fixture(beige=True):
            self.triple();adapter=self.core._client._ftp_reads;original=adapter.mutate_evidence
            def changed(*args,**kwargs):
                result=original(*args,**kwargs)
                self.core._client._ftp_reads=object()
                return result
            try:
                with patch.object(adapter,'mutate_evidence',changed):self.failure()
                self.assertEqual('uncertain',self.journal().state)
                self.assertFalse(self.journal().operations[-1].mkd_proof.binding_valid)
                self.assertNotIn(b'STOR',self.server.verbs[self.start:])
            finally:self.core._client._ftp_reads=adapter

    def test_transport_returning_no_observation_cannot_claim_non_submission(self):
        with self.fixture(beige=True):
            self.triple();adapter=self.core._client._ftp_reads;original=adapter.mutate_evidence
            def lost(*args,**kwargs):original(*args,**kwargs);return None
            with patch.object(adapter,'mutate_evidence',lost):self.failure()
            j=self.journal();self.assertEqual('uncertain',j.state)
            self.assertEqual('mkd-unobserved',j.reason)
            self.assertIsNone(j.operations[-1].mkd_proof)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_contradictory_transport_proof_rejected_without_outcome_or_stor(self):
        from c64u_browser.c64u_ftp_types import Outcome
        from c64u_browser.import_transaction import TransactionError
        with self.fixture(beige=True):
            self.triple();adapter=self.core._client._ftp_reads;original=adapter.mutate_evidence
            def contradictory(*args,**kwargs):
                result=original(*args,**kwargs)
                # Retain actual submission/257/ack/raw bytes: change only the
                # contradictory transport claim, exactly as in the inspection.
                return replace(result,outcome=Outcome.NOT_STARTED)
            with patch.object(adapter,'mutate_evidence',contradictory):error=self.failure()
            self.assertIsInstance(error,TransactionError)
            self.assertIn('transport/submission',str(error))
            self.assertTrue(any('durable intent retained' in n for n in error.__notes__))
            j=self.journal();self.assertEqual('uncertain',j.state)
            self.assertEqual('intent',j.operations[-1].outcome)
            self.assertIsNone(j.operations[-1].mkd_proof)
            self.assertEqual(1,self.server.verbs[self.start:].count(b'MKD'))
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])

    def test_unknown_after_positive_ack_keeps_evidence_but_never_stores(self):
        from c64u_browser.c64u_ftp_types import Outcome
        with self.fixture(beige=True):
            self.triple();adapter=self.core._client._ftp_reads;original=adapter.mutate_evidence
            def uncertain(*args,**kwargs):return replace(original(*args,**kwargs),outcome=Outcome.UNKNOWN)
            with patch.object(adapter,'mutate_evidence',uncertain):self.failure()
            j=self.journal();self.assertEqual('uncertain',j.state)
            proof=j.operations[-1].mkd_proof
            self.assertEqual(('unknown','completed','unqualified'),
                             (proof.transport_outcome,proof.acknowledgment,proof.decision))
            self.assertTrue(proof.reply_lines_hex)
            self.assertNotIn(b'STOR',self.server.verbs[self.start:])
