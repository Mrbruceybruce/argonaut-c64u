# SPDX-License-Identifier: GPL-3.0-or-later
"""Small text-entry helpers for C64-visible input."""


_LOWER = 'abcdefghijklmnopqrstuvwxyz'
_UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
_ASCII_UPPER = str.maketrans(_LOWER, _UPPER)


def c64_upper(text):
    """Uppercase ordinary ASCII letters without changing other characters."""
    if not isinstance(text, str):
        raise TypeError('text must be text')
    return text.translate(_ASCII_UPPER)


def uppercase_entry(entry):
    """Keep a GTK entry aligned with the uppercase text sent to a C64."""
    text = entry.get_text()
    upper = c64_upper(text)
    if upper == text:
        return
    position = entry.get_position()
    entry.set_text(upper)
    entry.set_position(position)
