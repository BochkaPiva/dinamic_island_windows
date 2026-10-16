# SPDX-License-Identifier: GPL-3.0-only
"""Own-window integration test: native click-through, edge dwell and live rendering."""
import ctypes
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
from island.app import IslandWindow
from island.media import Snapshot
from island.storage import Settings
from island.platform_win import keep_desktop_visible, exclude_from_peek

out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/native-check")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
with tempfile.TemporaryDirectory() as folder:
    under = QWidget(flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    bounds = app.primaryScreen().geometry()
    under.setGeometry(bounds.x(), bounds.top(), bounds.width(), 130)
    button = QPushButton("Own test tab", under)
    button.setGeometry(bounds.width()//2-60, 2, 120, 35)
    clicked = []
    button.clicked.connect(lambda: clicked.append(True))
    under.show()
    w = IslandWindow(Settings(folder), services=False)
    w._notch_pointer_timer.stop()
    w.show()
    w.raise_()
    QTest.qWait(100)
    w._notch_hover_timer.stop()
    center = bounds.x()+bounds.width()//2
    art = QPixmap(80, 80)
    art.fill(QColor("#426078"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    art.save(buffer, "PNG")
    w._handle_snapshot(Snapshot(title="Музыка рядом", artist="Cloud Island", has_session=True,
                       aumid="demo.player", status="Playing", thumb=bytes(buffer.data()),
                       can_play=True, can_pause=True, can_next=True, can_prev=True,
                       can_seek=True, pos_sec=42, dur_sec=211, sources=("demo.player",)))
    pointer = w._notch_pointer
    pointer.covered = True
    pointer.context_provider = lambda: True
    cursor = QPoint(center, bounds.top()+24)
    pointer.cursor_provider = lambda: cursor
    frames = []
    def capture():
        canvas = QPixmap(820, 320)
        canvas.fill(QColor("#e4e8ed"))
        p = QPainter(canvas)
        p.fillRect(0, 20, 820, 5, QColor("black"))
        p.fillRect(0, 25, 820, 32, QColor("#cdd4dd"))
        p.drawPixmap((820-w.width())//2, 25, w.grab())
        p.setPen(QColor("white"))
        p.setBrush(QColor("#48515f"))
        p.drawEllipse(QPointF(410+cursor.x()-center, 25+cursor.y()-bounds.top()), 4, 4)
        p.end()
        data = QBuffer()
        data.open(QIODevice.OpenModeFlag.WriteOnly)
        canvas.save(data, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(data.data()))).convert("RGB"))
    try:
        # This DWM attribute is set-only: DwmGetWindowAttribute returns
        # E_INVALIDARG. Require success from the real setter on each new HWND.
        peek_results = []
        def apply_peek(widget):
            result = exclude_from_peek(widget)
            peek_results.append((widget is w, result))
            return result
        with patch("island.app.exclude_from_peek", side_effect=apply_peek):
            w.hide()
            w.show()
            w.hide()
            w.destroy()
            w.show()
        assert peek_results == [(True, True), (True, True)], peek_results
        QTest.qWait(50)
        pointer.tick()
        assert pointer.passthrough
        class Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        user = ctypes.windll.user32
        user.WindowFromPoint.argtypes = [Point]
        user.WindowFromPoint.restype = ctypes.c_void_p
        user.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user.GetAncestor.restype = ctypes.c_void_p
        native = Point(round(bounds.width()/2*under.devicePixelRatioF()), round(22*under.devicePixelRatioF()))
        user.ClientToScreen(ctypes.c_void_p(int(under.winId())), ctypes.byref(native))
        assert int(user.GetAncestor(user.WindowFromPoint(native), 2)) == int(under.winId())
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert clicked == [True]
        for i in range(120):
            if i >= 25:
                phase = min(i-25, 119-i)/47
                cursor = QPoint(center+round(-72+144*phase), bounds.top()+28)
            pointer.tick()
            QTest.qWait(16)
            w.status_mark.set_spectrum((.2, .6, .8, .4, .3))
            capture()
        frames[0].save(out/"cloud-wave.gif", save_all=True, append_images=frames[1:], duration=16, loop=0)
        cursor = QPoint(center, bounds.top())
        panel_sizes = set()
        for _ in range(55):
            pointer.tick()
            QTest.qWait(20)
            panel_sizes.add((w.notch_hub.width(), w.notch_hub.height()))
        assert w._island_expanded and not pointer.passthrough
        assert (w.width(), w.height()) == w._scale_window_size(100)
        assert len(panel_sizes) == 1
        assert w.x()+w.width()//2 == center
        # Send wheel messages only to our own test window. Device identification
        # is supplied by a fixture; real Qt timestamps/routing remain intact.
        # The output callback is replaced, so no system volume is changed.
        w._notch_pointer.enabled = False
        actions = []
        w._volume_scroll.output = actions.append
        w._volume_scroll.preference = lambda: False
        position = w.mapToGlobal(QPoint(300, 5))
        scale = w.devicePixelRatioF()
        lparam = (round(position.x()*scale) & 0xffff) | ((round(position.y()*scale) & 0xffff) << 16)
        user.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        for device, expected in ((0x10, -1), (0x02, 1)):
            with patch("island.volume_scroll.current_input_device", return_value=device):
                assert user.PostMessageW(ctypes.c_void_p(int(w.winId())), 0x020A, 120 << 16, lparam)
                QTest.qWait(80)
            assert actions and actions[-1] == expected, (device, actions)
        # Simulate only our overlay being minimized/lowered, as can happen on
        # Show Desktop. Restore it above the fixture without stealing focus.
        under.activateWindow()
        button.setFocus()
        QTest.qWait(80)
        user.GetForegroundWindow.restype = ctypes.c_void_p
        foreground = user.GetForegroundWindow()
        geometry = w.geometry()
        user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user.SetWindowPos(ctypes.c_void_p(int(w.winId())), ctypes.c_void_p(-2), 0, 0, 0, 0, 0x213)
        w.showMinimized()
        QTest.qWait(50)
        assert user.IsIconic(ctypes.c_void_p(int(w.winId())))
        # Minimization can itself activate another window. Measure the recovery,
        # not that preceding OS activation, for the no-focus-stealing assertion.
        foreground = user.GetForegroundWindow()
        assert keep_desktop_visible(w)
        QTest.qWait(80)
        assert not user.IsIconic(ctypes.c_void_p(int(w.winId())))
        assert user.GetForegroundWindow() == foreground, "Desktop recovery stole keyboard focus"
        assert w.geometry() == geometry, "Desktop recovery changed the island bounds"
        user.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        assert user.GetWindowLongPtrW(ctypes.c_void_p(int(w.winId())), -20) & 0x8
        w.grab().save(str(out/"overview.png"))
        (out/"report.json").write_text(json.dumps({"click_through": True, "tab_click": True,
               "top_edge_open": True, "fixed_content": True, "centered": True,
               "volume_native_routing": True, "desktop_recovery": True,
               "focus_preserved": True, "peek_api_accepted": True,
               "peek_reapplied_after_recreation": True}), encoding="utf-8")
        print("Native routing, edge activation, desktop recovery and DWM Peek exclusion: PASS")
    finally:
        w.cleanup()
        w.hide()
        under.hide()
