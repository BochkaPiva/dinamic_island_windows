# SPDX-License-Identifier: GPL-3.0-only
"""Explicit DWM preview: no recording, focus injection or screenshot polling."""
import ctypes
from ctypes import wintypes as W
from .window_layouts import api


class Thumbnail:
    def __init__(self,destination,window):
        self.window=window;self.handle=W.HANDLE()
        self.user=api()
        self.user.IsIconic.argtypes=(W.HWND,)
        self.user.GetClientRect.argtypes=(W.HWND,ctypes.POINTER(W.RECT))
        self.user.SetForegroundWindow.argtypes=(W.HWND,)
        self.dwm=ctypes.WinDLL('dwmapi')
        self.dwm.DwmRegisterThumbnail.argtypes=(W.HWND,W.HWND,ctypes.POINTER(W.HANDLE))
        self.dwm.DwmRegisterThumbnail.restype=ctypes.c_long
        self.dwm.DwmUnregisterThumbnail.argtypes=(W.HANDLE,)
        self.dwm.DwmQueryThumbnailSourceSize.argtypes=(W.HANDLE,ctypes.POINTER(W.SIZE))
        self.dwm.DwmUpdateThumbnailProperties.argtypes=(W.HANDLE,ctypes.c_void_p)
        if not self.valid() or self.dwm.DwmRegisterThumbnail(W.HWND(destination),W.HWND(window.hwnd),ctypes.byref(self.handle))<0:
            raise OSError('Не удалось открыть предпросмотр этого окна')

    def valid(self):
        pid=W.DWORD();self.user.GetWindowThreadProcessId(W.HWND(self.window.hwnd),ctypes.byref(pid))
        return bool(self.user.IsWindow(W.HWND(self.window.hwnd)) and pid.value==self.window.pid)

    def minimized(self):return bool(self.user.IsIconic(W.HWND(self.window.hwnd)))

    def update(self,rect,opacity=255,visible=True):
        if not self.handle:return
        size=W.SIZE()
        if self.dwm.DwmQueryThumbnailSourceSize(self.handle,ctypes.byref(size))<0:return
        client=W.RECT()
        if self.user.GetClientRect(W.HWND(self.window.hwnd),ctypes.byref(client)):
            size.cx,size.cy=client.right-client.left,client.bottom-client.top
        x,y,width,height=rect
        scale=min(width/max(1,size.cx),height/max(1,size.cy))
        dw,dh=round(size.cx*scale),round(size.cy*scale)
        x+=max(0,(width-dw)//2);y+=max(0,(height-dh)//2)
        class Properties(ctypes.Structure):
            _fields_=[('flags',W.DWORD),('destination',W.RECT),('source',W.RECT),
                      ('opacity',W.BYTE),('visible',W.BOOL),('client_only',W.BOOL)]
        props=Properties(1|4|8|16,W.RECT(x,y,x+dw,y+dh),W.RECT(),opacity,visible,True)
        if self.dwm.DwmUpdateThumbnailProperties(self.handle,ctypes.byref(props))<0:
            raise OSError('Предпросмотр окна недоступен')

    def activate(self):
        if self.valid():
            self.user.ShowWindow(W.HWND(self.window.hwnd),9)
            self.user.SetForegroundWindow(W.HWND(self.window.hwnd))

    def close(self):
        if self.handle:self.dwm.DwmUnregisterThumbnail(self.handle);self.handle=W.HANDLE()
