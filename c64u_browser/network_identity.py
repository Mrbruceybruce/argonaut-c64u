# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Best-effort identity for a directly connected IPv4 network peer on Linux."""
import ipaddress
import json
import re
import socket
import subprocess

def peer_mac(host):
    try:
        address=str(ipaddress.IPv4Address(socket.gethostbyname(host)))
        def read(*args):
            return json.loads(subprocess.check_output(['/usr/bin/ip','-j',*args],stderr=subprocess.DEVNULL,timeout=2,text=True))
        routes=read('route','get',address)
        if len(routes)!=1 or routes[0].get('gateway') or routes[0].get('type') in ('local','unreachable','blackhole'):return ''
        device=routes[0].get('dev')
        if not device:return ''
        peers=read('neigh','show','to',address,'dev',device)
        matches=[]
        for peer in peers:
            mac=peer.get('lladdr','').lower()
            if peer.get('dst')!=address or peer.get('dev',device)!=device:continue
            if not set(peer.get('state',[])) & {'REACHABLE','STALE','DELAY','PROBE','PERMANENT'}:continue
            if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',mac):continue
            if mac=='00:00:00:00:00:00' or int(mac[:2],16)&1:continue
            matches.append(mac)
        return matches[0] if len(matches)==1 else ''
    except (OSError,ValueError,subprocess.SubprocessError):return ''
