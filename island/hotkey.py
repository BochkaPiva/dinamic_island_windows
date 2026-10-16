# SPDX-License-Identifier: GPL-3.0-only
"""One optional registered hotkey; no global keyboard hook."""
import ctypes
from ctypes import wintypes
from PyQt6.QtCore import QAbstractNativeEventFilter


class HubHotkey(QAbstractNativeEventFilter):
    identifier = 0x4348

    def __init__(self, app, callback):
        super().__init__()
        self.app, self.callback = app, callback
        self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.identifier, 0x4003, 0x48))
        if self.registered:
            app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        if msg.message == 0x0312 and msg.wParam == self.identifier:
            self.callback()
            return True, 0
        return False, 0

    def close(self):
        if self.registered:
            self.app.removeNativeEventFilter(self)
            ctypes.windll.user32.UnregisterHotKey(None, self.identifier)
            self.registered = False
