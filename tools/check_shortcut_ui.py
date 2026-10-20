# SPDX-License-Identifier: GPL-3.0-only
"""Native shortcut sheet and composition QA against our own topmost fixture."""
from pathlib import Path
import json,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.shortcut_ui import ShortcutDialog
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
 w=IslandWindow(Settings(folder),services=False)
 w._system_timer.stop();w._notch_pointer_timer.stop();w._notch_pointer.enabled=False
 try:
  w.show_hub();c=w.control_center;c._setting('hub_animations',False)
  c.resize(1120,760);c.navigate('shortcuts')
  c.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);c.show()
  d=ShortcutDialog(c,'hotkey_search','Быстрый поиск')
  d.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);d.show();d.raise_();d.activateWindow();QTest.qWait(300)
  QTest.keyClick(d.capture,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier)
  assert d.capture.value=='Ctrl+Alt+K'
  QTest.keyClick(d.capture,Qt.Key.Key_L,Qt.KeyboardModifier.MetaModifier|Qt.KeyboardModifier.ShiftModifier)
  assert d.capture.value=='Meta+Shift+L'
  QTest.qWait(100)
  # Direct grabs show alpha without DWM; use composition over our own complete window.
  screen=d.screen();shot=screen.grabWindow(0,d.x(),d.y(),d.width(),d.height())
  shot.save(str(out/'shortcut-sheet-native.png'))
  d.reject();QTest.qWait(50)
  assert w.settings.get('hotkey_search')=='Alt+Space'
  c.grab().save(str(out/'shortcut-list.png'))
  d=ShortcutDialog(c,'hotkey_search','Быстрый поиск');d.show()
  QTest.keyClick(d.capture,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier)
  d.apply();assert w.settings.get('hotkey_search')=='Ctrl+Alt+K'
  d=ShortcutDialog(c,'hotkey_search','Быстрый поиск');d.show()
  d.capture.value='Ctrl+Alt+H';d.apply()
  assert d.isVisible() and d.error.isVisible()
  assert w.settings.get('hotkey_search')=='Ctrl+Alt+K'
  d.reject()
  report={'native_material':d.material,'cancel_preserves_value':True,'save_persists':True,'duplicate_keeps_dialog_and_old_value':True}
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  print(json.dumps(report))
 finally:w.cleanup();w.hide();c.hide()
