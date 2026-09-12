# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only configuration model. Values are held in memory, never saved locally."""
from dataclasses import dataclass
import json
import math
from .api import BrowserError

@dataclass(frozen=True)
class Setting:
    name: str
    current: str
    details: str
    choices: tuple = ()
    value_type: type = str
    minimum: object = None
    maximum: object = None
    raw_choices: tuple = ()
    editable: bool = True
    presets: tuple = ()

    def parse(self, text):
        if not self.editable or self.current == 'Hidden':
            raise ValueError('This value is read-only.')
        if self.choices:
            if text not in self.choices: raise ValueError('Choose a listed value.')
            return self.raw_choices[self.choices.index(text)] if self.raw_choices else text
        if self.value_type is str: return text
        if self.value_type is bool:
            if text not in ('true', 'false'): raise ValueError('Use true or false.')
            return text == 'true'
        if self.value_type not in (int, float): raise ValueError('Unsupported value type.')
        try: value=self.value_type(text)
        except (ValueError, OverflowError): raise ValueError('Enter a valid number.') from None
        if isinstance(value,float) and not math.isfinite(value): raise ValueError('Enter a finite number.')
        if self.minimum is not None and value < self.minimum: raise ValueError(f'Minimum is {self.minimum}.')
        if self.maximum is not None and value > self.maximum: raise ValueError(f'Maximum is {self.maximum}.')
        return value


def display(value):
    return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)

WIRED_STATUS_FIELDS = ('Status', 'Active IP address', 'Interface MAC')

# Confirmed read-only in the C64U Spiffy menu; REST omits this metadata.
READ_ONLY_FIELDS = {
    ('SID Sockets Configuration', name)
    for name in ('SID Detected Socket 1', 'SID Detected Socket 2',
                 'SID Socket 1 Capacitors', 'SID Socket 2 Capacitors')
} | {('U64 Specific Settings','C64U Model'),('Network Settings','Current device ID'),('Network Settings','Current network MAC')} | {(category, name) for category in ('Ethernet Settings', 'WiFi settings') for name in WIRED_STATUS_FIELDS}

class Configuration:
    def __init__(self, client): self.client=client

    def categories(self):
        data=self.client.read_configuration()
        categories=data.get('categories')
        if not isinstance(categories,list) or not all(isinstance(c,str) and c for c in categories):
            raise BrowserError('Device returned an invalid configuration category list.')
        return list(dict.fromkeys(categories))

    def settings(self, category):
        data=self.client.read_configuration(category)
        items=data.get(category)
        if not isinstance(items,dict):
            raise BrowserError('Device did not return the requested configuration category.')
        rows=[]
        for name,metadata in items.items():
            if not isinstance(metadata,dict) or 'current' not in metadata:
                rows.append(Setting(name,'Unavailable','Read-only · This firmware returned unfamiliar setting metadata.',editable=False));continue
            # Some network categories contain credentials. Do not expose their values/defaults.
            if any(word in name.casefold() for word in ('password','secret','passphrase','credential')):
                rows.append(Setting(name,'Hidden','Sensitive value',editable=False));continue
            detail=[]
            for key,label in [('default','Default'),('values','Allowed values'),('options','Options'),('min','Minimum'),('max','Maximum'),('format','Format')]:
                if key in metadata: detail.append(label+': '+display(metadata[key]))
            choices = metadata.get('values', metadata.get('options', ()))
            valid_choices=isinstance(choices,(list,tuple)) and all(isinstance(v,(str,int,float,bool)) for v in choices)
            if not valid_choices:choices=()
            presets=metadata.get('presets',())
            if not isinstance(presets,(list,tuple)) or not all(isinstance(v,str) for v in presets):presets=()
            kind=type(metadata['current'])
            numeric=lambda key: metadata.get(key) if type(metadata.get(key)) in (int,float) else None
            editable=valid_choices and kind in (str,int,float,bool) and not metadata.get('read_only',metadata.get('readonly',False)) and (category,name) not in READ_ONLY_FIELDS
            if not editable:detail.insert(0,'Read-only')
            rows.append(Setting(name,display(metadata['current']),' · '.join(detail),tuple(display(v) for v in choices),
                                kind,numeric('min'),numeric('max'),tuple(choices),editable,tuple(presets)))
        if category == 'Network Settings':
            response=self.client.test_connection()
            info=response.get('info',{})
            value=info.get('unique_id')
            rows=[row for row in rows if row.name not in ('Current device ID','Current network MAC')]
            rows.append(Setting('Current device ID',value if isinstance(value,str) and value and value not in ('Default','None') else 'Not reported','Read-only · Reported by the connected device.',editable=False))
            mac=response.get('network_mac')
            rows.append(Setting('Current network MAC',mac if isinstance(mac,str) and mac else 'Not available','Read-only · Local-network identity for this connection; Ethernet and Wi-Fi have separate addresses.',editable=False))
        return rows

    def all_settings(self, categories):
        return {category: self.settings(category) for category in categories}
