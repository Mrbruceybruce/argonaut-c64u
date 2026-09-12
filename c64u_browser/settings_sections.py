# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Presentation mapping based on the user's Spiffy menu and live REST names.

Keep original (category, item) identities: these labels never become API paths.
"""
from .configuration import WIRED_STATUS_FIELDS
from .dependencies import NETWORK_CATEGORIES

SECTIONS = (
    'Memory & ROMs', 'Turbo Boost', 'Video Setup', 'Audio Setup',
    'Joystick & Controllers', 'LED Lighting', 'Network Services & Timezone',
    'Wired Network Setup', 'WiFi Network Setup', 'Modems', 'Printers',
    'User Interface', 'Built-in Drive A', 'Built-in Drive B',
    'Disk & Tape', 'System Information', 'Additional Settings',
)

CATEGORY_SECTIONS = {
    'C64 and Cartridge Settings': 'Memory & ROMs',
    'Audio Mixer': 'Audio Setup', 'Speaker Mixer': 'Audio Setup',
    'SID Sockets Configuration': 'Audio Setup', 'UltiSID Configuration': 'Audio Setup',
    'SID Addressing': 'Audio Setup', 'ARMSID in Socket 1': 'Audio Setup',
    'ARMSID in Socket 2': 'Audio Setup', 'LED Strip Settings': 'LED Lighting',
    'Keyboard Lighting': 'LED Lighting', 'Network Settings': 'Network Services & Timezone',
    'Ethernet Settings': 'Wired Network Setup', 'WiFi settings': 'WiFi Network Setup',
    'Modem Settings': 'Modems', 'Printer Settings': 'Printers',
    'User Interface Settings': 'User Interface', 'Drive A Settings': 'Built-in Drive A',
    'Drive B Settings': 'Built-in Drive B', 'SoftIEC Drive Settings': 'Disk & Tape',
    'Tape Settings': 'Disk & Tape',
}

ITEM_SECTIONS = {
    ('U64 Specific Settings', name): section
    for section, names in (
        ('Turbo Boost', ('Turbo Control', 'CPU Speed', 'Badline Timing', 'SuperCPU Detect (D0BC)')),
        ('Video Setup', ('System Mode', 'HDMI Tx Swing', 'HDMI Scan Resolution',
                         'Palette Definition', 'Adjust Color Clock', 'Analog Video Mode',
                         'Digital Video Mode', 'HDMI Scan lines')),
        ('Joystick & Controllers', ('Joystick Swapper',)),
        ('LED Lighting', ('LED Select Top', 'LED Select Bot')),
        ('Audio Setup', ('SID Player Autoconfig', 'Allow Autoconfig uses UltiSid')),
        ('Disk & Tape', ('Serial Bus Mode', 'SpeedDOS Parallel Cable', 'Burst Mode Patch')),
        ('System Information', ('C64U Model',)),
    ) for name in names
}
ITEM_SECTIONS.update({
    ('SID Addressing', 'Paddle Override'): 'Joystick & Controllers',
    ('C64 and Cartridge Settings', 'Map Ultimate Audio $DF20-DFFF'): 'Memory & ROMs',
    ('C64 and Cartridge Settings', 'DMA Load Mimics ID:'): 'Network Services & Timezone',
    ('C64 and Cartridge Settings', 'Command Interface'): 'Memory & ROMs',
    ('Data Streams', 'Stream VIC to'): 'Video Setup',
    ('Data Streams', 'Stream Audio to'): 'Audio Setup',
    ('Data Streams', 'Stream Debug to'): 'Network Services & Timezone',
    ('Data Streams', 'Debug Stream Mode'): 'Network Services & Timezone',
})

def section_for(category, name):
    return ITEM_SECTIONS.get((category, name), CATEGORY_SECTIONS.get(category, 'Additional Settings'))

def section_entries(settings):
    groups = {section: [] for section in SECTIONS}
    for category, rows in settings.items():
        for item in rows:
            if category in NETWORK_CATEGORIES and item.name in WIRED_STATUS_FIELDS:
                continue
            groups[section_for(category, item.name)].append((category, item))
            if (category,item.name)==('SID Addressing','Paddle Override'):
                groups['Audio Setup'].append((category,item))
            if category in ('Drive A Settings', 'Drive B Settings') and item.name.startswith('ROM for '):
                groups['Memory & ROMs'].append((category, item))
    for section, rows in groups.items():
        rows.sort(key=lambda entry: presentation_order(section, *entry))
    return {section: rows for section, rows in groups.items() if rows}

def visible_entries(settings, section, query='', favorites=None):
    query = query.casefold().strip()
    result = []
    seen = set()
    for label, rows in section_entries(settings).items():
        if not query and favorites is None and label != section:
            continue
        for category, item in rows:
            if favorites is not None and (category, item.name) not in favorites:
                continue
            if query and query not in f'{label} {category} {item.name} {display_name(category, item.name)} {item.current}'.casefold():
                continue
            if (category, item.name) in seen:
                continue
            seen.add((category, item.name))
            result.append((category, item))
    return result

DISPLAY_NAMES = {
    ('C64 and Cartridge Settings', 'Basic ROM'): 'BASIC ROM',
    ('C64 and Cartridge Settings', 'Char ROM'): 'Character ROM',
    ('C64 and Cartridge Settings', 'REU Size'): 'Size',
    ('U64 Specific Settings', 'Joystick Swapper'): 'Joystick Input',
    ('U64 Specific Settings', 'LED Select Top'): 'Output 1',
    ('U64 Specific Settings', 'LED Select Bot'): 'Output 2',
    ('C64 and Cartridge Settings', 'Map Ultimate Audio $DF20-DFFF'): 'Ultimate Audio',
}
for category in ('LED Strip Settings', 'Keyboard Lighting'):
    for source, label in (('LedStrip Mode', 'Mode'), ('LedStrip Auto SID Mode', 'Music Detect'),
                          ('LedStrip Pattern', 'Pattern'), ('Strip Intensity', 'Brightness'),
                          ('Fixed Color', 'Color'), ('Color tint', 'Tint')):
        DISPLAY_NAMES[(category, source)] = label

def display_name(category, name):
    return DISPLAY_NAMES.get((category, name), name)

def subsection_for(section, category, name):
    if category in ('Ethernet Settings', 'WiFi settings') and name in ('Status', 'Active IP address', 'Interface MAC'): return 'Status'
    if name == 'C64U Model': return 'Status'
    if section == 'Memory & ROMs' and category == 'C64 and Cartridge Settings':
        if name in ('Kernal ROM', 'Basic ROM', 'Char ROM', 'Cartridge', 'RAM Expansion Unit', 'REU Size', 'Command Interface', 'Map Ultimate Audio $DF20-DFFF'): return 'Settings'
        return 'Advanced'
    if category == 'Data Streams': return 'Stream settings'
    if category in ('Drive A Settings', 'Drive B Settings'):
        if section == 'Memory & ROMs': return category.replace(' Settings', '')
        if name.startswith('ROM for '): return 'ROMs'
        return 'Drive' if name in ('Drive', 'Drive Type', 'Drive Bus ID') else 'Advanced'
    if section == 'Audio Setup':
        return 'SID Player Behavior' if category == 'U64 Specific Settings' else category
    if section == 'LED Lighting':
        return {'U64 Specific Settings': 'Power LED', 'LED Strip Settings': 'LED Strip (if installed)'}.get(category, category)
    if category == 'Network Settings':
        if name in ('Host Name', 'Unique ID', 'Current device ID', 'Current network MAC', 'Network Password'): return 'Identity'
        if name.startswith(('Time', 'SNTP')): return 'Time Synchronization'
        return 'Services'
    if category == 'Modem Settings':
        if name.startswith('Modem ') and name.endswith(' Text'): return 'Automated Responses'
        if name in ('Set Socket Opt TCP_NODELAY', 'Loop Delay'): return 'Tweaks'
        if name in ('Modem Interface', 'ACIA (6551) Mapping', 'Hardware Mode', 'Listening Port'): return 'Interface'
        return 'Handshaking'
    if section == 'Video Setup' and name in ('HDMI Tx Swing', 'Adjust Color Clock'): return 'Advanced'
    return 'Settings'

SUBSECTION_ORDER = {
    'Wired Network Setup': ('Settings', 'Status'),
    'Memory & ROMs': ('Settings', 'Drive A', 'Drive B', 'Advanced'),
    'Audio Setup': ('Audio Mixer', 'Speaker Mixer', 'SID Sockets Configuration', 'UltiSID Configuration', 'SID Addressing', 'SID Player Behavior'),
    'LED Lighting': ('Power LED', 'LED Strip (if installed)', 'Keyboard Lighting'),
    'Network Services & Timezone': ('Identity', 'Services', 'Time Synchronization', 'Settings'),
    'Modems': ('Interface', 'Handshaking', 'Automated Responses', 'Tweaks'),
    'Built-in Drive A': ('Drive', 'ROMs', 'Advanced'),
    'Built-in Drive B': ('Drive', 'ROMs', 'Advanced'),
}
ITEM_ORDER = {
    'Memory & ROMs': ('Kernal ROM', 'Basic ROM', 'Char ROM', 'Cartridge', 'RAM Expansion Unit', 'REU Size', 'Command Interface', 'Map Ultimate Audio $DF20-DFFF'),
    'Turbo Boost': ('Turbo Control', 'CPU Speed', 'Badline Timing', 'SuperCPU Detect (D0BC)'),
    'Video Setup': ('System Mode', 'HDMI Scan Resolution', 'HDMI Scan lines', 'Palette Definition', 'Analog Video Mode', 'Digital Video Mode'),
    'Joystick & Controllers': ('Joystick Swapper', 'Paddle Override'),
}

def presentation_order(section, category, item):
    groups = SUBSECTION_ORDER.get(section, ('Settings', 'Advanced', 'Stream settings'))
    group = subsection_for(section, category, item.name)
    names = ITEM_ORDER.get(section, ())
    return (groups.index(group) if group in groups else len(groups),
            group if group not in groups else '',
            names.index(item.name) if item.name in names else len(names))
