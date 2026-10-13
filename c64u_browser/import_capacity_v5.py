# SPDX-License-Identifier: GPL-3.0-or-later
"""Branch-aware schema-5 envelope. Raw failure evidence is never discarded."""
import json
from dataclasses import fields
from .import_transaction import canonical, require
from .import_execution import ExecutionOperation, ExecutionAccounting, initial_journal
from .import_mkd_proof import maximum_document, destination
from .import_capacity import planned_operations, EvidenceCapacity

def encoded(d):return (json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def size(d):return len(encoded(d))

def observation(verb, failure=False):
    # Longest independently allowed scalar encodings, even if not co-reachable.
    return dict(command_hex=(b'CWD /\r\n' if verb=='CWD' else b'PWD\r\n').hex(),
        path_hex='2f' if verb=='CWD' else None,
        transport_outcome='not-started', submission='not-attempted', reply_code=None,
        reply_wire_hex='f'*(2*(16384 if failure else 4098)),
        reply_octets_observed=16385, reply_octets_retained=16384, availability='unavailable',
        parsed_directory_hex=('f'*8192 if failure else '2f') if verb=='PWD' else None,
        completion='wrong-directory', binding_before=False,binding_after=False)

def context(t, mode):
    d=dict(transaction_id=t.id,operation_id='f'*36,encoding='latin-1',
        destination_hex='f'*(2*len(destination(t,'utf-8'))),
        core_session_id=t.session_id,device_id=t.library.device_id,
        ftp_session_id='f'*32,adapter_owner_id='f'*32,
        physical_id='\\'*128,product='\\'*128,firmware='\\'*128,api_version='\\'*128,
        provenance='unavailable',cwd=observation('CWD',mode=='cwd-failure'),
        pwd=None if mode=='cwd-failure' else observation('PWD',mode=='pwd-failure'),
        mkd_lease_id='f'*32,mkd_owner_valid=False)
    return d

def envelope(t, mode='success'):
    plan=planned_operations(t)
    d=canonical(initial_journal(t))
    d['schema_version']=5;d['transaction']['execution_policy_version']=4
    d.update(state='awaiting-confirmation',reason='x'*256,revision=519,
             previous_digest='f'*64,checkpoint=len(plan),operations=[])
    for n,(kind,path) in enumerate(plan,1):
        op=canonical(ExecutionOperation('f'*36,n,kind,path))
        op.update(outcome='not-started',size=2**63-1,sha256='f'*64,
            collision='not-applicable',accounting={k:2**63-1 for k in canonical(ExecutionAccounting())},
            mkd_proof=None,context=None,context_phase=None)
        if kind=='mkdir':
            op['context']=context(t,mode)
            op['context_phase']='context-intent'
            if mode not in ('cwd-failure','pwd-failure'):
                op['mkd_proof']=maximum_document(t)
                if mode=='success':op['mkd_proof']['reply_lines_hex']=['f'*8192]
        d['operations'].append(op)
    return d

def bound(t):
    vals={m:size(envelope(t,m)) for m in ('success','cwd-failure','pwd-failure','mkd-failure')}
    S=vals['success'];F=max(vals.values());R=2*len(planned_operations(t))+9
    return dict(envelopes=vals,S=S,F=F,R=R,reservation=(R-1)*S+F,
        successful_history_upper=(R-1)*S,
        failure_history_upper=(R-1)*S+F,
        context_sizes={m:size(context(t,m))-1 for m in ('success','cwd-failure','pwd-failure')})


def reserve(tx):
    from .import_execution_v4 import ExecutionTransactionV4
    from .import_execution import ExecutionTransaction
    from .import_capacity import reserve_capacity
    tx.validate()
    # Sizing-only historical admission floor, never persisted or dispatched.
    old = ExecutionTransactionV4(**{f.name: 3 if f.name == 'execution_policy_version' else getattr(tx, f.name)
                                   for f in fields(ExecutionTransaction)})
    reserve_capacity(old)
    b = bound(tx)
    require(len(planned_operations(tx)) <= tx.budgets.operations and b['reservation'] <= tx.budgets.journal_bytes,
            'Insufficient schema-5 aggregate journal evidence capacity.')
    return EvidenceCapacity(b['F'], b['R'], b['reservation'], b['S'])
