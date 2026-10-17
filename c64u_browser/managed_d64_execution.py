# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit managed D64 execution, isolated from preflight and GUI presentation."""
from dataclasses import dataclass

from .api import BrowserError
from .disk_run import DmaLaunchError, run_image_bytes
from .jobs import CoreJob
from .scheduler import JobBinding


@dataclass(frozen=True)
class ManagedD64Outcome:
    outcome: str  # rejected, accepted, uncertain
    stage: str
    message: str
    plan_id: str
    cancellation_requested: bool = False
    playable_verified: bool = False


class ManagedD64ExecutionError(BrowserError):
    def __init__(self, result):
        super().__init__(result.message)
        self.result=result
        self.code='managed-launch-'+result.outcome


def execute(core, plan_id):
    service=core.managed_d64_preflight
    stage={'name':'admission', 'boundary':False}
    def rejected(exc):
        return ManagedD64Outcome('rejected',stage['name'],str(exc),plan_id)
    try:
        # consume_plan retires authority before its own session admission.
        plan=service.consume_plan(plan_id)
        selection=plan.selection
        with core._session_admission():
            service._check(selection)
            client=core._require_client()
        def task(job):
            stage['name']='validation'
            data=service._validated_bytes(selection,client,job)
            stage['name']='dispatch-admission'
            with core._session_admission():
                def validate_dispatch():
                    service._check(selection,client,job)
                    if service._clock()>=plan.expires_at:
                        raise BrowserError('Managed launch plan expired before dispatch.')
                def before_submit():
                    validate_dispatch()
                    stage['name']='dma-submit'
                    stage['boundary']=True
                validate_dispatch()
                stage['name']='dma-connect-authentication'
                # No FTP lease survives this call. Session replacement is excluded
                # through AUTH, RUN_IMG and the following IDENTIFY response.
                run_image_bytes(client,data,before_submit=before_submit)
                return ManagedD64Outcome('accepted','dma-response',
                    'DMA command accepted; playable state is not verified.',plan_id,
                    job.state=='cancel-requested')
        def failure(exc):
            # DMA's sent flag distinguishes proven pre-submission failure from
            # partial sends or lost responses. Unexpected post-boundary failures
            # are conservatively uncertain; authority is never reinstated.
            uncertain=(exc.command_may_have_started if isinstance(exc,DmaLaunchError)
                       else stage['boundary'])
            return ManagedD64Outcome('uncertain' if uncertain else 'rejected',
                stage['name'],str(exc),plan_id,job.state=='cancel-requested')
        job=CoreJob('game-library.managed-execute',task,failure_result=failure)
        return core.scheduler.submit(job,JobBinding.device(selection.session),reject_busy=True)
    except Exception as exc:
        raise ManagedD64ExecutionError(rejected(exc)) from exc
