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

    def exists(self, profile_id):
        """Find the existing generic-password item without requesting password data."""
        if self.error: raise BrowserError(self.error)
        try:
            import ctypes as c
            security=c.CDLL('/System/Library/Frameworks/Security.framework/Security')
            find=security.SecKeychainFindGenericPassword
            find.argtypes=[c.c_void_p,c.c_uint32,c.c_char_p,c.c_uint32,c.c_char_p,
                           c.c_void_p,c.c_void_p,c.c_void_p]
            find.restype=c.c_int32
            service,account=self.service.encode('utf-8'),profile_id.encode('utf-8')
            # NULL output pointers request neither password bytes nor an item reference.
            status=find(None,len(service),service,len(account),account,None,None,None)
            if status == -25300:return False  # errSecItemNotFound
            if status != 0:raise BrowserError('macOS Keychain could not be accessed.')
            return True
        except Exception as exc:
            raise BrowserError('macOS Keychain could not be accessed. Unlock it or use a session-only password.') from exc

    def get(self, profile_id):
        return self.call('get_password', profile_id) or ''

    def set(self, profile_id, password):
        self.call('set_password', profile_id, password)

    def delete(self, profile_id):
        if self.exists(profile_id):
            self.call('delete_password', profile_id)
