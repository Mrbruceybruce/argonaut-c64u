# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit opt-in identity for the separate development launcher."""
import os

def enabled():
    return os.environ.get('ARGONAUT_DEVELOPMENT') == '1'
