# SPDX-License-Identifier: GPL-3.0-only
"""Configurable RegisterHotKey bindings; no global keyboard hooks."""
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter


def parse_shortcut(value):
    if not value:
        return None
    parts = value.replace(" ", "").split("+")
    modifiers = {"Ctrl": 2, "Alt": 1, "Shift": 4, "Meta": 8, "Win": 8}
    if len(parts) < 2 or any(p not in modifiers for p in parts[:-1]):
        raise ValueError("Нужна клавиша с Ctrl, Alt или Win, например Alt+Space")
    mask = 0
    for part in parts[:-1]:
        mask |= modifiers[part]
    if not mask & 11:
        raise ValueError("Добавь Ctrl, Alt или Win")
    key = parts[-1]
    vk = {"Space": 0x20, "Home": 0x24, "End": 0x23, "Insert": 0x2D}.get(key)
    if len(key) == 1 and key.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        vk = ord(key.upper())
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    if vk is None:
        raise ValueError("Используй букву, цифру, F1–F24, Space, Home, End или Insert")
    return mask | 0x4000, vk


class HubHotkey(QAbstractNativeEventFilter):

    def __init__(self, app, callback, value="Ctrl+Alt+H", identifier=0x4348):
        super().__init__()
        self.app, self.callback, self.identifier = app, callback, identifier
        self.registered, self.value, self.error = False, "", ""
        app.installNativeEventFilter(self)
        self.rebind(value)

    def rebind(self, value):
        try:
            parsed = parse_shortcut(value)
        except ValueError as error:
            self.error = str(error)
            return False
        if parsed == parse_shortcut(self.value) and (self.registered or not value):
            self.value = value
            return True
        candidate = self.identifier ^ 0x1000
        if parsed and not ctypes.windll.user32.RegisterHotKey(None, candidate, *parsed):
            self.error = "Сочетание занято Windows или другим приложением. Выбери другое."
            return False
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.identifier)
        self.identifier = candidate
        self.value, self.registered, self.error = value, bool(parsed), ""
        return True

    def nativeEventFilter(self, event_type, message):
        msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
        if self.registered and msg.message == 0x0312 and msg.wParam == self.identifier:
            self.callback()
            return True, 0
        return False, 0

    def close(self):
        self.app.removeNativeEventFilter(self)
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.identifier)
            self.registered = False

    def suspend(self):
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None,self.identifier)
            self.registered = False

    def resume(self):
        return self.rebind(self.value)
