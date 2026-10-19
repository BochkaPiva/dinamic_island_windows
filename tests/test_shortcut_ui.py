# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.shortcut_ui import ShortcutDialog,ShortcutButton

class Binding:
    def __init__(self,value):self.value=value;self.registered=True;self.error=''
    def suspend(self):self.registered=False
    def rebind(self,value):self.value=value;self.registered=bool(value);return True
    def close(self):self.registered=False

class ShortcutSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w._system_timer.stop();self.w._notch_pointer_timer.stop();self.w._notch_pointer.enabled=False
        self.w.show_hub();self.c=self.w.control_center;self.w.settings.set('hub_animations',False);self.c.navigate('shortcuts')
        self.w.hotkeys={key:Binding(self.w.settings.get(key)) for key in self.c.key_editors}
        self.d=ShortcutDialog(self.c,'hotkey_search','Быстрый поиск');self.d.show();QTest.qWait(10)
    def tearDown(self):
        self.d.reject();self.d.deleteLater();self.w.cleanup();self.c.hide();self.c.deleteLater();self.w.hide();self.w.deleteLater()
        QTest.qWait(10);self.temp.cleanup()
    def test_cancel_restores_bindings_without_persisting_capture(self):
        QTest.keyClick(self.d.capture,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(self.d.capture,Qt.Key.Key_Escape)
        self.assertEqual(self.w.settings.get('hotkey_search'),'Alt+Space')
        self.assertTrue(all(b.registered for b in self.w.hotkeys.values()))
    def test_enter_saves_and_restores_other_bindings(self):
        QTest.keyClick(self.d.capture,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(self.d.capture,Qt.Key.Key_Return)
        self.assertEqual(self.w.settings.get('hotkey_search'),'Ctrl+Alt+K')
        self.assertEqual(self.w.hotkeys['hotkey_search'].value,'Ctrl+Alt+K')
        self.assertTrue(all(b.registered for b in self.w.hotkeys.values()))
    def test_duplicate_keeps_old_setting_and_dialog(self):
        self.d.capture.value='Ctrl+Alt+H';self.d.apply()
        self.assertTrue(self.d.isVisible());self.assertTrue(self.d.error.isVisible())
        self.assertEqual(self.w.settings.get('hotkey_search'),'Alt+Space')
    def test_invalid_combo_does_not_write_settings(self):
        before=self.w.settings.path.read_bytes()
        QTest.keyClick(self.d.capture,Qt.Key.Key_K,Qt.KeyboardModifier.ShiftModifier)
        self.assertFalse(self.d.save_button.isEnabled());self.assertTrue(self.d.error.isVisible())
        self.assertEqual(before,self.w.settings.path.read_bytes())
    def test_native_letter_works_with_cyrillic_layout(self):
        event=QKeyEvent(QEvent.Type.KeyPress,0x0424,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier,0,0x41,0,'ф')
        QApplication.sendEvent(self.d.capture,event)
        self.assertEqual(self.d.capture.value,'Ctrl+Alt+A')
    def test_fallback_is_opaque_and_meta_round_trips(self):
        self.assertFalse(self.d.material)
        self.assertEqual(self.d.grab().toImage().pixelColor(20,20).alpha(),255)
        button=ShortcutButton('Win+Shift+L')
        self.assertEqual(button.keySequence().toString(),'Meta+Shift+L')
