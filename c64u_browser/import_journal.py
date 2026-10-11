# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, private host journals. Remote record publication is not implemented."""
from contextlib import contextmanager
from dataclasses import fields
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from .import_transaction import (Budgets, Journal, MAX_JOURNAL_BYTES, MAX_RECOVERY_JOURNALS, OperationEvidence,
    Transaction, TransactionError, TransactionItem, canonical, require, MAX_DEPTH)
from .managed_library import LibraryIdentity, uuid_text
from .picker_model import PickerSelection


def encode(journal):
    require(type(journal) is Journal, 'Expected transaction journal.');journal.validate()
    # Each scalar and collection is already bounded; iterencode avoids a full
    # JSON string. Never append beyond the captured byte allowance.
    limit=journal.transaction.budgets.journal_bytes
    data=bytearray()
    encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    for chunk in encoder.iterencode(canonical(journal)):
        block=chunk.encode('utf-8', errors='strict')
        require(len(block)<=limit-len(data)-1, 'Journal size exceeded.')
        data.extend(block)
    data.extend(b'\n')
    return bytes(data)


def _check_depth(data):
    # Bound nesting before json.loads allocates nested containers. Structural
    # bytes inside quoted UTF-8 strings are ignored; syntax is checked by JSON.
    depth=0;quoted=False;escaped=False
    for c in data:
        if quoted:
            if escaped:escaped=False
            elif c==92:escaped=True
            elif c==34:quoted=False
        elif c==34:quoted=True
        elif c in (91,123):
            depth+=1;require(depth<=MAX_DEPTH, 'Journal nesting limit exceeded.')
        elif c in (93,125):depth-=1



def _object(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate journal field.');result[key]=value
    return result


def _fields(value,kind):
    require(type(value) is dict and set(value)=={f.name for f in fields(kind)},'Unknown/missing journal fields.')
    return dict(value)


def decode(data):
    require(type(data) is bytes and 0<len(data)<=MAX_JOURNAL_BYTES,'Invalid journal size.')
    _check_depth(data)
    try:
        raw=_fields(json.loads(data.decode('utf-8'),object_pairs_hook=_object),Journal)
        tx=_fields(raw['transaction'],Transaction)
        tx['library']=LibraryIdentity(**_fields(tx['library'],LibraryIdentity))
        tx['budgets']=Budgets(**_fields(tx['budgets'],Budgets));tx['budgets'].validate()
        require(type(tx['items']) is list and len(tx['items'])<=tx['budgets'].files,'Invalid item count.')
        items=[]
        for value in tx['items']:
            item=_fields(value,TransactionItem)
            item['source']=PickerSelection(**_fields(item['source'],PickerSelection))
            require(type(item['local_identity']) is list,'Invalid source identity.')
            item['local_identity']=tuple(item['local_identity']);items.append(TransactionItem(**item))
        tx['items']=tuple(items);raw['transaction']=Transaction(**tx)
        require(type(raw['operations']) is list and len(raw['operations'])<=tx['budgets'].operations,'Invalid evidence count.')
        raw['operations']=tuple(OperationEvidence(**_fields(o,OperationEvidence)) for o in raw['operations'])
        result=Journal(**raw).validate()
        require(len(data)<=result.transaction.budgets.journal_bytes,'Journal size exceeded.')
        return result
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError) as exc:
        raise TransactionError('Invalid or corrupt transaction journal.') from exc


class JournalStore:
    """Caller-provided existing private directory; no default or startup side effects.

    Advisory host lock serializes cooperating writers. Returned False from save
    means directory fsync is unsupported; any other fsync error is raised and
    the caller must stop, inspect and never infer the old version survived.
    """
    def __init__(self,directory):self.directory=Path(directory)

    @contextmanager
    def _locked(self):
        directory=os.open(self.directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        lock=None
        try:
            info=os.fstat(directory)
            require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)&0o077==0,
                    'Journal directory must be private and owned by this user.')
            lock=os.open('journal.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=directory)
            info=os.fstat(lock)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and
                    stat.S_IMODE(info.st_mode)&0o077==0,'Unsafe journal lock.')
            fcntl.flock(lock,fcntl.LOCK_EX)
            yield directory
        finally:
            if lock is not None:os.close(lock)
            os.close(directory)

    @staticmethod
    def _name(transaction_id):
        uuid_text(transaction_id)
        return transaction_id+'.json'

    @staticmethod
    def _read(directory,name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and
                    stat.S_IMODE(info.st_mode)&0o077==0,'Unsafe journal file.')
            require(info.st_size<=MAX_JOURNAL_BYTES,'Journal size exceeded.')
            return decode(stream.read(MAX_JOURNAL_BYTES+1))

    def load(self,transaction_id):
        name=self._name(transaction_id)
        with self._locked() as directory:result=self._read(directory,name)
        require(result.transaction.id==transaction_id,'Journal filename identity mismatch.')
        # Loading is inspection only: no retry, cleanup or session rebinding.
        return result

    def save(self,journal,*,previous=None):
        data=encode(journal);name=self._name(journal.transaction.id)
        if previous is not None:
            previous.validate()
            require(previous.transaction==journal.transaction,'Cannot replace another transaction.')
            require(journal!=previous,'No checkpoint change.')
            # Only pre-execution state changes can be saved in 3B-1. Loaded
            # recovery observations cannot be advanced or turned into authority.
            require(journal==previous.transition(journal.state,reason=journal.reason),
                    'Journal update is not an available pre-execution transition.')
        else:require(journal==Journal(journal.transaction),'Initial journal must be prepared.')
        temporary='journal-write-'+uuid4().hex
        with self._locked() as directory:
            try:current=self._read(directory,name)
            except FileNotFoundError:current=None
            require(current==previous,'Existing or changed journal; refusing overwrite.')
            if current is None:
                require(sum(n.endswith('.json') for n in os.listdir(directory))<MAX_RECOVERY_JOURNALS,
                        'Recovery journal count exceeded; explicit review required.')
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            primary=None
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,name,src_dir_fd=directory,dst_dir_fd=directory)
                try:os.fsync(directory)
                except OSError as exc:
                    if exc.errno in (errno.EINVAL,errno.ENOTSUP):return False
                    raise
                return True
            except BaseException as exc:
                primary=exc
                raise
            finally:
                try:os.unlink(temporary,dir_fd=directory)
                except FileNotFoundError:pass
                except OSError:
                    if primary is None:raise
                    primary.add_note('Host journal temporary cleanup also failed; preserve the primary outcome.')
