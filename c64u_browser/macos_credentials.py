# SPDX-License-Identifier: GPL-3.0-or-later
"""Use only the macOS Keychain backend, never automatic backend selection."""
from .api import BrowserError

class MacOSCredentials:
    service = 'org.argonaut.c64u'
    def __init__(self):
        self.error = None
        try:
            from keyring.backends.macOS import Keyring
            self.backend = Keyring()
        except Exception:
            self.error = 'macOS Keychain unavailable. Passwords can be used for this session only.'

    def call(self, operation, *args):
        if self.error:
            raise BrowserError(self.error)
        try:
            return getattr(self.backend, operation)(self.service, *args)
        except Exception as exc:
            raise BrowserError('macOS Keychain could not be accessed. Unlock it or use a session-only password.') from exc

    def get(self, profile_id):
        return self.call('get_password', profile_id) or ''

    def set(self, profile_id, password):
        self.call('set_password', profile_id, password)

    def delete(self, profile_id):
        if self.get(profile_id):
            self.call('delete_password', profile_id)
