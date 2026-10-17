# SPDX-License-Identifier: GPL-3.0-only
"""Desktop ancestry must not trigger the full-screen hiding policy."""
import os
import unittest
from unittest.mock import Mock, patch
from island.platform_win import (is_desktop_window, is_fullscreen, exclude_from_peek,
    anchor_desktop_panel, disable_window_transitions, apply_search_backdrop)
from island.motion import top_application


def hwnd(value):
    return value.value if hasattr(value, "value") else value


def windows(leaf="TMainBox", root=200, bounds=(0, 0, 1920, 1080)):
    user = Mock()
    user.GetForegroundWindow.return_value = 101
    user.GetShellWindow.return_value = 200
    user.GetAncestor.side_effect = lambda handle, flag: root if hwnd(handle) == 101 else hwnd(handle)
    classes = {101: leaf, 200: "Progman"}
    user.GetClassNameW.side_effect = lambda handle, text, length: setattr(text, "value", classes.get(hwnd(handle), "Unknown")) or 1
    user.GetWindowThreadProcessId.side_effect = lambda handle, pid: setattr(pid._obj, "value", 7) or 1
    user.IsIconic.return_value = False
    user.IsWindowVisible.return_value = True
    user.MonitorFromWindow.return_value = 300
    def rect(handle, pointer):
        for name, value in zip(("left", "top", "right", "bottom"), bounds):
            setattr(pointer._obj, name, value)
        return 1
    def monitor(handle, pointer):
        field = pointer._obj.bounds if hasattr(pointer._obj, "bounds") else pointer._obj.monitor
        for name, value in zip(("left", "top", "right", "bottom"), (0, 0, 1920, 1080)):
            setattr(field, name, value)
        return 1
    user.GetWindowRect.side_effect = rect
    user.GetMonitorInfoW.side_effect = monitor
    return user


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.owner = Mock()
        self.owner.winId.return_value = 1000
        self.owner.devicePixelRatioF.return_value = 1.0

    def test_custom_desktop_child_does_not_hide_or_trigger_avoidance(self):
        user = windows()
        with patch("island.platform_win.ctypes.windll.user32", user):
            self.assertTrue(is_desktop_window(101))
            self.assertFalse(is_fullscreen(self.owner))
            self.assertFalse(top_application(self.owner))

    def test_fullscreen_browser_and_file_explorer_still_hide(self):
        for name in ("Chrome_WidgetWin_1", "CabinetWClass", "TMainBox"):
            user = windows(leaf=name, root=101)
            with patch("island.platform_win.ctypes.windll.user32", user):
                self.assertFalse(is_desktop_window(101))
                self.assertTrue(is_fullscreen(self.owner))

    def test_maximized_work_area_is_not_fullscreen(self):
        user = windows(leaf="Chrome_WidgetWin_1", root=101, bounds=(0, 0, 1920, 1040))
        with patch("island.platform_win.ctypes.windll.user32", user):
            self.assertFalse(is_fullscreen(self.owner))

    def test_failed_geometry_query_does_not_hide_the_island(self):
        for method in ("GetWindowRect", "GetMonitorInfoW"):
            user = windows(leaf="Chrome_WidgetWin_1", root=101)
            getattr(user, method).side_effect = None
            getattr(user, method).return_value = 0
            with patch("island.platform_win.ctypes.windll.user32", user):
                self.assertFalse(is_fullscreen(self.owner))

    def test_peek_exclusion_targets_only_our_window_with_win32_bool(self):
        dwm = Mock()
        dwm.DwmSetWindowAttribute.return_value = 0
        with patch("island.platform_win.ctypes.windll.dwmapi", dwm):
            self.assertTrue(exclude_from_peek(self.owner))
        handle, attribute, value, size = dwm.DwmSetWindowAttribute.call_args.args
        self.assertEqual(hwnd(handle), 1000)
        self.assertEqual(attribute, 12)  # EXCLUDED_FROM_PEEK, not DISALLOW_PEEK
        self.assertEqual(value._obj.value, 1)
        self.assertEqual(size, 4)

    def test_peek_api_failure_does_not_crash_the_overlay(self):
        for failure in (-2147024809, OSError("DWM unavailable")):
            dwm = Mock()
            if isinstance(failure, Exception):
                dwm.DwmSetWindowAttribute.side_effect = failure
            else:
                dwm.DwmSetWindowAttribute.return_value = failure
            with patch("island.platform_win.ctypes.windll.dwmapi", dwm):
                self.assertFalse(exclude_from_peek(self.owner))

    def test_desktop_owner_targets_our_hwnd_and_never_raises_over_apps(self):
        user=Mock()
        user.GetShellWindow.return_value=200
        user.IsWindow.return_value=True
        user.IsWindowVisible.return_value=True
        user.IsIconic.return_value=False
        current=[None]
        user.GetWindow.side_effect=lambda h,flag:current[0]
        user.SetWindowLongPtrW.side_effect=lambda h,key,value:current.__setitem__(0,value)
        with patch("island.platform_win.ctypes.windll.user32",user):
            self.assertTrue(anchor_desktop_panel(self.owner))
            self.assertTrue(anchor_desktop_panel(self.owner))
        h,key,value=user.SetWindowLongPtrW.call_args.args
        self.assertEqual((hwnd(h),key,value),(1000,-8,200))
        user.SetWindowPos.assert_called_once()
        h,after,*rest=user.SetWindowPos.call_args.args
        self.assertEqual((hwnd(h),hwnd(after)),(1000,1))  # bottom, never topmost
        self.assertTrue(rest[-1]&0x10)  # NOACTIVATE
        user.GetForegroundWindow.assert_not_called()

    def test_desktop_waits_for_explorer_and_disables_fly_in_animation(self):
        user=Mock()
        user.GetShellWindow.return_value=None
        with patch("island.platform_win.ctypes.windll.user32",user):
            self.assertFalse(anchor_desktop_panel(self.owner))
        user.SetWindowLongPtrW.assert_not_called()
        dwm=Mock()
        dwm.DwmSetWindowAttribute.return_value=0
        with patch("island.platform_win.ctypes.windll.dwmapi",dwm):
            self.assertTrue(disable_window_transitions(self.owner))
        h,attribute,value,size=dwm.DwmSetWindowAttribute.call_args.args
        self.assertEqual((hwnd(h),attribute,value._obj.value,size),(1000,3,1,4))

    def test_layered_palette_does_not_request_the_rectangular_native_backplate(self):
        dwm=Mock()
        dwm.DwmSetWindowAttribute.return_value=0
        with patch("island.platform_win.ctypes.windll.dwmapi",dwm):
            self.assertFalse(apply_search_backdrop(self.owner))
        requests={args[1]:args[2]._obj.value for args,_ in dwm.DwmSetWindowAttribute.call_args_list}
        self.assertEqual(requests[38],1)  # NONE: native success did not mean visual support.
        self.assertEqual(requests[34],-2)  # DWMWA_COLOR_NONE


if __name__ == "__main__":
    unittest.main()
