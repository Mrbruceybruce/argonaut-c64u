# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Launch the paired C64 client with a runtime-only Command Interface change."""
from .api import BrowserError
from .configuration import Configuration
from .files import inspect


CLIENT_PATH = '/USB2/argonaut-ai.prg'
CATEGORY = 'C64 and Cartridge Settings'
ITEM = 'Command Interface'


def launch_c64_ai(client, profile, path=CLIENT_PATH):
    if client is None or profile is None:
        raise BrowserError('Connect the paired C64U first.')
    profile.verify_identity(client.test_connection(), require_bound=True)
    entry = inspect(client, path)
    if entry is None or entry.kind != 'file':
        raise BrowserError('The paired Argonaut AI client was not found on USB2.')
    setting = next((row for row in Configuration(client).settings(CATEGORY)
                    if row.name == ITEM), None)
    if setting is None or 'Enabled' not in setting.choices:
        raise BrowserError('This firmware does not expose the Command Interface setting.')
    changed = setting.current != 'Enabled'
    if changed:
        client.apply_configuration({CATEGORY: {ITEM: 'Enabled'}})
    client.run_prg(path)
    return {'path': path, 'command_interface_changed': changed,
            'saved_to_flash': False}
