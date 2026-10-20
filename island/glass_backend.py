# SPDX-License-Identifier: GPL-3.0-only
"""A native Composition backdrop below Qt's sharp, per-pixel content window.

No desktop capture or fabricated reflections. The composition clip applies to the
blur itself, unlike rectangular AccentPolicy blur on a layered Qt HWND.
"""
import ctypes
from PySide6.QtCore import QObject,QEvent,Qt,QRectF
from PySide6.QtWidgets import QWidget

_queue_controller=None

class BackdropSurface(QWidget):
    def paintEvent(self,event):pass
    def nativeEvent(self,event_type,message):
        from ctypes import wintypes
        msg=ctypes.cast(int(message),ctypes.POINTER(wintypes.MSG)).contents
        if msg.message==0x84:return True,-1  # HTTRANSPARENT
        if msg.message==0x21:return True,3  # MA_NOACTIVATE
        return False,0

class GlassBackdrop(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        from winrt.windows.ui.composition import Compositor
        from winrt.windows.ui.composition.interop import create_desktop_window_target
        from winrt.windows.system.interop import create_dispatcher_queue_controller
        from winrt.windows.system import DispatcherQueue
        self.owner=owner;self.enabled=False;self.closed=False;self.failed=False;self.key=None
        # Keep one dispatcher for the Qt UI thread, not one per show or color change.
        global _queue_controller
        if not DispatcherQueue.get_for_current_thread():_queue_controller=create_dispatcher_queue_controller()
        self.surface=BackdropSurface(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus|
            Qt.WindowType.WindowTransparentForInput|Qt.WindowType.NoDropShadowWindowHint)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.surface.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.surface.setWindowTitle('Nelviro · материал')
        self.surface.setEnabled(False)
        self.compositor=Compositor()
        self.target=create_desktop_window_target(self.compositor,int(self.surface.winId()))
        self.root=self.compositor.create_container_visual()
        self.sprite=self.compositor.create_sprite_visual()
        self.sprite.brush=self.compositor.create_host_backdrop_brush()
        self.geometry=self.compositor.create_rounded_rectangle_geometry()
        self.clip=self.compositor.create_geometric_clip_with_geometry(self.geometry)
        self.sprite.clip=self.clip;self.root.children.insert_at_top(self.sprite);self.target.root=self.root
        self.user=ctypes.WinDLL('user32',use_last_error=True);self.dwm=ctypes.WinDLL('dwmapi')
        self.user.GetWindowLongPtrW.argtypes=(ctypes.c_void_p,ctypes.c_int);self.user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t)
        self.user.EnableWindow.argtypes=(ctypes.c_void_p,ctypes.c_int)
        self.user.SetWindowPos.argtypes=(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint)
        self.dwm.DwmSetWindowAttribute.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint)
        self.dwm.DwmExtendFrameIntoClientArea.argtypes=(ctypes.c_void_p,ctypes.c_void_p)
        owner.installEventFilter(self)
    def native_style(self):
        hwnd=int(self.surface.winId())
        style=self.user.GetWindowLongPtrW(hwnd,-20)
        self.user.SetWindowLongPtrW(hwnd,-20,(style|0x200000|0x20|0x8000080)&~0x80000)
        self.user.EnableWindow(hwnd,False)
        enabled=ctypes.c_int(1)
        result=self.dwm.DwmSetWindowAttribute(hwnd,17,ctypes.byref(enabled),4)
        if result<0:raise OSError('Host backdrop is unavailable')
        margins=(ctypes.c_int*4)(-1,-1,-1,-1)
        self.dwm.DwmExtendFrameIntoClientArea(hwnd,ctypes.byref(margins))
        self.dwm.DwmSetWindowAttribute(hwnd,12,ctypes.byref(enabled),4)
    def configure(self,enabled):
        self.enabled=enabled and not self.failed;self.sync();return self.enabled
    def eventFilter(self,obj,event):
        if obj is self.owner:
            if event.type() in (QEvent.Type.Hide,QEvent.Type.Close):self.surface.hide()
            elif event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.Show):self.sync()
        return False
    def sync(self):
        if self.closed:return
        try:self._sync()
        except (OSError,RuntimeError):
            self.enabled=False;self.failed=True;self.surface.hide()
            self.owner.island_material=False;self.owner._glass_backend_failed=True;self.owner.card.update()
    def _sync(self):
        if self.closed:return
        w=self.owner
        if not self.enabled or not w.isVisible():self.surface.hide();return
        rect=w.geometry()
        if self.surface.geometry()!=rect:self.surface.setGeometry(rect)
        if not self.surface.isVisible():self.surface.show();self.native_style()
        ratio=self.surface.devicePixelRatioF();width=w.width();height=w.height()
        card=w.card;media=bool(getattr(w,'media_stage',None) and w.media_stage.engaged)
        if media:
            box=QRectF(0,0,width,height);radius=min(22,height/2)
        elif w.floating_mode():
            t=card._retreat*card._retreat*(3-2*card._retreat)
            inset=width*.20*t;bottom=height+(6-height)*t
            box=QRectF(inset,-6*t,width-2*inset,bottom+6*t);radius=min(24.,height/2)+(6-min(24.,height/2))*t
        else:
            flare=min(18.,max(8.,height*.1));radius=min(30.,(height-flare)*.65)
            bottom=min(card.retreat_boundary(width*x/16)[0] for x in range(17)) if card._retreat else height
            radius=min(radius,max(1,bottom/2));box=QRectF(flare,-radius,width-2*flare,bottom+radius)
        key=(rect.width(),rect.height(),box.x(),box.y(),box.width(),box.height(),radius,ratio)
        if key!=self.key:
            self.sprite.size=(width*ratio,height*ratio)
            self.geometry.offset=(box.x()*ratio,box.y()*ratio)
            self.geometry.size=(max(1,box.width()*ratio),max(1,box.height()*ratio))
            self.geometry.corner_radius=(radius*ratio,radius*ratio);self.key=key
        self.root.opacity=max(0.,min(1.,w.windowOpacity()))
        self.user.SetWindowPos(int(self.surface.winId()),int(w.winId()),0,0,0,0,0x13)
    def close(self):
        if self.closed:return
        self.closed=True;self.owner.removeEventFilter(self);self.surface.hide()
        self.target.root=None;self.target.close();self.compositor.close();self.surface.close();self.surface.deleteLater()
        # The queue belongs to the Qt UI thread and may be shared by later windows.
