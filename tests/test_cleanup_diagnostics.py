"""Target-only cleanup evidence with real services and a network-blocked peer."""
import json
from threading import Event
from unittest.mock import patch
import unittest
from c64u_browser import diagnostics
from c64u_browser.api import BrowserError
from c64u_browser.scheduler import DeviceSession
import test_deferred_upload_cleanup as fixtures


class CleanupDiagnostics(unittest.TestCase):
    start = fixtures.CleanupContinuation.start
    finish = fixtures.CleanupContinuation.finish
    issued = fixtures.CleanupContinuation.issued
    prepare = fixtures.CleanupContinuation.prepare

    def setUp(self):
        fixtures.CleanupContinuation.setUp(self)
        self.events = []
        self.terminal = Event()
        def capture(*args, **kw):
            if args[1] == 'partial_cleanup':
                self.events.append(kw)
                if kw['details']['event'] == 'terminal':self.terminal.set()
        self.real_emitter=diagnostics.diagnostic_event
        logger = patch.object(diagnostics, 'diagnostic_event', side_effect=capture)
        logger.start();self.addCleanup(logger.stop)

    def fields(self, event):
        return [e['details'] for e in self.events if e['details']['event'] == event]

    def execute(self, evidence):
        self.terminal.clear()
        job = self.service._execute_intent_cleanup(evidence)
        result = job.wait(5)
        self.assertTrue(self.terminal.wait(5))
        return result

    def test_exact_observations_and_correlation(self):
        evidence, result = self.issued();self.prepare(evidence)
        deleted = self.execute(evidence)
        self.assertEqual('succeeded', deleted.state)
        self.assertTrue(all(e['attempt_id'] == evidence.job_id for e in
                            (x['details'] for x in self.events)))
        self.assertTrue(self.fields('cancellation')[0]['accepted'])
        self.assertTrue(self.fields('snapshot_comparison')[0]['snapshot_match'])
        observations = self.fields('target_observation')
        self.assertEqual(2, len(observations))
        self.assertTrue(all(e['target_match'] and e['kind'] == 'file' for e in observations))
        self.assertEqual(observations[0]['size'], observations[1]['size'])
        self.assertTrue(all(e['parent_match'] for e in self.fields('parent_identity')))
        self.assertTrue(self.fields('transfer_evidence'))
        self.assertEqual(1, self.fields('deletion_result')[-1]['removed_count'])

    def test_changed_size_rejects_without_mutation(self):
        evidence,_ = self.issued();self.prepare(evidence)
        self.peer.files[evidence.partial_upload.location.path.encode()] = b'longer staging bytes'
        result = self.execute(evidence)
        event = self.fields('snapshot_comparison')[-1]
        self.assertEqual('file-size-change', event['reason'])
        self.assertNotEqual(event['reviewed_size'], event['size'])
        self.assertEqual('failed', result.state)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_changed_type_rejects_without_traversal(self):
        evidence,_ = self.issued();self.prepare(evidence)
        path = evidence.partial_upload.location.path.encode()
        del self.peer.files[path];self.peer.directories.add(path)
        before = len(self.peer.calls)
        result = self.execute(evidence)
        self.assertEqual('file-type-change',self.fields('snapshot_comparison')[-1]['reason'])
        self.assertEqual('failed',result.state)
        self.assertNotIn(('list',path),self.peer.calls[before:])
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_missing_target_classification(self):
        evidence,_ = self.issued();self.prepare(evidence)
        del self.peer.files[evidence.partial_upload.location.path.encode()]
        self.assertEqual('failed',self.execute(evidence).state)
        self.assertEqual('target-missing',self.fields('target_observation')[-1]['reason'])
        self.assertFalse(self.fields('target_observation')[-1]['target_match'])
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_parent_mismatch_does_not_log_entries(self):
        evidence,_ = self.issued();self.prepare(evidence)
        original = self.client.list_directory
        with patch.object(self.client,'list_directory',side_effect=lambda p:('/wrong',original(p)[1])):
            self.assertEqual('failed',self.execute(evidence).state)
        self.assertFalse(self.fields('parent_identity')[-1]['parent_match'])
        self.assertEqual('directory-identity', self.fields('execution_stop')[-1]['error_code'])
        self.assertNotIn('/wrong',json.dumps(self.events))

    def test_privacy_unrelated_entries_and_payload(self):
        self.peer.files[b'/USB2/private-password-token'] = b'PRIVATE PAYLOAD'
        evidence,_ = self.issued();self.prepare(evidence);self.execute(evidence)
        encoded = json.dumps(self.events)
        for secret in ('private-password-token','PRIVATE PAYLOAD','/USB2/',
                       evidence.partial_upload.location.path,self.session.device_id,self.session.session_id):
            self.assertNotIn(secret,encoded)

    def test_logging_failure_does_not_change_calls_or_results(self):
        sequences=[]
        for broken in (False,True):
            evidence,_ = self.issued()
            before=len(self.peer.calls)
            with patch.object(diagnostics,'diagnostic_event',side_effect=RuntimeError('sink failed')) if broken else patch.object(diagnostics,'diagnostic_event'):
                self.prepare(evidence)
                result=self.service._execute_intent_cleanup(evidence).wait(5)
            self.assertEqual('succeeded',result.state)
            sequences.append([(c[0],) for c in self.peer.calls[before:]])
        self.assertEqual(sequences[0],sequences[1])
        self.assertEqual(1,sum(c[0]=='delete' for c in sequences[0]))

    def test_session_replacement_and_no_retry(self):
        job,release=self.start()
        self.session=DeviceSession('other','replacement')
        self.assertFalse(self.service._request_upload_cancel(job,'delete'))
        self.assertFalse(self.fields('cancellation')[-1]['session_match'])
        self.finish(job,release)
        self.assertFalse(any(c[0] in ('delete','rmdir') for c in self.peer.calls))

    def test_no_timers_or_sleeps_added_to_diagnostics(self):
        import inspect
        source=inspect.getsource(diagnostics.cleanup_event)
        self.assertNotIn('sleep(',source)
        self.assertNotIn('timeout_add',source)
        self.assertNotIn('submit(',source)

    def test_terminal_stor_acknowledgement_preserved(self):
        evidence,_=self.issued()
        self.assertTrue(self.terminal.wait(5))
        transfer=self.fields('transfer_evidence')[-1]
        self.assertTrue(transfer['terminal_stor_acknowledged'])
        self.assertEqual('staging-candidate',transfer['publication'])

    def test_stor_timeout_unknown_and_byte_counts(self):
        from c64u_browser.c64u_ftp_types import WriteEvidence, FtpOperationError, ErrorCode, Outcome
        def timeout(path, source, **kw):
            self.peer.files[path]=b'partial'
            raise FtpOperationError(ErrorCode.DATA_IDLE_TIMEOUT,'data-io',
                transfer=WriteEvidence(100,True,150,None,7,None,Outcome.UNKNOWN,
                                       attempted_send_bytes=15))
        with patch.object(self.peer,'write_from',side_effect=timeout):
            evidence,_=self.issued()
        self.assertTrue(self.terminal.wait(5))
        event=self.fields('transfer_evidence')[-1]
        self.assertFalse(event['terminal_stor_acknowledged'])
        self.assertEqual(7,event['sender_confirmed_bytes'])
        self.assertEqual(15,event['attempted_send_bytes'])

    def test_mutation_failure_and_unknown_evidence_no_retry(self):
        from c64u_browser.c64u_ftp_types import FtpOperationError, ErrorCode, Outcome, MutationEvidence
        for outcome in (Outcome.REJECTED,Outcome.UNKNOWN):
            evidence,_=self.issued();self.prepare(evidence)
            error=FtpOperationError(ErrorCode.NETWORK,'delete',mutation=MutationEvidence(
                'delete','DELE',outcome,True,True,None))
            with patch.object(self.peer,'delete',side_effect=error) as dispatch:
                result=self.execute(evidence)
                self.assertEqual('failed',result.state)
                self.assertEqual(outcome.value,self.fields('deletion_result')[-1]['mutation_outcome'])
                with self.assertRaises(BrowserError):self.service._execute_intent_cleanup(evidence)
                dispatch.assert_called_once()

    def test_real_lease_release_event_after_close(self):
        from c64u_browser.c64u_ftp import C64UFtpLeaseManager
        from c64u_browser.c64u_ftp_types import ConnectionBinding
        from unittest.mock import Mock
        binding=self.client._ftp_reads.binding
        manager=C64UFtpLeaseManager(lambda _:binding,lambda _: 'PRIVATE PASSWORD')
        client=Mock()
        with diagnostics.cleanup_context('a'*32), patch('c64u_browser.c64u_ftp.C64UFtpClient',return_value=client):
            with manager.lease(binding):
                self.assertEqual(1,manager.active_count)
            self.assertEqual(0,manager.active_count)
        client.close.assert_called_once()
        self.assertTrue(self.fields('lease_release')[-1]['local_release'])

    context = fixtures.CleanupCoordinator.context
    complete = fixtures.CleanupCoordinator.complete

    def test_admission_rejection_and_completion_diagnostics(self):
        from unittest.mock import Mock
        app,coordinator,job=self.complete()
        before=list(self.peer.calls)
        app.run_file_job=Mock(return_value=False)
        coordinator.complete(Mock())
        self.assertFalse(self.fields('admission')[-1]['admitted'])
        self.assertTrue(self.fields('coordinator_complete'))
        self.assertEqual(before,self.peer.calls)
        coordinator.complete(Mock())
        app.run_file_job.assert_called_once()

    def test_stale_coordinator_reports_no_ui_authority(self):
        from unittest.mock import Mock
        app,coordinator,job=self.complete()
        self.session=DeviceSession('other','new')
        done=Mock();coordinator.complete(done)
        done.assert_not_called()
        self.assertFalse(self.fields('coordinator_complete')[-1]['session_match'])


    def test_existing_logger_supplies_timestamp_and_job_phase(self):
        # Restore the real emitter within this test only.
        import logging
        class Capture(logging.Handler):
            def emit(inner, record):inner.event=record.operation_event
        sink=Capture();diagnostics.LOGGER.addHandler(sink)
        self.addCleanup(diagnostics.LOGGER.removeHandler,sink)
        emitter=self.real_emitter
        with patch.object(diagnostics,'diagnostic_event',emitter), diagnostics.cleanup_context('a'*32), diagnostics.operation_context(job_id='b'*32,phase='file.delete.prepare'):
            diagnostics.cleanup_event('target_observation',kind='file',size=7,target_match=True)
        self.assertIsInstance(sink.event['timestamp'],float)
        self.assertEqual('b'*32,sink.event['job_id'])
        self.assertEqual('file.delete.prepare',sink.event['phase'])
