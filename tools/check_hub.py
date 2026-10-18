# SPDX-License-Identifier: GPL-3.0-only
"""Own-window native profile, service-suspension and visual smoke check."""
import json
import ctypes
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.control_center import ProcessUsage

out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/hub-check")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as directory:
    settings = Settings(directory)
    settings.set("updates", False)
    settings.set("profile", "work")
    # Alt+Space may belong to a user's other launcher; don't reconfigure it.
    settings.set("hotkey_search", "Ctrl+Alt+Space")
    # Keep a running installed instance's bindings intact during source checks.
    settings.set("hotkey_hub","Ctrl+Alt+F10")
    settings.set("hotkey_search","Ctrl+Alt+F11")
    settings.set("hotkey_island","Ctrl+Alt+F12")
    with patch("island.app.is_fullscreen", return_value=False), patch("island.app.desktop_is_foreground", return_value=False):
        w = IslandWindow(settings, services=True)
        w._notch_pointer.enabled = False  # Fixture controls expansion, not the user's real cursor.
        try:
            w.show()
            w._update_services()
            QTest.qWait(1800)
            assert w.worker.poll_active.is_set(), "Media did not start"
            assert w.audio.capture_active.is_set(), "WASAPI did not start"
            assert all(p.isVisible() and p.desktop_anchored for p in w.modules.desktop.panels.values())
            w._toggle_setting("profile", "battery")
            QTest.qWait(200)
            assert w.audio.capture_active.is_set(), "Battery profile unexpectedly disabled spectrum"
            assert w.audio.economy.is_set()
            w._toggle_setting("spectrum_battery_save",True)
            QTest.qWait(200)
            assert not w.audio.capture_active.is_set(), "Explicit battery saving kept WASAPI open"
            assert w.worker.enabled.is_set()
            w._set_island_expanded(True)
            QTest.qWait(900)
            assert w.audio.capture_active.is_set(), "Expanded battery panel did not resume spectrum"
            w._toggle_setting("spectrum_battery_save",False)
            w._toggle_setting("profile", "game")
            QTest.qWait(1200)
            assert not w.isVisible()
            assert not w.audio.capture_active.is_set()
            assert not w.worker.poll_active.is_set()
            assert not w.modules.desktop.timer.isActive()
            assert all(not p.isVisible() for p in w.modules.desktop.panels.values())
            assert not w._notch_pointer_timer.isActive()
            w.show_hub()
            QTest.qWait(200)
            hub = w.control_center
            hub.grab().save(str(out/"modules.png"))
            hub.navigate("workspaces")
            QTest.qWait(50)
            hub.grab().save(str(out/"workspaces.png"))
            hub.close()
            assert not hub.refresh_timer.isActive()
            assert w._hub_hotkey.registered, "Ctrl+Alt+H was not registered"
            thread = ctypes.windll.kernel32.GetCurrentThreadId()
            assert ctypes.windll.user32.PostThreadMessageW(thread, 0x0312, w._hub_hotkey.identifier, 0)
            QTest.qWait(80)
            assert hub.isVisible(), "Native global hotkey did not open Cloud Hub"
            hub.close()
            w._toggle_setting("profile","work")
            search_key = w.hotkeys["hotkey_search"]
            assert search_key.registered, "Search hotkey was not registered"
            assert ctypes.windll.user32.PostThreadMessageW(thread,0x0312,search_key.identifier,0)
            QTest.qWait(100)
            assert w.modules.search.isVisible(), "Search hotkey did not open the palette"
            w.modules.search.hide()
            w._toggle_setting("profile", "battery")
            w._set_island_expanded(False)
            QTest.qWait(1200)
            assert w.isVisible() and w.worker.poll_active.is_set()
            assert w.audio.capture_active.is_set()
            usage = ProcessUsage()
            usage.sample()
            QTest.qWait(6000)
            measured = usage.sample()
            w._toggle_setting("profile", "work")
            w.show_hub()
            hub.navigation.setCurrentRow(0)
            QTest.qWait(100)
            hub.grab().save(str(out/"overview.png"))
            (out/"report.json").write_text(json.dumps({"native_profile_switching": True,
                "battery_capture_continues": True, "explicit_battery_saving": True, "expanded_capture_resumed": True,
                "game_all_services_suspended": True, "work_restored": True,
                "hub_refresh_stops_when_hidden": True, "native_hub_hotkey": True,
                "native_search_hotkey": True,
                "battery_short_sample": measured},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print((out/"report.json").read_text(encoding="utf-8"))
        finally:
            w.cleanup()
            w.hide()
