# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Transport-neutral Core scheduling and bounded job retention."""
from collections import OrderedDict
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Lock, Thread
import time

from .api import BrowserError
from .jobs import TERMINAL_STATES


@dataclass(frozen=True)
class DeviceSession:
    """Stable physical-device identity plus one connection incarnation."""
    device_id: str
    session_id: str


@dataclass(frozen=True)
class JobBinding:
    lane: str
    device_id: str = ''
    session_id: str = ''
    requires_device: bool = False

    @classmethod
    def core_host(cls): return cls('core-host')

    @classmethod
    def device(cls, session):
        if not session.device_id or not session.session_id:
            raise BrowserError('Connect to a C64U before requesting device work.')
        return cls('c64u:'+session.device_id, session.device_id,
                   session.session_id, True)


class CoreScheduler:
    """FIFO execution lanes owned by Core rather than a presentation client.

    Each physical C64U has one conservative lane: no two operations touching
    that device coexist. Core-host-only work has a separate ordered lane and
    may coexist because it does not use device state or transport.
    """
    def __init__(self, session_provider, *, completed_limit=128,
                 completed_ttl=3600, clock=time.time):
        self._session_provider = session_provider
        self.completed_limit = max(0, int(completed_limit))
        self.completed_ttl = max(0, float(completed_ttl))
        self._clock = clock
        self._jobs = OrderedDict()
        self._lanes = {}
        self._lock = Lock()
        self._closed = False

    def submit(self, job, binding):
        with self._lock:
            if self._closed: raise BrowserError('Core is shutting down.')
            self._cleanup_locked()
            self._jobs[job.id] = job
            queue = self._lanes.get(binding.lane)
            if queue is None:
                queue = Queue()
                self._lanes[binding.lane] = queue
                Thread(target=self._worker, args=(binding.lane, queue),
                       name='argonaut-core-'+binding.lane,
                       daemon=True).start()
            job._queue(binding.lane, binding.device_id, binding.session_id)
            queue.put((job, binding))
        return job

    def _worker(self, lane, queue):
        while True:
            try:item = queue.get(timeout=60)
            except Empty:
                with self._lock:
                    if self._lanes.get(lane) is queue and queue.empty():
                        self._lanes.pop(lane,None);return
                continue
            if item is None:
                queue.task_done(); return
            job, binding = item
            try:
                job.run(_scheduled=True,
                        preflight=lambda:self._validate(binding))
            finally:
                with self._lock:
                    self._cleanup_locked()
                queue.task_done()

    def _validate(self, binding):
        if not binding.requires_device: return
        current = self._session_provider()
        if current.device_id != binding.device_id:
            error = BrowserError(
                'The active C64U changed while this operation was queued. '
                'Prepare the operation again.')
            error.code = 'device'; raise error
        if current.session_id != binding.session_id:
            error = BrowserError(
                'The C64U connection changed while this operation was queued. '
                'Prepare the operation again.')
            error.code = 'session'; raise error

    def job(self, job_id):
        with self._lock:
            self._cleanup_locked(); job = self._jobs.get(job_id)
        if job is None:
            raise BrowserError('Core job is no longer retained.')
        return job.snapshot()

    def cancel(self, job_id):
        with self._lock:
            self._cleanup_locked(); job = self._jobs.get(job_id)
        return False if job is None else job.request_cancel()

    def cleanup(self):
        with self._lock:self._cleanup_locked()

    def _cleanup_locked(self):
        now = self._clock()
        completed = [(job_id, job) for job_id, job in self._jobs.items()
                     if job.state in TERMINAL_STATES]
        for job_id, job in completed:
            if (job.finished_at is not None and self.completed_ttl >= 0 and
                    now-job.finished_at > self.completed_ttl):
                self._jobs.pop(job_id, None)
        completed = [job_id for job_id, job in self._jobs.items()
                     if job.state in TERMINAL_STATES]
        while len(completed) > self.completed_limit:
            self._jobs.pop(completed.pop(0), None)

    def close(self):
        """Stop idle lane workers. Active operations retain their outcomes."""
        with self._lock:
            if self._closed:return
            self._closed=True; queues=tuple(self._lanes.values())
        for queue in queues:queue.put(None)
