# SPDX-License-Identifier: GPL-3.0-only
"""Native settings interactions must survive the new window shell and themes."""
import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from island.app import IslandWindow
from island.storage import Settings
from island.hub_ui import ToggleSwitch,ModuleCard
from island import __version__


class HubDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w._system_timer.stop()
        self.w._notch_pointer_timer.stop()
        self.w._notch_pointer.enabled=False
        self.w.show_hub()
        self.center=self.w.control_center
        QTest.qWait(20)

    def tearDown(self):
        self.w.cleanup()
        self.center.deleteLater()
        self.w.hide()
        self.w.deleteLater()
        QTest.qWait(10)
        self.temp.cleanup()

    def test_page_search_keyboard_navigation_and_clear(self):
        c=self.center
        c.settings_search.setText('обновление')
        self.assertEqual(sum(not c.navigation.item(i).isHidden() for i in range(c.navigation.count())),1)
        QTest.keyClick(c.settings_search,Qt.Key.Key_Return)
        self.assertEqual(c.pages.currentIndex(),c.page_indices['updates'])
        c.navigate('desktop')
        self.assertEqual(c.settings_search.text(),'')
        self.assertTrue(all(not c.navigation.item(i).isHidden() for i in range(c.navigation.count())))
        c.settings_search.setText('nonexistent')
        self.assertTrue(c.search_empty.isVisible())

    def test_keyboard_switch_updates_preference_and_other_surface(self):
        toggle=self.center.module_switches['search_enabled']
        toggle.setFocus()
        QTest.keyClick(toggle,Qt.Key.Key_Space)
        self.assertFalse(self.w.settings.get('search_enabled'))
        self.assertFalse(self.center.checks['search_enabled'].isChecked())
        self.center.navigate('search')
        QTest.keyClick(self.center.checks['search_enabled'],Qt.Key.Key_Space)
        self.assertTrue(self.w.settings.get('search_enabled'))
        self.assertTrue(toggle.isChecked())

    def test_light_dark_and_reduced_motion_without_idle_animation(self):
        c=self.center
        original=c.timer_label.styleSheet()
        c._setting('hub_theme','light')
        self.assertNotEqual(c.timer_label.styleSheet(),original)
        self.assertIn(c.colors['text'],c.timer_label.styleSheet())
        c._setting('hub_theme','dark')
        self.assertEqual(c.timer_label.styleSheet(),original)
        c._setting('hub_animations',False)
        c.navigate('timer')
        self.assertNotEqual(c.transition.animation.state(),QAbstractAnimation.State.Running)
        c.hide()
        self.assertFalse(c.refresh_timer.isActive())
        self.assertFalse(c.focus_tick.isActive())
        for widget in c.findChildren(ToggleSwitch)+c.findChildren(ModuleCard):
            self.assertNotEqual(widget.animation.state(),QAbstractAnimation.State.Running)

    def test_refresh_keeps_uncommitted_number_input(self):
        c=self.center
        c.navigate('island')
        spin=c.values['compact_width']
        c.pages.currentWidget().ensureWidgetVisible(spin)
        spin.setFocus()
        QTest.qWait(10)
        spin.lineEdit().setText('219')
        c.refresh()
        self.assertEqual(spin.cleanText(),'219')
        QTest.keyClick(spin,Qt.Key.Key_Return)
        self.assertEqual(self.w.settings.get('compact_width'),219)

    def test_transition_completes_and_releases_cached_frames(self):
        c=self.center
        c.navigate('desktop')
        c.navigate('timer')
        QTest.qWait(260)
        self.assertFalse(c.transition.isVisible())
        self.assertIsNone(c.transition.old)
        self.assertEqual(c.pages.currentIndex(),c.page_indices['timer'])

    def test_update_install_flushes_notes_and_supplies_remaining_timer(self):
        hub=self.w.notch_hub
        hub._timer_end=time.monotonic()+75
        with patch.object(self.w.updates,'install') as install,patch.object(self.center.notebook,'flush') as flush:
            self.w._install_update()
            context=install.call_args.args[0]
            self.assertTrue(context['timer']['running'])
            self.assertLessEqual(context['timer']['remaining'],75)
            self.assertGreater(context['timer']['remaining'],70)
            flush.assert_called_once()


class TimerUpdateResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_real_window_restores_update_timer_and_consumes_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'update-resume.json'
            value={'at':time.time(),'version':__version__,'timer':{'remaining':90,'running':True,'deadline':time.time()+90}}
            path.write_text(json.dumps(value),encoding='utf-8')
            w=IslandWindow(Settings(folder),services=False)
            try:
                self.assertTrue(w.notch_hub._timer_end)
                self.assertGreater(w.notch_hub.timer_seconds(),85)
                self.assertFalse(path.exists())
                self.assertTrue(w.notch_hub.clock.isActive())
            finally:
                w.cleanup(); w.hide(); w.deleteLater(); QTest.qWait(10)


if __name__=='__main__': unittest.main()
