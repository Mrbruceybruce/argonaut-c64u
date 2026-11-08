# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Pure, read-only LED snapshot presentation. Never an admission policy.

Evidence must be explicitly qualified for the snapshot's device/build. Product,
model, version strings and REST store presence cannot supply that qualification.
The settings UI currently supplies no such evidence and uses the neutral view.
"""
from dataclasses import dataclass

SOURCE_REVISION = '7b628eb166872965ea59d66f90ffd9bcf7d71d8a'
CATEGORIES = ('LED Strip Settings', 'Keyboard Lighting')
POWER = 'U64 Specific Settings'
POWER_FIELDS = (('LED Select Top', 'Output 1'), ('LED Select Bot', 'Output 2'))
FIELDS = (('LedStrip Mode', 'Mode'), ('LedStrip Auto SID Mode', 'Music Detect'),
          ('LedStrip Pattern', 'Pattern'), ('Strip Intensity', 'Brightness'),
          ('Fixed Color', 'Color'), ('Color tint', 'Tint'))
READ_ONLY = 'Read-only — safety qualification pending'
UNKNOWN = 'Native availability unknown'
MODES = ('Off', 'Fixed Color', 'SID Music', 'Rainbow', 'Rainbow Sparkle', 'Default')
PATTERNS = {
    CATEGORIES[0]: ('SingleColor', 'Left to Right', 'Right to Left', 'Serpentine', 'Outward'),
    CATEGORIES[1]: ('Single Color', 'Left to Right', 'Right to Left', 'Outward', 'Circular'),
}
# Pattern, Brightness, Color, Tint; pinned update_menu, not write permissions.
MODE_FLAGS = {'Off': (False, False, False, False),
              'Default': (False, True, False, False),
              'Fixed Color': (False, True, True, True),
              'SID Music': (True, True, False, False),
              'Rainbow': (True, True, False, True),
              'Rainbow Sparkle': (True, True, False, True),
              'Sparkle': (False, True, False, False)}


@dataclass(frozen=True)
class Evidence:
    value: object
    source: str
    device: str
    build: str
    observed_at: str = ''
    current: bool = True
    conflicting: bool = False

    def applies(self, scope):
        return bool(scope and all(scope) and self.source and self.current
                    and not self.conflicting and (self.device, self.build) == scope)

    def describe(self):
        return (f'{self.source}; device={self.device}; build={self.build}; '
                f'observed={self.observed_at or "not recorded"}; value={self.value}; '
                f'current={self.current}; conflicting={self.conflicting}')


@dataclass(frozen=True)
class Row:
    category: str
    name: str
    label: str
    setting: object
    availability: str

    @property
    def value(self):
        return self.setting.current if self.setting is not None else 'Not reported'


@dataclass(frozen=True)
class Group:
    heading: str
    rows: tuple


@dataclass(frozen=True)
class Presentation:
    layout: str
    groups: tuple
    provenance: tuple


def is_led(category, name):
    return category in CATEGORIES or (category == POWER and name in dict(POWER_FIELDS))


def _metadata_matches(category, rows):
    """Fail neutral for unfamiliar/missing metadata; never synthesize defaults."""
    vocabularies = {
        'LedStrip Mode': MODES + (('Sparkle',) if category == CATEGORIES[0] else ()),
        'LedStrip Auto SID Mode': ('Disabled', 'Enabled'),
        'LedStrip Pattern': PATTERNS[category],
        'Color tint': ('Pure', 'Bright', 'Pastel', 'Whisper'),
        'Fixed Color': ('Red', 'Scarlet', 'Orange', 'Amber', 'Yellow', 'Lemon-Lime',
                        'Chartreuse', 'Lime', 'Green', 'Jade', 'Spring Green', 'Aquamarine',
                        'Cyan', 'Deep Sky Blue', 'Azure', 'Royal Blue', 'Blue', 'Indigo',
                        'Violet', 'Purple', 'Magenta', 'Fuchsia', 'Rose', 'Cerise', 'White'),
    }
    for name, allowed in vocabularies.items():
        item = rows.get(name)
        if (item is None or not item.choices or item.current not in item.choices
                or not set(item.choices).issubset(allowed)
                or len(set(item.choices)) != len(item.choices)):
            return False
    intensity = rows.get('Strip Intensity')
    color = rows.get('Fixed Color')
    if (intensity is None or intensity.value_type is not int
            or intensity.minimum != 0 or intensity.maximum != 31
            or color is None or not color.choices or color.current not in color.choices):
        return False
    try:
        return 0 <= int(intensity.current) <= 31
    except (TypeError, ValueError):
        return False


def present_led(settings, *, scope=None, firmware=None, controller=None, installed=()):
    """Map existing Settings only; scope is (device, installed-build identity).

    firmware.value must be the qualified source revision, not a version label.
    controller.value is explicitly detected True/False, never a model-derived bit.
    installed evidence is attributed separately and never changes layout/status.
    """
    qualified = bool(firmware and firmware.applies(scope)
                     and firmware.value == SOURCE_REVISION)
    detection = (controller.value if qualified and controller and controller.applies(scope)
                 and type(controller.value) is bool else None)
    headings = ({POWER: 'Power LED (if installed)', CATEGORIES[0]: 'Case Lights',
                 CATEGORIES[1]: 'Keyboard Lights'} if detection is True else
                {POWER: 'Power LED', CATEGORIES[0]: 'LED Strip (if installed)'}
                if detection is False else {})
    groups = []
    for category in (POWER,) + CATEGORIES:
        source_rows = settings.get(category, ())
        rows = {item.name: item for item in source_rows
                if category != POWER or is_led(category, item.name)}
        if not rows:
            continue
        native = category in headings
        fields = POWER_FIELDS if category == POWER else FIELDS
        # Non-native keyboard store remains inspectable, without a native heading.
        rest_only = detection is False and category == CATEGORIES[1]
        valid = native and (category == POWER or _metadata_matches(category, rows))
        mode = rows.get('LedStrip Mode')
        mapped = []
        for name, label in (() if rest_only else fields):
            item = rows.get(name)
            status = UNKNOWN
            power_valid = (category != POWER or (item is not None and item.choices
                           and item.current in item.choices and item.value_type is str))
            if valid and item is not None and power_valid:
                active = True
                if category != POWER and name in dict(FIELDS[2:]):
                    active = MODE_FLAGS[mode.current][[n for n, _ in FIELDS[2:]].index(name)]
                status = 'Native active' if active else 'Native inactive — retained value'
            mapped.append(Row(category, name, label, item, status))
        if mapped:
            groups.append(Group(headings.get(category, category), tuple(mapped)))
        extras = [Row(category, item.name, item.name, item, UNKNOWN)
                  for item in source_rows if item.name in rows
                  and (rest_only or item.name not in dict(fields))]
        if extras:
            groups.append(Group(f'REST details — {category}', tuple(extras)))
    provenance = ['Values: existing settings snapshot; REST advertisement proves exposure only.',
                  f'Native rules: GideonZ/1541ultimate @ {SOURCE_REVISION}; '
                  'source revision does not establish installed-image equivalence.',
                  'Configured mode is not the current physical effect; Auto SID may change runtime behavior.']
    for label, evidence in (('Firmware qualification', firmware), ('Controller detection', controller)):
        provenance.append(f'{label}: {evidence.describe() if evidence else "unknown"}')
    for evidence in installed:
        provenance.append('Installed lighting (separate observation): ' + evidence.describe())
    provenance.append('Installed lighting is not inferred from native visibility or REST advertisement.')
    return Presentation('Native layout unknown' if detection is None else 'Qualified native layout',
                        tuple(groups), tuple(provenance))
