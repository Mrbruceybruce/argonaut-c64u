# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK-independent foreground presentation; execution authority stays in Browser/Core."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationView:
    state: str
    message: str
    cancel_available: bool


_LABELS = {
    'file.copy.prepare': 'Preparing copy…', 'file.copy.execute': 'Copying…',
    'file.delete.prepare': 'Preparing deletion…', 'file.delete.execute': 'Deleting…',
    'file.folder.create': 'Creating folder…', 'file.rename': 'Renaming…',
    'file.native-upload.prepare': 'Preparing Flash upload…',
    'file.native-upload.execute': 'Uploading to Flash…',
    'file.native-save-copy': 'Saving a local copy…',
    'usb.backup.prepare': 'Preparing backup…', 'usb.backup.execute': 'Backing up…',
    'usb.restore.prepare': 'Preparing restore…', 'usb.restore.execute': 'Restoring…',
    'game-library.bulk-scan': 'Scanning game candidates…',
    'game-library.bulk-import': 'Importing games…',
    'game-library.launch-preview': 'Preparing game launch…',
    'game-library.launch': 'Launching game…',
    'sid-jukebox.playback-preview': 'Preparing SID playback…',
    'sid-jukebox.play': 'Sending SID playback command…',
    'sid-jukebox.previous': 'Preparing previous SID…',
    'sid-jukebox.next': 'Preparing next SID…',
}


def operation_label(operation):
    if operation in _LABELS:return _LABELS[operation]
    if operation.startswith(('sid-jukebox.', 'game-library.')):
        if 'relink' in operation:return 'Relinking source…'
        if 'validate' in operation or 'add' in operation:return 'Validating source…'
    return 'Working…'


def progress_text(operation, progress, phase_text):
    """Counts are phase-local; never infer an overall percentage or byte total."""
    completed, total, unit = progress.completed, progress.total, progress.unit
    if type(completed) is not int or completed < 0:
        raise ValueError('Invalid completed count')
    if total is not None and (type(total) is not int or total < 0):
        raise ValueError('Invalid progress total')
    if not isinstance(phase_text, str) or not isinstance(unit, str):
        raise ValueError('Invalid progress text')
    label = phase_text or operation_label(operation)
    # Existing structured formatters already render these counts accurately.
    if operation.startswith('game-library.bulk') or progress.phase == 'storage-fingerprint':
        return label
    if unit not in ('bytes', 'items', 'files', 'directories', 'candidates', 'entries', 'catalogs'):
        return label
    if total is not None and total > 0:
        if completed > total:raise ValueError('Progress exceeds phase total')
        return f'{label} · {completed:,} / {total:,} {unit}'
    if unit == 'bytes' and label == f'Transferred {completed:,} bytes':return label
    if completed:return f'{label} · {completed:,} {unit}'
    return label


def terminal_text(snapshot):
    # Existing feature completion handlers may supply richer reviewed consequences.
    message = getattr(snapshot.result, 'message', None)
    if isinstance(message, str) and message:return message
    if snapshot.error is not None:
        message = snapshot.error.message
        if isinstance(message, str) and message:return message
    return {'succeeded':'Completed.', 'cancelled':'Operation cancelled.',
            'failed':'The operation failed.'}.get(snapshot.state, 'Operation finished.')


class OperationPresentation:
    """One view shared by the status label and any operation-specific modal."""
    def __init__(self, render, diagnostic=lambda:None):
        self.render = render
        self.diagnostic = diagnostic
        self.state = 'IDLE'
        self.message = ''
        self.job = self.token = None
        self.cancellable = self.attempted = False
        self._listeners = []

    @property
    def view(self):
        return OperationView(self.state, self.message,
            self.state == 'RUNNING' and self.cancellable and not self.attempted)

    def matches(self, job, token):
        return token is not None and token is self.token and job is self.job

    def _emit(self):
        view = self.view
        for callback in (self.render, *self._listeners):
            try:callback(view)
            except Exception:self.diagnostic()

    def set_text(self, text):
        # Existing ordinary status writers retain their lifetime convention:
        # the next ordinary message replaces the previous one after job release.
        if self.state in ('RUNNING', 'CANCELLATION_REQUESTED'):return
        self.state = 'IDLE';self.message = text;self._emit()

    def get_text(self):return self.message

    def begin(self, job, token, cancellable=True):
        self.job, self.token = job, token
        self.state = 'RUNNING';self.cancellable = cancellable;self.attempted = False
        self.message = operation_label(job.operation);self._listeners = []
        self._emit()

    def subscribe(self, job, callback):
        if job is not self.job:return
        self._listeners.append(callback)
        try:callback(self.view)
        except Exception:self.diagnostic()

    def progress(self, job, token, progress, formatter):
        if not self.matches(job, token) or self.state != 'RUNNING' or self.attempted:return
        try:self.message = progress_text(job.operation, progress, formatter(job.operation, progress))
        except Exception:
            self.diagnostic()
            self.message = operation_label(job.operation) + ' Progress unavailable.'
        self._emit()

    def cancelling(self, job, token):
        if not self.matches(job, token):return
        self.attempted = True;self.state = 'CANCELLATION_REQUESTED'
        self.message = 'Cancelling… Waiting for the operation to finish.';self._emit()

    def request_cancel(self, job, token, send):
        if not self.matches(job, token) or not self.view.cancel_available:return False
        # Consume this presentation action before service callbacks can reenter it.
        self.attempted = True;self._emit()
        try:accepted = send()
        except Exception:
            if self.matches(job, token):
                self.message = 'Cancellation could not be requested. Waiting for the operation’s result.'
                self.diagnostic();self._emit()
            return False
        if not self.matches(job, token):return False
        if accepted:self.cancelling(job, token)
        else:
            self.message = 'Cancellation was not accepted. Waiting for the operation’s result.'
            self._emit()
        return bool(accepted)

    def finish(self, job, token, snapshot):
        if not self.matches(job, token):return
        self.state = 'TERMINAL';self.cancellable = False
        self.message = terminal_text(snapshot)
        listeners = tuple(self._listeners);view = self.view
        self.job = self.token = None;self._listeners = []
        self._emit()
        for callback in listeners:
            try:callback(view)
            except Exception:self.diagnostic()
