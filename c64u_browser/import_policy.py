# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema-2 offline policy capture. No authorization, I/O metering or execution."""
from dataclasses import dataclass

from .app_preferences import validate as validate_preferences
from .import_transaction import (Transaction, Journal, _prepare_transaction, _eligible,
    MAX_FILES, MAX_JOURNAL_BYTES, MAX_OPERATIONS, MiB, integer, require, immutable)

SCHEMA_VERSION = 2
MAX_BATCH_BYTES = 4096 * MiB
MAX_TEMP_BYTES = 8192 * MiB
MAX_IO_BYTES = 2 * MAX_BATCH_BYTES


@dataclass(frozen=True)
class ImportPolicy:
    batch_payload_limit: int
    temporary_disk_limit: int
    selected_payload_bytes: int
    planned_upload_bytes: int
    planned_readback_bytes: int
    snapshot_read_allowance: int
    upload_allowance: int
    readback_allowance: int
    files: int = MAX_FILES
    journal_bytes: int = MAX_JOURNAL_BYTES
    operations: int = MAX_OPERATIONS

    def validate(self):
        immutable(self)
        integer(self.batch_payload_limit,MiB,MAX_BATCH_BYTES)
        integer(self.temporary_disk_limit,MiB,MAX_TEMP_BYTES)
        integer(self.selected_payload_bytes,1,self.batch_payload_limit)
        integer(self.planned_upload_bytes,1,self.selected_payload_bytes)
        integer(self.planned_readback_bytes,self.planned_upload_bytes,self.planned_upload_bytes)
        require(self.planned_upload_bytes<=self.temporary_disk_limit,'Planned spool exceeds disk limit.')
        # Independent cumulative allowances: rereads never inflate game payload.
        for value in (self.snapshot_read_allowance,self.upload_allowance,self.readback_allowance):
            integer(value,self.planned_upload_bytes,MAX_IO_BYTES)
        integer(self.files,1,MAX_FILES);integer(self.journal_bytes,1,MAX_JOURNAL_BYTES)
        integer(self.operations,1,MAX_OPERATIONS)
        return self


@dataclass(frozen=True)
class TransactionV2(Transaction):
    budgets: ImportPolicy

    def _validate_budgets(self):
        require(type(self.budgets) is ImportPolicy,'Schema-2 policy required.')
        self.budgets.validate()

    def _validate_payload(self):
        total=sum(i.size for i in self.items)
        require(total==self.budgets.planned_upload_bytes==self.budgets.planned_readback_bytes,
                'Planned transfer payload mismatch.')
        if self.skipped_duplicates==0:
            require(total==self.budgets.selected_payload_bytes,'Selected payload mismatch.')
        else:require(total<self.budgets.selected_payload_bytes,'Missing skipped payload.')

    def _validate_source_item(self):
        # The complete captured policy is validated, but its aggregate payload
        # refers to the whole batch rather than this single source (possibly a skip).
        return self._validate_structure()


def prepare_transaction_v2(original,revalidated,*,library,session,revision,manifest_digest,app_options):
    """Explicit new attempt. Existing journals are never converted to schema 2."""
    options=validate_preferences(app_options)
    _eligible(original);_eligible(revalidated)
    selected=sum(i.size for i in revalidated.items)
    transfer=sum(i.size for i in revalidated.items if i.classification=='new')
    batch=options['import_batch_mib']*MiB
    policy=ImportPolicy(batch,options['import_temp_mib']*MiB,selected,transfer,transfer,
                        2*batch,2*batch,2*batch).validate()
    return _prepare_transaction(original,revalidated,library=library,session=session,
        revision=revision,manifest_digest=manifest_digest,budgets=policy,transaction_type=TransactionV2)


@dataclass(frozen=True)
class ResourceAccounting:
    """Measured observations, never counters that dispatch work or grant consent.

    Failure observations may exceed policy; retaining truth is not authorization.
    Zero defaults mean no I/O observed, not a completed verification.
    """
    snapshot_read_bytes: int = 0
    temporary_disk_peak_bytes: int = 0
    upload_bytes: int = 0
    readback_bytes: int = 0

    def validate(self):
        immutable(self)
        for value in (self.snapshot_read_bytes,self.temporary_disk_peak_bytes,
                      self.upload_bytes,self.readback_bytes):integer(value,0,2**63-1)


@dataclass(frozen=True)
class JournalV2(Journal):
    schema_version: int = SCHEMA_VERSION
    accounting: ResourceAccounting = ResourceAccounting()

    def _validate_schema(self):
        require(type(self.schema_version) is int and self.schema_version==SCHEMA_VERSION,
                'Unknown journal schema.')
        require(type(self.transaction) is TransactionV2,'Schema-2 transaction required.')
        require(type(self.accounting) is ResourceAccounting,'Invalid accounting evidence.')
        self.accounting.validate()
        if self.state in ('prepared','awaiting-confirmation'):
            require(self.accounting==ResourceAccounting(),'Pre-execution record claims I/O.')
