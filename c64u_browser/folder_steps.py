# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit R1 folder steps. Evidence is observation, never recovery authority."""
from dataclasses import dataclass, replace
from pathlib import Path
import posixpath
import tempfile

from .api import BrowserError
from .files import operate_managed
from .ftp_reads import adapter_for
from .transfers import download, upload_managed


@dataclass(frozen=True)
class FolderStepEvidence:
    relative: str
    operation: str
    source: str
    destination: str
    phase: str = 'setup'
    validation: str = 'unperformed'
    source_observation: dict | None = None
    transport_error: dict | None = None
    mutation: object = None
    upload: object = None
    destination_observation: dict | None = None
    publication: str = 'not-completed'
    local_cleanup: tuple = ()
    error_category: str | None = None

    def inspection_message(self):
        if self.phase == 'complete':return ''
        lines = [f'Folder step {self.relative}: stopped during {self.phase}.',
                 f'Intended destination: {self.destination}']
        if self.mutation is not None and self.mutation.stopped:
            lines.append('Directory mutation outcome: ' + self.mutation.stopped['outcome'] + '.')
        if self.source_observation:
            lines.append(f"Source observation: {self.source_observation['bytes']} bytes; SHA-256 {self.source_observation['sha256']}.")
        if self.transport_error:
            lines.append('Transport failure: ' + self.transport_error['code'] + '.')
        if self.publication == 'completed':
            lines.append('Destination publication completed; it must not be replayed.')
        if self.local_cleanup:
            lines.append('Local temporary cleanup failed; primary remote/cancellation evidence is unchanged.')
        lines.append('Inspection only. These paths do not authorize retry, rollback or cleanup. Fresh inspection and explicit review are required.')
        return '\n'.join(lines)


class FolderStepFailure(BrowserError):
    retryable = False
    code = 'folder-step'

    def __init__(self, evidence):
        self.folder_step_evidence = evidence
        self.upload_evidence = evidence.upload
        self.partial_path = (evidence.upload.staging if evidence.upload is not None
                             and evidence.upload.disposition == 'staging-candidate' else None)
        super().__init__(evidence.inspection_message())


def execute_managed_step(client, step, progress, validate, *, directory=False):
    """One missing directory or same-device remote addition, one lazy lease."""
    evidence = FolderStepEvidence(step.relative, 'mkdir' if directory else 'remote-addition',
                                  str(step.source), str(step.destination))
    check = getattr(progress, 'check', lambda: None)
    temporary = None
    primary = None
    try:
        adapter = adapter_for(client)
        if adapter is None:raise BrowserError('Folder step requires a Core-managed session.')
        if not directory:
            evidence = replace(evidence, phase='local-prepare')
            temporary = tempfile.TemporaryDirectory(prefix='argonaut-copy-')
        with adapter.operation(check):
            evidence = replace(evidence, phase='validation')
            if validate() is not None:
                raise BrowserError('Destination appeared after review.')
            evidence = replace(evidence, validation='passed')
            if directory:
                evidence = replace(evidence, phase='mkdir')
                mutation = operate_managed(client, 'mkdir', step.destination, check=check)
                evidence = replace(evidence, mutation=mutation)
            else:
                evidence = replace(evidence, phase='source-download')
                staged = Path(temporary.name) / posixpath.basename(step.source)
                observed = download(client, step.source, staged, progress, preserve_cleanup=True)
                evidence = replace(evidence, source_observation={k:observed[k] for k in ('bytes','sha256')},
                                   phase='destination-upload')
                result = upload_managed(client, staged, posixpath.dirname(step.destination), progress)
                evidence = replace(evidence, upload=result['upload'], publication='completed',
                                   destination_observation={k:result[k] for k in ('bytes','sha256')})
        evidence = replace(evidence, phase='local-cleanup')
    except Exception as exc:
        wire = getattr(exc, 'ftp_error', None)
        upload = getattr(exc, 'upload_evidence', None)
        cancelled = bool(getattr(exc, 'cancelled', False))
        evidence = replace(evidence,
            validation='failed' if evidence.phase == 'validation' else evidence.validation,
            source_observation=getattr(exc, 'download_observation', evidence.source_observation),
            transport_error=wire.as_dict() if wire else (upload.transport_error if upload else None),
            mutation=getattr(exc, 'result', None) if evidence.phase == 'mkdir' else evidence.mutation,
            upload=upload or evidence.upload,
            publication=('unknown' if upload and upload.disposition == 'location-unknown' else evidence.publication),
            local_cleanup=tuple(getattr(exc, 'local_cleanup', ())),
        error_category='cancelled' if cancelled else wire.code.value if wire else
            upload.error_category if upload else 'local-io' if isinstance(exc, OSError) else
            evidence.phase if evidence.phase in ('setup', 'validation') else 'operation')
        if cancelled:
            primary = exc
            exc.folder_step_evidence = evidence
        else:primary = FolderStepFailure(evidence)
    finally:
        if temporary is not None:
            try:temporary.cleanup()
            except Exception:
                evidence = replace(evidence, local_cleanup=evidence.local_cleanup + (
                    dict(scope='temporary-directory', error_category='local-cleanup-failed'),))
                if primary is None:
                    evidence = replace(evidence, phase='local-cleanup', error_category='local-io')
                    primary = FolderStepFailure(evidence)
                else:primary.folder_step_evidence = evidence
    if primary is not None:raise primary from None
    return replace(evidence, phase='complete')
