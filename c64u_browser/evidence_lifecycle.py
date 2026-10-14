# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit one-job evidence owner. No publisher, global callback changes or retry."""
from threading import RLock
from .api import BrowserError
from .jobs import CoreJob
from .scheduler import JobBinding
from .required_evidence import RequiredEvidence, EvidenceFailure

# Ownership must survive exceptions at the caller boundary. This is intentionally
# not weak: blocked/unknown owners stay available for supervised inspection.
_LIVE_OWNERS = {}


class WorkerInterrupted(BrowserError):
    code = 'worker-interrupted'
    retryable = False


class EvidenceLifecycle:
    """Own an existing Core and exactly one directly scheduled device job.

    start() is for a controlling thread, not a task already holding a device lane.
    wait() reads the real job terminal snapshot and persists it synchronously;
    listeners/diagnostics never supply durability. close() is explicit and refuses
    before durable terminal evidence or while any Core resources remain active.
    Core belongs to this owner for the lifetime of this interface; do not close it
    separately. Failure never triggers automatic closure, recovery or cleanup.
    """
    def __init__(self, core, evidence):
        self.core = core
        self.evidence = evidence if type(evidence) is RequiredEvidence else RequiredEvidence(evidence)
        self.session = core.device_session()
        self.job = None
        self.terminal = None
        self.terminal_saved = False
        self.closed = self.complete = self.started = False
        self.close_attempted = False
        self.submission = 'not-started'
        self.interruption = None
        self._lock = RLock()
        _LIVE_OWNERS[id(self)] = self

    def _registered(self):
        if _LIVE_OWNERS.get(id(self)) is not self or self.closed:
            raise EvidenceFailure('Live lifecycle owner required.')

    def start(self, operation, task):
        with self._lock:
            self._registered()
            if self.started: raise EvidenceFailure('Lifecycle admission already consumed.')
            self.started = True
            if type(operation) is not str or not 0 < len(operation) <= 128:
                raise EvidenceFailure('Invalid operation name.')
            binding = JobBinding.device(self.session)
            self.evidence.save('operation-admission', dict(operation=operation,
                device_id=self.session.device_id, core_session_id=self.session.session_id,
                scheduler_lane=binding.lane))
            def work(job):
                try:
                    if self.core.device_session() != self.session:
                        raise BrowserError('Evidence operation session changed.')
                    if self.evidence.blocked:
                        raise EvidenceFailure('Required evidence is blocked.')
                    return task(job, self)
                except Exception:
                    raise
                except BaseException as exc:
                    # CoreJob catches Exception, not asynchronous worker interrupts.
                    # Keep the real interruption type, make the job observable as
                    # failed, and never fabricate successful task completion.
                    self.interruption = type(exc).__name__
                    raise WorkerInterrupted('Worker interrupted; effects require inspection.') from exc
            self.job = CoreJob(operation, work)
            self.evidence.save('job-registration', dict(job_id=self.job.id,
                operation=operation, scheduler_lane=binding.lane, submitted=False))
            self.evidence.save('job-submission-intent', dict(job_id=self.job.id))
            self.submission = 'possible'
            try:
                self.core.scheduler.submit(self.job, binding, reject_busy=True)
                self.submission = 'returned'
            except BaseException:
                # A raised submission is not proof the worker never started.
                # Retain the exact job/Core; only a real terminal can close it.
                raise
            return self.job

    def request_cancel(self):
        with self._lock:
            self._registered()
            if self.job is None: raise EvidenceFailure('No registered job.')
            with self.evidence.transition():
                self.evidence.save('cancellation-intent', dict(job_id=self.job.id))
                result = self.job._mark_cancel_requested()
                self.evidence.save('cancellation-result', dict(job_id=self.job.id, accepted=result))
        # Optional listeners run outside both owner and dispatch locks.
        if result:self.job._emit('cancel-requested')
        return result

    def observe_ftp(self, adapter, phase):
        """An observation of the caller's existing operation; never acquires FTP."""
        self._registered()
        state = adapter._context.get()
        client = None if state is None else state.client
        if state is None or client is None:
            raise EvidenceFailure('Existing FTP owner required for observation.')
        if (client.identity.device_id != self.session.device_id or
                client.identity.core_session_id != self.session.session_id or
                self.core.device_session() != self.session):
            raise EvidenceFailure('FTP observation session does not match lifecycle owner.')
        adapter._manager._check(adapter.binding)
        with adapter._manager._lock:
            if adapter._manager._leases.get(client.identity.device_id) is not client:
                raise EvidenceFailure('FTP lease ownership changed.')
        self.evidence.save('ftp-ownership', dict(phase=phase, adapter_owner=adapter._owner_id,
            device_id=client.identity.device_id, core_session_id=client.identity.core_session_id,
            ftp_session_id=client.identity.ftp_session_id,
            active_count=adapter._manager.active_count, independent_release='unverified'))

    def wait(self, timeout=None):
        self._registered()
        if self.job is None: raise EvidenceFailure('No registered job.')
        # A timeout propagates and retains this owner, never turns into terminal.
        snapshot = self.job.wait(timeout)
        with self._lock:
            self._registered()
            if snapshot.state not in ('succeeded', 'failed', 'cancelled'):
                raise EvidenceFailure('Positive terminal observation required.')
            self.terminal = snapshot
            if not self.terminal_saved:
                self.evidence.save('job-terminal', dict(job_id=snapshot.id, state=snapshot.state,
                    device_id=snapshot.device_id, core_session_id=snapshot.session_id,
                    error_code=None if snapshot.error is None else snapshot.error.code,
                    worker_interruption=self.interruption, submission=self.submission))
                self.terminal_saved = True
            return snapshot

    def close(self):
        with self._lock:
            self._registered()
            if self.close_attempted:
                raise EvidenceFailure('Core.close attempt already consumed; retain owner.')
            if not self.terminal_saved or self.evidence.blocked:
                raise EvidenceFailure('Durable terminal evidence required before Core.close.')
            scheduler = self.core.scheduler
            # Internal observations are explicitly not independent release proof.
            with scheduler._lock:
                active = any(job.snapshot().state not in ('succeeded', 'failed', 'cancelled')
                             for job in scheduler._jobs.values())
                pending = any(queue.unfinished_tasks for queue in scheduler._lanes.values())
            if active or pending or self.core._ftp_manager.active_count:
                raise EvidenceFailure('Core resources have not drained; retain owner.')
            self.evidence.save('core-close-intent', dict(job_id=self.job.id,
                terminal_observed=True, ftp_active_count=0, scheduler_pending=False,
                independent_ftp_release='unverified', independent_scheduler_release='unverified'))
            self.close_attempted = True
            try:
                self.core.close()
            except BaseException as exc:
                self.evidence.save('core-close-result', dict(returned=False, error_type=type(exc).__name__))
                raise
            self.closed = True
            self.evidence.save('core-close-result', dict(returned=True,
                independent_ftp_release='unverified', independent_scheduler_release='unverified'))
            self.complete = True
            del _LIVE_OWNERS[id(self)]
