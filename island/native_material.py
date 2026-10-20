# SPDX-License-Identifier: GPL-3.0-only
"""Bounded Windows acrylic adapter, with a completely opaque fallback.

Qt layered windows cannot reliably host DWMSBT_TRANSIENTWINDOW: Windows accepts
the call but paints an opaque backplate. The composition accent is isolated here;
it is optional, undocumented, and never a prerequisite for using the interface.
"""
import ctypes
import sys
import winreg
from PySide6.QtGui import QGuiApplication


def apply_acrylic(widget, *, light=False, enabled=True, tint_alpha=None,tint_rgb=None):
    if QGuiApplication.platformName() != 'windows' or sys.getwindowsversion().build < 22000:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            if not winreg.QueryValueEx(key, 'EnableTransparency')[0]:
                enabled=False
    except OSError:
        pass
    try:
        user=ctypes.WinDLL('user32',use_last_error=True)
        class Contrast(ctypes.Structure):
            _fields_=[('size',ctypes.c_uint),('flags',ctypes.c_uint),('scheme',ctypes.c_void_p)]
        contrast=Contrast(ctypes.sizeof(Contrast),0,None)
        spi=user.SystemParametersInfoW
        spi.argtypes=(ctypes.c_uint,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint)
        spi.restype=ctypes.c_int
        if spi(0x42,contrast.size,ctypes.byref(contrast),0) and contrast.flags & 1:
            enabled=False
        class Accent(ctypes.Structure):
            _fields_=[('state',ctypes.c_int),('flags',ctypes.c_int),
                      ('color',ctypes.c_uint),('animation',ctypes.c_int)]
        class Data(ctypes.Structure):
            _fields_=[('attribute',ctypes.c_int),('data',ctypes.c_void_p),('size',ctypes.c_size_t)]
        color=0xCCF4F4F4 if light else 0xBB222222
        if tint_rgb is not None:
            r,g,b=tint_rgb
            if any(type(channel) is not int or not 0<=channel<=255 for channel in (r,g,b)):raise ValueError('Invalid acrylic tint')
            color=(color & 0xFF000000)|(b<<16)|(g<<8)|r
        if tint_alpha is not None:color=(color & 0xFFFFFF)|(max(0,min(255,int(tint_alpha)))<<24)
        accent=Accent(4 if enabled else 0,0,color,0)
        data=Data(19,ctypes.cast(ctypes.pointer(accent),ctypes.c_void_p),ctypes.sizeof(accent))
        setter=user.SetWindowCompositionAttribute
        setter.argtypes=(ctypes.c_void_p,ctypes.POINTER(Data));setter.restype=ctypes.c_int
        return bool(setter(ctypes.c_void_p(int(widget.winId())),ctypes.byref(data))) and enabled
    except (AttributeError,OSError):
        return False



def island_transparency_available():
    """Rounded glass uses per-pixel alpha; rectangular accent blur is unsuitable."""
    if QGuiApplication.platformName()!='windows':return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            if not winreg.QueryValueEx(key,'EnableTransparency')[0]:return False
    except OSError:pass
    class Contrast(ctypes.Structure):
        _fields_=[('size',ctypes.c_uint),('flags',ctypes.c_uint),('scheme',ctypes.c_void_p)]
    value=Contrast(ctypes.sizeof(Contrast),0,None)
    user=ctypes.WinDLL('user32',use_last_error=True)
    return not (user.SystemParametersInfoW(0x42,value.size,ctypes.byref(value),0) and value.flags & 1)
