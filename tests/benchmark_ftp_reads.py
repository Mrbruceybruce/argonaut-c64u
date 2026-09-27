"""Reproducible loopback-only old/new read workload. No hardware or writes.

Run: PYTHONPATH=tests python3 -B tests/benchmark_ftp_reads.py --repeats 5
Both sides use identical fixtures and the unchanged volume digest algorithm.
Legacy UltimateClient/read_remote branches are the retained Slice 1 code.
"""
import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from c64u_ftp_server import FakeC64UFtp
from c64u_browser.api import UltimateClient
from c64u_browser.c64u_ftp import C64UFtpLeaseManager
from c64u_browser.c64u_ftp_types import ConnectionBinding, DeviceIdentity
from c64u_browser.ftp_reads import FtpReadAdapter
from c64u_browser.native_files import read_remote
from c64u_browser.usb_backup import UsbBackupService


def fixtures():
    def tree(count, files_per_dir, *, nested=False, raw=False, mixed=False):
        dirs={b'/USB1':[]};files={};parent=b'/USB1'
        for index in range(count):
            name=f'dir-{index:03d}'.encode()
            path=parent+b'/'+name
            dirs[parent].append(b'type=dir; '+name+b'\r\n');dirs[path]=[]
            for number in range(files_per_dir):
                extension=(b'.d64',b'.crt',b'.sid',b'.txt')[number%4] if mixed else b'.bin'
                leaf=(b'Schatzj\x84ger-' if raw else b'file-')+f'{number:03d}'.encode()+extension
                data=bytes((index%256,number%256,0,255))*128+b'!'
                files[path+b'/'+leaf]=data
                dirs[path].append(b'type=file;size='+str(len(data)).encode()+b'; '+leaf+b'\r\n')
            if nested:parent=path
        return {p:b''.join(rows) for p,rows in dirs.items()},files
    return {
        'many-small-files':tree(16,100),
        'nested-directories':tree(24,3,nested=True),
        'mixed-game-sid':tree(32,12,mixed=True),
        'non-utf8-identities':tree(8,16,raw=True),
    }


def measure(directories,files,new):
    with FakeC64UFtp(directories=directories,files=files) as server:
        client=UltimateClient('127.0.0.1',port=server.port,encoding='latin-1')
        if new:
            binding=ConnectionBinding(DeviceIdentity('benchmark-fixture'), 'benchmark-session',
                                      '127.0.0.1',server.port)
            manager=C64UFtpLeaseManager(lambda _:binding,lambda _:'')
            client._ftp_reads=FtpReadAdapter(manager,binding,encoding='latin-1')
        start=time.perf_counter()
        digest=UsbBackupService._volume_fingerprint(client,'/USB1')
        fingerprint_ms=(time.perf_counter()-start)*1000
        fingerprint_connections=server.connections
        start_read=time.perf_counter()
        for path,data in list(sorted(files.items()))[:4]:
            result=read_remote(client,path.decode('latin-1'),len(data))
            if result!=data:raise AssertionError('Read content changed')
        end=time.perf_counter()
        counts=Counter(server.verbs)
        return dict(total_ms=(end-start)*1000,fingerprint_ms=fingerprint_ms,
                    reads_ms=(end-start_read)*1000,control_connections=server.connections,
                    fingerprint_connections=fingerprint_connections,
                    authentications=counts[b'PASS'],feat=counts[b'FEAT'],
                    listings=counts[b'MLSD']+counts[b'LIST'],size=counts[b'SIZE'],
                    retr=counts[b'RETR'],bytes_transferred=server.bytes_transferred,
                    files=len(files),directories=len(directories),fingerprint=digest)


def benchmark(repeats):
    report={}
    for name,(directories,files) in fixtures().items():
        rows={'legacy':[],'slice2':[]}
        for trial in range(repeats):
            for key in (('legacy','slice2') if trial%2==0 else ('slice2','legacy')):
                rows[key].append(measure(directories,files,key=='slice2'))
        fingerprints={row['fingerprint'] for values in rows.values() for row in values}
        if len(fingerprints)!=1:raise AssertionError('Fingerprint differs')
        medians={}
        for key,values in rows.items():
            medians[key]={field:statistics.median(row[field] for row in values)
                          for field in values[0] if field!='fingerprint'}
        report[name]={'median':medians,'samples':rows,
                      'total_percent_change':100*(medians['slice2']['total_ms']/medians['legacy']['total_ms']-1),
                      'fingerprint_percent_change':100*(medians['slice2']['fingerprint_ms']/medians['legacy']['fingerprint_ms']-1)}
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repeats',type=int,default=5)
    args=parser.parse_args()
    if not 1<=args.repeats<=20:parser.error('Choose 1–20 repetitions')
    print(json.dumps(benchmark(args.repeats),indent=2))
