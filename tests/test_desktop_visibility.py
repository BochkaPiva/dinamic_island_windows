# SPDX-License-Identifier: GPL-3.0-only
"""Desktop ancestry must not trigger the full-screen hiding policy."""
import os
import unittest
from unittest.mock import Mock, patch
from island.platform_win import is_desktop_window, is_fullscreen
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


if __name__ == "__main__":
    unittest.main()
