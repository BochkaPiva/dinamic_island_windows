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

    def test_context_actions_and_history_follow_current_page(self):
        c=self.center
        c.navigate('search');c.navigate('timer')
        c.travel(-1)
        self.assertEqual(c.navigation.currentRow(),c.page_indices['search'])
        self.assertEqual(c.page_action_spec()[0],'Открыть поиск')
        self.assertIn('Поиск',c.action_footer.context.text())
        c.travel(1)
        self.assertEqual(c.navigation.currentRow(),c.page_indices['timer'])
        c.travel(-1);c.navigate('desktop');c.travel(1)
        self.assertEqual(c.navigation.currentRow(),c.page_indices['desktop'])
        with patch.object(self.w.modules.desktop,'arrange') as arrange:
            c.run_page_action();arrange.assert_called_once()

    def test_footer_key_hints_are_visible_and_fit_at_minimum_width(self):
        from island.hub_ui import HintButton
        c=self.center;c.resize(900,600);QTest.qWait(20)
        actions=c.action_footer.findChildren(HintButton)
        self.assertEqual(len(actions),2)
        for action in actions:
            self.assertGreaterEqual(action.width(),action.minimumSizeHint().width())
            self.assertTrue(action.isVisible())
            self.assertGreater(action.caption.width(),20)
        actions[0].click()
        self.assertTrue(c.settings_search.hasFocus())

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
        from island.hub_ui import SettingsSection
        section=next(s for s in c.findChildren(SettingsSection) if s.title=='Размер и прозрачность')
        section.button.setChecked(True)
        QTest.qWait(250)
        spin=c.values['compact_width']
        c.pages.currentWidget().ensureWidgetVisible(spin)
        spin.setFocus()
        QTest.qWait(10)
        spin.lineEdit().setText('219')
        c.refresh()
        self.assertEqual(spin.cleanText(),'219')
        QTest.keyClick(spin,Qt.Key.Key_Return)
        self.assertEqual(self.w.settings.get('compact_width'),219)

    def test_preview_audio_is_coalesced_and_stops_when_page_hides(self):
        preview=self.center.hero_preview
        for _ in range(100): preview.audio_changed([.2]*5)
        self.assertTrue(preview.clock.isActive())
        self.center.navigate('timer')
        self.assertFalse(preview.clock.isActive())
        preview.audio_changed([.9]*5)
        self.assertFalse(preview.clock.isActive())

    def test_theme_and_preview_do_not_mutate_saved_groups(self):
        store=self.w.modules.desktop.store
        before=store.path.read_bytes()
        for theme in ('light','dark'):
            self.center._setting('hub_theme',theme)
            self.center.hero_preview.grab()
            for panel in self.w.modules.desktop.panels.values(): panel.configure()
            search=self.w.modules.search
            search.apply_brand_theme()
            self.assertIn(self.center.colors['text'],search.styleSheet())
        self.assertEqual(before,store.path.read_bytes())

    def test_focus_preview_edits_shared_timer_and_starts_it(self):
        self.center.catalog_buttons["timer"].click()
        QTest.qWait(20)
        self.center.overview_timer.setFocus()
        self.center.overview_timer.selectAll()
        QTest.keyClicks(self.center.overview_timer,'7')
        QTest.keyClick(self.center.overview_timer,Qt.Key.Key_Return)
        self.assertEqual(self.w.settings.get('timer_minutes'),7)
        self.center.overview_start.click()
        self.assertTrue(self.w.notch_hub._timer_end)
        self.center.refresh_timer_display()
        self.assertEqual(self.center.overview_start.text(),'Пауза')

    def test_transition_completes_and_releases_cached_frames(self):
        c=self.center
        c.navigate('desktop')
        c.navigate('timer')
        # Qt's first animation tick can be delayed under native/video test load.
        # Wait for completion rather than assuming a particular timer phase.
        deadline=time.monotonic()+1
        while c.transition.isVisible() and time.monotonic()<deadline: QTest.qWait(25)
        self.assertFalse(c.transition.isVisible())
        self.assertIsNone(c.transition.old)
        self.assertEqual(c.pages.currentIndex(),c.page_indices['timer'])

    def test_collapsed_navigation_has_keyboard_escape_and_keeps_page_ids(self):
        c=self.center
        c.toggle_sidebar()
        self.assertEqual(c.sidebar.width(),54)
        c.navigate('desktop')
        self.assertEqual(c.pages.currentIndex(),c.page_indices['desktop'])
        c.focus_settings_search()
        self.assertFalse(c.sidebar_collapsed)
        self.assertTrue(c.settings_search.hasFocus())
        self.assertTrue(all(c.navigation.item(i).toolTip() for i in range(c.navigation.count())))

    def test_catalog_shows_one_preview_and_stops_hidden_audio_and_focus_ticks(self):
        from island.module_preview import ModulePreview
        c=self.center
        c.catalog_buttons['timer'].click()
        self.assertTrue(c.overview_timer.isVisible())
        self.assertTrue(c.focus_tick.isActive())
        c.catalog_buttons['search'].click()
        self.assertFalse(c.focus_tick.isActive())
        self.assertFalse(c.hero_preview.clock.isActive())
        self.assertLessEqual(sum(p.isVisible() for p in c.catalog_stack.findChildren(ModulePreview)),1)

    def test_form_picker_shows_effective_access_without_erasing_saved_choice(self):
        c=self.center
        self.w.settings.set('island_style','floating')
        with patch.object(self.w,'floating_mode',return_value=False):
            c.refresh()
            self.assertEqual(c.style_picker.currentData(),'notch')
            self.assertEqual(c.island_preview.display_style,'notch')
            self.assertEqual(self.w.settings.get('island_style'),'floating')
        with patch.object(self.w,'floating_mode',return_value=True):
            c.refresh()
            self.assertEqual(c.style_picker.currentData(),'floating')

    def test_long_group_name_does_not_expand_editor_or_hide_panel_menu(self):
        from PySide6.QtCore import QPoint
        c=self.center;c._setting('hub_animations',False);c.resize(900,600);c.navigate('desktop')
        group=self.w.modules.desktop.store.groups[0]
        group['title']='Р'*60
        self.w.modules.desktop.store.changed.emit()
        QTest.qWait(30)
        self.assertEqual(c.pages.currentWidget().horizontalScrollBar().maximum(),0)
        self.assertEqual(c.group_editor.title.text(),'Р'*60)
        self.assertEqual(c.group_editor.title.toolTip(),'Р'*60)
        panel=self.w.modules.desktop.panels[group['id']]
        panel.header.layout().activate()
        point=panel.mapFromGlobal(panel.menu_button.mapToGlobal(QPoint(0,0)))
        self.assertLessEqual(point.x()+panel.menu_button.width(),panel.width())

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
