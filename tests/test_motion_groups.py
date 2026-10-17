# SPDX-License-Identifier: GPL-3.0-only
"""Regressions for content escaping the shell and overlapping desktop tools."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QRect, QPointF
from PyQt6.QtGui import QPainterPathStroker
from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings


class MotionGroupTests(unittest.TestCase):
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
        QTest.qWait(10)
        self.temp.cleanup()

    def test_morph_clips_all_content_and_hands_back_live_controls(self):
        w = self.w
        w.notch_hub.setStyleSheet("background:#ff00ff;")
        w._set_island_expanded(True)
        cw,ch = w._scale_window_size(50)
        pw,ph = w._scale_window_size(100)
        for progress in (.15,.4,.7,.93):
            width,height = round(cw+(pw-cw)*progress),round(ch+(ph-ch)*progress)
            w._geo_anim_step(QRect(w.x(),w.y(),width,height))
            self.assertFalse(w.notch_hub.isVisible())
            self.assertTrue(w._notch_stage.reveal.isVisible())
            image = w.grab().toImage()
            ratio = image.devicePixelRatio()
            path = w.card.notch_path()
            stroke = QPainterPathStroker()
            stroke.setWidth(3)
            safe = path.united(stroke.createStroke(path))
            for x in range(0,width,3):
                for y in range(0,height,3):
                    if not safe.contains(QPointF(x+.5,y+.5)):
                        self.assertLess(image.pixelColor(round(x*ratio),round(y*ratio)).alpha(),20,(progress,x,y))
        w._geometry.stop()
        w._geo_anim_step(QRect(w.x(),w.y(),pw,ph))
        self.assertTrue(w.notch_hub.isVisible())
        self.assertFalse(w._notch_stage.reveal.isVisible())
        w._set_island_expanded(False)
        QTest.qWait(60)
        width = w.width()
        w._set_island_expanded(True)
        self.assertEqual(w.width(),width)
        QTest.qWait(850)
        self.assertTrue(w.notch_hub.isVisible())

    def test_new_groups_do_not_overlap_and_repair_preserves_data(self):
        manager = self.w.modules.desktop
        for _ in range(5):
            manager.store.add()
        panels = list(manager.panels.values())
        for i,panel in enumerate(panels):
            for other in panels[i+1:]:
                self.assertFalse(QRect(panel.pos(),panel.size()).intersects(QRect(other.pos(),other.size())))
        original = [(g["id"],g["title"],g["items"][:]) for g in manager.store.groups]
        for group in manager.store.groups:
            group.update(x=.03,y=.12)
        manager.store.save()
        self.assertEqual(original,[(g["id"],g["title"],g["items"]) for g in manager.store.groups])
        positions = {(p.x(),p.y()) for p in panels}
        self.assertEqual(len(positions),len(panels))
        self.assertTrue(manager.store.path.with_suffix(".before-arrange.json").exists())
        manager.arrange()
        first = [(g["x"],g["y"]) for g in manager.store.groups]
        manager.arrange()
        self.assertEqual(first,[(g["x"],g["y"]) for g in manager.store.groups])

    def test_group_reversal_retains_velocity_and_empty_group_is_compact(self):
        panel = next(iter(self.w.modules.desktop.panels.values()))
        panel.show()
        panel.animate(True)
        QTest.qWait(65)
        height,velocity = panel.height(),panel.extent.velocity
        panel.animate(False)
        self.assertEqual(panel.height(),height)
        self.assertEqual(panel.extent.velocity,velocity)
        QTest.qWait(45)
        panel.animate(True)
        QTest.qWait(800)
        self.assertEqual(panel.height(),112)
        self.assertTrue(panel.body.isVisible())
        self.assertFalse(panel.animation.isActive())
        for _ in range(4):
            panel.animate(True)
        self.assertFalse(panel.animation.isActive())
        self.assertFalse(panel.search.isVisible())

    def test_group_menu_and_native_dialog_do_not_hide_or_raise_panels(self):
        groups = self.w.modules.desktop
        groups.enabled = True
        panel = next(iter(groups.panels.values()))
        with patch("island.desktop_groups.anchor_desktop_panel",return_value=True) as anchor:
            groups.tick()
            menu = QMenu(panel)
            menu.addAction("Настройки")
            menu.popup(panel.mapToGlobal(panel.rect().bottomRight()))
            self.app.processEvents()
            groups.tick()
            self.assertTrue(panel.isVisible())
            groups.tick()
            self.assertTrue(panel.isVisible())
            self.assertTrue(anchor.called)
            menu.close()
        with patch("island.desktop_groups.anchor_desktop_panel",return_value=True):
            with panel.interacting():
                groups.tick()
                self.assertTrue(panel.isVisible())

    def test_group_data_changes_refresh_live_grid_without_moving_originals(self):
        groups = self.w.modules.desktop
        panel = next(iter(groups.panels.values()))
        panel.show()
        panel.animate(True)
        QTest.qWait(800)
        link = Path(self.temp.name)/"document.txt"
        link.write_text("original")
        groups.store.add_paths(panel.group,[str(link)])
        QTest.qWait(800)
        self.assertEqual(panel.shelf.paths(),[str(link)])
        self.assertTrue(panel.search.isVisible())
        self.assertGreater(panel.height(),112)
        self.assertEqual(link.read_text(),"original")
        saved = json.loads(groups.store.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["groups"][0]["items"],[str(link)])

    def test_live_width_changes_resize_body_without_reflow_during_reveal(self):
        panel = next(iter(self.w.modules.desktop.panels.values()))
        panel.show()
        panel.animate(True)
        QTest.qWait(800)
        self.w.settings.set("group_width",420)
        panel.configure()
        QTest.qWait(50)
        self.assertEqual(panel.body.width(),420)
        self.assertTrue(panel.body.isVisible())
        height = panel.body.height()
        panel.animate(False)
        QTest.qWait(80)
        self.assertEqual(panel.body.height(),height)
        self.assertFalse(panel.body.isVisible())

    def test_foreground_changes_do_not_show_hide_or_move_desktop_tiles(self):
        groups=self.w.modules.desktop
        groups.enabled=True
        panel=next(iter(groups.panels.values()))
        with patch("island.desktop_groups.anchor_desktop_panel",return_value=True):
            groups.tick()
            bounds=panel.geometry()
            with patch.object(panel,"show") as show,patch.object(panel,"hide") as hide:
                for _ in range(10):
                    groups.tick()
                show.assert_not_called()
                hide.assert_not_called()
            self.assertEqual(panel.geometry(),bounds)


if __name__ == "__main__":
    unittest.main()
