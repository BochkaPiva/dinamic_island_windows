# SPDX-License-Identifier: GPL-3.0-only
import json
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from island.app import IslandWindow
from island.desktop_groups import GroupStore
from island.hotkey import HubHotkey, parse_shortcut
from island.search import index_sql, Result
from island.storage import Settings


class WorkspaceDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_invalid_ranges_and_boolean_integers_do_not_enter_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"settings.json"
            path.write_text(json.dumps({"compact_width":True,"island_opacity":900,"timer_minutes":0,"profile":"work"}))
            settings = Settings(folder)
            self.assertEqual(settings.get("compact_width"),180)
            self.assertEqual(settings.get("island_opacity"),100)
            self.assertEqual(settings.get("timer_minutes"),25)
            self.assertEqual(settings.get("profile"),"work")
            for key,value in (("compact_width",True),("island_opacity",101),("timer_minutes",1441)):
                with self.assertRaises(ValueError):
                    settings.set(key,value)

    def test_group_links_are_deduplicated_and_missing_links_survive_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder)/"original.txt"
            original.write_text("content")
            store = GroupStore(folder)
            group = store.groups[0]
            store.add_paths(group,[str(original),str(original)])
            self.assertEqual(group["items"],[str(original)])
            original.rename(original.with_suffix(".moved"))
            reloaded = GroupStore(folder)
            self.assertEqual(reloaded.groups[0]["items"],[str(original)])
            reloaded.remove(group["id"])
            self.assertEqual(original.with_suffix(".moved").read_text(),"content")

    def test_deliberately_empty_group_collection_stays_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            store = GroupStore(folder)
            for group in list(store.groups):
                store.remove(group["id"])
            self.assertEqual(GroupStore(folder).groups,[])

    def test_search_input_cannot_inject_sql_or_shell_text(self):
        sql = index_sql("' OR 1=1; $(Get-Secret) % _ %")
        self.assertNotIn("$",sql)
        self.assertNotIn(";",sql)
        self.assertNotIn("Get-Secret",sql)
        self.assertIn("System.FileName LIKE '%Secret%'",sql)
        self.assertEqual(index_sql("% _ ' ;"),"")

    def test_conflicting_hotkey_keeps_previous_registration(self):
        native = Mock()
        native.RegisterHotKey.side_effect = [1,0,1]
        with patch("island.hotkey.ctypes.windll.user32",native):
            key = HubHotkey(self.app,lambda:None)
            original_id = key.identifier
            self.assertTrue(key.registered)
            self.assertFalse(key.rebind("Alt+Space"))
            self.assertEqual(key.identifier,original_id)
            self.assertEqual(key.value,"Ctrl+Alt+H")
            native.UnregisterHotKey.assert_not_called()
            self.assertTrue(key.rebind("Ctrl+Alt+J"))
            native.UnregisterHotKey.assert_called_once_with(None,original_id)
            key.close()

    def test_shortcuts_require_modifiers_and_single_chords(self):
        self.assertEqual(parse_shortcut("Alt+Space"),(0x4001,0x20))
        self.assertIsNone(parse_shortcut(""))
        for value in ("A","Shift+A","Ctrl+A, Ctrl+B","Ctrl+Delete"):
            with self.assertRaises(ValueError):
                parse_shortcut(value)


class WorkspaceWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = IslandWindow(Settings(self.temp.name),services=False)
        self.w._notch_pointer.enabled = False
        self.w.show()

    def tearDown(self):
        self.w.cleanup()
        self.w.hide()
        self.w.deleteLater()
        QTest.qWait(20)
        self.temp.cleanup()

    def test_custom_geometry_keeps_fixed_panel_during_morph_and_center(self):
        w = self.w
        w._toggle_setting("compact_width",250)
        w._toggle_setting("compact_height",50)
        w._toggle_setting("expanded_width",720)
        self.assertEqual((w.width(),w.height()),(250,50))
        self.assertEqual(w.notch_hub.width(),720)
        w._set_island_expanded(True)
        QTest.qWait(70)
        self.assertEqual(w.notch_hub.width(),720)
        self.assertLessEqual(abs(w.x()+w.width()//2-(w.screen().geometry().x()+w.screen().geometry().width()//2)),1)

    def test_arbitrary_timer_pause_and_resume(self):
        hub = self.w.notch_hub
        hub.preset.setValue(37)
        self.assertEqual(hub.timer_seconds(),2220)
        self.assertEqual(Settings(self.temp.name).get("timer_minutes"),37)
        hub.toggle_timer()
        QTest.qWait(25)
        hub.toggle_timer()
        remaining = hub.timer_seconds()
        self.assertIsNone(hub._timer_end)
        hub.toggle_timer()
        self.assertGreater(hub._timer_end,0)
        self.assertEqual(hub.timer_seconds(),remaining)
        hub.reset_timer()
        self.assertEqual(hub.timer_seconds(),2220)

    def test_calendar_today_centered_touchpad_does_not_adjust_volume(self):
        cal = self.w.notch_hub.calendar
        self.assertEqual(cal.position,0)
        event = QWheelEvent(QPointF(60,40),QPointF(60,40),QPoint(0,-64),QPoint(),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
        with patch.object(self.w._volume_scroll,"handle") as volume:
            self.app.sendEvent(cal,event)
            QTest.qWait(650)
            self.assertEqual(cal.position,2)
            volume.assert_not_called()
        cal.scroll_to(0)
        QTest.qWait(300)
        self.assertEqual(cal.position,0)

    def test_named_notes_never_replace_quick_note(self):
        self.w.notch_hub.notes.setPlainText("quick original")
        self.w.show_hub()
        book = self.w.control_center.notebook
        book.add()
        book.title.setText("work")
        book.editor.setPlainText("named body")
        book.flush()
        self.assertEqual(self.w.notch_hub.notes.toPlainText(),"quick original")
        book.list.setCurrentRow(0)
        book.editor.setPlainText("shared edit")
        self.assertEqual(self.w.notch_hub.notes.toPlainText(),"shared edit")
        book.list.setCurrentRow(1)
        self.assertEqual(book.editor.toPlainText(),"named body")
        saved = json.loads((Path(self.temp.name)/"notes.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["notes"][0]["text"],"named body")

    def test_stale_search_results_do_not_replace_current_query(self):
        search = self.w.modules.search
        search.generation = 9
        search._set_rows([Result("current","","current")])
        search._completed(8,[Result("stale","","stale")],"")
        self.assertEqual(search.results.count(),1)
        self.assertEqual(search.results.item(0).data(Qt.ItemDataRole.UserRole).target,"current")

    def test_search_and_desktop_do_not_require_powertoys(self):
        self.w._toggle_setting("manage_powertoys",False)
        self.w._toggle_setting("profile","work")
        self.assertTrue(self.w.modules.search.enabled)
        self.w._toggle_setting("paused",True)
        self.assertFalse(self.w.modules.search.enabled)
        self.assertFalse(self.w.modules.desktop.timer.isActive())


if __name__ == "__main__":
    unittest.main()
