"""Offline publisher acceptance. Network endpoints are numeric loopback only.

Workflow tests use the existing redistributable VICE D64 and replace only pinned
fixture hashes/reference bytes. Production has no override switch. Separate model
and history tests retain every real PA-4.13/PA-4.15 pin and canonical fixture hash.
"""
import copy
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4
from c64u_browser import publication_model as m
from c64u_browser import publication_verify as verify
from c64u_browser import managed_publication as publication
from c64u_browser.publication_history import load_reference
from c64u_browser.publication_journal import (PublicationJournal,inspect,JOURNAL_RESERVATION,
    EVENT_BYTES,CHECKPOINT_BYTES,MAX_EVENTS,reservation,admit)
from c64u_browser.required_evidence import EvidenceFailure,RequiredEvidence
from c64u_browser.core import ArgonautCore
from c64u_browser.api import UltimateClient
from c64u_browser.profiles import Preferences,Profile
from c64u_browser.ftp_reads import adapter_for
from c64u_browser.evidence_lifecycle import _LIVE_OWNERS
from c64u_browser.managed_library import ManagedLibraryReader
from c64u_ftp_server import FakeC64UFtp
from test_core import FakeCredentials

HISTORY=Path(__file__).parent/'fixtures/publication_history'
D64=Path(__file__).parent/'fixtures/vice-1541-authentic.d64'
INFO={'info':dict(unique_id='25EA78',product='C64 Ultimate',firmware_version='1.1.0s2'),
      'version':dict(version='0.1')}

class ModelTests(unittest.TestCase):
    def plan(self,title='C64Robots v1.3'):
        old,record,history=load_reference(HISTORY.resolve())
        return m.make_plan(str(uuid4()),title,old,record,history)
    def test_real_pinned_chain_and_deterministic_uuid(self):
        p=self.plan();self.assertEqual(m.game_id(),'56834b05-92d5-585f-9683-b4c79738cfaa')
        self.assertEqual(p.sha256,p.sha256)
    def test_exact_canonical_confirmed_title_fixtures(self):
        p=self.plan()
        self.assertEqual((len(p.manifest),m.digest(p.manifest)),(448,'f2b2d1150e42f8b5207baa15f1fbd2817086432e938f6778bd918969d2cc9e71'))
        self.assertEqual((len(p.metadata),m.digest(p.metadata)),(407,'4462bd06019230287542ce62a873da0e3dea1475f5f385417a968e3b59a9a5f5'))
        manifest=json.loads(p.manifest);self.assertEqual(manifest['revision'],1)
        self.assertEqual(manifest['created_at'],m.CREATED);self.assertEqual(manifest['library_id'],m.LIBRARY)
        self.assertEqual(len(manifest['games']),1);self.assertEqual(manifest['games'][0]['title'],'C64Robots v1.3')
    def test_title_bounds_and_no_fallback(self):
        for title in ('',None,'x'*513,'x\x7f','x\nq','x\x85q'):
            with self.subTest(title=repr(title)),self.assertRaises(Exception):self.plan(title)
        self.assertEqual(m.confirmed_title(' cafe\u0301 '),'café')
    def test_changed_manifest_and_record_refused(self):
        p=self.plan()
        for old,record in ((p.old_manifest+b' ',p.record),(p.old_manifest,p.record[:-1]+b' ')):
            with self.assertRaises(m.PublicationError):m.make_plan(str(uuid4()),p.title,old,record,p.history_digest)
    def test_journal_chain_is_inspection_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.plan();j=PublicationJournal(Path(tmp)/'evidence',p)
            try:
                channel=RequiredEvidence(j);channel.save('test-intent',dict(value='one'))
                channel.save('test-outcome',dict(value='two'))
                result=inspect(j.store.path,p.attempt);self.assertEqual(len(result),2)
                self.assertIsInstance(result,tuple);self.assertFalse(hasattr(result,'save'))
                event=j.store.path/(p.attempt+'.event-000000');event.write_bytes(b'{}\n')
                with self.assertRaises(Exception):inspect(j.store.path,p.attempt)
            finally:j.close()
    def test_exact_capacity_limit_and_one_below(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'evidence'
            self.assertGreater(admit(path,JOURNAL_RESERVATION),JOURNAL_RESERVATION)
            with self.assertRaises(m.PublicationError):admit(path,JOURNAL_RESERVATION-1)
            with patch('os.fstatvfs',return_value=type('FS',(),dict(f_frsize=4096,f_bavail=0))()):
                with self.assertRaises(m.PublicationError):admit(path,JOURNAL_RESERVATION)
    def test_capacity_exhaustion_retains_terminal_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=PublicationJournal(Path(tmp)/'evidence',self.plan())
            try:
                for i in range(MAX_EVENTS-12):j.save('observed',dict(n=i))
                j.save('publication-failure',dict(reason='retained'))
                with self.assertRaises(Exception):j.save('observed',dict(n=999))
                self.assertTrue(j.blocked)
            finally:j.close()
    def test_history_pin_corruption_refused(self):
        with patch('c64u_browser.publication_history.digest',return_value='0'*64):
            with self.assertRaises(m.PublicationError):load_reference(HISTORY.resolve())

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.tmp=self.stack.enter_context(tempfile.TemporaryDirectory());self.root=Path(self.tmp)
        old,record,history=load_reference(HISTORY.resolve())
        self.payload=D64.read_bytes();sha=m.digest(self.payload)
        doc=json.loads(record);doc['items'][0]['sha256']=sha;self.record=m.canonical(doc)
        self.old=old
        self.stack.enter_context(patch.object(m,'PAYLOAD',sha))
        self.stack.enter_context(patch.object(verify,'PAYLOAD',sha))
        self.stack.enter_context(patch.object(publication,'PAYLOAD',sha))
        self.stack.enter_context(patch.object(m,'RECORD_HASH',m.digest(self.record)))
        self.stack.enter_context(patch.object(publication,'load_reference',return_value=(old,self.record,history)))
        files={(m.ROOT+'/manifest.json').encode():old,(m.DIRECTORY+'/transaction.json').encode():self.record,
               (m.DIRECTORY+'/item-0001.d64').encode():self.payload}
        dirs={p.encode():b'' for p in ('/','/USB0',m.ROOT,m.DIRECTORY,m.ROOT+'/games',m.ROOT+'/metadata',m.ROOT+'/artwork')}
        self.server=self.stack.enter_context(FakeC64UFtp(files=files,directories=dirs,mutation_tree=True))
        def factory(host,password,port,http_port):
            client=UltimateClient(host,password,port=port,http_port=http_port)
            client.test_connection=lambda:INFO
            client.read_about=lambda route:INFO[route]
            return client
        self.core=ArgonautCore(preferences=Preferences(self.root/'config.json'),credentials=FakeCredentials(),client_factory=factory)
        self.addCleanup(self.core.close)
        profile=replace(Profile.new('fixture','127.0.0.1',device_id='25EA78'),ftp_port=self.server.port)
        self.core.connect(profile,remote_folder='/USB0')
        self.core.preferences.game_library_location=dict(library_id=m.LIBRARY,device_id=m.DEVICE,root='/USB0',path=m.ROOT)
        self.attempt=None
        self.addCleanup(self.release_inert)
    def release_inert(self):
        # Offline tests own all fake resources, including deliberately blocked owners.
        if self.attempt:
            self.attempt.journal.close();_LIVE_OWNERS.pop(id(self.attempt.lifecycle),None)
    def drain(self):
        with self.core.scheduler._lock:queues=tuple(self.core.scheduler._lanes.values())
        for q in queues:q.join()
    def review(self):
        snap=self.core.review_managed_publication(HISTORY.resolve(),'C64Robots v1.3',self.core.device_session()).wait(5)
        self.drain();self.assertEqual(snap.state,'succeeded',snap.error)
        return snap.result
    def authorize(self,review=None):
        r=review or self.review()
        return self.core.confirm_managed_publication(r,confirmed=True,confirmation_text=r.confirmation_text,
            exclusive_writer=True,unchanged_media=True,media_capacity_assured=True)
    def start(self,auth=None):
        self.attempt=self.core.publish_managed_transaction(auth or self.authorize(),journal_directory=self.root/'evidence')
        return self.attempt
    def mutations(self):
        return [(v,a) for v,a in self.server.commands if v in (b'STOR',b'RNFR',b'RNTO',b'DELE',b'MKD',b'RMD',b'APPE',b'SITE')]
    def failed(self):
        snap=self.attempt.wait(5);self.drain()
        self.assertIn(snap.state,('failed','cancelled'));self.assertIsNone(self.attempt.receipt)
        self.assertFalse(self.attempt.verified)
        with self.assertRaises(Exception):self.attempt.complete(1)
        self.assertFalse(any(v in (b'DELE',b'RMD',b'MKD',b'APPE',b'SITE') for v,a in self.mutations()))
        return snap
    def test_success_exact_sequence_no_payload_upload_and_display(self):
        a=self.start();snap=a.wait(5);self.drain();self.assertEqual(snap.state,'succeeded',snap.error)
        self.assertIsNone(a.receipt)
        expected=[]
        for kind,source,target in a.plan.mutations:
            expected.extend([(b'STOR',target.encode())] if kind=='STOR' else [(b'RNFR',source.encode()),(b'RNTO',target.encode())])
        self.assertEqual(self.mutations(),expected)
        self.assertEqual(self.server.files[m.FINAL.encode()],self.payload)
        self.assertEqual(self.server.files[(m.ROOT+'/manifest.json').encode()],a.plan.manifest)
        self.assertEqual(self.server.files[a.plan.backup.encode()],self.old)
        receipt=a.complete(1)
        self.assertEqual((receipt.library.games[0].title,receipt.platform,receipt.media),('C64Robots v1.3','Commodore 64','D64 disk image'))
        self.assertEqual(receipt.library.identity.device_id,m.DEVICE)
        self.assertEqual(len(receipt.library.games),1)
        self.assertFalse((self.root/'game-library.json').exists())
        self.assertTrue(inspect(a.journal.store.path,a.plan.attempt))
        events=[json.loads(p.read_bytes()) for p in sorted(a.journal.store.path.glob('*.event-*'))]
        kinds=[e['kind'] for e in events]
        self.assertLess(kinds.index('rnfr-outcome'),kinds.index('rnto-intent'))
        self.assertLess(kinds.index('job-terminal'),kinds.index('publication-complete'))
        raw=[e for e in events if e['kind']=='rnfr-outcome'][0]['value']
        self.assertEqual(raw['reply_hex'],b'350 Continue\r\n'.hex())
    def test_copied_authorization_and_repeat_refused(self):
        auth=self.authorize()
        with self.assertRaises(Exception):self.start(copy.copy(auth))
        a=self.start(auth);a.wait(5);self.drain()
        with self.assertRaises(Exception):self.core.publish_managed_transaction(auth,journal_directory=self.root/'second')
    def test_exact_confirmation_and_staging_authority_refused(self):
        r=self.review()
        with self.assertRaises(Exception):self.core.confirm_managed_publication(r,confirmed=True,confirmation_text='yes',exclusive_writer=True,unchanged_media=True,media_capacity_assured=True)
        with self.assertRaises(Exception):self.core.publish_managed_transaction(object(),journal_directory=self.root/'evidence')
        self.assertEqual(self.mutations(),[])
    def test_missing_payload(self):
        auth=self.authorize();del self.server.files[(m.DIRECTORY+'/item-0001.d64').encode()]
        self.start(auth);self.failed();self.assertEqual(self.mutations(),[])
    def test_changed_record(self):
        auth=self.authorize();path=(m.DIRECTORY+'/transaction.json').encode()
        self.server.files[path]=self.record.replace(b'format_version',b'Format_version')
        self.start(auth);self.failed();self.assertEqual(self.mutations(),[])
    def test_changed_manifest(self):
        auth=self.authorize();self.server.files[(m.ROOT+'/manifest.json').encode()]=self.old.replace(b'2026',b'2025')
        self.start(auth);self.failed();self.assertEqual(self.mutations(),[])
    def test_equal_bytes_destination_collision(self):
        auth=self.authorize();self.server.files[m.FINAL.encode()]=self.payload
        self.start(auth);self.failed();self.assertEqual(self.mutations(),[])
    def test_casefold_destination_collision(self):
        auth=self.authorize();self.server.files[m.FINAL.upper().replace('/USB0/ARGONAUT_LIBRARY/GAMES/','/USB0/ARGONAUT_LIBRARY/games/').encode()]=self.payload
        self.start(auth);self.failed();self.assertEqual(self.mutations(),[])
    def test_rnfr_refusal(self):
        auth=self.authorize();self.server.replies[b'RNFR']=b'550 Refused\r\n'
        self.start(auth);self.failed();self.assertEqual([v for v,a in self.mutations()],[b'STOR',b'STOR',b'RNFR'])
    def test_rnfr_lost_reply(self):
        auth=self.authorize();self.server.replies[b'RNFR']=None
        self.start(auth);self.failed();self.assertEqual([v for v,a in self.mutations()],[b'STOR',b'STOR',b'RNFR'])
        self.assertEqual(self.attempt.failure.state,'uncertain')
    def test_rnto_refusal(self):
        auth=self.authorize();self.server.replies[b'RNTO']=b'550 Refused\r\n'
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),4)
    def test_rnto_lost_reply(self):
        auth=self.authorize();self.server.after_mutation[b'RNTO']=None
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),4)
        self.assertEqual(self.attempt.failure.state,'uncertain')
    def test_pending_readback_mismatch(self):
        auth=self.authorize()
        self.server.readback_data=lambda path,data:b'x'*len(data) if b'metadata.pending-' in path else data
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),1)
    def test_partial_json_upload(self):
        auth=self.authorize();self.server.transfer_completion=lambda v,p:b'451 Partial\r\n' if v==b'STOR' else b'226 Complete\r\n'
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),1)
    def test_final_manifest_rename_ambiguity(self):
        auth=self.authorize()
        self.server.after_mutation[b'RNTO']=lambda path:None if path==(m.ROOT+'/manifest.json').encode() else b'250 Renamed\r\n'
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),10)
        self.assertEqual(self.attempt.catalog,'unknown')
    def test_external_writer_between_operations(self):
        auth=self.authorize()
        def hook(v,p):
            if v==b'STOR':self.server.files[(m.ROOT+'/metadata/external.json').encode()]=b'x'
        self.server.transfer_hook=hook
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),1)
    def test_one_source_index_blocks_different_attempt_directory(self):
        auth1=self.authorize();auth2=self.authorize()
        self.server.replies[b'RNFR']=b'550 Refused\r\n'
        self.start(auth1);self.failed()
        with self.assertRaises(Exception):self.core.publish_managed_transaction(auth2,journal_directory=self.root/'new')
        self.assertEqual(len(self.mutations()),3)
    def test_session_invalidation_between_commands(self):
        auth=self.authorize();original=PublicationJournal.save
        def save(store,kind,value):
            result=original(store,kind,value)
            if kind=='rnfr-outcome':self.core._session_id='changed'
            return result
        with patch.object(PublicationJournal,'save',save):
            self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),3)
    def test_cancellation_during_rnfr_persistence(self):self.cancel_at('rnfr-outcome')
    def test_cancellation_after_rnto_intent(self):self.cancel_at('rnto-intent')
    def test_cancellation_after_rnto_dispatch(self):self.cancel_at('rnto-outcome',expected=4)
    def cancel_at(self,kind,expected=3):
        auth=self.authorize();original=PublicationJournal.save;once=[False]
        def save(store,event,value):
            result=original(store,event,value)
            if event==kind and not once[0]:
                once[0]=True
                # Worker can obtain the retained owner before publish() returns.
                attempt=self.core._managed_publisher._attempts[store.plan.attempt]
                attempt.request_cancel()
            return result
        with patch.object(PublicationJournal,'save',save):self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),expected)
    def test_required_evidence_failure_before_rnto(self):
        auth=self.authorize();original=PublicationJournal.save
        def save(store,kind,value):
            if kind=='rnto-intent':raise OSError('injected persistence failure')
            return original(store,kind,value)
        with patch.object(PublicationJournal,'save',save):
            a=self.start(auth);snap=a.job.wait(5);self.drain()
            self.assertEqual(snap.state,'failed');self.assertTrue(a.channel.blocked)
            with self.assertRaises(Exception):a.wait(1)
        self.assertEqual(len(self.mutations()),3);self.assertIsNone(a.receipt)
    def test_terminal_persistence_failure_prevents_receipt(self):
        a=self.start();a.job.wait(5);self.drain();original=PublicationJournal.save
        def save(store,kind,value):
            if kind=='job-terminal':raise OSError('terminal failed')
            return original(store,kind,value)
        with patch.object(PublicationJournal,'save',save),self.assertRaises(Exception):a.complete(1)
        self.assertIsNone(a.receipt);self.assertFalse(a.lifecycle.close_attempted)
    def test_cancellation_immediately_after_rnfr_before_persistence(self):
        auth=self.authorize();original=PublicationJournal.save;once=[False]
        def save(store,kind,value):
            if kind=='rnfr-outcome' and not once[0]:
                once[0]=True
                self.core._managed_publisher._attempts[store.plan.attempt].request_cancel()
            return original(store,kind,value)
        with patch.object(PublicationJournal,'save',save):self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),3)
        events=[json.loads(p.read_bytes()) for p in self.attempt.journal.store.path.glob('*.event-*')]
        accepted=[e for e in events if e['kind']=='rnfr-outcome']
        self.assertEqual(len(accepted),1);self.assertEqual(accepted[0]['value']['reply_code'],350)
    def test_lease_invalidation_between_commands(self):
        auth=self.authorize();original=PublicationJournal.save
        def save(store,kind,value):
            result=original(store,kind,value)
            if kind=='rnfr-outcome':self.core._ftp_manager.invalidate(m.DEVICE)
            return result
        with patch.object(PublicationJournal,'save',save):self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),3)
    def test_policy_changed_after_review_refuses_before_mutation(self):
        auth=self.authorize()
        self.core._ftp_manager._policy=replace(self.core._ftp_manager._policy,reply_bytes=1000)
        with self.assertRaises(Exception):self.start(auth)
        self.assertEqual(self.mutations(),[])
    def test_cancellation_racing_actual_rnto_send(self):
        auth=self.authorize();original=PublicationJournal.save
        entered=threading.Event();release=threading.Event();cancel_done=threading.Event();installed=[False]
        def save(store,kind,value):
            result=original(store,kind,value)
            if kind=='rnto-intent' and not installed[0]:
                installed[0]=True;c=adapter_for(self.core._client)._context.get().client
                sock=c._control
                class Proxy:
                    def __getattr__(self,name):return getattr(sock,name)
                    def sendall(self,data):
                        if data.startswith(b'RNTO '):
                            entered.set()
                            if not release.wait(3):raise TimeoutError('test barrier')
                        return sock.sendall(data)
                    def recv(self,n,*args):
                        if entered.is_set() and not cancel_done.wait(3):raise TimeoutError('cancel barrier')
                        return sock.recv(n,*args)
                c._control=Proxy()
            return result
        with patch.object(PublicationJournal,'save',save):
            a=self.start(auth);self.assertTrue(entered.wait(3))
            errors=[];started=threading.Event()
            def cancel():
                started.set()
                try:a.request_cancel()
                except BaseException as e:errors.append(e)
                finally:cancel_done.set()
            thread=threading.Thread(target=cancel);thread.start();self.assertTrue(started.wait(3))
            release.set();thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
            self.failed()
        self.assertEqual(len(self.mutations()),4)
        self.assertIn(m.FINAL.encode(),self.server.files)
    def test_final_readback_mismatch_has_no_receipt(self):
        auth=self.authorize()
        self.server.readback_data=lambda p,d:(b'x'*len(d) if p==(m.ROOT+'/manifest.json').encode() and len(d)!=181 else d)
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),10)
    def test_positive_rename_with_both_names_retained_is_refused(self):
        auth=self.authorize()
        def hook(verb,path):
            if verb==b'RNTO' and path==m.FINAL.encode():
                self.server.files[(m.DIRECTORY+'/item-0001.d64').encode()]=self.payload
        self.server.mutation_hook=hook
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),4)
    def test_overlong_raw_stor_reply_stops_before_payload(self):
        auth=self.authorize();self.server.replies[b'STOR']=b'150 '+b'x'*5000+b'\r\n'
        self.start(auth);self.failed();self.assertEqual(len(self.mutations()),1)
    def test_capacity_rejected_before_remote_mutation(self):
        auth=self.authorize()
        with self.assertRaises(Exception):self.core.publish_managed_transaction(auth,journal_directory=self.root/'evidence',journal_allowance=JOURNAL_RESERVATION-1)
        self.assertEqual(self.mutations(),[])
        with self.assertRaises(Exception):self.core.publish_managed_transaction(auth,journal_directory=self.root/'other')
    def test_expired_review_refused(self):
        r=self.review()
        with patch.object(publication.time,'monotonic',return_value=r.expires_at+1):
            with self.assertRaises(Exception):self.authorize(r)
        self.assertEqual(self.mutations(),[])
    def test_busy_admission_consumes_authorization(self):
        from c64u_browser.jobs import CoreJob
        from c64u_browser.scheduler import JobBinding
        auth=self.authorize();ready=threading.Event();release=threading.Event()
        def work(job):ready.set();release.wait(3)
        self.core.scheduler.submit(CoreJob('busy-fixture',work),JobBinding.device(self.core.device_session()))
        self.assertTrue(ready.wait(3))
        try:
            with self.assertRaises(Exception):self.start(auth)
            with self.assertRaises(Exception):self.start(auth)
            self.assertEqual(self.mutations(),[])
        finally:
            release.set();self.drain()
            self.attempt=next(iter(self.core._managed_publisher._attempts.values()))

# Distinct parameterized test methods, each with fresh Core/server/evidence.
# Count test methods through unittest, not subtest rows.
def cancellation_boundary(kind,ordinal,expected):
    def test(self):
        auth=self.authorize();original=PublicationJournal.save;seen=[0]
        def save(store,event,value):
            result=original(store,event,value)
            if event==kind:
                seen[0]+=1
                if seen[0]==ordinal:self.core._managed_publisher._attempts[store.plan.attempt].request_cancel()
            return result
        with patch.object(PublicationJournal,'save',save):self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),expected)
    return test
for _kind,_count in (('stor-intent',2),('rnfr-outcome',4),('rnto-intent',4),('rnto-outcome',4)):
    for _ordinal in range(1,_count+1):
        _expected=(_ordinal-1 if _kind=='stor-intent' else 2+2*(_ordinal-1)+(2 if _kind=='rnto-outcome' else 1))
        setattr(WorkflowTests,'test_boundary_'+_kind.replace('-','_')+'_'+str(_ordinal),cancellation_boundary(_kind,_ordinal,_expected))

def rename_reply_fault(verb,ordinal,lost):
    def test(self):
        auth=self.authorize();seen=[0]
        def before(v,p):
            if v==verb:
                seen[0]+=1
                if seen[0]==ordinal:return b'' if lost else b'550 Refused\r\n'
        self.server.before_command=before
        self.start(auth);self.failed()
        self.assertEqual(len(self.mutations()),2+2*(ordinal-1)+(1 if verb==b'RNFR' else 2))
    return test
for _verb in (b'RNFR',b'RNTO'):
    for _ordinal in range(1,5):
        for _lost in (False,True):
            setattr(WorkflowTests,'test_reply_'+_verb.decode()+'_'+str(_ordinal)+('_lost' if _lost else '_refused'),rename_reply_fault(_verb,_ordinal,_lost))

def persistence_boundary(kind,ordinal,expected):
    def test(self):
        auth=self.authorize();original=PublicationJournal.save;seen=[0]
        def save(store,event,value):
            if event==kind:
                seen[0]+=1
                if seen[0]==ordinal:raise OSError('required persistence boundary')
            return original(store,event,value)
        with patch.object(PublicationJournal,'save',save):
            a=self.start(auth);snap=a.job.wait(5);self.drain()
            self.assertIn(snap.state,('failed','cancelled'))
            self.assertTrue(a.channel.blocked);self.assertIsNone(a.receipt)
            with self.assertRaises(Exception):a.complete(1)
        self.assertEqual(len(self.mutations()),expected)
    return test
for _kind,_count in (('stor-intent',2),('stor-preliminary',2),('stor-terminal',2),('stor-outcome',2),
                     ('rnfr-intent',4),('rnfr-outcome',4),('rnto-intent',4),('rnto-outcome',4)):
    for _ordinal in range(1,_count+1):
        if _kind.startswith('stor'):_expected=_ordinal-(1 if _kind=='stor-intent' else 0)
        else:_expected=2+2*(_ordinal-1)+(0 if _kind=='rnfr-intent' else 2 if _kind=='rnto-outcome' else 1)
        setattr(WorkflowTests,'test_persistence_'+_kind.replace('-','_')+'_'+str(_ordinal),persistence_boundary(_kind,_ordinal,_expected))

def exact_disk_capacity(self):
    with tempfile.TemporaryDirectory() as tmp:
        needed=reservation(1)
        for available,accepted in ((needed,True),(needed-1,False)):
            fs=type('FS',(),dict(f_frsize=1,f_bavail=available))()
            with patch('os.fstatvfs',return_value=fs):
                if accepted:self.assertEqual(admit(Path(tmp)/'evidence',JOURNAL_RESERVATION),needed)
                else:
                    with self.assertRaises(m.PublicationError):admit(Path(tmp)/'evidence',JOURNAL_RESERVATION)
ModelTests.test_actual_disk_exact_limit_and_one_byte_below=exact_disk_capacity

def strict_checkpoint_fields(self):
    from c64u_browser.required_evidence import encode_record
    with tempfile.TemporaryDirectory() as tmp:
        p=self.plan();j=PublicationJournal(Path(tmp)/'evidence',p)
        try:
            j.save('publication-prepared',dict(state='prepared'))
            checkpoint=j.store.path/(p.attempt+'.publication-000000')
            doc=json.loads(checkpoint.read_bytes());doc['value']['extra']=True
            checkpoint.write_bytes(encode_record(doc))
            with self.assertRaises(m.PublicationError):inspect(j.store.path,p.attempt)
        finally:j.close()
ModelTests.test_unknown_checkpoint_fields_refused=strict_checkpoint_fields

def actual_partial_upload(self):
    auth=self.authorize();adapter=adapter_for(self.core._client);installed=[False]
    def diagnostic(event):
        if event.get('kind')=='transfer-start' and event.get('operation')=='STOR' and not installed[0]:
            installed[0]=True;client=adapter._context.get().client;data_socket=client._data
            class Partial:
                def __getattr__(self,name):return getattr(data_socket,name)
                def sendall(self,data):
                    data_socket.sendall(data[:17]);raise OSError('partial data delivery')
            client._data=Partial()
    self.core._ftp_manager._diagnostic=diagnostic
    self.start(auth);self.failed()
    self.assertEqual(len(self.mutations()),1)
    events=[json.loads(p.read_bytes()) for p in self.attempt.journal.store.path.glob('*.event-*')]
    transfer=next(e['value']['transfer'] for e in events if e['kind']=='stor-failure')
    self.assertGreater(transfer['attempted_send_bytes'],0)
    self.assertEqual(transfer['confirmed_sender_bytes'],0)
    self.assertEqual(transfer['acknowledgment'],'unknown')
    self.assertEqual(self.attempt.failure.state,'uncertain')
WorkflowTests.test_actual_partial_json_data_delivery_retained=actual_partial_upload

def discovery_after_completion(self):
    a=self.start();self.assertEqual(a.wait(5).state,'succeeded');self.drain();receipt=a.complete(1)
    def factory(host,password,port,http_port):
        client=UltimateClient(host,password,port=port,http_port=http_port)
        client.test_connection=lambda:INFO;client.read_about=lambda route:INFO[route]
        return client
    core=ArgonautCore(preferences=Preferences(self.root/'config.json'),credentials=FakeCredentials(),client_factory=factory)
    self.addCleanup(core.close)
    profile=replace(Profile.new('fixture','127.0.0.1',device_id='25EA78'),ftp_port=self.server.port)
    core.connect(profile,remote_folder='/USB0');core.preferences.game_library_location=receipt.library.identity.preference()
    snap=core.load_managed_library(expected_session=core.device_session()).wait(5)
    self.assertEqual(snap.state,'succeeded',snap.error)
    self.assertEqual(snap.result.status,'valid')
    library=snap.result.libraries[0]
    self.assertEqual(library,receipt.library)
    self.assertEqual(library.games[0].path,'games/C64Robots v1.3.d64')
    review=core.review_managed_publication(HISTORY.resolve(),'C64Robots v1.3',core.device_session()).wait(5)
    self.assertEqual(review.state,'failed')
    self.assertEqual(len(self.mutations()),10)
    self.assertFalse((self.root/'game-library.json').exists())
WorkflowTests.test_existing_managed_discovery_and_no_duplicate_publication=discovery_after_completion
