# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import unittest
import ctypes
from ctypes import wintypes
import tempfile
from unittest.mock import patch, Mock
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent, QInputDevice, QPointingDevice
from PySide6.QtWidgets import QApplication
from island.volume_scroll import VolumeScroll, NativeWheelSource
from island.platform_win import adjust_volume
from island.app import IslandWindow
from island.storage import Settings


def wheel(delta=120, inverted=False, pixel=0, device=None):
    return QWheelEvent(QPointF(40, 20), QPointF(40, 20), QPoint(0, pixel), QPoint(0, delta),
                       Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                       Qt.ScrollPhase.NoScrollPhase, inverted,
                       Qt.MouseEventSource.MouseEventNotSynthesized,
                       device or QPointingDevice.primaryPointingDevice())


class VolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mouse_wheel_is_not_globally_reversed(self):
        actions = []
        controller = VolumeScroll(actions.append)
        controller.handle(wheel(120), now=1)
        controller.handle(wheel(-120), now=2)
        self.assertEqual(actions, [1, -1])

    def test_window_handler_reproduces_and_corrects_the_reported_bug(self):
        with tempfile.TemporaryDirectory() as folder, patch("island.app.adjust_volume") as output:
            window = IslandWindow(Settings(folder), services=False)
            window._notch_pointer_timer.stop()
            try:
                source = Mock()
                source.device_for.return_value = 0x10
                window._volume_scroll.source = source
                window._volume_scroll.preference = lambda: False
                window.wheelEvent(wheel(120))  # touchpad: fingers down
                output.assert_called_once_with(-1)
                source.device_for.return_value = 0x02
                window.wheelEvent(wheel(120))  # mouse: wheel up
                self.assertEqual([c.args for c in output.call_args_list], [(-1,), (1,)])
            finally:
                window.cleanup()
                window.deleteLater()

    def test_native_metadata_is_matched_to_the_correct_wheel_event(self):
        bridge = NativeWheelSource(self.app)
        try:
            msg = wintypes.MSG()
            msg.message, msg.wParam, msg.time = 0x020A, 120 << 16, 1234
            with patch("island.volume_scroll.current_input_device", return_value=0x10):
                result = bridge.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
            self.assertEqual(result, (False, 0))
            event = wheel(120)
            stamped = Mock(wraps=event)
            stamped.timestamp.return_value = 1234
            self.assertEqual(bridge.device_for(stamped), 0x10)
            self.assertEqual(bridge.device_for(stamped), 0)
        finally:
            bridge.close()

    def test_windows_natural_touchpad_reported_as_mouse(self):
        # Reproduce the bug: Windows/Qt emits a positive wheel packet for a
        # downward finger gesture, without setting QWheelEvent.inverted().
        source = Mock()
        source.device_for.return_value = 0x10
        actions = []
        controller = VolumeScroll(actions.append, source, preference=lambda: False)
        controller.handle(wheel(120), now=1)
        controller.handle(wheel(-120), now=2)
        self.assertEqual(actions, [-1, 1])

    def test_reversed_windows_preference_uses_opposite_packet_sign(self):
        source = Mock()
        source.device_for.return_value = 0x10
        actions = []
        controller = VolumeScroll(actions.append, source, preference=lambda: True)
        controller.handle(wheel(-120), now=1)  # fingers down
        controller.handle(wheel(120), now=2)   # fingers up
        self.assertEqual(actions, [-1, 1])

    def test_qt_inversion_is_applied_once(self):
        source = Mock()
        source.device_for.return_value = 0x10
        actions = []
        controller = VolumeScroll(actions.append, source, preference=lambda: False)
        controller.handle(wheel(120, inverted=True), now=1)
        controller.handle(wheel(-120, inverted=True), now=2)
        self.assertEqual(actions, [-1, 1])

    def test_qt_touchpad_device_does_not_require_native_metadata(self):
        device = QPointingDevice("test pad", 7, QInputDevice.DeviceType.TouchPad,
                                  QPointingDevice.PointerType.Finger,
                                  QInputDevice.Capability.Position, 2, 0)
        actions = []
        controller = VolumeScroll(actions.append, preference=lambda: False)
        controller.handle(wheel(120, device=device), now=1)
        self.assertEqual(actions, [-1])

    def test_precision_packets_accumulate_and_reversal_resets_partial_step(self):
        actions = []
        controller = VolumeScroll(actions.append)
        for i in range(4):
            controller.handle(wheel(30), now=1+i*.02)
        self.assertEqual(actions, [1])
        controller.handle(wheel(30), now=1.1)
        controller.handle(wheel(-120), now=1.2)
        self.assertEqual(actions, [1, -1])
        controller.handle(wheel(30), now=2)
        controller.handle(wheel(90), now=3)  # old partial gesture has expired
        self.assertEqual(actions, [1, -1])

    def test_pixel_only_horizontal_and_zero_events(self):
        actions = []
        controller = VolumeScroll(actions.append)
        for i in range(5):
            controller.handle(wheel(0, pixel=-8), now=1+i*.02)
        self.assertEqual(actions, [-1])
        event = wheel(0)
        controller.handle(event, now=2)
        self.assertFalse(event.isAccepted())
        self.assertEqual(actions, [-1])

    def test_explicit_driver_override_and_windows_volume_keys(self):
        actions = []
        controller = VolumeScroll(actions.append)
        controller.handle(wheel(120), reverse=True, now=1)
        self.assertEqual(actions, [-1])
        user = Mock()
        with patch("island.platform_win.ctypes.windll.user32", user):
            adjust_volume(1)
            adjust_volume(-1)
        self.assertEqual([call.args[:3] for call in user.keybd_event.call_args_list],
                         [(0xAF, 0, 0), (0xAF, 0, 2), (0xAE, 0, 0), (0xAE, 0, 2)])


if __name__ == "__main__":
    unittest.main()
