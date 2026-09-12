# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-user Windows Credential Manager; no plaintext fallback."""
import ctypes as c
from ctypes import wintypes as w
from .api import BrowserError

class Credential(c.Structure):
    _fields_=[('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),
              ('Comment',w.LPWSTR),('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),
              ('CredentialBlob',c.POINTER(c.c_ubyte)),('Persist',w.DWORD),
              ('AttributeCount',w.DWORD),('Attributes',c.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]

class WindowsCredentials:
    error=None
    def __init__(self):
        self.dll=c.WinDLL('advapi32',use_last_error=True)
        self.dll.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.POINTER(c.POINTER(Credential))]
        self.dll.CredReadW.restype=w.BOOL
        self.dll.CredWriteW.argtypes=[c.POINTER(Credential),w.DWORD];self.dll.CredWriteW.restype=w.BOOL
        self.dll.CredDeleteW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD];self.dll.CredDeleteW.restype=w.BOOL
        self.dll.CredFree.argtypes=[c.c_void_p];self.dll.CredFree.restype=None
    def target(self,key):return 'Argonaut/profile/'+str(key)
    def failed(self):raise BrowserError('Windows Credential Manager failed (error '+str(c.get_last_error())+').')
    def get(self,key):
        ptr=c.POINTER(Credential)()
        if not self.dll.CredReadW(self.target(key),1,0,c.byref(ptr)):
            if c.get_last_error()==1168:return ''
            self.failed()
        try:return c.string_at(ptr.contents.CredentialBlob,ptr.contents.CredentialBlobSize).decode('utf-16-le')
        finally:self.dll.CredFree(ptr)
    def set(self,key,password):
        data=password.encode('utf-16-le')
        if len(data)>2560:raise BrowserError('Password exceeds Windows Credential Manager size limit.')
        buf=(c.c_ubyte*len(data)).from_buffer_copy(data)
        cred=Credential();cred.Type=1;cred.TargetName=self.target(key);cred.UserName='Argonaut'
        cred.CredentialBlobSize=len(data);cred.CredentialBlob=buf;cred.Persist=2
        if not self.dll.CredWriteW(c.byref(cred),0):self.failed()
    def delete(self,key):
        if not self.dll.CredDeleteW(self.target(key),1,0) and c.get_last_error()!=1168:self.failed()
