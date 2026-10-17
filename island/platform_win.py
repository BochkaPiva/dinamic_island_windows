# SPDX-License-Identifier: GPL-3.0-only
"""Small Windows integration layer; no administrative privileges required."""
import ctypes
import os
from pathlib import Path
import sys
import winreg


def autostart(enabled):
    command = f'"{sys.executable}" --background'
    if not getattr(sys, "frozen", False):
        interpreter = Path(sys.executable).with_name("pythonw.exe")
        command = f'"{interpreter}" "{Path(__file__).resolve().parents[1] / "main.py"}" --background'
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


DESKTOP_CLASSES = {"Progman", "WorkerW", "SHELLDLL_DefView", "SysListView32",
                   "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32769"}


def _window_class(user, hwnd):
    name = ctypes.create_unicode_buffer(128)
    user.GetClassNameW(ctypes.c_void_p(hwnd), name, 128)
    return name.value


def is_desktop_window(hwnd, user=None):
    """Recognize desktop descendants/owned overlays, not just their leaf class.

    Desktop organizers can put their own controls under Progman/WorkerW. Their
    full-screen bounds do not make them a full-screen application.
    """
    if not hwnd:
        return False
    user = user or ctypes.windll.user32
    user.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    user.GetAncestor.restype = ctypes.c_void_p
    user.GetShellWindow.restype = ctypes.c_void_p
    shell = user.GetShellWindow()
    roots = {hwnd, user.GetAncestor(ctypes.c_void_p(hwnd), 2),
             user.GetAncestor(ctypes.c_void_p(hwnd), 3)} - {None, 0}
    return bool(shell and shell in roots) or any(_window_class(user, root) in DESKTOP_CLASSES for root in roots)


def desktop_is_foreground():
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = ctypes.c_void_p
    return is_desktop_window(user.GetForegroundWindow(), user)


def exclude_from_peek(owner):
    """Keep our overlay composed during another window's taskbar Peek.

    Topmost alone does not prevent DWM from fading a window during Peek.
    This per-HWND attribute leaves other applications' previews enabled.
    Reapply after showing a newly created native window.
    """
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint)
        setter.restype = ctypes.c_long  # HRESULT
        enabled = ctypes.c_int(1)  # Win32 BOOL, not a one-byte C bool
        return setter(ctypes.c_void_p(int(owner.winId())), 12,  # DWMWA_EXCLUDED_FROM_PEEK
                      ctypes.byref(enabled), ctypes.sizeof(enabled)) >= 0
    except (AttributeError, OSError):
        return False


def apply_search_backdrop(owner):
    """Remove native frame/material from the layered Qt palette.

    DWMSBT_TRANSIENTWINDOW paints a rectangular backplate outside layered
    QWidget alpha/masks on Windows 11. Native acceptance is not visual support.
    Use our single translucent surface until the renderer can host it correctly.
    """
    if sys.getwindowsversion().build < 22621:
        return False
    try:
        setter=ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes=(ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint)
        setter.restype=ctypes.c_long
        hwnd=ctypes.c_void_p(int(owner.winId()))
        # Our complete client surface supplies its contour and one hairline.
        # Suppress DWM's additional border: layered custom chrome otherwise
        # acquires the thick grey frame visible on Windows 11.
        for attribute,value in ((20,1),(33,1),(34,0xfffffffe),(38,1)):
            native=ctypes.c_int(value)
            setter(hwnd,attribute,ctypes.byref(native),ctypes.sizeof(native))
    except (AttributeError,OSError):
        pass
    return False


def keep_desktop_visible(owner):
    """Restore only our overlay, without activating it or changing its bounds."""
    user = ctypes.windll.user32
    hwnd = ctypes.c_void_p(int(owner.winId()))
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    user.SetWindowPos.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
    user.SetWindowPos.restype = ctypes.c_int
    # HWND_TOPMOST, NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER.
    return bool(user.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0213))


def restore_desktop_panel(owner):
    """Recover Show Desktop without topmost windows or raising over our menus.

    Ordinary apps naturally cover these tools. Repair z-order only when the
    Explorer desktop surface actually covers them, never on every poll.
    """
    user = ctypes.windll.user32
    hwnd = ctypes.c_void_p(int(owner.winId()))
    restored = bool(user.IsIconic(hwnd))
    if restored:
        user.ShowWindow(hwnd, 4)
    user.GetWindow.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    user.GetWindow.restype = ctypes.c_void_p
    candidate = user.GetWindow(hwnd, 3)  # GW_HWNDPREV: windows above this one
    for _ in range(256):
        if not candidate:
            break
        if user.IsWindowVisible(ctypes.c_void_p(candidate)) and _window_class(user,candidate) in {"Progman","WorkerW"}:
            restored = True
            break
        candidate = user.GetWindow(ctypes.c_void_p(candidate),3)
    if restored:
        exclude_from_peek(owner)
        user.SetWindowPos.argtypes = (ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint)
        user.SetWindowPos(hwnd, None, 0,0,0,0,0x0213)  # HWND_TOP; NOACTIVATE
    return restored


def anchor_desktop_panel(owner, reset=False):
    """Own only our tool HWND by the shell; keep it below ordinary apps.

    Documented top-level ownership keeps it above Progman even when Explorer
    activates. No reparenting, shell messages, injected DLLs or Explorer writes.
    Qt can reset native ownership on show; reapply then and after shell changes.
    """
    user = ctypes.windll.user32
    user.GetShellWindow.restype = ctypes.c_void_p
    user.GetWindow.argtypes = (ctypes.c_void_p,ctypes.c_uint)
    user.GetWindow.restype = ctypes.c_void_p
    shell = user.GetShellWindow()
    if not shell or not user.IsWindow(ctypes.c_void_p(shell)):
        return False
    hwnd = ctypes.c_void_p(int(owner.winId()))
    if not user.IsWindow(hwnd):
        # Explorer can destroy its owned HWNDs while restarting. Qt retains the
        # widget, data and position; recreate only our native surface.
        owner.hide()
        owner.destroy()
        owner.show()
        hwnd = ctypes.c_void_p(int(owner.winId()))
        reset = True
    changed = user.GetWindow(hwnd,4) != shell  # GW_OWNER
    if changed:
        user.SetWindowLongPtrW.argtypes = (ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t)
        user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user.SetWindowLongPtrW(hwnd,-8,shell)  # GWLP_HWNDPARENT (owner, not parent)
        if user.GetWindow(hwnd,4) != shell:
            return False
    if user.IsIconic(hwnd) or not user.IsWindowVisible(hwnd):
        user.ShowWindow(hwnd,4)
        reset = True
    if changed or reset:
        user.SetWindowPos.argtypes = (ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint)
        user.SetWindowPos(hwnd,ctypes.c_void_p(1),0,0,0,0,0x213)  # HWND_BOTTOM; owned stays above shell
    return True


def disable_window_transitions(owner):
    """Desktop tiles have their own animation; never fly in from the taskbar."""
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = (ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_uint)
        setter.restype = ctypes.c_long
        value = ctypes.c_int(1)
        return setter(ctypes.c_void_p(int(owner.winId())),3,ctypes.byref(value),ctypes.sizeof(value)) >= 0
    except (AttributeError,OSError):
        return False


def is_fullscreen(owner):
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.MonitorFromWindow.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    user.MonitorFromWindow.restype = ctypes.c_void_p
    hwnd = user.GetForegroundWindow()
    if not hwnd or is_desktop_window(hwnd, user):
        return False
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    if user.IsIconic(ctypes.c_void_p(hwnd)) or not user.IsWindowVisible(ctypes.c_void_p(hwnd)):
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
    if not user.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return False
    if not user.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        return False
    return (rect.left == info.bounds.left and rect.right == info.bounds.right and
            rect.top == info.bounds.top and rect.bottom == info.bounds.bottom)


def adjust_volume(direction):
    # These virtual keys address the default Windows output, not a player.
    key = 0xAF if direction > 0 else 0xAE
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)
