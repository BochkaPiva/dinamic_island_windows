# SPDX-License-Identifier: GPL-3.0-only
"""Native checks of our own windows; no input/capture of other applications."""
import ctypes
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, Qt, QPoint
from PyQt6.QtGui import QColor, QPainter, QPixmap, QPen
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidget
from island.app import IslandWindow
from island.media import Snapshot
from island.storage import Settings
from island.platform_win import anchor_desktop_panel, exclude_from_peek

out = Path(sys.argv[1] if len(sys.argv)>1 else "build/motion-groups-check")
out.mkdir(parents=True,exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
user = ctypes.windll.user32
user.GetForegroundWindow.restype = ctypes.c_void_p
user.GetAncestor.argtypes = (ctypes.c_void_p,ctypes.c_uint)
user.GetAncestor.restype = ctypes.c_void_p
user.GetWindowLongPtrW.argtypes = (ctypes.c_void_p,ctypes.c_int)
user.GetWindowLongPtrW.restype = ctypes.c_ssize_t

def png(widget):
    data = QBuffer()
    data.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(data,"PNG")
    return Image.open(io.BytesIO(bytes(data.data()))).convert("RGBA")

with tempfile.TemporaryDirectory() as folder:
    w = IslandWindow(Settings(folder),services=False)
    w._notch_pointer.enabled = False
    w._notch_pointer_timer.stop()
    try:
        cover = QPixmap(96,96)
        cover.fill(QColor("#c17c58"))
        painter = QPainter(cover)
        painter.setPen(QPen(QColor("#f8dbad"),5))
        for r in (14,28,40):
            painter.drawEllipse(QPoint(48,48),r,r)
        painter.end()
        data = QBuffer()
        data.open(QIODevice.OpenModeFlag.WriteOnly)
        cover.save(data,"PNG")
        w._handle_snapshot(Snapshot(title="Тихий вечер",artist="Cloud Hub · Studio",has_session=True,
            aumid="fixture",status="Playing",thumb=bytes(data.data()),can_play=True,can_pause=True,
            can_prev=True,can_next=True,can_seek=True,pos_sec=44,dur_sec=218,sources=("fixture",)))
        w.show()
        w.raise_()
        QTest.qWait(280)
        frames, stamps = [],[]
        started = time.monotonic()
        for expanded,count in ((True,48),(False,48),(True,7),(False,5),(True,48)):
            width = w.width()
            w._set_island_expanded(expanded)
            assert w.width() == width  # no jump on retarget
            for _ in range(count):
                QTest.qWait(16)
                frame = Image.new("RGB",(940,320),"#7d8a99")
                island = png(w)
                frame.paste(island,((940-island.width)//2,0),island)
                frames.append(frame)
                stamps.append(round(1000*(time.monotonic()-started)))
        assert not w._geometry.timer.isActive() and w.notch_hub.isVisible()
        frames[0].save(out/"island-reveal.gif",save_all=True,append_images=frames[1:],
            duration=[max(16,b-a) for a,b in zip([0]+stamps[:-1],stamps)],loop=0)
        w.grab().save(str(out/"island-expanded.png"))
        sheet = Image.new("RGB",(940,320*6),"#7d8a99")
        for row,index in enumerate((2,6,12,50,55,62)):
            sheet.paste(frames[index],(0,row*320))
        sheet.save(out/"reveal-frames.jpg")
        w.hide()
        w._system_timer.stop()  # Manual desktop fixture; services=False owns no running modules.

        groups = w.modules.desktop
        groups.timer.stop()
        for title in ("Проекты","Материалы","Личное"):
            groups.store.add(title)
        panel = next(iter(groups.panels.values()))
        group = panel.group
        for name in ("Проект.txt","Задачи.txt","Идеи.txt","Ссылки.txt"):
            path = Path(folder)/name
            path.write_text("fixture",encoding="utf-8")
            groups.store.add_paths(group,[str(path)])
        # Force the old duplicate positions; repair must retain every reference.
        for record in groups.store.groups:
            record.update(x=.03,y=.12)
        groups.store.save()
        assert len({(p.x(),p.y()) for p in groups.panels.values()}) == len(groups.panels)
        groups.enabled = True
        groups.tick()
        panel.hover.stop()
        panel.collapse.stop()
        panel.animate(True)
        group_frames = []
        for _ in range(45):
            QTest.qWait(16)
            panel.collapse.stop()
            frame = Image.new("RGB",(520,560),"#7d8a99")
            group_image = png(panel)
            frame.paste(group_image,(20,20),group_image)
            group_frames.append(frame)
        assert not panel.animation.isActive() and panel.body.isVisible()
        panel.grab().save(str(out/"desktop-group.png"))
        assert panel.shelf.verticalScrollBar().maximum() == 0, panel.shelf.verticalScrollBar().maximum()
        menu = QMenu(panel)
        menu.addAction("Добавить файлы / ярлыки…")
        menu.addAction("Настроить группы…")
        menu.popup(panel.mapToGlobal(QPoint(panel.width()-35,38)))
        QTest.qWait(80)
        with patch("island.desktop_groups.anchor_desktop_panel",wraps=anchor_desktop_panel):
            for _ in range(5):
                groups.tick()
                QTest.qWait(80)
            assert panel.isVisible() and menu.isVisible()
        # Native z-order: the menu is reached before the panel walking downward.
        user.GetTopWindow.argtypes = (ctypes.c_void_p,)
        user.GetTopWindow.restype = ctypes.c_void_p
        user.GetWindow.argtypes = (ctypes.c_void_p,ctypes.c_uint)
        user.GetWindow.restype = ctypes.c_void_p
        order = []
        handle = user.GetTopWindow(None)
        for _ in range(1024):
            if not handle:
                break
            order.append(handle)
            handle = user.GetWindow(handle,2)
        assert order.index(int(menu.winId())) < order.index(int(panel.winId()))
        menu_image = png(menu)
        combined = Image.new("RGB",(850,560),"#7d8a99")
        panel_image = png(panel)
        combined.paste(panel_image,(20,20),panel_image)
        combined.paste(menu_image,(20+round((panel.width()-35)*panel.devicePixelRatioF()),
            20+round(38*panel.devicePixelRatioF())),menu_image)
        combined.save(out/"desktop-menu.png")
        menu.close()
        panel.collapse.stop()
        # A native file picker keeps its owning group visible throughout its modal loop.
        with panel.interacting():
            groups.tick()
            assert all(p.isVisible() for p in groups.panels.values())
        # Show Desktop can minimize tools independently of Qt visibility.
        hwnd = ctypes.c_void_p(int(panel.winId()))
        user.ShowWindow(hwnd,6)
        QTest.qWait(50)
        foreground = user.GetForegroundWindow()
        anchor_desktop_panel(panel)
        QTest.qWait(50)
        assert not user.IsIconic(hwnd)
        assert user.GetForegroundWindow() == foreground
        assert not user.GetWindowLongPtrW(hwnd,-20)&8  # not WS_EX_TOPMOST
        # DWMWA_EXCLUDED_FROM_PEEK is set-only; GetWindowAttribute cannot query it.
        assert exclude_from_peek(panel)
        panel.animate(False)
        for _ in range(45):
            QTest.qWait(16)
            frame = Image.new("RGB",(520,560),"#7d8a99")
            image = png(panel)
            frame.paste(image,(20,20),image)
            group_frames.append(frame)
        group_frames[0].save(out/"group-reveal.gif",save_all=True,append_images=group_frames[1:],duration=20,loop=0)
        # Ordinary windows cover persistent groups; no hide/show cycle on return.
        other = QWidget()
        other.setWindowTitle("Cloud Hub fixture")
        other.show()
        other.activateWindow()
        QTest.qWait(100)
        groups.tick()
        assert all(p.isVisible() for p in groups.panels.values())
        other.close()
        assert all(p.isVisible() for p in groups.panels.values())
        assert len(group["items"]) == 4 and all(Path(p).read_text()=="fixture" for p in group["items"])
        report = {"native_menu_above_group":True,"menu_does_not_raise_panels":True,
            "dialogs_keep_groups":True,"desktop_restore_without_focus":True,"peek_api_accepted":True,
            "panels_not_topmost":True,"overlap_repair":True,"references_preserved":True,
            "no_idle_animation":not panel.animation.isActive(),"content_and_shell_synchronized":True,
            "rapid_reversal_continuous":True,"ordinary_apps_cover_persistent_groups":True}
        (out/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report))
    finally:
        w.cleanup()
        w.hide()
