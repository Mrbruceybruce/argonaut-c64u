# SPDX-License-Identifier: GPL-3.0-or-later
"""Enumerate connected IPv4 LANs with native, bounded read-only commands."""
import ipaddress
import json
import os
import re
import subprocess
import sys
from .api import BrowserError


def network(address,mask):
    interface=ipaddress.ip_interface(f'{address}/{mask}')
    ip=interface.ip
    if ip.version==4 and ip.is_private and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):
        return str(interface.network)


def parse_linux(data):
    rows=json.loads(data)
    return sorted({n for row in rows if row.get('ifname')!='lo'
                   for addr in row.get('addr_info',[]) if addr.get('scope')=='global'
                   if (n:=network(addr['local'],addr['prefixlen']))})


def parse_windows(data):
    if not data.strip():return []
    rows=json.loads(data.lstrip('\ufeff'))
    if rows is None:rows=[]
    if isinstance(rows,dict):rows=[rows]
    return sorted({n for row in rows if (n:=network(row['IPAddress'],row['PrefixLength']))})


def parse_macos(data):
    result=set()
    for block in re.split(r'(?=^\S[^\n]*: flags=)',data,flags=re.M):
        header=block.splitlines()[0] if block else ''
        flags=re.search(r'<([^>]+)>',header)
        if not flags or not {'UP','RUNNING'}.issubset(flags[1].split(',')):continue
        if 'LOOPBACK' in flags[1].split(',') or re.search(r'status:\s+inactive',block):continue
        for address,mask in re.findall(r'^\s+inet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(\S+)',block,re.M):
            if mask.startswith('0x'):mask=str(ipaddress.IPv4Address(int(mask,16)))
            n=network(address,mask)
            if n:result.add(n)
    return sorted(result)


def local_networks():
    try:
        options=dict(timeout=10,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        if sys.platform=='darwin':
            return parse_macos(subprocess.check_output(['/sbin/ifconfig','-a'],**options))
        if sys.platform=='win32':
            powershell=os.path.join(os.environ.get('SystemRoot',r'C:\Windows'),'System32','WindowsPowerShell','v1.0','powershell.exe')
            script="""$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $connected=@(Get-NetIPInterface -AddressFamily IPv4 | Where-Object ConnectionState -eq 'Connected' | Select-Object -ExpandProperty InterfaceIndex); @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceIndex -in $connected -and $_.AddressState -eq 'Preferred' } | Select-Object IPAddress,PrefixLength) | ConvertTo-Json -Compress"""
            return parse_windows(subprocess.check_output([powershell,'-NoLogo','-NoProfile','-NonInteractive','-Command',script],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**options))
        return parse_linux(subprocess.check_output(['ip','-j','-4','address','show','up'],**options))
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        raise BrowserError('Could not read this computer’s local IPv4 networks. Connect by IP address; discovery cannot verify the local network.') from exc
