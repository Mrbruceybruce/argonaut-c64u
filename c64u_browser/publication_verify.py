# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase-aware exact membership and independent readback; no mutations."""
import io
from .publication_model import (ROOT,DIRECTORY,FINAL,SIZE,PAYLOAD,DEVICE,require,digest)
from .disk_image import D64Image


class Budget:
    def __init__(self,maximum,parent=None): self.maximum=maximum; self.used=0; self.parent=parent
    @property
    def remaining(self):return self.maximum-self.used
    def require(self,n):
        require(type(n) is int and 0<=n<=self.remaining,'Publication read allowance exhausted.')
        if self.parent:self.parent.require(n)
    def consume(self,n):
        self.require(n);self.used+=n
        if self.parent:self.parent.consume(n)


class Verifier:
    def __init__(self,adapter,plan,check,save=lambda *args:None,*,review=False):
        self.adapter,self.plan,self.check,self.save=adapter,plan,check,save
        self.control=Budget(6*1024*1024);self.payload=Budget(SIZE if review else 4*SIZE)
        self.listings=0

    def read(self,path,data=None,*,payload=False):
        self.check()
        expected=SIZE if payload else len(data)
        sink=io.BytesIO()
        result=self.adapter.read_into(path,sink,expected_bytes=expected,
            budget=self.payload if payload else self.control)
        raw=sink.getvalue()
        require(result.bytes_transferred==expected if hasattr(result,'bytes_transferred') else len(raw)==expected,
                'Read length changed.')
        require(len(raw)==expected and digest(raw)==(PAYLOAD if payload else digest(data)), 'Independent readback mismatch.')
        if payload:
            validation=D64Image(raw).validate()
            require(validation.standard_compatible and not validation.issues,'Invalid staged D64 structure.')
        else:require(raw==data,'Control bytes changed.')
        self.check()
        self.save('verified-read',dict(path=path,size=len(raw),sha256=digest(raw)))
        return raw

    def memberships(self,phase):
        p=self.plan
        expected={
            '/USB0':{'ARGONAUT_LIBRARY':('dir',None)},
            ROOT:{'games':('dir',None),'metadata':('dir',None),'artwork':('dir',None),
                  DIRECTORY.rsplit('/',1)[1]:('dir',None)},
            DIRECTORY:{'transaction.json':('file',len(p.record))},
            ROOT+'/games':{},ROOT+'/metadata':{},ROOT+'/artwork':{}}
        if phase<5:expected[ROOT]['manifest.json']=('file',len(p.old_manifest))
        if phase==6:expected[ROOT]['manifest.json']=('file',len(p.manifest))
        if phase>=5:expected[ROOT][p.backup.rsplit('/',1)[1]]=('file',len(p.old_manifest))
        if 2<=phase<6:expected[ROOT][p.pending.rsplit('/',1)[1]]=('file',len(p.manifest))
        if phase<3:expected[DIRECTORY]['item-0001.d64']=('file',SIZE)
        else:expected[ROOT+'/games']['C64Robots v1.3.d64']=('file',SIZE)
        if 1<=phase<4:expected[DIRECTORY][p.metadata_pending.rsplit('/',1)[1]]=('file',len(p.metadata))
        if phase>=4:expected[ROOT+'/metadata'][p.metadata_final.rsplit('/',1)[1]]=('file',len(p.metadata))
        evidence=[]
        for path,wanted in expected.items():
            self.check(); self.listings+=1
            require(self.listings<=64,'Publication listing allowance exhausted.')
            actual,entries=self.adapter.list_directory(path,budget=Budget(65536,self.control),allow_fallback=False)
            require(actual==path and len(entries)==len(wanted),'Publication membership changed.')
            seen=set(); rows=[]
            for entry in entries:
                require(entry.name in wanted and entry.name.casefold() not in seen,'Unexpected or colliding member.')
                seen.add(entry.name.casefold());kind,size=wanted[entry.name]
                require(entry.kind==kind and (size is None or entry.size==size),'Publication member type/size changed.')
                rows.append([entry.name,entry.kind,entry.size])
            evidence.append(dict(path=path,entries=rows))
        self.check();self.save('verified-memberships',dict(phase=phase,listings=evidence))

    def preflight(self):
        self.memberships(0)
        self.read(ROOT+'/manifest.json',self.plan.old_manifest)
        self.read(DIRECTORY+'/transaction.json',self.plan.record)
        self.read(self.plan.source,payload=True)
