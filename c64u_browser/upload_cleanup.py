# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GTK-thread handoff from one completed upload to optional file-only cleanup."""

from .diagnostics import cleanup_event


class UploadCleanup:
    def __init__(self, app, job, token):
        self.app, self.job, self.token = app, job, token
        self.session = app.core.device_session()
        self.client = getattr(app, "client", None)
        self.bound = app.foreground.owns(token, job)
        self.started = self.finished = False
        self.stage = "upload"
        self.evidence = None
        self.snapshot = None
        self.done = None
        app.upload_cleanup = self

    def owns_presentation(self):
        return (not self.app.cleanup_closed and self.app.upload_cleanup is self and
                self.app.core.device_session() == self.session and
                getattr(self.app, "client", None) is self.client)

    def current(self):
        return not self.finished and self.owns_presentation()

    def complete(self, done):
        if self.started or self.finished:return
        self.started = True
        cleanup_event('handoff', origin=self.job.id, job_id=self.job.id,
                      session_match=self.app.core.device_session() == self.session)
        self.done = done
        self.snapshot = self.job.snapshot()
        if not self.bound or self.snapshot.state not in ('succeeded', 'failed', 'cancelled'):
            self.close()
            return
        if not self.current():
            cleanup_event('admission', origin=self.job.id, stage='preparation', admitted=False, reason='stale-session')
            self.finish('Cleanup not started: the device/session changed.', refresh=False)
            return
        if self.app.foreground.token is not None or self.app.busy:
            cleanup_event('admission', origin=self.job.id, stage='preparation', admitted=False, reason='foreground-busy')
            self.evidence = self.app.core.files._take_cleanup_eligibility(self.job)
            self.finish('Cleanup not started: another operation owns the foreground.', refresh=False)
            return
        service = self.app.core.files
        decision = service._cleanup_decision(self.job)
        self.evidence = service._take_cleanup_eligibility(self.job)
        if self.evidence is None:
            message = ''
            if decision == 'delete':
                result = self.snapshot.result
                if self.snapshot.state == 'succeeded':
                    message = 'Cleanup was not necessary: the upload completed despite cancellation. Completed files were kept.'
                elif any(getattr(item, 'disposition', '') == 'location-unknown'
                         for item in getattr(result, 'uploads', ())):
                    message = 'Publication is uncertain; no cleanup performed.'
                elif getattr(result, 'partial_upload', None) is None:
                    message = 'No verified incomplete staging file is available for cleanup; no cleanup performed.'
                else:
                    message = 'Cleanup could not safely proceed: recovery authority is unavailable; no cleanup performed.'
            self.finish(message)
            return
        self.stage = "preparing"
        admitted = self.app.run_file_job(lambda:service._prepare_intent_cleanup(self.evidence),
                              self.prepared, failed=self.preparation_rejected,
                              presentation_guard=self.current, presentation_abandoned=self.close)
        cleanup_event('admission', origin=self.job.id, stage='preparation', admitted=bool(admitted))
        if not admitted and not self.finished:
            self.finish('Cleanup preparation not admitted; no retry.', refresh=False)

    def preparation_rejected(self, error):
        self.finish('Cleanup could not safely proceed. Cleanup preparation rejected: '+str(error))

    def confirmed_absence(self, result):
        return (self.evidence is not None and result is not None and
                getattr(result, 'absent_target', None) == self.evidence.partial_upload.location.path and
                not result.removed and result.mutation is None)

    def absence_message(self):
        return 'Cleanup was unnecessary: the incomplete staging file was not found during verification.'

    def prepared(self, snapshot):
        if self.finished or self.stage != "preparing":return
        self.stage = "executing"
        if not self.current():
            self.finish('Cleanup stopped: the device/session changed.', refresh=False)
            return
        if snapshot.state != 'succeeded':
            if self.confirmed_absence(snapshot.result):
                self.finish(self.absence_message(), absent=True)
                return
            self.finish('Cleanup could not safely proceed. Cleanup preparation stopped: '+
                        (snapshot.error.message if snapshot.error else 'no reviewed plan'))
            return
        # Both run_file_job completions release their own foreground token
        # before invoking us. No nested admission or synchronous wait occurs.
        admitted = self.app.run_file_job(lambda:self.app.core.files._execute_intent_cleanup(self.evidence),
                              self.executed, failed=self.execution_rejected,
                              presentation_guard=self.current, presentation_abandoned=self.close)
        cleanup_event('admission', origin=self.job.id, stage='execution', admitted=bool(admitted))
        if not admitted and not self.finished:
            self.finish('Cleanup execution not admitted; no retry.', refresh=False)

    def execution_rejected(self, error):
        self.finish('Cleanup could not safely proceed. Cleanup execution rejected before submission: '+str(error))

    def executed(self, snapshot):
        if self.finished or self.stage != "executing":return
        result = snapshot.result
        if self.confirmed_absence(result):
            self.finish(self.absence_message(), absent=True, refresh=self.current())
            return
        if result is not None:
            removed = self.evidence.partial_upload.location.path in result.removed
            # Preserve the service's exact acknowledged counts, remaining paths
            # and uncertainty; terminal state alone is never evidence of removal.
            outcome = (result.mutation or {}).get('outcome')
            if removed:
                heading = ('Cleanup removal was acknowledged, but a later error occurred.'
                           if result.failure else 'Cleanup succeeded.')
            elif outcome == 'unknown':
                heading = 'Cleanup outcome is uncertain; removal could not be confirmed.'
            elif outcome == 'rejected':
                heading = 'Cleanup failed: the file deletion was rejected.'
            elif result.not_attempted:
                heading = 'Cleanup could not safely proceed; no deletion was attempted.'
            else:
                heading = 'Cleanup could not be confirmed.'
            message = heading+' '+result.message
        else:
            removed = False
            message = 'Cleanup could not be confirmed: '+(snapshot.error.message if snapshot.error else 'no deletion evidence')
        self.finish(message, removed=removed, refresh=self.current())

    def finish(self, message, *, removed=False, refresh=True, absent=False):
        if self.finished:return
        current = self.current()
        cleanup_event('coordinator_complete', origin=self.job.id, stage=self.stage,
                      session_match=self.app.core.device_session() == self.session,
                      removed_count=int(removed), admitted=current)
        # Report only the captured Core-issued target, never current selection
        # or arbitrary paths from a later result. This grants no new authority.
        partial = (self.evidence.partial_upload if self.evidence is not None else
                   getattr(getattr(self.snapshot, 'result', None), 'partial_upload', None))
        if message and not removed and not absent and partial is not None:
            message += (' The incomplete file may remain at '+partial.location.path+
                        '. Review it manually in its remote folder.')
        self.finished = True
        if self.evidence is not None:self.app.core.files._abandon_intent_cleanup(self.evidence)
        # Retain presentation identity through the asynchronous Files refresh.
        # A newer coordinator, session/client, shutdown or foreground owner
        # invalidates ALL UI output, including no-result/rejection messages.
        if (current and self.owns_presentation() and self.done is not None and
                not self.app.busy and self.app.foreground.token is None):
            self.done(self.snapshot, message, removed, refresh)

    def close(self):
        cleanup_event('coordinator_close', origin=self.job.id, stage=self.stage,
                      session_match=self.app.core.device_session() == self.session)
        self.finished = True
        if self.evidence is None and self.bound:
            self.evidence = self.app.core.files._take_cleanup_eligibility(self.job)
        if self.evidence is not None:self.app.core.files._abandon_intent_cleanup(self.evidence)
        if self.app.upload_cleanup is self:self.app.upload_cleanup = None
