"""Command-dependent in-memory peer for PA-5.1B concurrency regressions."""
import copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,threading,types,unittest
from pathlib import Path
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch
from c64u_browser.c64u_ftp import C64UFtpLeaseManager
from c64u_browser.c64u_ftp_types import ConnectionBinding,DeviceIdentity,FtpPolicy
from c64u_browser.ftp_reads import FtpReadAdapter
from c64u_browser.managed_rename import RenameStopped
from c64u_browser.required_evidence import RequiredEvidence,EvidenceDirectory,EvidenceReceipt,EvidenceFailure,encode_record
from c64u_browser.evidence_lifecycle import EvidenceLifecycle,_LIVE_OWNERS
from c64u_browser.jobs import CoreJob,JobCancelled
from c64u_browser.scheduler import CoreScheduler,DeviceSession

class Peer:
    def __init__(self,replies=None):
        self.pending=bytearray(b'220 inspection fixture\r\n');self.requests=[];self.connected=0;self.closed=False
        self.replies={b'USER':b'331 Password\r\n',b'PASS':b'230 Ready\r\n',b'FEAT':b'500 Not supported\r\n',b'TYPE':b'200 Binary\r\n',b'RNFR':b'350 Exact from\r\n',b'RNTO':b'250 Exact to\r\n',b'SIZE':b'213 3\r\n',**(replies or {})}
    def settimeout(self,t):pass
    def connect(self,address):self.connected+=1
    def sendall(self,raw):
        self.requests.append(raw);verb=raw.partition(b' ')[0].strip();self.pending.extend(self.replies.get(verb,b'500 Unknown\r\n') or b'')
    def recv(self,n):
        block=bytes(self.pending[:n]);del self.pending[:n];return block
    def shutdown(self,*a):pass
    def close(self):self.closed=True
    @property
    def mutations(self):return [r for r in self.requests if r.startswith((b'RNFR ',b'RNTO ',b'STOR ',b'DELE ',b'RMD ',b'MKD '))]

class MemorySink:
    def __init__(self,fail=None,hook=None):self.records=[];self.fail=fail;self.hook=hook
    def save(self,kind,value):
        if self.hook:self.hook(kind,value)
        if self.fail==kind:raise OSError('independent required save failure')
        data=encode_record(dict(kind=kind,value=value));self.records.append(json.loads(data))
        return EvidenceReceipt(str(len(self.records)),hashlib.sha256(data).hexdigest())

@contextmanager
def fixture(replies=None,diagnostic=None,module=None):
    peer=Peer(replies);binding=ConnectionBinding(DeviceIdentity('inspection-device'),'inspection-session','127.0.0.1');current=[binding]
    cls=C64UFtpLeaseManager if module is None else module.C64UFtpLeaseManager
    manager=cls(lambda _:current[0],lambda _:'',diagnostic=diagnostic,policy=FtpPolicy(control_reply=.1))
    adapter=FtpReadAdapter(manager,binding)
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',21))]),patch('socket.socket',return_value=peer):
        yield peer,adapter,current
