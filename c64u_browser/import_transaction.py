# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline import transaction evidence. Nothing here authorizes or performs I/O."""
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from .import_plan import ImportPlan, ImportItem, ContentEvidence, LIMITS, MAX_SOURCE_BYTES, validate_selections
from .managed_library import LibraryIdentity, LibraryError, location, relative_path, uuid_text
from .picker_model import PickerSelection
from .scheduler import DeviceSession

MiB = 1024 * 1024
MAX_FILES = 64
MAX_SNAPSHOT_BYTES = 128 * MiB
MAX_SPOOL_BYTES = 128 * MiB
MAX_UPLOAD_BYTES = 128 * MiB
MAX_READBACK_BYTES = 128 * MiB
MAX_JOURNAL_BYTES = MiB
MAX_OPERATIONS = 256
MAX_RECOVERY_JOURNALS = 64
SCHEMA_VERSION = 1
MAX_TEXT = 4096
MAX_DEPTH = 12
MAX_NODES = 200000


class TransactionError(ValueError):
    pass


def require(ok, message):
    if not ok:raise TransactionError(message)


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'Invalid integer bound.')


def text(value, limit=MAX_TEXT, *, empty=False):
    require(type(value) is str and (empty or bool(value)) and len(value) <= limit,
            'Invalid or oversized text.')
    try:value.encode('utf-8', errors='strict')
    except UnicodeError as exc:raise TransactionError('Invalid UTF-8 text.') from exc
    require(not any(ord(c) < 32 or ord(c) == 127 for c in value), 'Invalid text.')


def digest(value):
    require(type(value) is str and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'Missing or invalid SHA-256.')


def immutable(value):
    """Reject oversized/deep evidence before recursive conversion or encoding."""
    remaining = MAX_NODES
    def visit(item, depth):
        nonlocal remaining
        remaining -= 1
        require(remaining >= 0 and depth <= MAX_DEPTH, 'Evidence nesting/node limit exceeded.')
        if type(item) is str:
            text(item, empty=True);return
        if type(item) is int:
            require(item.bit_length() <= 128, 'Excessive integer.');return
        if type(item) in (bool, type(None)):return
        if type(item) is tuple:
            require(len(item) <= 10000, 'Evidence collection limit exceeded.')
            for v in item:visit(v, depth+1)
            return
        if is_dataclass(item) and not isinstance(item, type) and item.__dataclass_params__.frozen:
            require(len(fields(item)) <= 32, 'Excessive record fields.')
            for field in fields(item):visit(getattr(item, field.name), depth+1)
            return
        raise TransactionError('Mutable or unsupported evidence.')
    visit(value, 0)


def identity(value):
    require(type(value) is LibraryIdentity, 'Invalid library identity.')
    try:location(value.preference());uuid_text(value.library_id)
    except (LibraryError, TypeError, ValueError) as exc:raise TransactionError('Invalid library identity.') from exc
    text(value.device_id,256);text(value.path)
    require(':' not in value.path, 'Library path alias.')


def canonical(value):
    if is_dataclass(value):return {f.name: canonical(getattr(value, f.name)) for f in fields(value)}
    if type(value) is tuple:return [canonical(v) for v in value]
    return value


def evidence_digest(plan):
    return hashlib.sha256(json.dumps(canonical(plan.evidence()), sort_keys=True,
        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class Budgets:
    """Planned payload ceilings only; actual I/O consumption is a 3B-2 concern."""
    files: int = MAX_FILES
    snapshot_bytes: int = MAX_SNAPSHOT_BYTES
    spool_bytes: int = MAX_SPOOL_BYTES
    upload_bytes: int = MAX_UPLOAD_BYTES
    readback_bytes: int = MAX_READBACK_BYTES
    journal_bytes: int = MAX_JOURNAL_BYTES
    operations: int = MAX_OPERATIONS

    def validate(self):
        for field in fields(self):integer(getattr(self, field.name), 1, getattr(Budgets(), field.name))


@dataclass(frozen=True)
class TransactionItem:
    source: PickerSelection
    local_identity: tuple
    format: str
    size: int
    sha256: str
    final_path: str
    staged_path: str


@dataclass(frozen=True)
class Transaction:
    id: str
    plan_id: str
    revalidated_plan_id: str
    plan_digest: str
    library: LibraryIdentity
    session_id: str
    manifest_revision: int
    manifest_digest: str
    created_at: str
    budgets: Budgets
    items: tuple[TransactionItem, ...]
    skipped_duplicates: int

    @property
    def directory(self):return 'argonaut-import-' + self.id

    @property
    def record_path(self):return self.directory + '/transaction.json'

    @property
    def recovery_location(self):return self.library.path + '/' + self.directory

    def validate(self):
        self._validate_structure()
        self._validate_payload()
        return self

    def _validate_structure(self):
        require(type(self.items) is tuple and len(self.items)<=MAX_FILES, 'Invalid item count.')
        immutable(self);identity(self.library)
        for value in (self.id, self.plan_id, self.revalidated_plan_id):
            try:uuid_text(value)
            except LibraryError as exc:raise TransactionError('Invalid transaction/plan UUID.') from exc
        require(self.plan_id != self.revalidated_plan_id, 'Explicit revalidation required.')
        digest(self.plan_digest);digest(self.manifest_digest);text(self.session_id,256)
        integer(self.manifest_revision, 0, 2**63-1)
        text(self.created_at,64)
        try:stamp = datetime.fromisoformat(self.created_at)
        except (TypeError, ValueError) as exc:raise TransactionError('Invalid timestamp.') from exc
        require(stamp.tzinfo is not None, 'Timestamp needs timezone.')
        self._validate_budgets()
        integer(len(self.items), 1, self.budgets.files)
        integer(self.skipped_duplicates, 0, self.budgets.files-len(self.items))
        names=set();hashes=set()
        sources=tuple(i.source for i in self.items)
        try:validate_selections(sources, DeviceSession(self.library.device_id, self.session_id))
        except (ValueError, LibraryError) as exc:raise TransactionError('Invalid source binding.') from exc
        for n,item in enumerate(self.items, 1):
            require(type(item) is TransactionItem and type(item.source) is PickerSelection, 'Invalid item.')
            require(item.format in LIMITS, 'Unsupported format.')
            integer(item.size, 1, LIMITS[item.format]);digest(item.sha256)
            text(item.source.filename,255)
            require(item.source.filename.lower().endswith('.'+item.format.lower()), 'Format mismatch.')
            # Reject lexical aliases without accessing local or remote files.
            require(item.source.path.startswith('/') and not any(p in ('', '.', '..')
                    for p in item.source.path.split('/')[1:]) and
                    '\\' not in item.source.path, 'Source path alias.')
            text(item.source.path)
            if item.source.scope == 'core-host':
                require(len(item.local_identity)==5 and all(type(v) is int for v in item.local_identity)
                        and item.local_identity[2]==item.size, 'Missing local source identity.')
            else:require(item.local_identity==(), 'Unexpected local evidence.')
            require(item.final_path=='games/'+item.source.filename, 'Destination alias.')
            try:relative_path(item.final_path,'games')
            except LibraryError as exc:raise TransactionError('Invalid destination.') from exc
            require(item.staged_path==f'{self.directory}/item-{n:04d}.{item.format.lower()}',
                    'Invalid staged path.')
            require(item.final_path.casefold() not in names and (item.size,item.sha256) not in hashes,
                    'Duplicate transfer item.')
            names.add(item.final_path.casefold());hashes.add((item.size,item.sha256))
        return self

    def _validate_source_item(self):
        return self.validate()

    def _validate_budgets(self):
        require(type(self.budgets) is Budgets, 'Invalid resource budgets.')
        self.budgets.validate()

    def _validate_payload(self):
        total=sum(i.size for i in self.items)
        for cap in (self.budgets.snapshot_bytes,self.budgets.spool_bytes,
                    self.budgets.upload_bytes,self.budgets.readback_bytes):
            require(total<=cap,'Transaction resource budget exceeded.')

    def require_absent(self, entries):
        """Validate a supplied complete parent listing; never a lease/ownership claim."""
        self.validate()
        require(type(entries) is tuple and all(type(e) is str for e in entries), 'Invalid listing.')
        require(all(e.casefold()!=self.directory.casefold() for e in entries),
                'Existing transaction directory must not be reused.')


def _eligible(plan):
    require(type(plan) is ImportPlan, 'Expected immutable import plan.');immutable(plan)
    identity(plan.library);text(plan.session_id);digest(plan.manifest_sha256)
    require(plan.completion=='complete-review-only', 'Incomplete plan.')
    integer(plan.revision,0,2**63-1);integer(len(plan.items),1,MAX_FILES)
    require(all(type(i) is ImportItem for i in plan.items), 'Invalid plan item.')
    require(len(plan.content)<=10000 and all(type(g) is ContentEvidence for g in plan.content), 'Invalid catalog evidence.')
    require(all(type(e) is tuple and len(e)==2 and all(type(v) is str for v in e)
                for e in plan.destination_entries), 'Invalid destination listing.')
    for item in plan.items:
        require(type(item.source) is PickerSelection and item.format in LIMITS, 'Invalid source/format.')
        integer(item.size,1,LIMITS[item.format]);digest(item.sha256)
    for game in plan.content:
        text(game.path);digest(game.sha256);integer(game.size,1,64*MiB)
        require(game.status in ('verified','manifest-only','mismatch','unavailable'), 'Invalid catalog status.')
    integer(plan.source_bytes_read,1,MAX_SOURCE_BYTES)
    integer(plan.bytes_read,plan.source_bytes_read,2**63-1)
    require(plan.source_bytes_read>=2*sum(i.size for i in plan.items), 'Missing verification reads.')
    require(plan.transfer_bytes==sum(i.size for i in plan.items if i.classification=='new'), 'Invalid workload.')
    seen=[]
    for item in plan.items:
        require(item.classification in ('new','same-name-duplicate','content-duplicate','batch-duplicate'),
                'Unresolved candidate blocks the batch.')
        digest(item.sha256);require(item.format in LIMITS,'Unsupported format.')
        integer(item.size,1,LIMITS[item.format])
        named=[g for g in plan.content if g.path.casefold()==item.relative_destination.casefold()]
        matching=[g for g in plan.content if (g.size,g.sha256)==(item.size,item.sha256)]
        require(all(g.status=='verified' for g in named+matching),'Unverified catalog evidence.')
        require(all((g.size,g.sha256)==(item.size,item.sha256) for g in named),'Catalog conflict.')
        occupied=[(name,kind) for name,kind in plan.destination_entries if name.casefold()==item.source.filename.casefold()]
        require(not occupied or (named and len(occupied)==1 and occupied[0][1]=='file'), 'Destination collision.')
        require(not named or len(occupied)==1,'Missing catalog file.')
        require(not any(p.relative_destination.casefold()==item.relative_destination.casefold() and
                        (p.size,p.sha256)!=(item.size,item.sha256) for p in plan.items), 'Batch conflict.')
        expected=('same-name-duplicate' if named else 'content-duplicate') if matching else (
            'batch-duplicate' if any((p.size,p.sha256)==(item.size,item.sha256) and
            p.classification in ('new','batch-duplicate') for p in seen) else 'new')
        require(item.classification==expected,'Inconsistent duplicate classification.')
        seen.append(item)


def prepare_transaction(original, revalidated, *, library, session, revision, manifest_digest,
                        budgets=Budgets()):
    """Pure construction from explicit revalidation evidence, never execution authority.

    Trusted future Core must supply the actual revalidation result. Offline data
    cannot prove freshness or human consent; execution must recheck both.
    """
    return _prepare_transaction(original,revalidated,library=library,session=session,
        revision=revision,manifest_digest=manifest_digest,budgets=budgets)


def _prepare_transaction(original,revalidated,*,library,session,revision,manifest_digest,
                         budgets,transaction_type=Transaction):
    _eligible(original);_eligible(revalidated)
    identity(library);integer(revision,0,2**63-1);digest(manifest_digest)
    require(type(session) is DeviceSession, 'Invalid captured session.')
    require(original.id!=revalidated.id and original.evidence()==revalidated.evidence(), 'Stale/unrevalidated plan.')
    require(revalidated.library==library and revalidated.session_id==session.session_id and
            library.device_id==session.device_id and revalidated.revision==revision and
            revalidated.manifest_sha256==manifest_digest,'Captured context mismatch.')
    transaction_id=str(uuid4());directory='argonaut-import-'+transaction_id
    selected=tuple(i for i in revalidated.items if i.classification=='new')
    require(bool(selected),'Duplicate-only batch has nothing to stage.')
    result=transaction_type(transaction_id,original.id,revalidated.id,evidence_digest(revalidated),library,
        session.session_id,revision,manifest_digest,datetime.now(timezone.utc).isoformat(),budgets,
        tuple(TransactionItem(i.source,i.local_identity,i.format,i.size,i.sha256,i.relative_destination,
              f'{directory}/item-{n:04d}.{i.format.lower()}') for n,i in enumerate(selected,1)),
        len(revalidated.items)-len(selected))
    # Validate skipped source references as strictly as transfer references.
    for i in revalidated.items:
        check=replace(result,items=(TransactionItem(i.source,i.local_identity,i.format,i.size,i.sha256,
            i.relative_destination,f'{directory}/item-0001.{i.format.lower()}'),),skipped_duplicates=0)
        check._validate_source_item()
    return result.validate()


STATES=('prepared','awaiting-confirmation','staging','verifying','verified-staged',
        'canceled','failed','uncertain','published')
RESERVED_STATES = ('staging','verifying','verified-staged','published')
_TRANSITIONS={
    'prepared':('awaiting-confirmation','canceled','failed'),
    'awaiting-confirmation':('canceled','failed'),
}



@dataclass(frozen=True)
class OperationEvidence:
    sequence: int
    kind: str
    path: str
    outcome: str = 'intent'
    size: int = 0
    sha256: str = ''


@dataclass(frozen=True)
class Journal:
    transaction: Transaction
    state: str = 'prepared'
    operations: tuple[OperationEvidence, ...] = ()
    checkpoint: int = 0
    reason: str = ''
    schema_version: int = SCHEMA_VERSION

    @property
    def requires_inspection(self):
        return bool(self.operations) or self.state not in ('prepared','awaiting-confirmation')

    def validate(self):
        require(type(self.operations) is tuple and len(self.operations)<=MAX_OPERATIONS, 'Invalid evidence count.')
        immutable(self);self.transaction.validate()
        self._validate_schema()
        require(self.state in STATES and self.state not in RESERVED_STATES,
                'Execution/publication states are reserved for later authorized phases.')
        integer(len(self.operations),0,self.transaction.budgets.operations)
        integer(self.checkpoint,0,len(self.operations))
        require(type(self.reason) is str and len(self.reason)<=256 and
                all(c.islower() or c.isdigit() or c=='-' for c in self.reason),'Use a bounded reason code, not raw errors.')
        items={i.staged_path:i for i in self.transaction.items}
        verified=set();uploaded=set();directory=False;record=False;pending=False;reading=False
        acknowledged=0
        for n,op in enumerate(self.operations,1):
            require(type(op) is OperationEvidence and type(op.sequence) is int and op.sequence==n,'Invalid operation ordering.')
            require(not pending,'Unresolved intent must stop further operations.')
            require(op.kind in ('mkdir','record','upload','readback'),'Unknown operation.')
            require(op.outcome in ('intent','completed','rejected','unknown'),'Invalid operation outcome.')
            require(self.state not in ('prepared','awaiting-confirmation'),'Operations precede staging.')
            # Recovery observations may truthfully exceed planned payload limits.
            # This bounds representation, not actual I/O; there is no I/O here.
            integer(op.size,0,2**63-1)
            if op.outcome=='intent':
                require(op.size==0 and not op.sha256, 'Unsubmitted intent cannot claim consumption.')
            if op.sha256:digest(op.sha256)
            if op.kind=='mkdir':
                require(n==1 and op.path==self.transaction.directory and op.size==0 and not op.sha256,'Invalid mkdir evidence.')
                directory=op.outcome=='completed'
            elif op.kind=='record':
                require(directory and not record and op.path==self.transaction.record_path,'Invalid record evidence.')
                if op.outcome=='completed':
                    integer(op.size,1,self.transaction.budgets.journal_bytes);digest(op.sha256);record=True
            else:
                require(directory and record and op.path in items,'Unowned staged path.')
                item=items[op.path]
                require(op.path not in (uploaded if op.kind=='upload' else verified),'No automatic retry.')
                if op.kind=='readback':
                    require(uploaded==set(items),'Readback before all uploads completed.');reading=True
                else:require(not reading,'Upload after readback phase.')
                if op.outcome=='completed':
                    require((op.size,op.sha256)==(item.size,item.sha256),'Content evidence mismatch.')
                    (uploaded if op.kind=='upload' else verified).add(op.path)
            if op.outcome!='completed':pending=True
            else:acknowledged=n
            if n<=self.checkpoint:require(op.outcome=='completed','Checkpoint includes unresolved operation.')
        require(self.checkpoint==acknowledged, 'Checkpoint must match acknowledged prefix.')
        require(verified!=set(items), 'Recovery record cannot claim complete staged verification.')
        unknown=any(op.outcome=='unknown' for op in self.operations)
        require((self.state=='uncertain')==unknown, 'Unknown outcome requires uncertain recovery state.')

        return self

    def _validate_schema(self):
        require(type(self.schema_version) is int and self.schema_version==SCHEMA_VERSION,
                'Unknown journal schema.')
        require(type(self.transaction) is Transaction, 'Schema-1 transaction required.')

    def transition(self,state,*,reason=''):
        self.validate()
        require(state in _TRANSITIONS.get(self.state,()),'Invalid/terminal state transition.')
        return replace(self,state=state,reason=reason).validate()

    def intent(self,kind,path):
        raise TransactionError('Execution intent recording is reserved for Phase 3B-2.')

    def outcome(self,status,*,size=0,sha256=''):
        raise TransactionError('Execution outcome recording is reserved for Phase 3B-2.')
