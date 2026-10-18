# SPDX-License-Identifier: GPL-3.0-only
"""Read native system-list icons without shortcut overlays, off the UI thread."""
from collections import OrderedDict
import ctypes
import os
from pathlib import Path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QFileIconProvider


def native_icon(path):
    if os.name!='nt':
        return QImage()
    class FileInfo(ctypes.Structure):
        _fields_=[('icon',ctypes.c_void_p),('index',ctypes.c_int),('attributes',ctypes.c_ulong),
                  ('name',ctypes.c_wchar*260),('type',ctypes.c_wchar*80)]
    ole=ctypes.windll.ole32
    shell=ctypes.windll.shell32
    common=ctypes.windll.comctl32
    user=ctypes.windll.user32
    initialized=ole.CoInitializeEx(None,2) in (0,1)
    image_list=ctypes.c_void_p()
    icon=None
    try:
        info=FileInfo()
        shell.SHGetFileInfoW.argtypes=(ctypes.c_wchar_p,ctypes.c_ulong,ctypes.POINTER(FileInfo),ctypes.c_uint,ctypes.c_uint)
        shell.SHGetFileInfoW.restype=ctypes.c_void_p
        # Request only the index: SHGFI_ICON would bake a link arrow into .lnk icons.
        standard=shell.SHGetFileInfoW(str(path),0,ctypes.byref(info),ctypes.sizeof(info),0x4000)
        if not standard:
            return QImage()
        iid=(ctypes.c_byte*16)()
        ole.CLSIDFromString.argtypes=(ctypes.c_wchar_p,ctypes.c_void_p)
        ole.CLSIDFromString('{46EB5926-582E-4017-9FDF-E8998DAA0950}',ctypes.byref(iid))
        shell.SHGetImageList.argtypes=(ctypes.c_int,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))
        shell.SHGetImageList.restype=ctypes.c_long
        shell.SHGetImageList(2,ctypes.byref(iid),ctypes.byref(image_list))
        common.ImageList_GetIcon.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_uint)
        common.ImageList_GetIcon.restype=ctypes.c_void_p
        icon=common.ImageList_GetIcon(image_list.value or standard,info.index,1)
        return QImage.fromHICON(icon).copy() if icon else QImage()
    finally:
        if icon:
            user.DestroyIcon.argtypes=(ctypes.c_void_p,)
            user.DestroyIcon(icon)
        if image_list.value:
            table=ctypes.cast(image_list,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong,ctypes.c_void_p)(table[2])(image_list)
        if initialized:
            ole.CoUninitialize()


class IconTask(QRunnable):
    def __init__(self,cache,key):
        super().__init__()
        self.cache,self.key=cache,key

    def run(self):
        try:
            result=native_icon(self.key[0])
        except (OSError,ValueError,AttributeError):
            result=QImage()
        try:
            self.cache.ready.emit(self.key,result)
        except RuntimeError:
            pass


class GroupIcons(QObject):
    ready=Signal(object,QImage)
    changed=Signal(str)

    def __init__(self,parent):
        super().__init__(parent)
        self.cache=OrderedDict()
        self.pending=set()
        self.pool=QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.pool.setExpiryTimeout(3000)
        self.fallback=QFileIconProvider().icon(QFileIconProvider.IconType.File)
        self.ready.connect(self.loaded)

    def icon(self,path):
        path=str(path)
        try:
            state=Path(path).stat()
            key=(path,state.st_mtime_ns,state.st_size)
        except OSError:
            return self.fallback
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if key not in self.pending:
            self.pending.add(key)
            self.pool.start(IconTask(self,key))
        return self.fallback

    def loaded(self,key,image):
        self.pending.discard(key)
        self.cache[key]=QIcon(QPixmap.fromImage(image)) if not image.isNull() else self.fallback
        while len(self.cache)>256:
            self.cache.popitem(last=False)
        self.changed.emit(key[0])


def group_icons():
    app=QApplication.instance()
    if not hasattr(app,'_cloud_group_icons'):
        app._cloud_group_icons=GroupIcons(app)
    return app._cloud_group_icons
