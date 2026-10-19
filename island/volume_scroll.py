# SPDX-License-Identifier: GPL-3.0-only
"""Volume follows physical up/down, independently of content scroll direction."""
from collections import deque
import ctypes
from ctypes import wintypes
import os
import time
from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QInputDevice


def touchpad_scroll_reversed():
    """Read settings only. SPI is available on Windows 11 24H2 and newer."""
    class Parameters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint32) for name in
                    ("version", "contacts", "legacy", "status", "settings", "sensitivity",
                     "speed", "feedback", "force", "width", "height")]
    if os.name != "nt":
        return None
    parameters = Parameters()
    parameters.version = 1
    user = ctypes.windll.user32
    if user.SystemParametersInfoW(0xAE, ctypes.sizeof(parameters), ctypes.byref(parameters), 0):
        return bool(parameters.settings & (1 << 9))
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad") as key:
            value = winreg.QueryValueEx(key, "ScrollDirection")[0]
        return bool(value) if value in (0, 1) else None
    except OSError:
        return None


def current_input_device():
    """Query this app's current message, without a global hook or input capture.

    Qt's Windows wheel adapter commonly labels touchpad wheels as a mouse and
    omits inverted(). NativeWheelSource opts this UI thread in to expose the
    source. Qt 6.11 passes PT_TOUCHPAD pointers to DefWindowProc, which performs
    normal Windows gesture-to-wheel conversion; this code never handles contacts.
    https://learn.microsoft.com/windows/win32/input-precisiontouchpad/registertouchpadcapable
    """
    class Source(ctypes.Structure):
        _fields_ = [("device", ctypes.c_uint32), ("origin", ctypes.c_uint32)]
    if os.name != "nt":
        return 0
    user = ctypes.windll.user32
    source = Source()
    return source.device if user.GetCurrentInputMessageSource(ctypes.byref(source)) else 0


class NativeWheelSource(QAbstractNativeEventFilter):
    """Associate native device metadata with the matching Qt wheel timestamp."""
    def __init__(self, application):
        super().__init__()
        self.application = application
        self.messages = deque(maxlen=128)
        self.register = (getattr(ctypes.windll.user32, "RegisterTouchpadCapableThread", None)
                         if os.name == "nt" else None)
        self.registered = bool(self.register and self.register(True))
        application.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt" and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x020A:  # WM_MOUSEWHEEL, own Qt application's messages only
                delta = ctypes.c_short((msg.wParam >> 16) & 0xffff).value
                self.messages.append((int(msg.time), delta, current_input_device(), time.monotonic()))
        return False, 0

    def device_for(self, event):
        timestamp, delta = int(event.timestamp()) & 0xffffffff, event.angleDelta().y()
        now = time.monotonic()
        for item in tuple(self.messages):
            if now-item[3] > .5:
                self.messages.remove(item)
            elif item[0] == timestamp and item[1] == delta:
                self.messages.remove(item)
                return item[2]
        return 0

    def close(self):
        self.application.removeNativeEventFilter(self)
        if self.registered:
            self.register(False)
            self.registered = False


def physical_delta(delta, *, inverted=False, touchpad=False, reversed_setting=None):
    if inverted:
        return -delta
    if touchpad and reversed_setting is False:
        return -delta
    return delta


class VolumeScroll:
    def __init__(self, output, source=None, preference=touchpad_scroll_reversed):
        self.output, self.source, self.preference = output, source, preference
        self.remainder = 0.0
        self.last_time = 0.0
        self.last_kind = None
        self.setting = None
        self.setting_at = -10.0

    def handle(self, event, reverse=False, now=None):
        now = time.monotonic() if now is None else now
        angle, pixels = event.angleDelta().y(), event.pixelDelta().y()
        if not angle and not pixels:
            event.ignore()
            return
        native_device = self.source.device_for(event) if self.source else 0
        touchpad = native_device == 0x10 or event.device().type() == QInputDevice.DeviceType.TouchPad
        if touchpad and now-self.setting_at > 1:
            self.setting, self.setting_at = self.preference(), now
        delta = physical_delta(angle if angle else pixels, inverted=event.inverted(),
                               touchpad=touchpad, reversed_setting=self.setting)
        if reverse:
            delta = -delta
        kind = (touchpad, bool(angle), event.inverted(), reverse)
        if now-self.last_time > .4 or kind != self.last_kind or delta*self.remainder < 0:
            self.remainder = 0
        self.last_time, self.last_kind = now, kind
        # One ordinary wheel detent = one Windows volume key step. Accumulate
        # precision deltas rather than sending a key for every tiny packet.
        self.remainder += delta / (120 if angle else 40)
        steps = int(self.remainder)
        self.remainder -= steps
        for _ in range(min(20, abs(steps))):
            self.output(1 if steps > 0 else -1)
        event.accept()
