# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""User storage roots, separate from internal Flash management."""
import re

def storage_root(path):
 parts=path.split('/')
 if len(parts)<2 or not re.fullmatch(r'USB[0-9]+|SD',parts[1]):return None
 if any(p in ('.','..','') for p in parts[1:]):return None
 return '/'+parts[1]

def discover(client):
 _,entries=client.list_directory('/')
 roots=sorted('/'+e.name for e in entries if e.kind=='dir' and re.fullmatch(r'USB[0-9]+|SD',e.name))
 client.storage_roots=roots
 return roots

def initial_directory(client,preferred='/USB2'):
 roots=discover(client)
 target=preferred if preferred in roots else next(iter(roots),None)
 return client.list_directory(target) if target else ('/',[])
