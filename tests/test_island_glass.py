# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtGui import QColor,QImage,QPainter,QPainterPath
from PySide6.QtCore import QRectF,Qt
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.entitlements import Grant,PRO_FEATURES,PRO_LIMITS,COMMUNITY_BASE_FEATURES,FREE_LIMITS
from island.island_material import effective_appearance,paint_island,Appearance,smoke_color
from island.color_ui import IslandColorDialog

class IslandGlassTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.w=IslandWindow(Settings(self.temp.name),services=False)
  self.w._system_timer.stop();self.w._notch_pointer_timer.stop();self.w._notch_pointer.enabled=False
  self.w._toggle_setting('hub_animations',False)
 def tearDown(self):
  self.w.cleanup()
  if self.w.control_center:self.w.control_center.deleteLater()
  self.w.hide();self.w.deleteLater();QTest.qWait(5);self.temp.cleanup()
 def member(self):self.w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS));self.w.access.changed.emit()
 def free(self):self.w.access.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS));self.w.access.changed.emit()
 def dialog(self):
  self.member();self.w.show_hub();return IslandColorDialog(self.w.control_center)
 def test_default_black_and_strict_settings(self):
  s=self.w.settings;self.assertEqual(s.get('island_material'),'black');self.assertEqual(effective_appearance(self.w),Appearance())
  for key,value in [('island_material','acrylic'),('island_color','#fff'),('island_color','#GG0000'),('island_color','red')]:
   with self.subTest(value=value),self.assertRaises(ValueError):s.set(key,value)
  s.set('island_color','#ab239f');self.assertEqual(Settings(self.temp.name).get('island_color'),'#AB239F')
 def test_both_capabilities_denied_and_forged_settings_do_not_grant_access(self):
  self.free();self.assertFalse(self.w._toggle_setting('island_material','glass'));self.assertFalse(self.w._toggle_setting('island_color','#FFFFFF'))
  self.w.settings.set('island_material','glass');self.w.settings.set('island_color','#FFFFFF')
  self.assertEqual(effective_appearance(self.w),Appearance());self.w.refresh_island_material();self.assertFalse(self.w.island_material)
 def test_expiry_preserves_preferences_and_renewal_restores_them(self):
  self.member();self.w._toggle_setting('island_material','glass');self.w._toggle_setting('island_color','#327FAC')
  self.assertEqual(effective_appearance(self.w),Appearance(True,'#327FAC'))
  self.w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS),1)
  self.assertEqual(effective_appearance(self.w),Appearance())
  self.assertEqual(self.w.settings.get('island_material'),'glass');self.assertEqual(self.w.settings.get('island_color'),'#327FAC')
  self.member();self.assertEqual(effective_appearance(self.w),Appearance(True,'#327FAC'))
  self.w._toggle_setting('island_material','black');self.assertEqual(effective_appearance(self.w),Appearance())
 def test_classic_pixels_and_transparent_outside_glass(self):
  path=QPainterPath();path.addRoundedRect(QRectF(0,0,180,38),19,19)
  for appearance in (Appearance(),Appearance(True,'#FFFFFF')):
   image=QImage(180,38,QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
   p=QPainter(image);paint_island(p,path,appearance,native=True);p.end()
   self.assertEqual(image.pixelColor(0,0).alpha(),0)
   if not appearance.glass:self.assertEqual(image.pixelColor(90,19),QColor('black'))
   else:self.assertLess(image.pixelColor(90,19).alpha(),255)
  for value in ('#FFFFFF','#FFFF00','#FF0000','#00FF00','#0000FF'):self.assertLessEqual(smoke_color(value).valueF(),.171)
 def test_rgb_hex_and_cancel_preview_do_not_save(self):
  d=self.dialog();before=self.w.settings.path.read_bytes()
  d.hex_changed('#327FAC');self.assertEqual([s.value() for s in d.rgb],[50,127,172]);d.live_preview()
  self.assertEqual(self.w._island_color_preview,'#327FAC');self.assertEqual(self.w.settings.path.read_bytes(),before)
  d.hex_changed('#12');self.assertFalse(d.save_button.isEnabled());d.reject()
  self.assertIsNone(self.w._island_color_preview);self.assertEqual(self.w.settings.path.read_bytes(),before);d.deleteLater()
 def test_apply_persists_exact_rgb_and_failed_save_stays_open(self):
  d=self.dialog();d.choose(QColor(15,29,238));d.apply();self.assertEqual(d.result(),QDialog.DialogCode.Accepted)
  self.assertEqual(Settings(self.temp.name).get('island_color'),'#0F1DEE');d.deleteLater()
  d=self.dialog();d.choose(QColor('#123456'))
  with patch.object(self.w.settings,'set',side_effect=OSError('fixture read-only')):d.apply()
  self.assertNotEqual(d.result(),QDialog.DialogCode.Accepted);self.assertFalse(d.error.isHidden());d.reject();d.deleteLater()
 def test_loss_of_access_while_color_dialog_open_denies_save(self):
  d=self.dialog();d.choose(QColor('#ABCDEF'));self.free();d.apply()
  self.assertNotEqual(d.result(),QDialog.DialogCode.Accepted);self.assertEqual(self.w.settings.get('island_color'),'#000000');d.reject();d.deleteLater()
 def test_wheel_keyboard_brightness_and_no_black_trap(self):
  d=self.dialog();d.wheel.setFocus();QTest.keyClick(d.wheel,Qt.Key.Key_Right)
  self.assertGreater(d.color.value(),0)
  d.choose(QColor('#FF0000'));d.brightness.setValue(500);self.assertAlmostEqual(d.color.red(),128,delta=1)
  d.rgb[1].setValue(77);self.assertEqual(d.color.green(),77);self.assertTrue(d.save_button.isEnabled());d.reject();d.deleteLater()

 def test_glass_motion_uses_smooth_alpha_without_polygon_mask(self):
  self.member()
  with patch('island.native_material.island_transparency_available',return_value=True):
   self.w._toggle_setting('island_material','glass');self.w._toggle_setting('island_style','floating');self.w.show()
   self.assertTrue(self.w.mask().isEmpty())
   self.w.card.set_retreat(.8,.5);self.assertTrue(self.w.mask().isEmpty())
   self.w.card.set_retreat(0,.5);self.w.media_stage.begin('file','Fixture');QTest.qWait(20)
   self.assertTrue(self.w.mask().isEmpty());self.w.media_stage.close_media();QTest.qWait(20)
   self.assertFalse(self.w.media_stage.engaged)
 def test_optical_shape_contains_soft_shading_and_cached_illumination(self):
  from island.island_material import reflected_light
  path=QPainterPath();path.addRoundedRect(QRectF(0,0,180,38),19,19)
  image=QImage(360,76,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(2);image.fill(Qt.GlobalColor.transparent)
  p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing);paint_island(p,path,Appearance(True),native=True);p.end()
  self.assertEqual(image.pixelColor(0,0).alpha(),0)
  self.assertTrue(any(0<image.pixelColor(x,y).alpha()<100 for x in range(40) for y in range(20)))
  self.assertGreater(image.pixelColor(35,22).red(),image.pixelColor(180,38).red())
  self.assertIs(reflected_light(180,38),reflected_light(180,38))

if __name__=='__main__':unittest.main()
