"""Offline schema-3 persistence and crash boundaries; sockets are forbidden."""
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from c64u_browser.import_transaction import Journal, TransactionError, MiB
from c64u_browser.import_policy import JournalV2, prepare_transaction_v2
from c64u_browser.import_journal import JournalStore, encode, decode
from c64u_browser.import_execution import (ExecutionLimits, ExecutionAccounting as A,
    ExecutionJournal, ExecutionOperation, execution_transaction, intent, outcome, transition)
from c64u_browser.import_execution_store import ExecutionJournalStore
from tests.test_import_transaction import TransactionFixture


class ExecutionTests(TransactionFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(patch.stopall)
        patch('socket.socket', side_effect=AssertionError('network forbidden')).start()
        self.v2 = prepare_transaction_v2(self.first, self.second, library=self.f.library.identity,
            session=self.f.session, revision=0, manifest_digest=self.second.manifest_sha256, app_options={})
        self.tx3 = execution_transaction(self.v2, snapshot_evidence_sha256='a'*64,
            limits=ExecutionLimits(self.v2.budgets.planned_upload_bytes, MiB, 16*MiB))
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ExecutionJournalStore(self.root)

    def start(self):
        writer = self.store.create(self.tx3)
        writer.transition('awaiting-confirmation', previous=writer.current)
        writer.transition('staging', previous=writer.current)
        return writer

    def op(self, w, kind, path, *, size=0, sha256='', accounting=A(), collision='not-applicable'):
        operation_id = str(uuid4())
        w.intent(operation_id, kind, path, previous=w.current, collision=collision)
        return w.outcome(operation_id, 'completed', previous=w.current,
                         size=size, sha256=sha256, accounting=accounting)

    def directory(self, w):
        size = self.tx3.budgets.planned_upload_bytes
        self.op(w, 'snapshot-validation', '', size=size, accounting=A(snapshot_validation_reads=size))
        self.op(w, 'mkdir', self.tx3.directory, collision='absent')

    def uploads(self, w):
        self.directory(w)
        self.op(w, 'record', self.tx3.record_path, size=20, sha256='b'*64,
                accounting=A(control_upload_bytes=20, control_read_bytes=20), collision='absent')
        for item in self.tx3.items:
            self.op(w, 'upload', item.staged_path, size=item.size, sha256=item.sha256,
                    accounting=A(attempted_upload_bytes=item.size, confirmed_sender_bytes=item.size), collision='absent')

    def test_successful_chain_and_readback_are_inspection_only(self):
        w = self.start(); self.uploads(w)
        w.transition('verifying', previous=w.current)
        for item in self.tx3.items:
            self.op(w, 'readback', item.staged_path, size=item.size, sha256=item.sha256,
                    accounting=A(readback_bytes=item.size))
        w.transition('verified-staged', previous=w.current)
        loaded = self.store.load(self.tx3.id)
        self.assertEqual(w.current, loaded)
        self.assertEqual(encode(loaded), encode(decode(encode(loaded))))
        self.assertEqual(self.tx3.budgets.planned_upload_bytes, loaded.accounting.readback_bytes)
        self.assertFalse(hasattr(loaded, 'intent'))
        with self.assertRaises(ValueError): self.store.save(loaded)
        with self.assertRaises(TransactionError): self.store.create(self.tx3)
        with self.assertRaises(TransactionError): w.transition('staging', previous=w.current)

    def test_legacy_roundtrips_and_reserved_states_unchanged(self):
        for journal in (Journal(self.tx), JournalV2(self.v2)):
            raw = encode(journal)
            self.assertEqual(raw, encode(decode(raw)))
            self.assertIs(type(journal), type(decode(raw)))
            for state in ('staging', 'verifying', 'verified-staged', 'published'):
                with self.assertRaises(TransactionError): replace(journal, state=state).validate()
            with self.assertRaises(TransactionError): journal.intent('mkdir', self.tx.directory)
        with self.assertRaises(TransactionError): execution_transaction(self.tx, snapshot_evidence_sha256='a'*64, limits=self.tx3.limits)
        with self.assertRaises(TransactionError): JournalStore(self.root).save(ExecutionJournal(self.tx3))

    def test_projection_excludes_host_source_paths_and_tokens(self):
        raw = encode(ExecutionJournal(self.tx3))
        self.assertNotIn(self.tx.items[0].source.path.encode(), raw)
        for forbidden in (b'password', b'authorization', b'token', b'local_identity'):
            self.assertNotIn(forbidden, raw)

    def test_strict_versions_fields_and_types(self):
        raw = json.loads(encode(ExecutionJournal(self.tx3)))
        for key, value in [('schema_version', True), ('schema_version', 4), ('authorized', True),
                           ('state', 'published'), ('revision', True), ('checkpoint', -1)]:
            with self.subTest(key=key, value=value):
                changed = dict(raw); changed[key] = value
                with self.assertRaises(TransactionError): decode(json.dumps(changed).encode())
        for key in raw:
            changed = dict(raw); del changed[key]
            with self.assertRaises(TransactionError): decode(json.dumps(changed).encode())
        with self.assertRaises(TransactionError): decode(b'{"schema_version":3,"schema_version":3}')
        with self.assertRaises(TransactionError): decode(b'['*20+b']'*20)
        with self.assertRaises(TransactionError): decode(b'\xff')
        with self.assertRaises(TransactionError): decode(encode(ExecutionJournal(self.tx3))[:-2])

    def test_bad_policy_reference_and_snapshot_hash(self):
        for changes in ({'policy_version': 3}, {'execution_policy_version': True},
                        {'snapshot_evidence_sha256': 'bad'}, {'session_id': ''}):
            with self.assertRaises(TransactionError): replace(self.tx3, **changes).validate()

    def test_malformed_paths_and_duplicate_items(self):
        item = self.tx3.items[0]
        for field, value in [('staged_path', '../escape'), ('staged_path', '/USB1/x'),
                             ('staged_path', self.tx3.directory+'/ITEM-0001.crt'),
                             ('final_path', 'games/../x.crt'), ('final_path', 'games/sub/x.crt')]:
            with self.assertRaises(TransactionError):
                replace(self.tx3, items=(replace(item, **{field:value}),)).validate()
        with self.assertRaises(TransactionError): replace(self.tx3, items=(item, item)).validate()

    def test_invalid_transitions_and_no_publication(self):
        w = self.start()
        for state in ('published', 'verified-staged', 'verifying', 'prepared'):
            with self.assertRaises(TransactionError): w.transition(state, previous=w.current)
        for kind in ('delete', 'rmdir', 'rename', 'manifest', 'cleanup'):
            with self.assertRaises(TransactionError): w.intent(str(uuid4()), kind, self.tx3.directory, previous=w.current)

    def test_outcome_requires_intent_and_matching_identity(self):
        w = self.start()
        with self.assertRaises(TransactionError): w.outcome(str(uuid4()), 'completed', previous=w.current)
        operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        with self.assertRaises(TransactionError): w.outcome(str(uuid4()), 'completed', previous=w.current)
        with self.assertRaises(TransactionError): w.intent(str(uuid4()), 'mkdir', self.tx3.directory, previous=w.current, collision='absent')
        self.assertEqual('intent', self.store.load(self.tx3.id).operations[-1].outcome)

    def test_duplicate_and_missing_sequence_rejected(self):
        w = self.start(); self.directory(w)
        last = w.current.operations[-1]
        for modified in (replace(last, id=w.current.operations[0].id), replace(last, sequence=5)):
            with self.assertRaises(TransactionError): replace(w.current, operations=w.current.operations[:-1]+(modified,)).validate()

    def test_collision_refusal_never_claims_creation(self):
        w = self.start(); size = self.tx3.budgets.planned_upload_bytes
        self.op(w, 'snapshot-validation', '', size=size, accounting=A(snapshot_validation_reads=size))
        operation_id = str(uuid4())
        w.intent(operation_id, 'mkdir', self.tx3.directory, previous=w.current, collision='absent')
        w.outcome(operation_id, 'rejected', previous=w.current, collision='present', reason='collision')
        self.assertEqual('failed', w.current.state)
        self.assertEqual(1, w.current.checkpoint)
        self.assertEqual(w.current, self.store.load(self.tx3.id))
        with self.assertRaises(TransactionError): w.transition('staging', previous=w.current)

    def test_loaded_previous_cannot_be_used_by_live_writer(self):
        w = self.start()
        with self.assertRaises(TransactionError): w.transition('failed', previous=self.store.load(self.tx3.id), reason='failure')
        self.assertFalse(w.blocked)

    def test_stale_expected_previous_rejected(self):
        w = self.start(); old = w.current
        w.intent(str(uuid4()), 'snapshot-validation', '', previous=old)
        with self.assertRaises(TransactionError): w.transition('uncertain', previous=old, reason='interrupted')

    def test_pending_intent_only_allows_uncertain_termination(self):
        w = self.start(); w.intent(str(uuid4()), 'snapshot-validation', '', previous=w.current)
        for state in ('failed', 'canceled'):
            with self.assertRaises(TransactionError): w.transition(state, previous=w.current, reason='interrupted')
        w.transition('uncertain', previous=w.current, reason='interrupted')
        self.assertEqual('intent', w.current.operations[-1].outcome)

    def test_known_not_started_outcome_is_terminal(self):
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        w.outcome(operation_id, 'not-started', previous=w.current, reason='canceled-before-read')
        self.assertEqual('failed', w.current.state)
        with self.assertRaises(TransactionError): w.outcome(operation_id, 'completed', previous=w.current)

    def test_accounting_overflow_and_partition(self):
        for evidence in (A(readback_bytes=2**63), A(control_read_bytes=True),
                         A(attempted_upload_bytes=4, confirmed_sender_bytes=5),
                         A(attempted_upload_bytes=5, confirmed_sender_bytes=2, uncertain_send_bytes=2)):
            with self.assertRaises(TransactionError): evidence.validate()
        with self.assertRaises(TransactionError): A(readback_bytes=2**63-1).plus(A(readback_bytes=1))

    def test_partial_upload_uncertainty_retains_accounting(self):
        w = self.start(); self.directory(w)
        self.op(w, 'record', self.tx3.record_path, size=20, sha256='b'*64,
                accounting=A(control_upload_bytes=20, control_read_bytes=20), collision='absent')
        operation_id = str(uuid4()); item = self.tx3.items[0]
        w.intent(operation_id, 'upload', item.staged_path, previous=w.current, collision='absent')
        w.outcome(operation_id, 'unknown', previous=w.current, size=3, sha256='c'*64,
                  accounting=A(attempted_upload_bytes=7, confirmed_sender_bytes=3, uncertain_send_bytes=4), reason='lost-send')
        restored = self.store.load(self.tx3.id)
        self.assertEqual('uncertain', restored.state)
        self.assertEqual(4, restored.accounting.uncertain_send_bytes)

    def test_mismatch_and_readback_order(self):
        w = self.start()
        with self.assertRaises(TransactionError): w.intent(str(uuid4()), 'readback', self.tx3.items[0].staged_path, previous=w.current)
        self.uploads(w); w.transition('verifying', previous=w.current)
        with self.assertRaises(TransactionError): w.intent(str(uuid4()), 'upload', self.tx3.items[0].staged_path, previous=w.current, collision='absent')
        operation_id = str(uuid4()); item = self.tx3.items[0]
        w.intent(operation_id, 'readback', item.staged_path, previous=w.current)
        with self.assertRaises(TransactionError): w.outcome(operation_id, 'completed', previous=w.current, size=item.size, sha256='e'*64, accounting=A(readback_bytes=item.size))
        w.outcome(operation_id, 'rejected', previous=w.current, size=item.size, sha256='e'*64,
                  accounting=A(readback_bytes=item.size), reason='hash-mismatch')
        self.assertEqual('failed', self.store.load(self.tx3.id).state)

    def test_record_requires_readback_evidence(self):
        w = self.start(); self.directory(w); operation_id = str(uuid4())
        w.intent(operation_id, 'record', self.tx3.record_path, previous=w.current, collision='absent')
        with self.assertRaises(TransactionError): w.outcome(operation_id, 'completed', previous=w.current, size=20, sha256='b'*64, accounting=A(control_upload_bytes=20))

    def test_oversized_record_and_terminal_overbudget_evidence(self):
        tiny = replace(self.tx3, budgets=replace(self.tx3.budgets, journal_bytes=1))
        with self.assertRaises(TransactionError): encode(ExecutionJournal(tiny))
        with self.assertRaises(TransactionError): decode(b' '*(MiB+1))
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        w.outcome(operation_id, 'rejected', previous=w.current, reason='budget-exceeded', size=self.tx3.limits.snapshot_validation_reads+1,
                  accounting=A(snapshot_validation_reads=self.tx3.limits.snapshot_validation_reads+1))
        self.assertEqual(w.current, self.store.load(self.tx3.id))

    def test_failure_before_intent_retains_previous_and_blocks_writer(self):
        w = self.start(); previous = w.current
        with patch('os.replace', side_effect=OSError('replace failure')):
            with self.assertRaises(OSError): w.intent(str(uuid4()), 'snapshot-validation', '', previous=previous)
        self.assertIs(previous, w.current); self.assertTrue(w.blocked)
        self.assertEqual(previous, self.store.load(self.tx3.id))
        with self.assertRaises(TransactionError): w.intent(str(uuid4()), 'snapshot-validation', '', previous=previous)

    def test_failure_after_simulated_mutation_preserves_durable_intent(self):
        w = self.start(); self.directory(w)
        operation_id = str(uuid4())
        w.intent(operation_id, 'record', self.tx3.record_path, previous=w.current, collision='absent')
        previous = w.current; simulated_remote_bytes = b'record'
        self.assertTrue(simulated_remote_bytes)
        with patch('os.replace', side_effect=OSError('outcome failed')):
            with self.assertRaises(OSError): w.outcome(operation_id, 'completed', previous=previous,
                size=6, sha256=hashlib.sha256(simulated_remote_bytes).hexdigest(), accounting=A(control_upload_bytes=6, control_read_bytes=6))
        self.assertIs(previous, w.current)
        self.assertEqual('intent', self.store.load(self.tx3.id).operations[-1].outcome)

    def test_directory_sync_unsupported_fails_closed(self):
        for error in (errno.EINVAL, errno.ENOTSUP, errno.EIO):
            with patch('os.fsync', side_effect=OSError(error, 'sync')):
                with self.assertRaises(OSError): self.store.create(self.tx3)
        self.assertEqual([], list(self.root.glob('*.execution-*')))

    def test_post_replace_sync_failure_keeps_prior_intent_file(self):
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        previous = w.current
        prior_path = self.root/self.store._filename(self.tx3.id, previous.revision)
        raw = prior_path.read_bytes(); original = os.fsync; calls = []
        def failing(fd):
            calls.append(fd)
            if len(calls) == 3: raise OSError(errno.EIO, 'directory sync failed')
            return original(fd)
        size = self.tx3.budgets.planned_upload_bytes
        with patch('os.fsync', side_effect=failing):
            with self.assertRaises(OSError): w.outcome(operation_id, 'completed', previous=previous,
                size=size, accounting=A(snapshot_validation_reads=size))
        self.assertTrue(w.blocked); self.assertIs(w.current, previous)
        self.assertEqual(raw, prior_path.read_bytes())
        # Replacement may be visible despite failed durability. Loading is only
        # inspection and never certifies that this latest revision survived crash.
        loaded = self.store.load(self.tx3.id)
        self.assertEqual(previous.revision+1, loaded.revision)
        with self.assertRaises(TransactionError): self.store.create(self.tx3)

    def test_file_sync_failure_keeps_previous(self):
        w = self.start(); previous = w.current; original = os.fsync; calls = []
        def failing(fd):
            calls.append(fd)
            if len(calls) == 2: raise OSError(errno.EIO, 'file sync failed')
            return original(fd)
        with patch('os.fsync', side_effect=failing):
            with self.assertRaises(OSError): w.intent(str(uuid4()), 'snapshot-validation', '', previous=previous)
        self.assertEqual(previous, self.store.load(self.tx3.id))
        self.assertTrue(w.blocked)

    def test_atomic_persistence_order(self):
        original_sync = os.fsync; original_replace = os.replace; events = []
        def sync(fd): events.append('sync'); return original_sync(fd)
        def rename(*args, **kwargs): events.append('replace'); return original_replace(*args, **kwargs)
        with patch('os.fsync', side_effect=sync), patch('os.replace', side_effect=rename): self.store.create(self.tx3)
        self.assertEqual(['sync', 'sync', 'replace', 'sync'], events)

    def test_crash_reload_at_each_boundary(self):
        w = self.store.create(self.tx3)
        def verify():
            restored = ExecutionJournalStore(self.root).load(self.tx3.id)
            self.assertEqual(w.current, restored)
            with self.assertRaises(ValueError): self.store.save(restored)
            with self.assertRaises(TransactionError): self.store.create(self.tx3)
        verify()
        for state in ('awaiting-confirmation', 'staging'):
            w.transition(state, previous=w.current); verify()
        operation_id = str(uuid4()); w.intent(operation_id, 'snapshot-validation', '', previous=w.current); verify()
        size = self.tx3.budgets.planned_upload_bytes
        w.outcome(operation_id, 'completed', previous=w.current, size=size, accounting=A(snapshot_validation_reads=size)); verify()

    def test_missing_checkpoint_and_tampered_predecessor(self):
        w = self.start()
        path = self.root/self.store._filename(self.tx3.id, 1); raw = path.read_bytes(); path.unlink()
        with self.assertRaises(TransactionError): self.store.load(self.tx3.id)
        path.write_bytes(raw); path.chmod(0o600)
        data = json.loads(raw); data['previous_digest'] = 'f'*64; path.write_text(json.dumps(data))
        with self.assertRaises(TransactionError): self.store.load(self.tx3.id)

    def test_private_permissions_symlinks_and_exclusive_creation(self):
        w = self.store.create(self.tx3)
        path = self.root/self.store._filename(self.tx3.id, 0)
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        with self.assertRaises(TransactionError): self.store.create(self.tx3)
        raw = path.read_bytes(); path.unlink(); target = self.root/'target'; target.write_bytes(raw); path.symlink_to(target)
        with self.assertRaises(OSError): self.store.load(self.tx3.id)

    def test_checkpoint_quota_and_foreign_identity(self):
        with patch('c64u_browser.import_execution_store.MAX_RECOVERY_JOURNALS', 0):
            with self.assertRaises(TransactionError): self.store.create(self.tx3)
        w = self.store.create(self.tx3)
        with self.assertRaises(TransactionError): replace(w.current, transaction=replace(self.tx3, id=str(uuid4()))).validate()


    def test_retained_history_has_aggregate_byte_bound(self):
        self.tx3 = replace(self.tx3, budgets=replace(self.tx3.budgets, journal_bytes=8000))
        w = self.start()
        with self.assertRaises(TransactionError): self.uploads(w)
        self.assertTrue(w.blocked)
        self.assertEqual(w.current, self.store.load(self.tx3.id))
        self.assertLessEqual(sum(p.stat().st_size for p in self.root.glob('*.execution-*')), 8000)

    def test_completed_consequence_can_terminate_without_claiming_success(self):
        w = self.start(); operation_id = str(uuid4()); size = self.tx3.budgets.planned_upload_bytes
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        w.outcome(operation_id, 'completed', previous=w.current, size=size,
            accounting=A(snapshot_validation_reads=size), terminal_state='canceled', reason='canceled-after-read')
        self.assertEqual('completed', w.current.operations[-1].outcome)
        self.assertEqual('canceled', self.store.load(self.tx3.id).state)

    def test_truncated_revision_does_not_fall_back_to_resume(self):
        w = self.start()
        path = self.root/self.store._filename(self.tx3.id, w.current.revision)
        path.write_bytes(path.read_bytes()[:50])
        with self.assertRaises(TransactionError): self.store.load(self.tx3.id)
        with self.assertRaises(TransactionError): self.store.create(self.tx3)

    def test_remote_control_overflow_is_preserved_only_as_failure(self):
        w = self.start(); operation_id = str(uuid4()); size = self.tx3.budgets.planned_upload_bytes
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        evidence = A(snapshot_validation_reads=size, control_read_bytes=self.tx3.limits.control_read_bytes+1)
        with self.assertRaises(TransactionError):
            w.outcome(operation_id, 'completed', previous=w.current, size=size, accounting=evidence)
        w.outcome(operation_id, 'completed', previous=w.current, size=size, accounting=evidence,
                  terminal_state='failed', reason='control-budget')
        self.assertEqual(evidence, self.store.load(self.tx3.id).accounting)

    def test_library_aliases_rejected(self):
        for path in ('/USB1/../ARGONAUT_LIBRARY', '/USB1//ARGONAUT_LIBRARY', '/USB1/./ARGONAUT_LIBRARY'):
            with self.assertRaises(TransactionError):
                replace(self.tx3, library=replace(self.tx3.library, root='/USB1', path=path)).validate()

    def test_unstarted_operation_can_retain_control_reads(self):
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        w.outcome(operation_id, 'not-started', previous=w.current,
                  accounting=A(control_read_bytes=10), reason='admission-failed')
        self.assertEqual(10, self.store.load(self.tx3.id).accounting.control_read_bytes)

    def test_failure_counts_cannot_contradict_observations(self):
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        with self.assertRaises(TransactionError):
            w.outcome(operation_id, 'rejected', previous=w.current, size=1,
                      accounting=A(snapshot_validation_reads=2), reason='bad-observation')

    def test_loading_oversized_history_fails_before_decode(self):
        self.store.create(self.tx3)
        path = self.root/self.store._filename(self.tx3.id, 1)
        path.write_bytes(b'x'*MiB); path.chmod(0o600)
        with patch('c64u_browser.import_execution_store.decode', side_effect=AssertionError('must reject before parsing')):
            with self.assertRaises(TransactionError): self.store.load(self.tx3.id)

    def test_historical_transaction_cannot_be_adopted(self):
        JournalStore(self.root).save(JournalV2(self.v2))
        with self.assertRaises(ValueError): self.store.create(self.tx3)
        self.assertEqual(JournalV2(self.v2), JournalStore(self.root).load(self.v2.id))

    def test_full_chain_crash_prefixes_remain_inspection_only(self):
        import shutil
        w = self.start(); self.uploads(w); w.transition('verifying', previous=w.current)
        for item in self.tx3.items:
            self.op(w, 'readback', item.staged_path, size=item.size, sha256=item.sha256,
                    accounting=A(readback_bytes=item.size))
        w.transition('verified-staged', previous=w.current)
        with tempfile.TemporaryDirectory() as folder:
            crash_store = ExecutionJournalStore(folder)
            for path in sorted(self.root.glob('*.execution-*')):
                shutil.copy2(path, Path(folder)/path.name)
                visible = crash_store.load(self.tx3.id)
                self.assertEqual(decode(path.read_bytes()), visible)
                with self.assertRaises(TransactionError): crash_store.create(self.tx3)
                with self.assertRaises(ValueError): crash_store.save(visible)

    @staticmethod
    def invalid_hashes():
        class StringSubclass(str): pass
        return (None, False, True, 0, -1, 1.5, 0.0, [], {}, (), b'a'*64,
                StringSubclass('a'*64), 'A'*64, 'a'*63+'B', 'a'*63, 'a'*65,
                ' '*64, 'a'*63+' ', 'g'*64, 'a'*63+'\n', 'a'*63+'é')

    def test_hash_direct_construction_rejects_all_invalid_types_and_strings(self):
        for kind in ('snapshot-validation', 'mkdir', 'record', 'upload', 'readback'):
            for status in ('intent', 'completed', 'rejected', 'unknown', 'not-started'):
                for value in self.invalid_hashes():
                    with self.subTest(kind=kind, status=status, value=repr(value)):
                        with self.assertRaises(TransactionError):
                            ExecutionOperation(str(uuid4()), 1, kind, '', outcome=status, sha256=value)

    def test_hash_absence_and_mandatory_contracts(self):
        for kind in ('record', 'upload', 'readback'):
            with self.assertRaises(TransactionError):
                ExecutionOperation(str(uuid4()), 1, kind, '', outcome='completed', sha256='')
            for status in ('intent', 'not-started', 'rejected', 'unknown'):
                op = ExecutionOperation(str(uuid4()), 1, kind, '', outcome=status, sha256='')
                self.assertEqual('', op.sha256)
            for status in ('completed', 'rejected', 'unknown'):
                op = ExecutionOperation(str(uuid4()), 1, kind, '', outcome=status, sha256='abcdef0123456789'*4)
                self.assertEqual('abcdef0123456789'*4, op.sha256)
        for kind in ('snapshot-validation', 'mkdir'):
            for status in ('intent', 'completed', 'rejected', 'unknown', 'not-started'):
                self.assertEqual('', ExecutionOperation(str(uuid4()), 1, kind, '', outcome=status).sha256)
                with self.assertRaises(TransactionError):
                    ExecutionOperation(str(uuid4()), 1, kind, '', outcome=status, sha256='a'*64)
        for status in ('intent', 'not-started'):
            with self.assertRaises(TransactionError):
                ExecutionOperation(str(uuid4()), 1, 'upload', '', outcome=status, sha256='a'*64)
        with self.assertRaises(TransactionError):
            ExecutionOperation(str(uuid4()), 1, 'record', '', outcome='rejected', collision='present', sha256='a'*64)

    def test_hash_encoding_revalidates_bypassed_constructor(self):
        import copy
        w = self.start(); operation_id = str(uuid4())
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        for value in self.invalid_hashes():
            op = copy.copy(w.current.operations[-1])
            object.__setattr__(op, 'sha256', value)  # Deliberately forge memory for encoder defense.
            malformed = replace(w.current, operations=(op,))
            with self.assertRaises(TransactionError): malformed.validate()
            with self.assertRaises(TransactionError): encode(malformed)

    def test_hash_decode_rejects_malformed_intent_and_outcome_json(self):
        w = self.start(); self.directory(w); operation_id = str(uuid4())
        w.intent(operation_id, 'record', self.tx3.record_path, previous=w.current, collision='absent')
        pending = encode(w.current)
        w.outcome(operation_id, 'completed', previous=w.current, size=20, sha256='b'*64,
                  accounting=A(control_upload_bytes=20, control_read_bytes=20))
        completed = encode(w.current)
        values = (None, False, True, 0, -1, 1.5, 0.0, [], {}, 'A'*64,
                  'a'*63+'B', 'a'*63, 'a'*65, ' '*64, 'a'*63+' ', 'g'*64)
        for raw in (pending, completed):
            for value in values:
                document = json.loads(raw); document['operations'][-1]['sha256'] = value
                with self.subTest(intent=raw is pending, value=value):
                    with self.assertRaises(TransactionError): decode(json.dumps(document).encode())
        document = json.loads(completed); document['operations'][-1]['sha256'] = ''
        with self.assertRaises(TransactionError): decode(json.dumps(document).encode())
        self.assertEqual(pending, encode(decode(pending)))
        self.assertEqual(completed, encode(decode(completed)))

    def test_hash_invalid_outcomes_never_advance_writer_or_disk(self):
        w = self.start(); operation_id = str(uuid4()); size = self.tx3.budgets.planned_upload_bytes
        w.intent(operation_id, 'snapshot-validation', '', previous=w.current)
        previous = w.current
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        for value in self.invalid_hashes():
            with self.assertRaises(TransactionError):
                w.outcome(operation_id, 'completed', previous=previous, size=size, sha256=value,
                          accounting=A(snapshot_validation_reads=size))
            self.assertIs(previous, w.current)
            self.assertFalse(w.blocked)  # Invalid input rejected before any persistence attempt.
            self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})
            self.assertEqual(previous, self.store.load(self.tx3.id))
        w.outcome(operation_id, 'completed', previous=previous, size=size, sha256='',
                  accounting=A(snapshot_validation_reads=size))
        self.assertEqual('', self.store.load(self.tx3.id).operations[-1].sha256)

    def test_hash_mandatory_record_outcome_empty_rejected_without_advance(self):
        w = self.start(); self.directory(w); operation_id = str(uuid4())
        w.intent(operation_id, 'record', self.tx3.record_path, previous=w.current, collision='absent')
        previous = w.current
        for value in ('', *self.invalid_hashes()):
            with self.assertRaises(TransactionError):
                w.outcome(operation_id, 'completed', previous=previous, size=20, sha256=value,
                          accounting=A(control_upload_bytes=20, control_read_bytes=20))
            self.assertIs(previous, w.current)
            self.assertEqual(previous, self.store.load(self.tx3.id))
        w.outcome(operation_id, 'completed', previous=previous, size=20, sha256='b'*64,
                  accounting=A(control_upload_bytes=20, control_read_bytes=20))
        self.assertEqual('b'*64, self.store.load(self.tx3.id).operations[-1].sha256)

    def test_hash_reload_rejects_malformed_latest_intent_and_outcome(self):
        w = self.start(); self.directory(w); operation_id = str(uuid4())
        w.intent(operation_id, 'record', self.tx3.record_path, previous=w.current, collision='absent')
        def inspect_rejection(journal):
            path = self.root/self.store._filename(self.tx3.id, journal.revision)
            raw = path.read_bytes()
            try:
                for value in (None, False, True, 0, -1, 0.0, [], {}, 'A'*64, 'g'*64):
                    document = json.loads(raw); document['operations'][-1]['sha256'] = value
                    path.write_bytes(json.dumps(document).encode())
                    with self.assertRaises(TransactionError): self.store.load(self.tx3.id)
                    self.assertIs(journal, w.current)
            finally: path.write_bytes(raw)
            self.assertEqual(journal, self.store.load(self.tx3.id))
        inspect_rejection(w.current)
        w.outcome(operation_id, 'completed', previous=w.current, size=20, sha256='b'*64,
                  accounting=A(control_upload_bytes=20, control_read_bytes=20))
        inspect_rejection(w.current)

    def test_hash_corrupt_history_blocks_next_writer_transition(self):
        w = self.start(); self.directory(w); previous = w.current
        path = self.root/self.store._filename(self.tx3.id, previous.revision)
        document = json.loads(path.read_bytes()); document['operations'][-1]['sha256'] = False
        path.write_bytes(json.dumps(document).encode())
        files_before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with self.assertRaises(TransactionError):
            w.intent(str(uuid4()), 'record', self.tx3.record_path, previous=previous, collision='absent')
        self.assertIs(previous, w.current); self.assertTrue(w.blocked)
        self.assertEqual(files_before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_hash_creation_rejects_invalid_transaction_references_without_files(self):
        for field in ('snapshot_evidence_sha256', 'plan_digest', 'manifest_digest'):
            for value in ('', *self.invalid_hashes()):
                with self.assertRaises(TransactionError): self.store.create(replace(self.tx3, **{field:value}))
                self.assertEqual([], list(self.root.iterdir()))

if __name__ == '__main__': unittest.main()
