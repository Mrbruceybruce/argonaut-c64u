# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Bounded standard queries and optional local subnet probing; never sends credentials."""
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import socket
import struct
import subprocess
import time
import uuid
from .api import UltimateClient, ConnectionFailure, BrowserError

@dataclass
class Candidate:
    host: str
    port: int = 80
    source: str = ''
    status: str = 'Unverified advertisement'
    info: dict = field(default_factory=dict)


def dns_name(data, offset):
    seen, labels, end = set(), [], None
    while True:
        if offset in seen or offset >= len(data): raise ValueError('Invalid DNS name')
        seen.add(offset)
        size = data[offset]; offset += 1
        if size & 0xc0 == 0xc0:
            if offset >= len(data): raise ValueError('Truncated DNS pointer')
            target = ((size & 63) << 8) | data[offset]
            end = offset+1 if end is None else end
            offset = target
        elif size == 0: return '.'.join(labels), end or offset
        elif size > 63 or offset+size > len(data): raise ValueError('Invalid DNS label')
        else:
            labels.append(data[offset:offset+size].decode('utf-8', errors='replace')); offset += size


def dns_records(data):
    if len(data) < 12: raise ValueError('Truncated DNS')
    _, flags, questions, answers, authorities, additional = struct.unpack_from('!6H', data)
    if not flags & 0x8000: return []
    offset = 12
    for _ in range(questions):
        _, offset = dns_name(data, offset); offset += 4
    records = []
    for _ in range(answers+authorities+additional):
        name, offset = dns_name(data, offset)
        kind, _, ttl, length = struct.unpack_from('!HHIH', data, offset); offset += 10
        stop = offset+length
        if stop > len(data): raise ValueError('Truncated DNS record')
        if ttl:
            if kind == 1 and length == 4: records.append((name, 'A', socket.inet_ntoa(data[offset:stop])))
            elif kind == 12: records.append((name, 'PTR', dns_name(data, offset)[0]))
            elif kind == 33 and length >= 7:
                records.append((name, 'SRV', (struct.unpack_from('!H', data, offset+4)[0], dns_name(data, offset+6)[0])))
        offset = stop
    return records


def query(sock, name, kind=12):
    q = b''.join(bytes([len(p)])+p.encode() for p in name.split('.'))+b'\0'
    sock.sendto(struct.pack('!6H',0,0,1,0,0,0)+q+struct.pack('!HH',kind,0x8001), ('224.0.0.251',5353))


def ident_scan(seconds=2):
    """Maintainer's json + nonce protocol; one broadcast per connected IPv4 LAN."""
    nonce = 'argo-' + uuid.uuid4().hex[:12]
    candidates = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try: sock.bind(('',64640))
        except OSError as exc:
            raise BrowserError('Discovery reply port 64640 is busy. Close another scan and retry, or use Scan subnet.') from exc
        sock.settimeout(.2)
        networks = [ipaddress.ip_network(n) for n in local_networks()]
        if not networks:raise BrowserError('No connected private IPv4 network found. Check the network connection or connect by IP address.')
        for network in networks:
            sock.sendto(('json'+nonce).encode(), (str(network.broadcast_address), 64))
        sock.sendto(('json'+nonce).encode(), ('255.255.255.255', 64))
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                payload, sender = sock.recvfrom(4096)
                if sender[1] != 64 or not any(ipaddress.ip_address(sender[0]) in n for n in networks): continue
                data = json.loads(payload)
                if not isinstance(data,dict) or data.get('your_string') != nonce: continue
                if not all(isinstance(data.get(k),str) and data[k] for k in ('product','firmware_version','hostname')): continue
                candidates[sender[0],80] = Candidate(sender[0],80,'Ultimate Ident (UDP 64)',info={'ident':data})
            except socket.timeout: pass
            except (ValueError, UnicodeError): continue
    return candidates


def avahi_scan(seconds=3):
    """Use the desktop mDNS daemon, including its normal multicast receive port."""
    from gi.repository import Gio, GLib
    context = GLib.MainContext.new()
    context.push_thread_default()
    connection = None
    subscription = None
    paths, types, candidates = set(), set(), {}
    def call(path, interface, method, signature=None, args=None):
        return connection.call_sync('org.freedesktop.Avahi', path, interface, method,
            GLib.Variant(signature,args) if signature else None, None,
            Gio.DBusCallFlags.NONE, 900, None).unpack()
    def browse(service_type):
        if service_type in types or len(types)>=32: return
        types.add(service_type)
        path = call('/', 'org.freedesktop.Avahi.Server', 'ServiceBrowserNew',
                    '(iissu)',(-1,0,service_type,'local',0))[0]
        paths.add(path)
    def signal(conn, sender, path, interface, member, parameters):
        if path not in paths or member!='ItemNew': return
        values=parameters.unpack()
        try:
            if interface=='org.freedesktop.Avahi.ServiceTypeBrowser':
                service_type=values[2]
                if any(t in service_type.lower() for t in ('http','ftp','ultimate','c64')): browse(service_type)
            elif interface=='org.freedesktop.Avahi.ServiceBrowser':
                index, protocol, name, service_type, domain, flags = values
                reply=call('/', 'org.freedesktop.Avahi.Server', 'ResolveService',
                    '(iisssiu)',(index,protocol,name,service_type,domain,0,0))
                host, port = reply[7], reply[8]
                if service_type != '_http._tcp': port=80
                candidates[host,port]=Candidate(host,port,'mDNS via Avahi: '+name)
        except GLib.Error: pass
    try:
        connection=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
        subscription=connection.signal_subscribe('org.freedesktop.Avahi',None,'ItemNew',None,None,Gio.DBusSignalFlags.NONE,signal)
        browse('_http._tcp');browse('_ftp._tcp')
        path=call('/', 'org.freedesktop.Avahi.Server', 'ServiceTypeBrowserNew','(iisu)',(-1,0,'local',0))[0]
        paths.add(path)
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            context.iteration(False);time.sleep(.01)
        return candidates
    finally:
        if connection:
            if subscription is not None:connection.signal_unsubscribe(subscription)
            for path in paths:
                interface='org.freedesktop.Avahi.ServiceTypeBrowser' if 'ServiceTypeBrowser' in path else 'org.freedesktop.Avahi.ServiceBrowser'
                try:call(path,interface,'Free')
                except Exception:pass
        context.pop_thread_default()


def standard_scan(seconds=5):
    results = ident_scan()
    notes = [f'Ultimate Ident: {len(results)} replies.']
    try:
        advertised=avahi_scan()
        results.update(advertised)
        notes.append(f'Avahi mDNS: {len(advertised)} candidate services.')
    except Exception:
        notes.append('Avahi unavailable; using direct mDNS queries.')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(.2)
        pending = {'_services._dns-sd._udp.local', '_http._tcp.local', '_ftp._tcp.local'}
        for name in pending: query(s, name)
        records = []
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            try:
                data, sender = s.recvfrom(65535)
                new = dns_records(data); records.extend(new)
                for owner, kind, value in new:
                    if kind == 'PTR' and value not in pending and len(pending) < 64:
                        pending.add(value); query(s, value, 33 if owner != '_services._dns-sd._udp.local' else 12)
                    if kind == 'SRV' and value[1] not in pending and len(pending) < 64:
                        pending.add(value[1]); query(s, value[1], 1)
            except socket.timeout: pass
            except (ValueError, struct.error): continue
        addresses = {name: value for name, kind, value in records if kind == 'A'}
        for name, kind, value in records:
            if kind != 'SRV': continue
            port, host = value
            if '_http._tcp.' not in name and '_ftp._tcp.' not in name: continue
            address = addresses.get(host)
            if not address: continue
            http_port = port if '_http._tcp.' in name else 80
            results.setdefault((address, http_port), Candidate(address,http_port,'mDNS: '+name))
        notes.append(f'mDNS: {len(records)} records; {sum(1 for c in results.values() if c.source.startswith("mDNS"))} additional HTTP/FTP candidates.')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(.2)
        s.sendto(b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n', ('239.255.255.250',1900))
        deadline, count = time.monotonic()+3, 0
        while time.monotonic() < deadline:
            try:
                data, sender = s.recvfrom(8192)
                if not data.startswith(b'HTTP/1.1 200'): continue
                count += 1
                results.setdefault((sender[0],80),Candidate(sender[0],80,'SSDP'))
            except socket.timeout: pass
        notes.append(f'SSDP: {count} replies.')
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [r for r in pool.map(verify, results.values()) if r is not None], notes


def verify(candidate):
    try:
        candidate.info = UltimateClient(candidate.host, timeout=.8, http_port=candidate.port).test_connection()
        candidate.status = 'Verified Ultimate · '+candidate.info['info']['firmware_version']
    except ConnectionFailure as exc:
        if exc.kind == 'authentication': candidate.status = 'Password required · identity unverified'
        else: return None
    except (OSError, ValueError, BrowserError): return None
    return candidate


from .local_networks import local_networks


def preferred_subnet(networks, hosts=()):
    """Prefer the selected/discovered device's LAN; do not guess among unrelated LANs."""
    parsed = [ipaddress.ip_network(n) for n in networks]
    for host in hosts:
        try: address = ipaddress.ip_address(host)
        except ValueError: continue
        matches = [n for n in parsed if address in n]
        if matches: return str(max(matches, key=lambda n: n.prefixlen))
    return networks[0] if len(networks) == 1 else ''


def subnet_scan(cidr):
    network = ipaddress.ip_network(cidr, strict=True)
    if network.version != 4 or network.num_addresses > 1024 or not network.is_private:
        raise ValueError('Choose a private IPv4 LAN of /22 or smaller (at most 1024 addresses).')
    if not any(network.subnet_of(ipaddress.ip_network(n)) for n in local_networks()):
        raise ValueError('Choose a subnet on a currently connected local interface.')
    def probe(host):
        try:
            with socket.create_connection((str(host),80), timeout=.25): pass
        except OSError: return None
        return verify(Candidate(str(host),80,'LAN probe'))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [r for r in pool.map(probe, network.hosts()) if r is not None]

if __name__ == '__main__':
    from dataclasses import asdict
    import sys
    candidates, notes = (subnet_scan(sys.argv[1]), ['Explicit local subnet scan']) if len(sys.argv)>1 else standard_scan()
    print(json.dumps({'notes':notes,'candidates':[asdict(c) for c in candidates]},indent=2))
