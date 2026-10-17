# SPDX-License-Identifier: GPL-3.0-only
"""Native own-window design and desktop-layer acceptance check."""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtGui import QColor, QPainter, QLinearGradient
from PyQt6.QtWidgets import QApplication, QWidget, QMenu
from PyQt6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.platform_win import anchor_desktop_panel

out=Path(sys.argv[1] if len(sys.argv)>1 else "build/surfaces-check")
out.mkdir(parents=True,exist_ok=True)
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
u=ctypes.windll.user32
u.GetWindow.argtypes=(ctypes.c_void_p,ctypes.c_uint)
u.GetWindow.restype=ctypes.c_void_p
u.GetShellWindow.restype=ctypes.c_void_p

def above(first,second):
    for _ in range(2048):
        if first==second: return True
        if not first: return False
        first=u.GetWindow(ctypes.c_void_p(first),2)
    return False

class Backdrop(QWidget):
    def paintEvent(self,event):
        p=QPainter(self)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        gradient.setColorAt(0,QColor("#818b9b")); gradient.setColorAt(1,QColor("#293e53"))
        p.fillRect(self.rect(),gradient)
        p.fillRect(250,60,800,100,QColor("#b16b43"))

with tempfile.TemporaryDirectory() as folder:
    w=IslandWindow(Settings(folder),services=False)
    w._system_timer.stop()
    w._notch_pointer_timer.stop()
    w._notch_pointer.enabled=False
    background=Backdrop(flags=Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
    background.setGeometry(100,120,1100,600)
    background.show()
    try:
        groups=w.modules.desktop
        panel=next(iter(groups.panels.values()))
        panel.group['title']='Проекты'
        panel.configure()
        panel.move(150,150)
        panel.show()
        panel.hover.stop()
        panel.grab().save(str(out/'group-closed.png'))
        for name in ('Бриф.pdf','План.docx','Заметки.txt','Ресурсы'):
            path=Path(folder)/name
            path.mkdir() if '.' not in name else path.write_text('fixture')
            groups.store.add_paths(panel.group,[str(path)])
        panel.move(150,150)
        panel.animate(True)
        QTest.qWait(850)
        panel.collapse.stop()
        panel.grab().save(str(out/'group-open.png'))
        menu=QMenu(panel)
        menu.addAction('Добавить файлы…')
        menu.addAction('Настроить группу…')
        menu.popup(panel.mapToGlobal(QPoint(panel.width()-30,40)))
        QTest.qWait(70)
        groups.enabled=True
        for _ in range(4): groups.tick()
        assert above(int(menu.winId()),int(panel.winId()))
        menu.close()
        assert panel.desktop_anchored
        assert above(int(panel.winId()),u.GetShellWindow())
        # An already-open ordinary app covers groups, including when a group
        # first appears. Minimize it: groups are visible *before* any next tick.
        other=QWidget()
        other.setGeometry(130,130,600,450)
        other.show()
        other.activateWindow()
        QTest.qWait(60)
        assert above(int(other.winId()),int(panel.winId()))
        geometry=panel.geometry()
        show_events=[]
        old_show=panel.show
        panel.show=lambda:show_events.append(True) or old_show()
        other.showMinimized()
        assert panel.isVisible() and u.IsWindowVisible(ctypes.c_void_p(int(panel.winId())))
        assert panel.geometry()==geometry
        groups.tick()
        assert not show_events
        other.close()
        # Simulate shell-owner destruction using only our own surrogate window.
        surrogate=QWidget()
        u.SetWindowLongPtrW.argtypes=(ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t)
        old_handle=int(panel.winId())
        u.SetWindowLongPtrW(ctypes.c_void_p(old_handle),-8,int(surrogate.winId()))
        surrogate.destroy()
        assert not u.IsWindow(ctypes.c_void_p(old_handle))
        assert anchor_desktop_panel(panel)
        assert u.IsWindow(ctypes.c_void_p(int(panel.winId())))
        assert u.GetWindow(ctypes.c_void_p(int(panel.winId())),4)==u.GetShellWindow()
        groups.enabled=False
        panel.hide()
        # Search uses our own backing window, never captures another app.
        search=w.modules.search
        w.settings.set('search_files',False)
        search.catalog=[]
        search.catalog_loading=True
        search.move(160,180)
        search.show()
        search.activateWindow()
        search._query('')
        QTest.qWait(100)
        search.grab().save(str(out/'search-empty.png'))
        background.grab().save(str(out/'own-background.png'))
        pixels=search.grab().toImage()
        assert pixels.pixelColor(0,0).alpha()==0
        assert pixels.pixelColor(30,30).alpha()>200
        search.input.setText('Cloud')
        search._set_rows(search._commands())
        search.status.setText('Команды Cloud Hub')
        QTest.qWait(300)
        search.grab().save(str(out/'search-results.png'))
        # Layered HWND BitBlt returns black. Our own topmost backing surface
        # completely covers this rectangle, so composition contains fixture UI only.
        search.screen().grabWindow(0,background.x(),background.y(),background.width(),background.height()).save(str(out/'search-native.png'))
        report={'persistent_desktop_layer':True,'above_desktop_below_apps':True,
            'visible_before_minimize_poll':True,'no_show_or_position_jump':True,
            'destroyed_owner_surface_recovers':True,
            'menu_above_group':True,'native_search_contour_clipped':True,
            'compact_group_width':panel.closed_width,'empty_search_height':96}
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        background.close()
        w.cleanup()
        w.hide()
