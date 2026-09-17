# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Warnings for settings with known hardware-transition risk."""

RISKY_SETTINGS = {
    ('U64 Specific Settings', 'SuperCPU Detect (D0BC)'):
        ('Changing SuperCPU Detect has been associated with an unresponsive '
         'C64U, although the cause is not confirmed. Stop running programs '
         'and save work first; a power cycle may be required.'),
}


def warning_for(category, name):
    return RISKY_SETTINGS.get((category, name))


def warnings_for(keys):
    """Return stable, de-duplicated warning text for setting identity keys."""
    warnings = []
    for category, name in keys:
        warning = warning_for(category, name)
        if warning and warning not in warnings:
            warnings.append(warning)
    return tuple(warnings)
