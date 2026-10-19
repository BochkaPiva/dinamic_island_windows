# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile
import unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.entitlements import Grant,PRO_FEATURES,PRO_LIMITS,COMMUNITY_BASE_FEATURES,FREE_LIMITS
from island.window_layouts import Window,zones,place_window


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w._system_timer.stop();self.w._notch_pointer_timer.stop()
        self.w._notch_pointer.enabled=False
        self.w.show();QTest.qWait(10)

    def tearDown(self):
        self.w.cleanup()
        if self.w.control_center: self.w.control_center.hide();self.w.control_center.deleteLater()
        self.w.hide();self.w.deleteLater();QTest.qWait(10);self.temp.cleanup()

    def supporter(self): self.w.access.grant=Grant('supporter',PRO_FEATURES,dict(PRO_LIMITS))

    def test_floating_access_gap_and_safe_expiry_fallback(self):
        w=self.w
        self.assertFalse(w._toggle_setting('island_style','floating'))
        self.supporter()
        before=w.modules.desktop.store.path.read_bytes()
        self.assertTrue(w._toggle_setting('island_style','floating'))
        self.assertEqual(w.y(),w.screen().geometry().top()+16)
        self.assertFalse(w.card.notch_path().contains(QPointF(1,1)))
        w._set_island_expanded(True);QTest.qWait(750)
        self.assertEqual(w.y(),w.screen().geometry().top()+16)
        w.access.grant=Grant('free',COMMUNITY_BASE_FEATURES,dict(FREE_LIMITS))
        w.access.changed.emit()
        self.assertFalse(w.floating_mode())
        self.assertEqual(w.settings.get('island_style'),'floating')
        self.assertEqual(w.y(),w.screen().geometry().top())
        self.assertEqual(before,w.modules.desktop.store.path.read_bytes())

    def test_fullscreen_reversal_is_continuous_and_has_no_stale_hide(self):
        w=self.w
        with patch('island.app.is_fullscreen',return_value=True) as fullscreen,patch('island.app.desktop_is_foreground',return_value=False):
            w._sync_visibility()
            self.assertTrue(w.isVisible())
            QTest.qWait(70)
            middle=w._visibility.fraction
            self.assertGreater(middle,0);self.assertLess(middle,1)
            fullscreen.return_value=False
            w._sync_visibility()
            self.assertEqual(w._visibility.fraction,middle)
            QTest.qWait(380)
            self.assertTrue(w.isVisible());self.assertAlmostEqual(w._visibility.fraction,1)
            fullscreen.return_value=True;w._sync_visibility();QTest.qWait(260)
            self.assertFalse(w.isVisible())
            self.assertFalse(w._visibility.moving)

    def test_reduced_motion_changes_visibility_without_timer(self):
        self.w.settings.set('hub_animations',False)
        self.w._visibility.set_visible(False)
        self.assertFalse(self.w.isVisible());self.assertFalse(self.w._visibility.moving)
        self.w._visibility.set_visible(True)
        self.assertTrue(self.w.isVisible());self.assertEqual(self.w._visibility.fraction,1)

    def test_page_scroll_is_inertial_and_stops_when_hidden(self):
        w=self.w;w.show_hub();c=w.control_center;c.resize(900,600);QTest.qWait(60)
        scroll=c.pages.currentWidget();bar=scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(),60)
        bar.setValue(0)
        event=QWheelEvent(QPointF(20,20),QPointF(20,20),QPoint(),QPoint(0,-120),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        scroll.smooth_scroll.wheel(event)
        self.assertEqual(bar.value(),0)
        QTest.qWait(60)
        self.assertGreater(bar.value(),0);self.assertLess(bar.value(),60)
        c.navigate('island')
        self.assertFalse(scroll.smooth_scroll.timer.isActive())


class WindowPlacementTests(unittest.TestCase):
    def test_zones_respect_negative_monitor_origin_work_area_and_gaps(self):
        result=zones((-1920,40,0,1080),'thirds',8)
        self.assertEqual(len(result),3)
        for i,(x,y,width,height) in enumerate(result):
            self.assertGreaterEqual(x,-1920);self.assertEqual(y,48)
            self.assertEqual(y+height,1072)
            self.assertLessEqual(x+width,0)
            if i: self.assertEqual(x-(result[i-1][0]+result[i-1][2]),16)

    def test_reused_handle_is_not_moved(self):
        user=Mock();user.IsWindow.return_value=True
        user.GetWindowThreadProcessId.side_effect=lambda h,p:setattr(p._obj,'value',99)
        with patch('island.window_layouts.api',return_value=user):
            ok,_=place_window(Window(10,101,'closed'),'halves',0)
        self.assertFalse(ok);user.SetWindowPos.assert_not_called()

    def test_minimum_size_is_checked_before_restoring_or_moving(self):
        user=Mock();user.IsWindow.return_value=True
        user.GetWindowThreadProcessId.side_effect=lambda h,p:setattr(p._obj,'value',99)
        def monitor(h,p):
            for key,value in zip(('left','top','right','bottom'),(0,0,1920,1040)): setattr(p._obj.work,key,value)
            return 1
        user.GetMonitorInfoW.side_effect=monitor;user.GetDpiForWindow.return_value=96
        def minimum(h,message,wparam,address,*args):
            import ctypes
            # MINMAXINFO: reserved, max size, max position, min track, max track.
            points=ctypes.cast(address,ctypes.POINTER(ctypes.c_long))
            points[6]=1200;points[7]=300
            return 1
        user.SendMessageTimeoutW.side_effect=minimum
        with patch('island.window_layouts.api',return_value=user):
            ok,message=place_window(Window(10,99,'wide app'),'thirds',0)
        self.assertFalse(ok);self.assertIn('Минимальный',message)
        user.ShowWindow.assert_not_called();user.SetWindowPos.assert_not_called()
