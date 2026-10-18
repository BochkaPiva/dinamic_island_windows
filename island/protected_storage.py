# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""Small current-Windows-user DPAPI boundary for installation identity and future credentials."""
import ctypes
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data,decrypt=False):
    if not isinstance(data,bytes) or len(data)>65536: raise ValueError('Invalid protected value')
    memory=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(memory,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    pointer=ctypes.POINTER(Blob)
    if decrypt:
        call=crypt.CryptUnprotectData
        call.argtypes=[pointer,ctypes.c_void_p,pointer,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,pointer]
        extra=None
    else:
        call=crypt.CryptProtectData
        call.argtypes=[pointer,wintypes.LPCWSTR,pointer,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,pointer]
        extra='Cloud Hub'
    call.restype=wintypes.BOOL
    if not call(ctypes.byref(source),extra,None,None,None,1,ctypes.byref(result)):
        raise OSError('Windows protected storage is unavailable')
    try: return ctypes.string_at(result.data,result.size)
    finally: kernel.LocalFree(ctypes.cast(result.data,ctypes.c_void_p))


def protect(data): return _crypt(data)
def unprotect(data): return _crypt(data,decrypt=True)
