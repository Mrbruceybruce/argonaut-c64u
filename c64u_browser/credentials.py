# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""GNOME libsecret only: no plaintext or alternate-backend fallback."""
import sys
from .api import BrowserError
from .platform_support import portable_root

class Credentials:
    def __new__(cls):
        if portable_root() is not None:return SessionCredentials()
        if sys.platform == "win32":
            from .windows_credentials import WindowsCredentials
            return WindowsCredentials()
        return super().__new__(cls)

    def __init__(self):
        self.error = None
        try:
            import gi
            gi.require_version('Secret', '1')
            from gi.repository import Secret
            self.secret = Secret
            self.schema = Secret.Schema.new('org.local.Argonaut', Secret.SchemaFlags.NONE,
                                            {'profile-id': Secret.SchemaAttributeType.STRING})
        except (ImportError, ValueError) as exc:
            self.error = 'GNOME keyring unavailable. Passwords can be used for this session only.'

    def call(self, operation, *args):
        if self.error: raise BrowserError(self.error)
        try: return operation(*args)
        except Exception as exc:
            raise BrowserError('GNOME keyring could not be accessed. Unlock it or use a session-only password.') from exc

    def get(self, profile_id):
        if self.error: raise BrowserError(self.error)
        return self.call(self.secret.password_lookup_sync, self.schema, {'profile-id': profile_id}, None) or ''

    def set(self, profile_id, password):
        if self.error: raise BrowserError(self.error)
        result = self.call(self.secret.password_store_sync, self.schema, {'profile-id': profile_id},
                           self.secret.COLLECTION_DEFAULT, 'Argonaut C64 Ultimate', password, None)
        if not result: raise BrowserError('GNOME keyring did not save the password.')

    def delete(self, profile_id):
        if self.error: raise BrowserError(self.error)
        self.call(self.secret.password_clear_sync, self.schema, {'profile-id': profile_id}, None)


class SessionCredentials:
    """Portable profiles never read or write the host credential store."""
    error=None
    session_only=True
    def get(self,profile_id):return ''
    def set(self,profile_id,password):raise BrowserError('Portable mode keeps passwords for this session only.')
    def delete(self,profile_id):pass
