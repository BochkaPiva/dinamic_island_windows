# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, verified window placement. No background replacement of Windows Snap."""
import ctypes
from ctypes import wintypes as W
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    title: str


def zones(bounds, preset='halves', gap=8):
    left,top,right,bottom=bounds
    ratios={'halves':(0,.5,1),'thirds':(0,1/3,2/3,1),'wide':(0,.6,1)}[preset]
    result=[]
    for a,b in zip(ratios,ratios[1:]):
        x=left+round((right-left)*a)+gap
        end=left+round((right-left)*b)-gap
        result.append((x,top+gap,max(1,end-x),max(1,bottom-top-2*gap)))
    return result


def api():
    # ctypes.windll caches one function object per process. Private prototypes
    # must not change GetWindowRect/GetMonitorInfo signatures used by the island.
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowThreadProcessId.argtypes=(W.HWND,ctypes.POINTER(W.DWORD))
    user.GetWindowTextW.argtypes=(W.HWND,W.LPWSTR,ctypes.c_int)
    user.IsWindow.argtypes=user.IsWindowVisible.argtypes=(W.HWND,)
    user.GetWindowRect.argtypes=(W.HWND,ctypes.POINTER(W.RECT))
    user.ShowWindow.argtypes=(W.HWND,ctypes.c_int)
    user.SetWindowPos.argtypes=(W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT)
    return user


def list_windows():
    user=api();result=[]
    callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def visit(hwnd,_):
        if not user.IsWindowVisible(hwnd): return True
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
        if pid.value!=os.getpid() and title.value and title.value!='Program Manager':
            cloaked=W.DWORD()
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(W.HWND(hwnd),14,ctypes.byref(cloaked),4)==0 and cloaked.value: return True
            result.append(Window(hwnd,pid.value,title.value))
        return True
    user.EnumWindows(callback(visit),0)
    return sorted(result,key=lambda w:w.title.casefold())


def place_window(window,preset,index):
    user=api()
    pid=W.DWORD()
    user.GetWindowThreadProcessId(W.HWND(window.hwnd),ctypes.byref(pid))
    if not user.IsWindow(W.HWND(window.hwnd)) or pid.value!=window.pid or pid.value==os.getpid():
        return False,'Окно уже закрыто. Обнови список.'
    class Monitor(ctypes.Structure):
        _fields_=[('size',W.DWORD),('bounds',W.RECT),('work',W.RECT),('flags',W.DWORD)]
    user.MonitorFromWindow.argtypes=(W.HWND,W.DWORD);user.MonitorFromWindow.restype=W.HMONITOR
    user.GetMonitorInfoW.argtypes=(W.HMONITOR,ctypes.POINTER(Monitor))
    info=Monitor();info.size=ctypes.sizeof(info)
    if not user.GetMonitorInfoW(user.MonitorFromWindow(W.HWND(window.hwnd),2),ctypes.byref(info)):
        return False,'Не удалось определить рабочую область экрана.'
    user.GetDpiForWindow.argtypes=(W.HWND,);user.GetDpiForWindow.restype=W.UINT
    gap=round(8*(user.GetDpiForWindow(W.HWND(window.hwnd)) or 96)/96)
    work=info.work
    x,y,width,height=zones((work.left,work.top,work.right,work.bottom),preset,gap)[index]
    class MinMax(ctypes.Structure):
        _fields_=[(name,W.POINT) for name in ('reserved','max_size','max_position','min_track','max_track')]
    minimum=MinMax();response=ctypes.c_size_t()
    user.SendMessageTimeoutW.argtypes=(W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,ctypes.POINTER(ctypes.c_size_t))
    if not user.SendMessageTimeoutW(W.HWND(window.hwnd),0x24,0,ctypes.addressof(minimum),2,150,ctypes.byref(response)):
        return False,'Окно не отвечает или запущено с другими правами.'
    if minimum.min_track.x>width+16 or minimum.min_track.y>height+16:
        return False,'Минимальный размер этого приложения больше зоны. Выбери более широкую раскладку.'
    user.ShowWindow(W.HWND(window.hwnd),9)
    outer=W.RECT();frame=W.RECT()
    user.GetWindowRect(W.HWND(window.hwnd),ctypes.byref(outer))
    margins=(0,0,0,0)
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(W.HWND(window.hwnd),9,ctypes.byref(frame),ctypes.sizeof(frame))==0:
        margins=(frame.left-outer.left,frame.top-outer.top,outer.right-frame.right,outer.bottom-frame.bottom)
    l,t,r,b=margins
    if not user.SetWindowPos(W.HWND(window.hwnd),None,x-l,y-t,width+l+r,height+t+b,0x14):
        return False,'Windows не разрешила изменить окно. Приложения с правами администратора могут требовать такие же права.'
    actual=W.RECT();user.GetWindowRect(W.HWND(window.hwnd),ctypes.byref(actual))
    if abs(actual.right-actual.left-(width+l+r))>12 or abs(actual.bottom-actual.top-(height+t+b))>12:
        return False,'Приложение ограничило изменение размера. Выбери более широкую зону.'
    return True,'Окно размещено и подогнано по размеру зоны.'
