# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Transport-neutral Core jobs, progress, cancellation, results and events."""
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from threading import Event, Lock
import time
import uuid

from .api import BrowserError, ConnectionFailure


class JobState(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    CANCEL_REQUESTED = 'cancel-requested'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


TERMINAL_STATES = frozenset((JobState.SUCCEEDED, JobState.FAILED,
                             JobState.CANCELLED))


@dataclass(frozen=True)
class JobProgress:
    phase: str
    completed: int = 0
    total: int | None = None
    unit: str = 'items'
    message: str = ''


@dataclass(frozen=True)
class JobError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class JobSnapshot:
    id: str
    operation: str
    state: str
    created_at: float
    started_at: float | None
    finished_at: float | None
    progress: JobProgress | None
    result: object = None
    error: JobError | None = None

    def as_dict(self): return _plain(self)


@dataclass(frozen=True)
class JobEvent:
    kind: str
    timestamp: float
    job: JobSnapshot

    def as_dict(self): return _plain(self)


def _plain(value):
    if isinstance(value, Enum): return value.value
    if is_dataclass(value): return {key:_plain(item) for key,item in asdict(value).items()}
    if isinstance(value, dict): return {str(key):_plain(item) for key,item in value.items()}
    if isinstance(value, (tuple, list)): return [_plain(item) for item in value]
    return value


class JobCancelled(BrowserError):
    cancelled = True
    def __init__(self, message='Operation cancelled by request.', result=None):
        super().__init__(message)
        self.result = result


def categorized_error(exc):
    if isinstance(exc, ConnectionFailure):
        return JobError(exc.kind, str(exc), exc.kind in ('host', 'network'))
    code = getattr(exc, 'code', None)
    if isinstance(code, str):
        return JobError(code, str(exc), bool(getattr(exc, 'retryable', False)))
    if isinstance(exc, OSError): return JobError('filesystem', str(exc))
    if isinstance(exc, BrowserError): return JobError('operation', str(exc))
    return JobError('internal', 'The operation could not be completed.')


class CoreJob:
    """One-shot synchronous job whose events are safe for any client adapter."""
    def __init__(self, operation, task):
        self.id = uuid.uuid4().hex
        self.operation = operation
        self.created_at = time.time()
        self.started_at = self.finished_at = None
        self.state = JobState.PENDING
        self.progress = self.result = self.error = None
        self._task = task
        self._cancel = Event()
        self._listeners = []
        self._lock = Lock()

    def snapshot(self):
        with self._lock:
            return JobSnapshot(self.id, self.operation, self.state.value,
                self.created_at, self.started_at, self.finished_at,
                self.progress, self.result, self.error)

    def add_listener(self, listener):
        with self._lock:self._listeners.append(listener)
        return lambda:self._remove_listener(listener)

    def _remove_listener(self, listener):
        with self._lock:
            if listener in self._listeners:self._listeners.remove(listener)

    def _emit(self, kind):
        snapshot=self.snapshot()
        event=JobEvent(kind,time.time(),snapshot)
        with self._lock:listeners=tuple(self._listeners)
        for listener in listeners:
            try:listener(event)
            except Exception:
                # A presentation or transport listener cannot change the job's
                # outcome. Clients may inspect the authoritative snapshot.
                pass

    def report(self, progress):
        self.check_cancel()
        with self._lock:self.progress=progress
        self._emit('progress')

    def byte_progress(self, phase='transfer'):
        last=[0.0]
        def progress(count):
            self.check_cancel()
            now=time.monotonic()
            if now-last[0]>=0.15:
                last[0]=now
                self.report(JobProgress(phase,count,None,'bytes',
                                        f'Transferred {count:,} bytes'))
        progress.check=self.check_cancel
        return progress

    def check_cancel(self):
        if self._cancel.is_set():raise JobCancelled()

    def request_cancel(self):
        with self._lock:
            if self.state in TERMINAL_STATES:return False
            self._cancel.set()
            if self.state in (JobState.PENDING,JobState.RUNNING):
                self.state=JobState.CANCEL_REQUESTED
        self._emit('cancel-requested')
        return True

    def run(self):
        with self._lock:
            already_started=self.started_at is not None
            if not already_started:
                self.started_at=time.time()
                self.state=JobState.CANCEL_REQUESTED if self._cancel.is_set() else JobState.RUNNING
        if already_started:return self.snapshot()
        self._emit('started')
        try:
            self.check_cancel()
            result=self._task(self)
            # A late cancellation request does not relabel completed consequential
            # work. Only a check that actually stopped work raises JobCancelled.
            with self._lock:
                self.result=result;self.state=JobState.SUCCEEDED
        except JobCancelled as exc:
            with self._lock:
                self.result=exc.result
                self.error=JobError('cancelled',str(exc),False)
                self.state=JobState.CANCELLED
        except Exception as exc:
            with self._lock:
                self.result=getattr(exc,'result',None)
                self.error=categorized_error(exc)
                self.state=JobState.FAILED
        with self._lock:self.finished_at=time.time()
        self._emit('finished')
        return self.snapshot()
