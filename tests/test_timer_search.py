# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ["QT_QPA_PLATFORM"]="offscreen"
import tempfile
import time
import unittest
from unittest.mock import Mock
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from island.app import IslandWindow
from island.search import Result


class TimerSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        from island.storage import Settings
        self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w._notch_pointer.enabled=False
        self.hub=self.w.notch_hub
        self.hub.alarm.player=Mock()  # Unit tests never make an audible alarm.

    def tearDown(self):
        self.w.cleanup()
        self.w.deleteLater()
        QTest.qWait(20)
        self.temp.cleanup()

    def wheel(self,target,delta=120,pixel=0):
        event=QWheelEvent(QPointF(15,15),QPointF(15,15),QPoint(0,pixel),QPoint(0,delta),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
        self.app.sendEvent(target,event)

    def test_wheel_on_preview_changes_minutes_and_never_system_volume(self):
        volume=Mock()
        self.w._volume_scroll.handle=volume
        self.wheel(self.hub.mini_time)
        self.assertEqual(self.w.settings.get("timer_minutes"),26)
        self.assertEqual(self.hub.timer_seconds(),1560)
        self.wheel(self.hub.mini_time,-120)
        self.assertEqual(self.hub.timer_seconds(),1500)
        self.wheel(self.hub.mini_time,30)
        self.wheel(self.hub.mini_time,30)
        self.assertEqual(self.hub.timer_seconds(),1500)
        self.wheel(self.hub.mini_time,60)
        self.assertEqual(self.hub.timer_seconds(),1560)
        volume.assert_not_called()

    def test_direct_input_commits_and_escape_cancels(self):
        readout=self.hub.timer_display
        from PySide6.QtGui import QFocusEvent
        readout.focusInEvent(QFocusEvent(QFocusEvent.Type.FocusIn))
        readout.selectAll()
        QTest.keyClicks(readout,"37")
        QTest.keyClick(readout,Qt.Key.Key_Return)
        self.assertEqual(self.hub.timer_seconds(),2220)
        readout.focusInEvent(QFocusEvent(QFocusEvent.Type.FocusIn))
        readout.selectAll()
        QTest.keyClicks(readout,"99")
        QTest.keyClick(readout,Qt.Key.Key_Escape)
        self.assertEqual(self.hub.timer_seconds(),2220)

    def test_ticks_do_not_overwrite_in_progress_duration_edit(self):
        from PySide6.QtGui import QFocusEvent
        readout=self.hub.timer_display
        readout.focusInEvent(QFocusEvent(QFocusEvent.Type.FocusIn))
        readout.selectAll()
        QTest.keyClicks(readout,"43")
        self.hub.tick()
        self.assertEqual(readout.text(),"43")
        QTest.keyClick(readout,Qt.Key.Key_Return)
        self.assertEqual(self.hub.timer_seconds(),2580)

    def test_alarm_plays_once_on_completion_and_dismisses_without_restarting(self):
        alarm=self.hub.alarm
        self.hub._timer_end=time.monotonic()-.1
        self.hub.tick()
        self.assertTrue(alarm.active)
        self.assertTrue(alarm.sounding)
        self.assertTrue(alarm.limit.isActive())
        self.assertIn("Остановить",self.hub.timer_button.text())
        calls=alarm.player.call_count
        self.hub.tick()
        self.assertEqual(alarm.player.call_count,calls)
        self.hub.toggle_timer()
        self.assertFalse(alarm.active)
        self.assertFalse(alarm.sounding)
        self.assertIsNone(self.hub._timer_end)
        alarm.player.assert_called_with(None,0)

    def test_alarm_timeout_stops_sound_but_keeps_completion_visible(self):
        alarm=self.hub.alarm
        alarm.start()
        alarm.stop_sound()
        self.assertTrue(alarm.active)
        self.assertFalse(alarm.sounding)
        self.hub.reset_timer()
        self.assertFalse(alarm.active)

    def test_muted_alarm_still_displays_completion(self):
        self.w.settings.set("timer_sound",False)
        self.hub.alarm.start()
        self.assertTrue(self.hub.alarm.active)
        self.hub.alarm.player.assert_not_called()

    def test_empty_search_suggests_commands_and_results_never_require_horizontal_scroll(self):
        search=self.w.modules.search
        search._query("")
        self.assertEqual(search.results.count(),5)
        self.assertTrue(all(search.results.item(i).data(Qt.ItemDataRole.UserRole).kind=="command" for i in range(5)))
        self.assertEqual(search.results.item(0).data(Qt.ItemDataRole.UserRole+1),"Команды Nelviro")
        self.assertLessEqual(search.height(),460)
        self.assertEqual(search.results.horizontalScrollBarPolicy(),Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(search.results.verticalScrollBarPolicy(),Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        search._set_rows([Result("Very long title "*100,"C:/"+"folder/"*100,"target")])
        self.assertLessEqual(search.width(),720)


if __name__=="__main__":
    unittest.main()
