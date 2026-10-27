# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Core-owned configuration dependency admission, independent of presentation.

LED rules: official 1.1.0, 7b628eb166872965ea59d66f90ffd9bcf7d71d8a.
See docs/CONFIGURATION-DEPENDENCIES.md for qualification boundaries.
"""
import math
import unicodedata
from dataclasses import dataclass


class ConfigurationRefused(ValueError):
    """Definite refusal before this operation writes configuration or history."""
    def __init__(self, reason):
        super().__init__('Configuration not sent. ' + reason)


@dataclass(frozen=True)
class Dependency:
    controller: str
    allowed: frozenset


LED_CATEGORIES = ('LED Strip Settings', 'Keyboard Lighting')
MODE = 'LedStrip Mode'
COMMON_MODES = frozenset(('Off', 'Default', 'Fixed Color', 'SID Music',
                          'Rainbow', 'Rainbow Sparkle'))
MODES = {LED_CATEGORIES[0]: COMMON_MODES | {'Sparkle'},
         LED_CATEGORIES[1]: COMMON_MODES}
LED_FIELDS = frozenset((MODE, 'LedStrip Auto SID Mode', 'LedStrip SID Select',
                       'LedStrip Pattern', 'Strip Intensity', 'Fixed Color', 'Color tint'))
LED_MODES = {
    'LedStrip Pattern': frozenset(('Rainbow', 'Rainbow Sparkle', 'SID Music')),
    'Strip Intensity': COMMON_MODES - {'Off'} | {'Sparkle'},
    'Fixed Color': frozenset(('Fixed Color',)),
    'Color tint': frozenset(('Fixed Color', 'Rainbow', 'Rainbow Sparkle')),
}
LED_ENUMS = {
    'LedStrip Auto SID Mode': frozenset(('Disabled', 'Enabled')),
    'LedStrip SID Select': frozenset(f'UltiSID{sid}-{voice}' for sid in (1, 2) for voice in 'ABCD'),
    'Fixed Color': frozenset(('Red', 'Scarlet', 'Orange', 'Amber', 'Yellow', 'Lemon-Lime',
        'Chartreuse', 'Lime', 'Green', 'Jade', 'Spring Green', 'Aquamarine', 'Cyan',
        'Deep Sky Blue', 'Azure', 'Royal Blue', 'Blue', 'Indigo', 'Violet', 'Purple',
        'Magenta', 'Fuchsia', 'Rose', 'Cerise', 'White')),
    'Color tint': frozenset(('Pure', 'Bright', 'Pastel', 'Whisper')),
}
PATTERNS = {
    'LED Strip Settings': frozenset(('SingleColor', 'Left to Right', 'Right to Left', 'Serpentine', 'Outward')),
    'Keyboard Lighting': frozenset(('Single Color', 'Left to Right', 'Right to Left', 'Outward', 'Circular')),
}
NETWORK_CATEGORIES = {'Ethernet Settings', 'WiFi settings'}
STATIC_FIELDS = {'Static IP', 'Static Netmask', 'Static Gateway', 'Static DNS'}
DEPENDENCIES = {
    **{(c, n): Dependency(MODE, modes) for c in LED_CATEGORIES for n, modes in LED_MODES.items()},
    **{(c, n): Dependency('Use DHCP', frozenset(('Disabled',)))
       for c in NETWORK_CATEGORIES for n in STATIC_FIELDS},
}


def identity(name):
    if (type(name) is not str or not name or name != name.strip()
            or any(unicodedata.category(c).startswith('C') for c in name)
            or any(c in name for c in '*?\\/:')):
        raise ConfigurationRefused('Invalid or ambiguous configuration identity.')
    return name.casefold()


def detach(values):
    """Validate shape and freeze caller intent into detached plain dictionaries."""
    if type(values) is not dict or not values:
        raise ConfigurationRefused('Expected a nonempty configuration mapping.')
    result = {}; categories = set()
    for category, items in values.copy().items():
        cid = identity(category)
        if cid in categories:
            raise ConfigurationRefused('Duplicate configuration category.')
        categories.add(cid)
        if type(items) is not dict or not items:
            raise ConfigurationRefused('Expected a nonempty settings mapping.')
        result[category] = {}; names = set()
        for name, value in items.copy().items():
            nid = identity(name)
            if nid in names:
                raise ConfigurationRefused('Duplicate configuration setting.')
            names.add(nid)
            if (type(value) not in (str, int, float, bool)
                    or type(value) is float and not math.isfinite(value)):
                raise ConfigurationRefused('Expected a finite scalar setting value.')
            result[category][name] = value
    return result


def controls_dependencies(category, name):
    return any(c == category and rule.controller == name
               for (c, _), rule in DEPENDENCIES.items())


def mode_write_blocked(category, name):
    """Argonaut containment policy, independent of firmware/menu metadata."""
    return (type(category) is str and type(name) is str
            and category.casefold() in {c.casefold() for c in LED_CATEGORIES}
            and name.casefold() == MODE.casefold())


def refuse_mode_writes(values):
    for category, items in values.items():
        for name in items:
            if mode_write_blocked(category, name):
                raise ConfigurationRefused(inactive_reason(category, name))


def led_apply_blocked(category):
    """Temporary #49 Apply containment; not a firmware capability rule."""
    return (type(category) is str
            and category.casefold() in {c.casefold() for c in LED_CATEGORIES})


def refuse_led_apply(values):
    # Refuse the complete request, including unknown and same-value fields.
    # Keep the narrower published mode rule independently enforced above.
    for category in values:
        if led_apply_blocked(category):
            raise ConfigurationRefused(inactive_reason(category, ''))


def enabled(category, name, settings, pending):
    if led_apply_blocked(category):
        return False
    rows = {s.name: s for s in settings.get(category, ())}
    if category in MODES:
        mode = pending.get((category, MODE), getattr(rows.get(MODE), 'current', None))
        if name not in LED_FIELDS or mode not in MODES[category]:
            return False
    rule = DEPENDENCIES.get((category, name))
    if rule is None:
        return True
    value = pending.get((category, rule.controller),
                        getattr(rows.get(rule.controller), 'current', None))
    return value in rule.allowed


def inactive_reason(category, name):
    if led_apply_blocked(category):
        return ('LED Apply writes are temporarily blocked by Argonaut pending Issue #49 '
                'safety qualification. LED values remain readable; all fields are read-only.')
    if category in NETWORK_CATEGORIES and name in STATIC_FIELDS:
        return 'Read-only while DHCP is enabled. Disable DHCP to edit these saved static settings.'
    return 'Inactive in the proposed LED mode, or this capability is unknown.'


def validate(values, settings):
    """Validate every requested edit against the complete proposed state.

    Dormant stored values are not edits. Controllers are overlaid before checking
    dependents, independent of caller insertion order. Returns canonical names.
    """
    from .configuration import display
    values = detach(values)
    refuse_mode_writes(values)
    refuse_led_apply(values)
    categories = {identity(c): c for c in settings}
    if len(categories) != len(settings):
        raise ConfigurationRefused('Ambiguous configuration category metadata.')
    payload = {}
    for category, items in values.items():
        canonical = categories.get(identity(category))
        if canonical is None:
            raise ConfigurationRefused('Configuration category is unavailable: ' + category)
        rows = {identity(s.name): s for s in settings[canonical]}
        if len(rows) != len(settings[canonical]):
            raise ConfigurationRefused('Ambiguous configuration setting metadata.')
        payload[canonical] = {}
        for name, value in items.items():
            setting = rows.get(identity(name))
            if setting is None:
                raise ConfigurationRefused('Setting is unavailable: ' + name)
            if canonical in MODES:
                if setting.name not in LED_FIELDS:
                    raise ConfigurationRefused('Unknown LED setting: ' + name)
                if setting.name == 'Strip Intensity':
                    if (setting.value_type is not int or setting.minimum != 0
                            or setting.maximum != 31 or setting.choices):
                        raise ConfigurationRefused('Unknown LED intensity metadata.')
                elif (setting.value_type is not str or not setting.choices
                      or any(type(v) is not str for v in setting.raw_choices)):
                    raise ConfigurationRefused('Unknown LED enum metadata: ' + name)
                else:
                    allowed = (MODES[canonical] if setting.name == MODE else
                               PATTERNS[canonical] if setting.name == 'LedStrip Pattern' else
                               LED_ENUMS[setting.name])
                    if (not set(setting.choices) <= allowed
                            or len(set(setting.choices)) != len(setting.choices)):
                        raise ConfigurationRefused('Unqualified LED enum choices: ' + name)
            try:
                parsed = setting.parse(display(value))
            except ValueError as exc:
                raise ConfigurationRefused(f'{canonical} / {name}: {exc}') from None
            # Never silently reinterpret an integer/bool as an enum or string.
            if type(parsed) is not type(value) or parsed != value:
                raise ConfigurationRefused('Setting value has the wrong type: ' + name)
            payload[canonical][setting.name] = value
    pending = {(c, n): v for c, items in payload.items() for n, v in items.items()}
    for category, items in payload.items():
        if category in MODES:
            rows = {s.name: s for s in settings[category]}
            controller = rows.get(MODE)
            if (controller is None or not controller.editable or not controller.choices
                    or not set(controller.choices) <= MODES[category]
                    or controller.current not in controller.choices
                    or pending.get((category, MODE), controller.current) not in controller.choices):
                raise ConfigurationRefused('LED mode capabilities are unknown: ' + category)
        for name in items:
            if not enabled(category, name, settings, pending):
                raise ConfigurationRefused(f'{category} / {name}: {inactive_reason(category, name)}')
    # REST applies fields sequentially. A validated enabling controller precedes
    # its dependents; this ordering is not a claim of device-side atomicity.
    return {c: dict(sorted(items.items(), key=lambda item: not controls_dependencies(c, item[0])))
            for c, items in payload.items()}


def execute(client, values, dispatch, *, expected=None, history_path=None, check_session=lambda: None):
    """Fresh admission shared by Core and the internal transport entry point."""
    from .configuration import Configuration
    from .config_history import save_before_apply
    payload = detach(values)
    expected = dict(expected) if expected is not None else None
    check_session()
    refuse_mode_writes(payload)
    refuse_led_apply(payload)
    # Canonicalize known stores before the read; unknown stores retain identity.
    known = {c.casefold(): c for c in (*LED_CATEGORIES, *NETWORK_CATEGORIES)}
    payload = {known.get(c.casefold(), c): items for c, items in payload.items()}
    try:
        fresh = Configuration(client).all_settings(list(payload))
        if any(c in MODES for c in payload):
            info = client.read_about('info')
            if (type(info) is not dict or info.get('firmware_version') != '1.1.0'
                    or info.get('product') != 'C64 Ultimate' or info.get('errors', [])):
                raise ConfigurationRefused('LED dependencies are not qualified for this firmware/product.')
        payload = validate(payload, fresh)
        if expected is not None:
            actual = {(c, s.name): s.current for c, rows in fresh.items() for s in rows}
            required = {(c, n) for c, items in payload.items() for n in items}
            required |= {(c, rule.controller) for (c, n), rule in DEPENDENCIES.items()
                         if c in payload and (n in payload[c] or c in MODES)}
            if any(key not in expected or actual.get(key) != expected[key] for key in required):
                raise ConfigurationRefused('Device settings or controlling settings changed since review. Reload before applying.')
        check_session()
    except ConfigurationRefused:
        raise
    except Exception as exc:
        raise ConfigurationRefused('Fresh configuration validation failed; reload before applying.') from exc
    if history_path is not None:
        save_before_apply(history_path, fresh, payload, client.host)
    return dispatch(payload)
