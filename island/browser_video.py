# SPDX-License-Identifier: GPL-3.0-only
"""On-demand handoff to a browser's own PiP, never a copy of its tab/window.

SMTC is metadata, not video. Do not guess a video rectangle or attach a DWM
thumbnail here. Native PiP remains entirely owned by the browser and is not
closed, paused or rebound when another application becomes the audio source.
"""
import ctypes
from ctypes import wintypes as W
from pathlib import PureWindowsPath
from .window_layouts import api, list_windows

BROWSERS = frozenset({'opera.exe', 'chrome.exe', 'msedge.exe', 'brave.exe', 'vivaldi.exe'})
PIP_TITLES = frozenset({'picture in picture', 'picture-in-picture', 'картинка в картинке',
    'видео поверх окон', 'video pop out', 'video pop-out', 'video popout'})


def process_name(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (W.DWORD, W.BOOL, W.DWORD)
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = (W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD))
    kernel.CloseHandle.argtypes = (W.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ''
    try:
        path = ctypes.create_unicode_buffer(32768); size = W.DWORD(len(path))
        return PureWindowsPath(path.value).name.casefold() if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)) else ''
    finally:
        kernel.CloseHandle(handle)


def pip_candidates(windows, executable):
    # Exact known titles + verified process, never an ordinary browser tab
    # whose media title happens to contain "picture" or "video".
    return [w for w in windows if w.title.strip().casefold() in PIP_TITLES and executable(w.pid) in BROWSERS]


def activate(window):
    user = api(); pid = W.DWORD()
    user.GetWindowThreadProcessId(W.HWND(window.hwnd), ctypes.byref(pid))
    if not user.IsWindow(W.HWND(window.hwnd)) or pid.value != window.pid or process_name(pid.value) not in BROWSERS:
        return False
    user.IsIconic.argtypes = (W.HWND,)
    user.SetForegroundWindow.argtypes = (W.HWND,)
    if user.IsIconic(W.HWND(window.hwnd)):
        user.ShowWindow(W.HWND(window.hwnd), 9)
    return bool(user.SetForegroundWindow(W.HWND(window.hwnd)))


def existing_pip():
    candidates = pip_candidates(list_windows(), process_name)
    # Never silently pick the wrong video if multiple browsers have PiP open.
    return candidates[0] if len(candidates) == 1 else None


def browser_for(snapshot):
    source = snapshot.aumid.casefold()
    expected = next((name for name in BROWSERS if name[:-4] in source), None)
    if not expected:
        return None
    windows = [w for w in list_windows() if process_name(w.pid) == expected and w.title.strip().casefold() not in PIP_TITLES]
    title = snapshot.title.strip().casefold()
    matching = [w for w in windows if title and title in w.title.casefold()]
    return matching[0] if len(matching) == 1 else windows[0] if len(windows) == 1 else None
