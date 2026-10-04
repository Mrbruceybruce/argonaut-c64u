# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit Core replacement composition; evidence never authorizes recovery."""
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
import posixpath
import tempfile
import uuid

from .api import BrowserError
from .diagnostics import operation_event
from .files import child, inspect, operate_managed
from .ftp_reads import adapter_for
from .replacement import signature
from .transfers import download, upload_managed


@dataclass(frozen=True)
class ReplacementEvidence:
    phase: str
    final: str
    staged: str
    directory: str
    backup: str
    mkdir: dict | None = None
    upload: object = None
    original_before: dict | None = None
    original_after: dict | None = None
    signature_before: object = None
    signature_after: object = None
    protection: str = 'unperformed'
    first_rename: dict | None = None
    publication_rename: dict | None = None
    backup_delete: dict | None = None
    directory_remove: dict | None = None
    acknowledged: tuple = ()
    stopped: str | None = None
    uncertain_step: str | None = None
    publication: str = 'not-completed'
    cleanup: str = 'unperformed'
    candidates: tuple = ()
    uncertain_paths: tuple = ()
    cancellation_observed: bool = False
    cancellation_deferred: bool = False
    error_category: str | None = None
    transport_error: dict | None = None
    local_cleanup: dict | None = None
    original_eligibility: tuple | None = None


    def inspection_message(self):
        """Core presentation of observations, never deletion/replay authority."""
        if self.phase == 'complete' and self.local_cleanup is None:return ''
        lines = [f'Replacement publication: {self.publication}; remote cleanup: {self.cleanup}.',
                 f'Stopped phase: {self.stopped or self.phase}.',
                 f'Intended final path: {self.final}']
        if self.uncertain_step:lines.append(f'Uncertain step: {self.uncertain_step}.')
        if self.uncertain_paths:
            label = ('Possible alternative locations (not confirmed)' if len(self.uncertain_paths) > 1
                     else 'Path with uncertain state')
            lines.append(label + ': ' + ' or '.join(self.uncertain_paths))
        if self.publication == 'completed':
            lines.append('Final replacement publication completed; do not replay replacement.')
            if self.cleanup != 'completed':lines.append('Remote cleanup is incomplete or uncertain.')
        first_done = self.first_rename and self.first_rename['outcome'] == 'completed'
        backup_removed = self.backup_delete and self.backup_delete['outcome'] == 'completed'
        backup_unknown = self.backup_delete and self.backup_delete['outcome'] == 'unknown'
        if first_done and not backup_removed:
            qualifier = '; deletion outcome is uncertain' if backup_unknown else ''
            lines.append(f'Last acknowledged original location: {self.backup}{qualifier}.')
        directory_removed = self.directory_remove and self.directory_remove['outcome'] == 'completed'
        if self.candidates and not directory_removed:
            lines.append(f'Staging directory inspection candidate: {self.directory}')
        if self.upload and self.upload.disposition == 'published' and self.publication == 'not-completed':
            lines.append(f'Last acknowledged staged replacement location: {self.staged}')
        elif self.upload and self.upload.disposition == 'staging-candidate':
            lines.append(f'Upload staging inspection candidate: {self.upload.staging}')
        if self.local_cleanup:
            lines.append('Local temporary cleanup also failed; remote evidence above is unchanged.'
                         if self.error_category != 'local-io' or self.phase != 'local-cleanup'
                         else 'Remote replacement completed; local temporary cleanup failed.')
        lines.append('Inspection only. These paths do not authorize replay, rollback or cleanup. '
                     'Fresh inspection and explicit review are required before destructive action.')
        return '\n'.join(lines)


class ReplacementFailure(BrowserError):
    retryable = False
    code = 'replacement'

    def __init__(self, evidence):
        self.replacement_evidence = evidence
        status = ('Publication and remote cleanup completed; local cleanup failed.'
                  if evidence.publication == 'completed' and evidence.cleanup == 'completed' else
                  'Publication completed; cleanup is incomplete.' if evidence.publication == 'completed'
                  else 'Publication location is uncertain.' if evidence.publication == 'unknown'
                  else 'Replacement did not complete publication.')
        super().__init__(status + ' Stopped during ' + evidence.phase +
                         '. Inspect the recorded paths in a new operation before further action; '
                         'no automatic retry, rollback or cleanup was attempted.')


class _Discard:
    def write(self, block):return len(block)


def replace_managed(client, step, source_local, progress, *, validate=None, original_validator_factory=None):
    """One file/lease. Legacy replacement consumers must opt in explicitly.

    None primitive/observation fields mean unattempted. Path records are last
    observations/candidates, never current existence or deletion authorization.
    """
    parent = posixpath.dirname(step.destination)
    name = Path(step.source).name
    directory = child(parent, 'c64u-replace-' + uuid.uuid4().hex)
    backup = child(parent, 'c64u-old-' + uuid.uuid4().hex)
    staged = child(directory, name)
    evidence = ReplacementEvidence('preflight', step.destination, staged, directory, backup)
    check = getattr(progress, 'check', lambda: None)
    deferred = None
    adapter = adapter_for(client)
    temporary_resource = None
    primary = None

    def original(slot):
        nonlocal evidence
        if original_validator_factory is None:
            return adapter.read_into(step.destination, _Discard(), check=check)
        sink = original_validator_factory(slot)
        # An interrupted observation stays unverified, even if RETR completed.
        evidence = replace(evidence, original_eligibility=(
            (evidence.original_eligibility or ()) + (sink.observation(),)))
        result = adapter.read_into(step.destination, sink, check=check)
        observation = sink.observation(result)
        evidence = replace(evidence, original_eligibility=(
            evidence.original_eligibility[:-1] + (observation,)))
        field = 'original_before' if slot == 'original-before' else 'original_after'
        evidence = replace(evidence, **{field: dict(bytes=result.transferred, sha256=result.sha256)})
        if observation.status != 'full-byte-match':
            raise BrowserError('Original content is not eligible for this replacement.')
        return result

    def mutation(field, verb, path, target=None):
        nonlocal evidence
        evidence = replace(evidence, phase=field)
        result = adapter.mutate(verb, path, target)
        evidence = replace(evidence, **{field: result},
                           acknowledged=evidence.acknowledged + (field,))

    try:
        if adapter is None:raise BrowserError('Replacement requires a Core-managed C64U session.')
        # Prepare local resources before lazy FTP acquisition. Remote-source
        # download/upload remain inside the same replacement operation.
        if not source_local:
            temporary_resource = tempfile.TemporaryDirectory(prefix='argonaut-replace-source-')
        with nullcontext(None if temporary_resource is None else temporary_resource.name) as temporary:
            with operation_event('ftp', 'replace_file', 'file'), adapter.operation(check):
                check()
                if validate is not None:validate()
                observed = signature(client, False, step.destination)
                evidence = replace(evidence, signature_before=observed)
                if observed != step.signature:raise BrowserError('Replacement target changed since review.')
                evidence = replace(evidence, phase='mkdir', candidates=(directory,))
                created = operate_managed(client, 'mkdir', directory, check=check)
                evidence = replace(evidence, mkdir=created.completed[0], acknowledged=('mkdir',))
                evidence = replace(evidence, phase='original-before')
                first = original('original-before')
                evidence = replace(evidence, original_before=dict(bytes=first.transferred, sha256=first.sha256),
                                   phase='staging')
                source = Path(step.source)
                if not source_local:
                    source = Path(temporary) / name
                    download(client, step.source, source, progress)
                uploaded = upload_managed(client, source, directory, progress)
                evidence = replace(evidence, upload=uploaded['upload'], candidates=(directory, staged),
                                   phase='revalidation')
                check()
                observed = signature(client, False, step.destination)
                evidence = replace(evidence, signature_after=observed)
                if observed != step.signature:raise BrowserError('Replacement target changed during copy.')
                evidence = replace(evidence, phase='original-after')
                second = original('original-after')
                evidence = replace(evidence, original_after=dict(bytes=second.transferred, sha256=second.sha256))
                if first.sha256 != second.sha256:
                    raise BrowserError('Replacement target contents changed during copy.')
                evidence = replace(evidence, protection='passed', phase='backup-inspection')
                if inspect(client, backup) is not None:raise BrowserError('Backup name already exists.')
                evidence = replace(evidence, phase='first_rename')
                # Entry checks binding/cancellation; exit never raises pending cancellation.
                with adapter.defer_cancellation() as deferred:
                    mutation('first_rename', 'rename', step.destination, backup)
                    evidence = replace(evidence, candidates=(directory, staged, backup))
                    mutation('publication_rename', 'rename', staged, step.destination)
                    evidence = replace(evidence, publication='completed', cleanup='pending',
                                       candidates=(directory, backup))
                    mutation('backup_delete', 'delete', backup)
                    evidence = replace(evidence, candidates=(directory,))
                    mutation('directory_remove', 'rmdir', directory)
                evidence = replace(evidence, phase='local-cleanup', cleanup='completed', candidates=(),
                                   cancellation_deferred=deferred.cancellation_observed,
                                   cancellation_observed=deferred.cancellation_observed)
        return replace(evidence, phase='complete')
    except Exception as exc:
        wire = getattr(exc, 'ftp_error', None)
        data = getattr(wire, 'mutation', None)
        upload = getattr(exc, 'upload_evidence', None)
        updates = {}
        if data is not None and evidence.phase in ('mkdir', 'first_rename', 'publication_rename', 'backup_delete', 'directory_remove'):
            updates[evidence.phase] = data.as_dict()
            # Lost RNFR has protocol uncertainty but no consequential submission.
            uncertain = data.outcome.value == 'unknown' or (data.stage == 'RNFR' and
                        data.stage_submitted and data.reply_code is None)
            if uncertain:updates['uncertain_step'] = evidence.phase
            if data.outcome.value == 'unknown':
                paths = {'mkdir': (directory,), 'first_rename': (step.destination, backup),
                         'publication_rename': (staged, step.destination),
                         'backup_delete': (backup,), 'directory_remove': (directory,)}
                updates['uncertain_paths'] = paths[evidence.phase]
                if evidence.phase == 'publication_rename':updates['publication'] = 'unknown'
        if upload is not None:
            updates['upload'] = upload
            updates['candidates'] = tuple(dict.fromkeys((directory, upload.staging, upload.destination)))
            if upload.disposition == 'location-unknown':
                updates['uncertain_paths'] = (upload.staging, upload.destination)
                updates['uncertain_step'] = 'staging'
        cancelled = bool(getattr(exc, 'cancelled', False))
        if evidence.publication == 'completed' and evidence.cleanup != 'completed':
            updates['cleanup'] = 'uncertain' if updates.get('uncertain_step') else 'incomplete'
        evidence = replace(evidence, **updates, stopped=evidence.phase,
            protection='failed' if evidence.phase in ('original-before', 'original-after', 'revalidation') else evidence.protection,
            cancellation_observed=cancelled or bool(deferred and deferred.cancellation_observed),
            cancellation_deferred=bool(deferred and deferred.cancellation_observed),
            error_category=('cancelled' if cancelled else wire.code.value if wire else
                            upload.error_category if upload else 'local-io' if isinstance(exc, OSError)
                            else 'validation' if isinstance(exc, BrowserError) else 'callback'),
            transport_error=wire.as_dict() if wire else (upload.transport_error if upload else None))
        if cancelled:
            primary = exc
            exc.replacement_evidence = evidence
            # Replacement staging is not the ordinary upload cleanup shortcut.
            if hasattr(exc, 'partial_path'):exc.partial_path = None
            raise
        primary = ReplacementFailure(evidence)
        raise primary from None
    finally:
        # Primary remote/cancellation evidence has already been normalized.
        # Local resource cleanup cannot replace that outcome while unwinding.
        if temporary_resource is not None:
            try:temporary_resource.cleanup()
            except Exception:
                secondary = dict(attempted=True, status='failed', error_category='local-cleanup-failed')
                if primary is not None:
                    primary.replacement_evidence = replace(primary.replacement_evidence,
                                                           local_cleanup=secondary)
                else:
                    raise ReplacementFailure(replace(evidence, phase='local-cleanup',
                        stopped='local-cleanup', error_category='local-io',
                        local_cleanup=secondary)) from None
