# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure policy-2 evidence rules. No transport, consent, or recovery authority."""
from dataclasses import fields, replace
import hashlib
import json

from .import_execution import ExecutionTransaction, ExecutionOperation, ExecutionAccounting, uuid
from .import_transaction import require, integer, MAX_JOURNAL_BYTES


def encode_record(transaction, *, format_version=1):
    """Allowlisted UTF-8 JSON, sorted compact keys, exactly one trailing LF."""
    require(type(transaction) is ExecutionTransaction, 'Explicit execution transaction required.')
    transaction.validate()
    require(transaction.execution_policy_version == 2, 'Policy-2 remote record required.')
    require(type(format_version) is int and format_version == 1, 'Unsupported remote record format.')
    tx = transaction
    document = {
        'format_version': format_version, 'journal_schema_version': 3,
        'execution_policy_version': 2, 'policy_version': tx.policy_version,
        'transaction_id': tx.id, 'plan_digest': tx.plan_digest,
        'library': {'library_id': tx.library.library_id, 'device_id': tx.library.device_id,
                    'root': tx.library.root, 'path': tx.library.path},
        'manifest': {'revision': tx.manifest_revision, 'sha256': tx.manifest_digest},
        'directory': tx.directory,
        'items': [{'staged_path': i.staged_path, 'final_path': i.final_path,
                   'format': i.format, 'size': i.size, 'sha256': i.sha256} for i in tx.items],
    }
    limit = min(MAX_JOURNAL_BYTES, tx.budgets.journal_bytes,
                tx.limits.control_upload_bytes, tx.limits.control_read_bytes)
    result = bytearray()
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    for chunk in encoder.iterencode(document):
        block = chunk.encode('utf-8', errors='strict')
        require(len(block) <= limit-len(result)-1, 'Remote record exceeds captured allowance.')
        result.extend(block)
    result.extend(b'\n')
    return bytes(result)


def record_expectation(transaction):
    data = encode_record(transaction)
    return len(data), hashlib.sha256(data).hexdigest()


def validate_record(data, transaction, *, format_version=1):
    """Exact bytes only: no JSON normalization, extra fields, or automatic repair."""
    require(type(data) is bytes and 0 < len(data) <= MAX_JOURNAL_BYTES, 'Invalid remote record bytes.')
    require(data == encode_record(transaction, format_version=format_version), 'Noncanonical or inconsistent remote record.')
    return data


def planned_operations(tx):
    return (('snapshot-validation', ''), ('mkdir', tx.directory), ('record-upload', tx.record_path),
            *(('upload', i.staged_path) for i in tx.items), ('record-readback', tx.record_path),
            *(('readback', i.staged_path) for i in tx.items), ('final-validation', tx.directory))


def validate_operations(journal):
    """Called only after common journal/transaction/header validation."""
    tx = journal.transaction
    plan = planned_operations(tx)
    expected_record = record_expectation(tx)
    require(len(journal.operations) <= len(plan), 'Too many policy-2 operations.')
    items = {i.staged_path: i for i in tx.items}
    ids = set(); stopped = None; acknowledged = 0
    upload_end = len(tx.items)+3
    for n, op in enumerate(journal.operations, 1):
        require(type(op) is ExecutionOperation, 'Invalid operation type.')
        uuid(op.id); require(op.id not in ids, 'Duplicate operation identity.'); ids.add(op.id)
        require(type(op.sequence) is int and op.sequence == n and
                (op.kind, op.path) == plan[n-1], 'Wrong policy-2 ordinal, kind or path.')
        require(stopped is None, 'No operation after unresolved outcome.')
        require(op.outcome in ('intent', 'completed', 'not-started', 'rejected', 'unknown'), 'Invalid outcome.')
        require(n <= upload_end or journal.state != 'staging', 'Verification requires verifying phase.')
        integer(op.size, 0, 2**63-1); op.validate_hash()
        require(type(op.accounting) is ExecutionAccounting, 'Invalid accounting.'); op.accounting.validate()
        a = op.accounting
        mutation = op.kind in ('mkdir', 'record-upload', 'upload')
        require(op.collision in (('absent', 'present') if mutation else ('not-applicable',)), 'Invalid collision evidence.')
        if op.collision == 'present':
            require(op.outcome == 'rejected' and op.size == 0 and op.sha256 == '' and
                    a.attempted_upload_bytes == a.control_upload_bytes == 0, 'Collision cannot claim a write.')
        if op.outcome == 'intent':
            require(op.size == 0 and op.sha256 == '' and a == ExecutionAccounting(), 'Intent claims I/O.')
        if op.outcome == 'not-started':
            require(op.size == 0 and op.sha256 == '' and
                    replace(a, control_read_bytes=0) == ExecutionAccounting(), 'Unsubmitted operation claims I/O.')
        allowed = {'control_read_bytes'}
        expected = None
        if op.kind == 'snapshot-validation':
            allowed.add('snapshot_validation_reads')
            require(op.size == a.snapshot_validation_reads, 'Snapshot observation/count mismatch.')
            if op.outcome == 'completed':
                require(op.size == tx.budgets.planned_upload_bytes, 'Incomplete snapshot validation.')
        elif op.kind in ('mkdir', 'final-validation'):
            require(op.size == 0 and op.sha256 == '', 'Control validation requires zero size and absent hash.')
        elif op.kind == 'record-upload':
            allowed.add('control_upload_bytes'); expected = expected_record
            # Control exposure is separate from payload counters. Confirmed sender
            # bytes are size; uncertain exposure is control_upload_bytes - size.
            require(op.size <= a.control_upload_bytes, 'Confirmed control bytes exceed attempted exposure.')
            if op.outcome == 'completed':
                require(op.size == a.control_upload_bytes, 'Incomplete control sender evidence.')
        elif op.kind == 'upload':
            allowed.update(('attempted_upload_bytes', 'confirmed_sender_bytes', 'uncertain_send_bytes'))
            item = items[op.path]; expected = (item.size, item.sha256)
            require(op.size == a.confirmed_sender_bytes, 'Sender observation/count mismatch.')
            if op.outcome == 'completed':
                require(a.attempted_upload_bytes == a.confirmed_sender_bytes == item.size and
                        a.uncertain_send_bytes == 0, 'Incomplete sender evidence.')
        elif op.kind == 'record-readback':
            expected = expected_record
            require(op.size <= a.control_read_bytes, 'Record read count exceeds actual control reads.')
        elif op.kind == 'readback':
            allowed.add('readback_bytes'); item = items[op.path]; expected = (item.size, item.sha256)
            require(op.size == a.readback_bytes, 'Readback observation/count mismatch.')
        if expected is not None and op.outcome == 'completed':
            require((op.size, op.sha256) == expected, 'Length or SHA-256 differs from immutable expectation.')
        require(all(getattr(a, f.name) == 0 for f in fields(a) if f.name not in allowed), 'Accounting does not match operation.')
        if op.outcome == 'completed': acknowledged = n
        else: stopped = op.outcome
    require(journal.checkpoint == acknowledged, 'Checkpoint must match completed prefix.')
    if stopped in ('unknown', 'rejected', 'not-started'):
        require(journal.state in (('uncertain',) if stopped == 'unknown' else ('failed', 'canceled')), 'Outcome requires terminal state.')
    if journal.state == 'uncertain': require(bool(journal.reason), 'Uncertainty requires reason.')
    if stopped == 'intent':
        require(journal.state in ('staging', 'verifying', 'uncertain'), 'Pending intent cannot claim definite termination.')
    if journal.state in ('verifying', 'verified-staged'):
        require(acknowledged >= upload_end, 'Verification before acknowledged uploads.')
    if journal.state == 'verified-staged':
        require(acknowledged == len(plan) and stopped is None and not journal.reason, 'Incomplete final staged verification.')
    total = journal.accounting
    if journal.state not in ('failed', 'canceled', 'uncertain'):
        require(total.snapshot_validation_reads <= tx.limits.snapshot_validation_reads and
                total.attempted_upload_bytes <= tx.budgets.upload_allowance and
                total.readback_bytes <= tx.budgets.readback_allowance and
                total.control_upload_bytes <= tx.limits.control_upload_bytes and
                total.control_read_bytes <= tx.limits.control_read_bytes, 'Execution accounting exceeds policy.')
    return journal
