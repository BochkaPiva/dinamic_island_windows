# SPDX-License-Identifier: GPL-3.0-only
"""New workspace UI: own windows only, isolated notes/groups/preferences."""
import ctypes
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from island.app import IslandWindow
from island.media import Snapshot
from island.search import indexed_files
from island.storage import Settings

out = Path(sys.argv[1] if len(sys.argv)>1 else "build/workspace-check")
out.mkdir(parents=True,exist_ok=True)
def failure(kind,value,trace):
    import traceback
    (out/"error.txt").write_text("".join(traceback.format_exception(kind,value,trace)),encoding="utf-8")
    sys.__excepthook__(kind,value,trace)
sys.excepthook = failure
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as folder:
    w = IslandWindow(Settings(folder),services=False)
    w._notch_pointer.enabled = False
    try:
        w.show_hub()
        center = w.control_center
        for key in center.page_indices:
            center.navigate(key)
            QTest.qWait(80)
            center.grab().save(str(out/(key+".png")))
        w._handle_snapshot(Snapshot(title="The Elimination Angel",artist="Lustmord · Metavoid",has_session=True,
            aumid="demo",status="Playing",can_play=True,can_pause=True,can_prev=True,can_next=True,
            can_seek=True,pos_sec=44,dur_sec=276,sources=("demo",)))
        w.show()
        w._set_island_expanded(True)
        QTest.qWait(1000)
        w.grab().save(str(out/"island-overview.png"))
        cal = w.notch_hub.calendar
        assert cal.position == 0
        event = QWheelEvent(QPointF(60,40),QPointF(cal.mapToGlobal(QPoint(60,40))),
            QPoint(0,-64),QPoint(),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,False)
        app.sendEvent(cal,event)
        QTest.qWait(700)
        assert cal.position == 2
        w.grab().save(str(out/"island-calendar-scrolled.png"))
        cal.scroll_to(0)
        for index in (1,2):
            w.notch_hub.select_tab(index)
            QTest.qWait(240)
            w.grab().save(str(out/("island-"+str(index)+".png")))
        w._toggle_setting("timer_minutes",37)
        w.notch_hub.toggle_timer()
        assert 2218 <= w.notch_hub.timer_seconds() <= 2220
        center.navigate("library")
        notebook = center.notebook
        notebook.add()
        notebook.title.setText("Проверка сохранения")
        notebook.editor.setPlainText("Текст новой заметки")
        notebook.edited()
        notebook.flush()
        assert json.loads((Path(folder)/"notes.json").read_text(encoding="utf-8"))["notes"][0]["text"] == "Текст новой заметки"
        notebook.list.setCurrentRow(0)
        notebook.editor.setPlainText("Общая быстрая заметка")
        QTest.qWait(650)
        assert w.notch_hub.notes.toPlainText() == "Общая быстрая заметка"
        assert (Path(folder)/"notch-notes.txt").read_text(encoding="utf-8") == "Общая быстрая заметка"
        groups = w.modules.desktop
        group = groups.store.groups[0]
        link = Path(folder)/"Документ.txt"
        link.write_text("original",encoding="utf-8")
        groups.store.add_paths(group,[str(link)])
        panel = groups.panels[group["id"]]
        panel.shelf.reload()
        panel.show()
        panel.animate(True)
        QTest.qWait(500)
        panel.grab().save(str(out/"desktop-group.png"))
        assert panel.height() > 44
        assert link.read_text(encoding="utf-8") == "original"
        panel.hide()
        with patch("island.desktop_groups.desktop_is_foreground",return_value=True):
            groups.enabled = True
            groups.tick()
            assert all(p.isVisible() for p in groups.panels.values())
        # The settings window is an ordinary foreground app, not a desktop group.
        center.show()
        center.activateWindow()
        QTest.qWait(100)
        with patch("island.desktop_groups.desktop_is_foreground",return_value=False):
            groups.tick()
            assert all(not p.isVisible() for p in groups.panels.values())
        groups.enabled = False
        w._toggle_setting("paused",True)
        assert not groups.timer.isActive() and not w.modules.search.enabled
        w._toggle_setting("paused",False)
        center.close()
        # Public screenshots contain only our fixture command, never user files/apps.
        w.settings.set("search_files",False)
        w.modules.search.catalog=[]
        w.modules.search.catalog_loading=True
        w.modules.search.toggle()
        w.modules.search.input.setText("Таймер")
        QTest.qWait(2200)
        assert w.modules.search.results.count() > 0
        w.modules.search.grab().save(str(out/"search-palette.png"))
        rows,status = indexed_files("Cloud")
        report = {"calendar_touchpad_animated":True,"arbitrary_timer":True,"named_notes_saved":True,
            "quick_note_shared":True,"groups_retain_originals":True,"pause_stops_modules":True,
            "groups_desktop_only":True,
            "index_status":status,"indexed_results":len(rows)}
        (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=True))
    finally:
        w.cleanup()
        w.hide()
