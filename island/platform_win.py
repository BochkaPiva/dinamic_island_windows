# SPDX-License-Identifier: GPL-3.0-only
"""Small Windows integration layer; no administrative privileges required."""
import ctypes
import os
from pathlib import Path
import sys
import winreg


def autostart(enabled):
    command = f'"{sys.executable}"'
    if not getattr(sys, "frozen", False):
        interpreter = Path(sys.executable).with_name("pythonw.exe")
        command = f'"{interpreter}" "{Path(__file__).resolve().parents[1] / "main.py"}"'
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            if enabled:
                winreg.SetValueEx(key, "Cloud Island", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "Cloud Island")
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def is_fullscreen(owner):
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.MonitorFromWindow.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    user.MonitorFromWindow.restype = ctypes.c_void_p
    hwnd = user.GetForegroundWindow()
    if not hwnd:
        return False
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    name = ctypes.create_unicode_buffer(128)
    user.GetClassNameW(ctypes.c_void_p(hwnd), name, 128)
    if name.value in {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"} or user.IsIconic(ctypes.c_void_p(hwnd)):
        return False
    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    class Monitor(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("bounds", Rect), ("work", Rect), ("flags", ctypes.c_ulong)]
    monitor = user.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
    if monitor != user.MonitorFromWindow(ctypes.c_void_p(int(owner.winId())), 2):
        return False
    rect, info = Rect(), Monitor()
    info.size = ctypes.sizeof(info)
    user.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    user.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info))
    return (rect.left == info.bounds.left and rect.right == info.bounds.right and
            rect.top == info.bounds.top and rect.bottom == info.bounds.bottom)


def adjust_volume(direction):
    # These virtual keys address the default Windows output, not a player.
    key = 0xAF if direction > 0 else 0xAE
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)
