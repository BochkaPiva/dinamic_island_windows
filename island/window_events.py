# SPDX-License-Identifier: GPL-3.0-only
"""Out-of-context notifications only; no keyboard hooks or injection."""
import ctypes
from PySide6.QtCore import QObject, Signal, QTimer


class WindowEvents(QObject):
    changed=Signal()
    geometry_changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.hooks=[]
        self.pending=QTimer(self)
        self.pending.setSingleShot(True)
        self.pending.setInterval(40)
        self.pending.timeout.connect(self.changed.emit)
        self.geometry_changed.connect(self.queue_geometry)
        callback=ctypes.WINFUNCTYPE(None,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,
            ctypes.c_long,ctypes.c_long,ctypes.c_ulong,ctypes.c_ulong)
        user=ctypes.windll.user32
        user.GetForegroundWindow.restype=ctypes.c_void_p
        def notify(hook,event,hwnd,object_id,child,thread,stamp):
            if event==0x800B:
                if object_id==0 and hwnd==user.GetForegroundWindow(): self.geometry_changed.emit()
            else: self.changed.emit()
        self.callback=callback(notify)
        user.SetWinEventHook.argtypes=(ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p,
            callback,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong)
        user.SetWinEventHook.restype=ctypes.c_void_p
        for event in (3,11,23,0x800B):  # foreground, move/size end, minimize end, location
            hook=user.SetWinEventHook(event,event,None,self.callback,0,0,0)
            if hook: self.hooks.append(hook)

    def queue_geometry(self):
        if not self.pending.isActive(): self.pending.start()

    def close(self):
        self.pending.stop()
        user=ctypes.windll.user32
        user.UnhookWinEvent.argtypes=(ctypes.c_void_p,)
        for hook in self.hooks: user.UnhookWinEvent(hook)
        self.hooks.clear()
