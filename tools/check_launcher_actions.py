# SPDX-License-Identifier: GPL-3.0-only
"""Native launcher composition and actual context actions over owned Qt windows."""
from pathlib import Path
import json,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget,QMenu
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
 w=IslandWindow(Settings(folder),services=False)
 w._system_timer.stop();w._notch_pointer_timer.stop();w._notch_pointer.enabled=False
 backing=QWidget();backing.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
 backing.setStyleSheet('background:#202020;');backing.setGeometry(20,20,1160,800);backing.show()
 try:
  w.show_hub();c=w.control_center;c._setting('hub_animations',False);c._setting('hub_theme','dark')
  c.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True);c.setGeometry(40,40,1120,760);c.show();c.raise_();c.activateWindow();QTest.qWait(200)
  for page in ('hub','integrations','shortcuts','account','desktop','island','timer','search','library'):
   c.navigate(page);c.feedback.hide();QTest.qWait(100)
   c.screen().grabWindow(0,c.x(),c.y(),c.width(),c.height()).save(str(out/(page+'-native.png')))
  from island.settings_pages import PAGES
  for title,name in (('Поведение','behavior'),('Размер и прозрачность','appearance'),('Оформление групп','group-appearance')):
   section=next(section for section in c.subpages if section.title==title)
   c.navigate(PAGES[section.parent_index][0]);section.click();c.feedback.hide();QTest.qWait(100)
   c.screen().grabWindow(0,c.x(),c.y(),c.width(),c.height()).save(str(out/(name+'-native.png')))
  search=w.modules.search
  search.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
  search._query('');search.move(c.x()+190,c.y()+120);search.show();search.raise_();search.activateWindow();QTest.qWait(250)
  assert c.geometry().contains(search.geometry())
  assert search.results.count()==5
  search.screen().grabWindow(0,search.x(),search.y(),search.width(),search.height()).save(str(out/'launcher-native.png'))
  def inspect_menu():
   menu=QApplication.activePopupWidget()
   assert isinstance(menu,QMenu)
   assert [a.text() for a in menu.actions() if not a.isSeparator()]==['Открыть','Настройки поиска']
   menu.close()
  QTimer.singleShot(80,inspect_menu);search.show_actions();QTest.qWait(40)
  assert search.isVisible() and search.input.hasFocus()
  search.open_settings();QTest.qWait(40)
  assert not search.isVisible() and c.navigation.currentRow()==c.page_indices['search']
  report={'native_material':search.backdrop_applied,'menu_keeps_launcher_visible':True,'settings_action_navigates':True,'empty_query_commands':5,'screenshots':'owned Qt fixture'}
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
 finally:w.cleanup();w.hide();c.hide();backing.close()
