# SPDX-License-Identifier: GPL-3.0-only
"""Real battery loopback and a short alarm test, using only our isolated window."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt,QPoint,QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from island.app import IslandWindow
from island.storage import Settings

out=Path(sys.argv[1] if len(sys.argv)>1 else "build/audio-timer-check")
out.mkdir(parents=True,exist_ok=True)
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as folder:
    settings=Settings(folder)
    for key,value in (("updates",False),("profile","battery"),("desktop_enabled",False),
                      ("hotkey_hub",""),("hotkey_search",""),("hotkey_island","")):
        settings.set(key,value)
    w=IslandWindow(settings,services=True)
    w._notch_pointer.enabled=False
    levels=[]
    w.audio.levels_changed.connect(lambda values:levels.append(tuple(values)))
    try:
        w.show()
        w._update_services()
        QTest.qWait(1600)
        assert w._policy.profile=="battery" and not w._island_expanded
        assert w.audio.capture_active.is_set() and w.audio.economy.is_set()
        field=w.notch_hub.mini_time
        event=QWheelEvent(QPointF(15,10),QPointF(field.mapToGlobal(QPoint(15,10))),QPoint(),QPoint(0,120),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
        app.sendEvent(field,event)
        assert w.notch_hub.timer_seconds()==26*60
        w._show_panel()
        w.notch_hub.select_tab(1)
        QTest.qWait(700)
        w.activateWindow()
        QTest.qWait(100)
        field=w.notch_hub.timer_display
        QTest.mouseClick(field,Qt.MouseButton.LeftButton)
        QTest.qWait(30)
        QTest.keyClicks(field,"37")
        QTest.keyClick(field,Qt.Key.Key_Return)
        assert w.notch_hub.timer_seconds()==37*60,(field.text(),field.hasFocus(),w.notch_hub.timer_seconds())
        w.notch_hub._timer_end=time.monotonic()-.1
        w.notch_hub.tick()
        QTest.qWait(850) # One short audible chime; don't leave the test alarm running.
        assert w.notch_hub.alarm.active and w.notch_hub.alarm.sounding
        assert w._island_expanded and w.notch_hub.stack.currentIndex()==1
        w.grab().save(str(out/"timer-finished.png"))
        w.notch_hub.toggle_timer()
        assert not w.notch_hub.alarm.active and not w.notch_hub.alarm.sounding
        assert max((max(v) for v in levels),default=0)>.03,"Loopback did not see audio/chime"
        assert len({tuple(round(n,2) for n in v) for v in levels})>2,"Spectrum did not follow audio"
        w._set_island_expanded(False)
        QTest.qWait(600)
        assert w.audio.capture_active.is_set()
        w._toggle_setting("spectrum_battery_save",True)
        QTest.qWait(200)
        assert not w.audio.capture_active.is_set()
        w._toggle_setting("spectrum_battery_save",False)
        QTest.qWait(1000)
        assert w.audio.capture_active.is_set()
        report={"battery_compact_capture":True,"real_loopback_reacts":True,"wheel_duration":True,
                "direct_duration_input":True,"audible_alarm_started_and_stopped":True,
                "alarm_opens_focus":True,"explicit_battery_saving":True,"resumes_after_saving":True,
                "level_updates":len(levels),"peak":max(max(v) for v in levels)}
        (out/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report))
    finally:
        w.cleanup()
        w.hide()
