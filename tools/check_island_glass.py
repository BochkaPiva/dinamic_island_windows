# SPDX-License-Identifier: GPL-3.0-only
"""Actual per-pixel island material over an owned checkerboard; isolated access/data."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.entitlements import Grant,PRO_FEATURES,PRO_LIMITS
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
class Backdrop(QWidget):
 def paintEvent(self,event):
  p=QPainter(self)
  for y in range(0,self.height(),28):
   for x in range(0,self.width(),28):p.fillRect(x,y,28,28,QColor('#AEAEAE' if (x//28+y//28)%2 else '#292929'))
  p.fillRect(0,60,self.width(),80,QColor('#92543F'))
with tempfile.TemporaryDirectory() as folder:
 w=IslandWindow(Settings(folder),services=False);c=None
 w._system_timer.stop();w._notch_pointer_timer.stop();w._notch_pointer.enabled=False
 w._toggle_setting('hub_animations',False)
 backing=Backdrop(f=Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
 screen=app.primaryScreen();bounds=screen.geometry();backing.setGeometry(bounds.x(),bounds.y(),bounds.width(),400);backing.show()
 report=[]
 try:
  w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS))
  for form in ('notch','floating'):
   w._toggle_setting('island_style',form)
   for mode in ('black','glass'):
    w._toggle_setting('island_material',mode)
    for expanded in (False,True):
     w._set_island_expanded(expanded);w.show();w.raise_();w._island_auto_timer.stop();QTest.qWait(90)
     geom=w.geometry();area=geom.adjusted(-12,-12,12,18).intersected(screen.geometry())
     screen.grabWindow(0,area.x(),area.y(),area.width(),area.height()).save(str(out/f'{form}-{mode}-{"open" if expanded else "compact"}.png'))
     corners_clean=True
     if mode=='glass':
      actual=screen.grabWindow(0,area.x(),area.y(),area.width(),area.height()).toImage()
      w.hide();QTest.qWait(70);baseline=screen.grabWindow(0,area.x(),area.y(),area.width(),area.height()).toImage();w.show();QTest.qWait(70)
      ratio=actual.width()/area.width()
      for x in (1,geom.width()-2):
       px=round((geom.x()-area.x()+x)*ratio);py=round((geom.y()-area.y()+geom.height()-2)*ratio)
       corners_clean &= actual.pixelColor(px,py)==baseline.pixelColor(px,py)
      assert corners_clean,'Material leaked outside the rounded shape'
     report.append({'form':form,'mode':mode,'expanded':expanded,'translucent':w.island_material,'corners_clean':corners_clean,'mask_covers_center':w.mask().isEmpty() or w.mask().contains(w.rect().center())})
  w._toggle_setting('island_color','#327FAC');w._toggle_setting('island_material','glass');w._set_island_expanded(False);QTest.qWait(60)
  w.show_hub();c=w.control_center;c._setting('hub_animations',False);c.navigate('island');c.resize(1120,760);c.show();QTest.qWait(80)
  c.grab().save(str(out/'island-settings.png'))
  from island.color_ui import IslandColorDialog
  dialog=IslandColorDialog(c);dialog.show();QTest.qWait(80);dialog.grab().save(str(out/'color-picker.png'));dialog.reject();dialog.deleteLater()
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
 finally:
  w.cleanup();w.hide();backing.close()
  if c:c.hide()
