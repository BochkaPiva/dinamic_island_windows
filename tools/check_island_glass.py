# SPDX-License-Identifier: GPL-3.0-only
"""Actual per-pixel island material over an owned checkerboard; isolated access/data."""
import json,sys,tempfile,statistics,ctypes
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
     corners_clean=True;blur_contrast_ratio=None
     if mode=='glass':
      actual=screen.grabWindow(0,area.x(),area.y(),area.width(),area.height()).toImage()
      w.hide();QTest.qWait(70);baseline=screen.grabWindow(0,area.x(),area.y(),area.width(),area.height()).toImage();w.show();QTest.qWait(70)
      ratio=actual.width()/area.width()
      for x in (1,geom.width()-2):
       px=round((geom.x()-area.x()+x)*ratio);py=round((geom.y()-area.y()+geom.height()-2)*ratio)
       corners_clean &= actual.pixelColor(px,py)==baseline.pixelColor(px,py)
      assert corners_clean,'Material leaked outside the rounded shape'
      # Actual live backdrop must attenuate detail, not just darken the checker.
      start_x=geom.width()/2+30 if expanded else 29
      y=geom.height()-12 if expanded else geom.height()/2
      pixels=[(round((geom.x()-area.x()+start_x+i)*ratio),round((geom.y()-area.y()+y)*ratio)) for i in range(32)]
      before=[baseline.pixelColor(x,y).red() for x,y in pixels];after=[actual.pixelColor(x,y).red() for x,y in pixels]
      spread=statistics.pstdev(before)
      if spread>5:
       blur_contrast_ratio=statistics.pstdev(after)/spread
       assert blur_contrast_ratio<.15,('Background is translucent rather than blurred',form,expanded,blur_contrast_ratio)
     report.append({'form':form,'mode':mode,'expanded':expanded,'native_blur':w.island_material,'blur_contrast_ratio':blur_contrast_ratio,'corners_clean':corners_clean,'mask_covers_center':w.mask().isEmpty() or w.mask().contains(w.rect().center())})
  for color in ('#FFFFFF','#FFCC00','#2355AA'):
   w._toggle_setting('island_material','black');w._toggle_setting('island_color',color);w._set_island_expanded(True);QTest.qWait(70)
   g=w.geometry();screen.grabWindow(0,g.x(),g.y(),g.width(),g.height()).save(str(out/('solid-'+color[1:]+'.png')))
  w._toggle_setting('island_material','glass');w._set_island_expanded(False);QTest.qWait(80)
  backend=w._glass_backend;assert backend and backend.enabled
  native=int(backend.surface.winId());user=ctypes.WinDLL('user32');user.IsWindowEnabled.argtypes=(ctypes.c_void_p,);user.GetForegroundWindow.restype=ctypes.c_void_p
  assert not user.IsWindowEnabled(native);assert user.GetForegroundWindow()!=native
  for retreat in (.25,.65,1.,0.):
   w.card.set_retreat(retreat,.5);QTest.qWait(30)
   assert backend.enabled
  w.media_stage.begin('file','Native glass fixture');QTest.qWait(80);w.move(w.x()+60,w.y()+80);w.media_stage.close_media();QTest.qWait(80)
  from island.entitlements import COMMUNITY_BASE_FEATURES,FREE_LIMITS
  w.access.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS));w.access.changed.emit();QTest.qWait(20)
  assert not backend.surface.isVisible();assert not w.island_material
  w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS));w.access.changed.emit();QTest.qWait(40)
  assert w._glass_backend is backend and backend.enabled
  w.hide();QTest.qWait(20);assert not backend.surface.isVisible()
  w.show();QTest.qWait(40);assert backend.surface.isVisible()
  report.append({'lifecycle':True,'input_transparent':True,'expiry_hides_backdrop':True,'renewal_reuses_backdrop':True,'hide_and_show':True})
  w._toggle_setting('island_color','#327FAC');w._toggle_setting('island_material','glass');w._set_island_expanded(False);QTest.qWait(60)
  w.show_hub();c=w.control_center;c._setting('hub_animations',False);c.navigate('island');c.resize(1120,760);c.show();QTest.qWait(80)
  c.grab().save(str(out/'island-settings.png'))
  from island.color_ui import IslandColorDialog
  dialog=IslandColorDialog(c);dialog.show();QTest.qWait(80);dialog.grab().save(str(out/'color-picker.png'));dialog.reject();dialog.deleteLater()
  (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
 finally:
  w.cleanup();w.hide();backing.close()
  if c:c.hide()
