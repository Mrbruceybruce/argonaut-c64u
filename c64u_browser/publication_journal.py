# SPDX-License-Identifier: GPL-3.0-or-later
"""Separate hash-linked publication checkpoints; inspection cannot acquire a writer."""
import json
import os
from pathlib import Path
from threading import RLock
from .required_evidence import EvidenceDirectory, EvidenceReceipt, EvidenceFailure, encode_record
from .publication_model import canonical, digest, require

MAX_EVENTS = 128
# Enforced encoded bounds, including raw hex expansion, title/path escapes,
# immutable plan repeated in each checkpoint, and canonical envelope overhead.
EVENT_BYTES = 73728
CHECKPOINT_BYTES = 32768
JOURNAL_RESERVATION = MAX_EVENTS * (EVENT_BYTES + CHECKPOINT_BYTES)
SEALED_ALLOWANCE = 1024 * 1024
CEILING = 16 * 1024 * 1024
assert JOURNAL_RESERVATION <= CEILING
TERMINAL_EVENTS = 12


def reservation(block_size=4096):
    require(type(block_size) is int and 0 < block_size <= 1024*1024, 'Invalid filesystem allocation unit.')
    round_up = lambda n: ((n+block_size-1)//block_size)*block_size
    # Each event and checkpoint may occupy a partial block; index and directory,
    # sealed bytes, one maximal partial record and a 1 MiB safety margin count.
    return (MAX_EVENTS*(round_up(EVENT_BYTES)+round_up(CHECKPOINT_BYTES)) +
            4*block_size + SEALED_ALLOWANCE + round_up(EVENT_BYTES) + 1024*1024)


def admit(directory, allowance):
    require(type(allowance) is int and JOURNAL_RESERVATION <= allowance <= CEILING,
            'Publication journal reservation unavailable.')
    from .import_snapshots import open_directory
    fd = open_directory(Path(directory).parent)
    try:
        fs = os.fstatvfs(fd)
        needed = reservation(fs.f_frsize)
        require(fs.f_bavail * fs.f_frsize >= needed, 'Insufficient actual publication filesystem capacity.')
        return needed
    finally: os.close(fd)


class _Store(EvidenceDirectory):
    def __init__(self, directory, attempt):
        self.attempt = attempt
        super().__init__(directory,byte_limit=JOURNAL_RESERVATION,record_limit=2*MAX_EVENTS)
    def _record_name(self, kind):
        if kind == 'publication-checkpoint':
            return self.attempt + '.publication-' + f'{self.sequence//2:06d}'
        return self.attempt + '.event-' + f'{self.sequence//2:06d}'


class PublicationJournal:
    def __init__(self, directory, plan, *, allowance=JOURNAL_RESERVATION):
        self.certificate = capacity_certificate(plan)
        self.disk_reservation = admit(directory,allowance)
        require(len(encode_record(plan.proof())) <= 24000, 'Publication proof exceeds repeated-proof bound.')
        self.plan = plan
        self.store = _Store(directory,plan.attempt)
        self.sequence = 0; self.previous = ''; self.blocked = False
        self._lock = RLock(); self.terminal = False

    def save(self, kind, value):
        with self._lock:
            if self.blocked: raise EvidenceFailure('Publication journal blocked.')
            try:
                terminal = kind in ('publication-failure','publication-cancellation','rename-cancellation',
                    'cancellation-intent','cancellation-result','job-terminal','core-close-intent',
                    'core-close-result','publication-complete','visibility-result')
                limit = MAX_EVENTS if terminal else MAX_EVENTS-TERMINAL_EVENTS
                require(self.sequence < limit, 'Publication checkpoint capacity exhausted.')
                raw = encode_record(dict(kind=kind,value=value))
                require(len(raw) <= EVENT_BYTES, 'Publication event exceeds reservation.')
                checkpoint = dict(kind='argonaut-managed-publication',schema_version=1,
                    execution_policy_version=1,resource_policy_version=1,attempt=self.plan.attempt,
                    sequence=self.sequence,predecessor=self.previous,plan=self.plan.proof(),
                    plan_sha256=self.plan.sha256,event_kind=kind,event_sha256=digest(raw),
                    event_file=self.plan.attempt+'.event-'+f'{self.sequence:06d}')
                encoded = encode_record(dict(kind='publication-checkpoint',value=checkpoint))
                require(len(encoded) <= CHECKPOINT_BYTES, 'Publication checkpoint exceeds reservation.')
                receipt = self.store.save(kind,value)
                self.store.save('publication-checkpoint',checkpoint)
                self.previous=digest(encoded); self.sequence+=1
                return receipt
            except BaseException:
                self.blocked=True
                raise

    def close(self): self.store.close()


def inspect(directory, attempt):
    """Return immutable encoded inspection records, with no append/execute API."""
    from uuid import UUID
    require(type(attempt) is str and str(UUID(attempt))==attempt and UUID(attempt).version==4,
            'Canonical publication attempt UUID required.')
    path=Path(directory)
    require(path.is_absolute() and path.resolve()==path,'Unaliased publication directory required.')
    previous=''; result=[]
    names=sorted(path.glob(attempt+'.publication-*'))
    require(len(names)<=MAX_EVENTS,'Too many publication checkpoints.')
    from .import_snapshots import open_directory
    import stat
    fd=open_directory(path)
    def read(name,bound):
        f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(f,'rb') as stream:
            info=os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid() and
                    stat.S_IMODE(info.st_mode)==0o600 and info.st_size<=bound,
                    'Unsafe publication record.')
            raw=stream.read(bound+1)
        value=json.loads(raw)
        require(encode_record(value)==raw,'Noncanonical publication record.')
        return raw,value
    try:
        for n,name in enumerate(names):
            require(name.name==attempt+'.publication-'+f'{n:06d}','Missing publication predecessor.')
            raw,doc=read(name.name,CHECKPOINT_BYTES); value=doc['value']
            require(set(doc)=={'kind','value'} and set(value)=={'kind','schema_version','execution_policy_version',
                'resource_policy_version','attempt','sequence','predecessor','plan','plan_sha256','event_kind',
                'event_sha256','event_file'},'Unknown publication fields.')
            require(all(type(value[k]) is int for k in ('schema_version','execution_policy_version',
                'resource_policy_version','sequence')),'Invalid publication integer.')
            require(doc['kind']=='publication-checkpoint' and value['kind']=='argonaut-managed-publication' and
                value['schema_version']==value['execution_policy_version']==value['resource_policy_version']==1 and
                value['attempt']==attempt and value['sequence']==n and value['predecessor']==previous,
                'Invalid publication chain.')
            require(digest(canonical(value['plan']))==value['plan_sha256'],'Publication plan changed.')
            from .publication_model import make_plan
            from dataclasses import replace
            proof=value['plan']
            rebuilt=make_plan(proof['attempt'],proof['title'],bytes.fromhex(proof['old_manifest_hex']),
                bytes.fromhex(proof['record_hex']),proof['history_digest'])
            require(all(type(proof[k]) is str and len(proof[k])<=128 for k in ('session_id','adapter_owner')),
                    'Invalid publication owner identity.')
            rebuilt=replace(rebuilt,session_id=proof['session_id'],adapter_owner=proof['adapter_owner'])
            require(canonical(rebuilt.proof())==canonical(proof),'Unknown or inconsistent publication proof fields.')
            if result:require(value['plan_sha256']==json.loads(result[0])['value']['plan_sha256'],'Immutable proof changed.')
            require(value['event_file']==attempt+'.event-'+f'{n:06d}','Invalid event filename.')
            event,decoded=read(value['event_file'],EVENT_BYTES)
            require(set(decoded)=={'kind','value'} and digest(event)==value['event_sha256'] and
                    decoded['kind']==value['event_kind'],'Event digest mismatch.')
            result.append(raw);previous=digest(raw)
    finally:os.close(fd)
    require(bool(result),'Empty publication history.')
    expected={attempt+suffix+f'{n:06d}' for n in range(len(result)) for suffix in ('.publication-','.event-')}
    require(set(os.listdir(path))==expected,'Partial or unexpected publication evidence; inspect retained files.')
    return tuple(result)


def capacity_certificate(plan):
    """Actual canonical encoder derivation under enforced runtime field bounds.

    Raw replies are at most 32768 bytes -> 65536 hex characters. Rename paths
    are at most 2048 bytes; identities are bounded here to 128 characters.
    Each raw STOR reply is a separate event, never two replies in one record.
    """
    identity='\\'*128
    binding=dict(device_id=identity,core_session_id=identity,ftp_session_id=identity,
                 adapter_owner=identity)
    wire=dict(**binding,verb='RNTO',request_hex='f'*(2*(2048+7)),reply_hex='f'*65536,
              reply_code=599,submitted=True,acknowledgment='not-started',framing_complete=False,
              truncated=True,binding_valid=False,evidence_complete=False,transport_outcome='unknown',
              remote_effects_possible=True,error_type='x'*128)
    raw_event=len(encode_record(dict(kind='rnto-outcome',value=wire)))
    # A checkpoint repeats at most 24000 encoded proof bytes. Derive the exact
    # remaining canonical wrapper overhead with the same production encoder.
    header=dict(kind='argonaut-managed-publication',schema_version=1,execution_policy_version=1,
        resource_policy_version=1,attempt=plan.attempt,sequence=127,predecessor='f'*64,plan={},
        plan_sha256='f'*64,event_kind='x'*64,event_sha256='f'*64,
        event_file=plan.attempt+'.event-000127')
    checkpoint=24000+len(encode_record(dict(kind='publication-checkpoint',value=header)))-3
    require(raw_event<=EVENT_BYTES and checkpoint<=CHECKPOINT_BYTES,'Publication encoder reservation insufficient.')
    return dict(raw_reply_bytes=32768,raw_hex_characters=65536,max_path_bytes=2048,
                max_title_characters=512,derived_wire_event_bytes=raw_event,
                derived_checkpoint_bytes=checkpoint,enforced_event_bytes=EVENT_BYTES,
                enforced_checkpoint_bytes=CHECKPOINT_BYTES,max_events=MAX_EVENTS,
                terminal_events=TERMINAL_EVENTS,journal_bytes=JOURNAL_RESERVATION,
                sealed_control_allowance=SEALED_ALLOWANCE,ceiling=CEILING)
