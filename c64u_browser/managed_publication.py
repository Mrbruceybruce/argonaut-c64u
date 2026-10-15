# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless one-use publisher. No launch, retry, recovery, adoption or cleanup."""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock
import time
from uuid import uuid4
from .publication_model import (ROOT,LIBRARY,TRANSACTION,DIRECTORY,DEVICE,FINAL,PAYLOAD,SIZE,
    make_plan,require,digest,canonical,PublicationError)
from .publication_history import load_reference
from .publication_journal import PublicationJournal,JOURNAL_RESERVATION
from .publication_verify import Verifier
from .required_evidence import EvidenceDirectory,RequiredEvidence
from .evidence_lifecycle import EvidenceLifecycle
from .ftp_reads import adapter_for
from .jobs import CoreJob
from .scheduler import JobBinding
from .managed_library import parse_manifest


@dataclass(frozen=True)
class PublicationReview:
    plan: object
    expires_at: float
    confirmation_text: str


@dataclass(frozen=True)
class PublicationAuthorization:
    token: str


@dataclass(frozen=True)
class PublicationReceipt:
    attempt: str
    library: object
    manifest_sha256: str
    payload_path: str
    state: str = 'verified-published'
    platform: str = 'Commodore 64'
    media: str = 'D64 disk image'
    evidence_scope: str = 'point-in-time'
    independent_release: str = 'unverified'


@dataclass(frozen=True)
class PublicationFailure:
    attempt: str
    state: str
    phase: int
    possible_paths: tuple
    remote_catalog_exposure: str
    error_type: str
    persistence_blocked: bool


class PublicationAttempt:
    """Own the lifecycle. Job success alone is NOT a published receipt.

    wait() persists actual terminal state. complete() observes drain and closes
    the exclusively owned Core through the reviewed foundation before returning
    a receipt. Timeout/close/persistence failures retain this live owner.
    """
    def __init__(self,service,plan,journal):
        self.service,self.plan,self.journal=service,plan,journal
        self.channel=RequiredEvidence(journal)
        self.lifecycle=EvidenceLifecycle(service.core,self.channel)
        self.failure=None;self.receipt=None;self.phase=0;self.catalog='not-attempted'
        self.possible=[];self.verified=False;self.completed=False
        self.job=None
    def request_cancel(self):return self.lifecycle.request_cancel()
    def wait(self,timeout=None):return self.lifecycle.wait(timeout)
    def complete(self,timeout=None):
        require(not self.completed,'Publication completion is one-use.')
        snap=self.wait(timeout)
        require(snap.state=='succeeded' and self.verified and not self.channel.blocked,
                'Publication did not verify; retain evidence.')
        # The terminal job may precede the scheduler task_done observation.
        with self.service.core.scheduler._lock:
            pending=any(q.unfinished_tasks for q in self.service.core.scheduler._lanes.values())
        require(not pending,'Scheduler has not drained; observe again without mutation.')
        self.lifecycle.close()
        self.channel.save('publication-complete',dict(attempt=self.plan.attempt,
            manifest_sha256=digest(self.plan.manifest),state='verified-published',catalog='independently-verified',
            internal_ftp_release=True,internal_scheduler_release=True,independent_release='unverified'))
        self.journal.close()
        self.completed=True
        self.receipt=PublicationReceipt(self.plan.attempt,parse_manifest(self.plan.manifest,DEVICE,ROOT),
                                        digest(self.plan.manifest),FINAL)
        # Event is visibility only; failures never authorize a second mutation.
        try:
            self.service.core._emit('managed-library-changed',data=dict(library_id=LIBRARY,
                session_id=self.plan.session_id,revision=1,manifest_sha256=digest(self.plan.manifest)))
        except Exception:
            pass
        return self.receipt


class ManagedPublisher:
    def __init__(self,core):
        self.core=core;self._reviews={};self._authorizations={};self._attempts={};self._lock=RLock()

    def _capture(self,expected_session):
        with self.core._session_admission():
            session=self.core.device_session();client=self.core._require_client();adapter=adapter_for(client)
            preference=dict(self.core.preferences.game_library_location or {})
            require(session==expected_session and session.device_id==DEVICE and bool(session.session_id),
                    'Current publication device/session required.')
            require(preference==dict(library_id=LIBRARY,device_id=DEVICE,root='/USB0',path=ROOT),
                    'Exact selected library required.')
            require(adapter is not None and adapter._encoding=='utf-8','Managed UTF-8 FTP adapter required.')
            config_path=self.core.preferences.path
            policy=adapter._manager._policy
            require(len(session.session_id)<=128 and len(adapter._owner_id)<=128, 'Publication identity exceeds bound.')
        return session,client,adapter,preference,config_path,policy

    def _check(self,binding,plan=None):
        session,client,adapter,preference,config_path,policy=binding
        require(self.core.device_session()==session and self.core._client is client and
            adapter_for(client) is adapter and self.core.preferences.game_library_location==preference and
            self.core.preferences.path==config_path and adapter._manager._policy==policy,'Publication session, adapter or library changed.')
        adapter._manager._check(adapter.binding)
        if plan is not None:
            require(plan.session_id==session.session_id and plan.adapter_owner==adapter._owner_id,
                    'Publication owner changed.')

    def _identity(self,binding):
        self._check(binding)
        client=binding[1]
        info=client.read_about('info');version=client.read_about('version')
        require(info.get('unique_id')=='25EA78' and info.get('product')=='C64 Ultimate' and
            info.get('firmware_version')=='1.1.0s2' and version.get('version')=='0.1',
            'Fresh publication REST identity mismatch.')
        self._check(binding)

    def review(self,history_directory,title,expected_session):
        binding=self._capture(expected_session)
        old,record,history_digest=load_reference(history_directory)
        plan=replace(make_plan(str(uuid4()),title,old,record,history_digest),
                     session_id=binding[0].session_id,adapter_owner=binding[2]._owner_id)
        def task(job):
            def check():job.check_cancel();self._check(binding,plan)
            self._identity(binding)
            with binding[2].operation(check,reject_busy=True):
                Verifier(binding[2],plan,check,review=True).preflight()
            check()
            text='Publish '+plan.title+' as '+FINAL+'; plan SHA-256 '+plan.sha256
            review=PublicationReview(plan,time.monotonic()+300,text)
            with self._lock:self._reviews[id(review)]=(review,binding,plan.sha256)
            return review
        return self.core.scheduler.submit(CoreJob('game-library.publication-review',task),
                                          JobBinding.device(binding[0]),reject_busy=True)

    def discard(self,review):
        with self._lock:
            entry=self._reviews.get(id(review))
            require(entry is not None and entry[0] is review,'Live review required.')
            del self._reviews[id(review)]

    def confirm(self,review,*,confirmed,confirmation_text,exclusive_writer,unchanged_media,media_capacity_assured):
        with self._lock:
            entry=self._reviews.pop(id(review),None)
            require(entry is not None and entry[0] is review,'Exact unconsumed review required.')
            require(all(v is True for v in (confirmed,exclusive_writer,unchanged_media,media_capacity_assured)),
                    'Exact confirmation and operating attestations required.')
            require(confirmation_text==review.confirmation_text and time.monotonic()<review.expires_at and
                    review.plan.sha256==entry[2],'Review changed or expired.')
            self._check(entry[1],review.plan)
            auth=PublicationAuthorization(uuid4().hex)
            self._authorizations[id(auth)]=(auth,entry,review.expires_at)
            return auth

    def publish(self,authorization,*,journal_directory,journal_allowance=JOURNAL_RESERVATION):
        with self._lock:
            held=self._authorizations.pop(id(authorization),None)
            require(held is not None and held[0] is authorization,'Exact one-use publication authorization required.')
            review,binding,plan_hash=held[1];plan=review.plan
            require(time.monotonic()<held[2] and plan.sha256==plan_hash,'Publication authority expired or changed.')
            self._check(binding,plan)
            # Permanent per-source exclusion is independent of P and chosen journal path.
            # Exclusive directory creation refuses a second attempt, including restart.
            key=digest(canonical([DEVICE,ROOT,LIBRARY,TRANSACTION,'item-0001.d64']))
            index=EvidenceDirectory(Path(binding[4]).parent/('publication-source-'+key),byte_limit=65536,record_limit=1)
            try:
                index.save('publication-attempt',dict(attempt=plan.attempt,plan_sha256=plan_hash,
                    journal_directory=str(journal_directory),source_key=key))
            finally:index.close()
            journal=PublicationJournal(journal_directory,plan,allowance=journal_allowance)
            attempt=PublicationAttempt(self,plan,journal)
            attempt.expires_at=held[2]
            self._attempts[plan.attempt]=attempt
            attempt.channel.save('publication-prepared',dict(plan_sha256=plan_hash,
                journal_reservation=JOURNAL_RESERVATION,disk_reservation=journal.disk_reservation,
                exclusive_writer=True,unchanged_media=True,media_capacity_assured=True,
                remote_free_space='unverified',firmware_rename_qualification='required-before-physical-use'))
            attempt.job=attempt.lifecycle.start('game-library.publication',
                lambda job,owner:self._execute(attempt,binding,plan_hash,job))
            return attempt

    def _execute(self,attempt,binding,plan_hash,job):
        p=attempt.plan;a=binding[2];save=attempt.channel.save
        def check():
            job.check_cancel();self._check(binding,p)
            require(p.sha256==plan_hash and not attempt.channel.blocked and time.monotonic()<attempt.expires_at,
                    'Publication proof, expiry or evidence changed.')
        v=Verifier(a,p,check,save)
        try:
            check();self._identity(binding)
            with a.operation(check,reject_busy=True):
                v.preflight();attempt.lifecycle.observe_ftp(a,'preflight')
                for n,(kind,source,target) in enumerate(p.mutations,1):
                    check()
                    if n==3:
                        v.read(ROOT+'/manifest.json',p.old_manifest)
                        v.read(DIRECTORY+'/transaction.json',p.record)
                        v.read(p.source,payload=True)
                    if n==5:
                        v.read(ROOT+'/manifest.json',p.old_manifest)
                        v.read(p.pending,p.manifest);v.read(p.metadata_final,p.metadata)
                    if n==6:v.read(p.pending,p.manifest)
                    # Last complete absence/source observation before each mutation.
                    v.memberships(n-1)
                    save('publication-operation-intent',dict(operation=n,kind=kind,source=source,target=target,
                        plan_sha256=plan_hash,phase=n-1))
                    attempt.possible.extend(x for x in (source,target) if x and x not in attempt.possible)
                    if n==6:attempt.catalog='unknown'
                    if kind=='STOR':
                        data=p.metadata if n==1 else p.manifest
                        result=a.write_publication_json(target,data,attempt.channel)
                        require(result.transfer.acknowledgment.value=='completed' and
                            result.transfer.confirmed_sender_bytes==len(data) and result.transfer.uncertain_send_bytes==0 and
                            result.transfer.sha256==digest(data),'JSON upload not definitively accepted.')
                    else:
                        owner=a.begin_evidenced_rename(source,target,attempt.channel)
                        owner.continue_rename()
                        require(owner.verified,'Rename incomplete.')
                    if n==6:attempt.catalog='acknowledged'
                    save('publication-operation-outcome',dict(operation=n,outcome='acknowledged',source=source,target=target))
                    check();attempt.phase=n
                    if n==1:v.read(target,p.metadata)
                    elif n==2:v.read(target,p.manifest)
                    elif n==3:v.read(target,payload=True)
                    elif n==4:v.read(target,p.metadata)
                    elif n==5:v.read(target,p.old_manifest)
                v.memberships(6)
                v.read(ROOT+'/manifest.json',p.manifest)
                library=parse_manifest(p.manifest,DEVICE,ROOT)
                require(library.revision==1 and len(library.games)==1,'Final manifest changed.')
                v.read(FINAL,payload=True);v.read(p.metadata_final,p.metadata)
                v.read(p.backup,p.old_manifest);v.read(DIRECTORY+'/transaction.json',p.record)
                v.memberships(6);check()
                attempt.catalog='independently-verified'
                save('publication-verified',dict(attempt=p.attempt,manifest_sha256=digest(p.manifest),
                    payload_sha256=PAYLOAD,payload_path=FINAL,revision=1,
                    payload_read_bytes=v.payload.used,control_read_bytes=v.control.used,listings=v.listings))
                attempt.lifecycle.observe_ftp(a,'verified-publication')
            check();attempt.verified=True
            return dict(state='verified-pending-lifecycle',attempt=p.attempt)
        except BaseException as exc:
            blocked=attempt.channel.blocked
            canceled=getattr(exc,'cancelled',False)
            uncertain=blocked
            for rename in a._rename_owners.values():
                for command in (rename.rnfr,rename.rnto):
                    if command is not None and command.submitted and not command.accepted and command.acknowledgment!='rejected':
                        uncertain=True
            wire_error=getattr(exc,'ftp_error',None)
            transfer=getattr(wire_error,'transfer',None)
            if transfer is not None and transfer.submitted and transfer.acknowledgment.value=='unknown':
                uncertain=True
            state='uncertain' if uncertain else 'canceled-retained' if canceled else 'failed-retained'
            attempt.failure=PublicationFailure(p.attempt,state,attempt.phase,tuple(attempt.possible),
                                              attempt.catalog,type(exc).__name__,blocked)
            exc.result=attempt.failure
            if not blocked:
                save('publication-cancellation' if canceled else 'publication-failure',
                     dict(attempt=p.attempt,state=state,phase=attempt.phase,possible_paths=attempt.possible,
                          catalog=attempt.catalog,error_type=type(exc).__name__,
                          pending_rename_context='unknown' if a._rename_owners else 'not-held'))
            raise
