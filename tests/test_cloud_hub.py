# SPDX-License-Identifier: GPL-3.0-only
import json
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from island.app import IslandWindow
from island.audio import AudioSpectrum
from island.media import MediaWorker
from island.integrations import PowerToysBridge, load_workspaces
from island.policy import runtime_policy
from island.storage import Settings


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_auto_battery_keeps_spectrum_unless_saving_is_explicit(self):
        self.assertTrue(runtime_policy(self.settings, True).spectrum)
        self.assertTrue(runtime_policy(self.settings, False).spectrum)
        self.assertTrue(runtime_policy(self.settings, False, expanded=True).spectrum)
        self.settings.set("spectrum_battery_save",True)
        self.assertFalse(runtime_policy(self.settings,False).spectrum)
        self.assertTrue(runtime_policy(self.settings,False,expanded=True).spectrum)
        self.assertTrue(runtime_policy(self.settings,True).spectrum)
        self.assertEqual(runtime_policy(self.settings, None).profile, "work")

    def test_pause_game_and_module_switches_preserve_preferences(self):
        for key, value in (("paused", True), ("profile", "game")):
            self.settings.set(key, value)
            policy = runtime_policy(self.settings, True)
            self.assertFalse(any((policy.island, policy.spectrum, policy.search, policy.layouts, policy.workspaces)))
            self.settings.set(key, Settings.DEFAULTS[key])
        self.settings.set("island_enabled", False)
        self.assertFalse(runtime_policy(self.settings, True).spectrum)
        self.assertTrue(runtime_policy(self.settings, True).search)
        self.assertTrue(self.settings.get("spectrum"))
        self.assertEqual(Settings(self.temp.name).get("island_enabled"), False)

    def test_legacy_settings_and_invalid_types_are_handled(self):
        path = Path(self.temp.name)/"settings.json"
        path.write_text(json.dumps({"spectrum": False, "profile": 4, "island_enabled": "false"}), encoding="utf-8")
        loaded = Settings(self.temp.name)
        self.assertFalse(loaded.get("spectrum"))
        self.assertEqual(loaded.get("profile"), "auto")
        self.assertTrue(loaded.get("island_enabled"))
        with self.assertRaises(ValueError):
            loaded.set("profile", "unknown")

    def test_paused_workers_can_shutdown_without_being_resumed(self):
        audio, media = AudioSpectrum(), MediaWorker()
        audio.set_enabled(False)
        media.command("player", "play_pause")
        media.set_enabled(False)
        self.assertTrue(media.commands.empty())
        for worker in (audio, media):
            worker.start()
            QTest.qWait(100)
            worker.stop()
            self.assertTrue(worker.wait(3000), "Paused worker blocked installer shutdown")
        self.assertFalse(audio.capture_active.is_set())
        self.assertFalse(media.poll_active.is_set())


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_dsc_preserves_complete_settings_and_follows_latest_profile(self):
        with patch("island.integrations.powertoys_root", return_value=Path(self.temp.name)), \
             patch("island.integrations.close_powertoys_runner", return_value=None):
            bridge = PowerToysBridge(self.temp.name)
            bridge.native_path = Path(self.temp.name)/"native.json"
            bridge.process = Mock()
            calls = []
            bridge._start = lambda args: calls.append(args)
            before = {"settings": {"startup": True, "theme": "dark", "future": {"keep": 17},
                      "enabled": {"CmdPal": True, "FancyZones": True, "Workspaces": False, "Other": True}}}
            bridge.process.readAllStandardOutput.return_value = json.dumps(before).encode()
            bridge.configure({key: False for key in ("CmdPal", "FancyZones", "Workspaces")})
            bridge._finished(0, QProcess.ExitStatus.NormalExit)
            sent = json.loads(calls[-1][-1])
            self.assertTrue(sent["settings"]["startup"])
            self.assertEqual(sent["settings"]["theme"], "dark")
            self.assertEqual(sent["settings"]["future"], {"keep": 17})
            self.assertTrue(sent["settings"]["enabled"]["Other"])
            self.assertFalse(sent["settings"]["enabled"]["CmdPal"])
            saved = json.loads(bridge.backup.read_text(encoding="utf-8"))
            self.assertEqual(saved["managed_enabled"], {"CmdPal": True, "FancyZones": True, "Workspaces": False})
            bridge.configure({key: True for key in ("CmdPal", "FancyZones", "Workspaces")})
            bridge.process.readAllStandardOutput.return_value = (json.dumps(sent)+'\n["settings"]').encode()
            bridge._finished(0, QProcess.ExitStatus.NormalExit)
            self.assertEqual(calls[-1][0], "get")
            self.assertTrue(bridge.busy)
            bridge.timeout.stop()

    def test_workspace_metadata_cannot_become_a_shell_command(self):
        path = Path(self.temp.name)/"workspaces.json"
        identifier = "{DCE582A8-8891-4EE9-AB78-807079237C92}"
        path.write_text(json.dumps({"workspaces": [{"id": identifier, "name": "Набор & calc.exe", "applications": []}]}), encoding="utf-8")
        self.assertEqual(load_workspaces(path), [(identifier, "Набор & calc.exe", 0)])
        bridge = PowerToysBridge(self.temp.name)
        with patch("island.integrations.load_workspaces", return_value=load_workspaces(path)), patch.object(bridge, "launch", return_value=True) as launch:
            self.assertTrue(bridge.launch_workspace(identifier))
            launch.assert_called_once_with("PowerToys.WorkspacesLauncher.exe", [identifier])
            self.assertFalse(bridge.launch_workspace("& calc.exe"))
        path.write_text("not json", encoding="utf-8")
        self.assertEqual(load_workspaces(path), [])

    def test_graceful_restart_reapplies_preclose_unmanaged_settings(self):
        kernel = Mock()
        kernel.WaitForSingleObject.return_value = 0
        with patch("island.integrations.powertoys_root", return_value=Path(self.temp.name)), \
             patch("island.integrations.close_powertoys_runner", return_value=123), \
             patch("island.integrations.ctypes.windll.kernel32", kernel):
            bridge = PowerToysBridge(self.temp.name)
            bridge.native_path = Path(self.temp.name)/"native.json"
            bridge.process = Mock()
            calls = []
            bridge._start = lambda args: calls.append(args)
            before = {"settings": {"startup": False, "theme": "system", "enabled":
                {"CmdPal": True, "FancyZones": True, "Workspaces": True, "Awake": False}}}
            bridge.process.readAllStandardOutput.return_value = json.dumps(before).encode()
            bridge.configure(dict.fromkeys(("CmdPal", "FancyZones", "Workspaces"), False))
            bridge._finished(0, QProcess.ExitStatus.NormalExit)
            self.assertTrue(bridge.runner_poll.isActive())
            self.assertEqual(calls[-1][0], "get")
            bridge._runner_closed()
            sent = json.loads(calls[-1][-1])
            self.assertFalse(sent["settings"]["enabled"]["Awake"])
            self.assertFalse(sent["settings"]["startup"])
            self.assertEqual(calls[-1][0], "set")
            self.assertIsNone(bridge._runner_handle)
            self.assertFalse(bridge.runner_poll.isActive())
            bridge.timeout.stop()

    def test_dsc_serializer_cannot_enable_unmanaged_file_explorer_or_drop_unknown_settings(self):
        with patch("island.integrations.powertoys_root", return_value=Path(self.temp.name)), \
             patch("island.integrations.close_powertoys_runner", return_value=None):
            bridge = PowerToysBridge(self.temp.name)
            bridge.native_path = Path(self.temp.name)/"native.json"
            before = {"startup": False, "future": {"preserve": 42}, "enabled":
                {"CmdPal": True, "FancyZones": True, "Workspaces": True, "File Explorer": False}}
            bridge.native_path.write_text(json.dumps(before), encoding="utf-8")
            bridge.process = Mock()
            calls = []
            bridge._start = lambda args: calls.append(args)
            vendor = {"settings": {"startup": False, "enabled":
                {"CmdPal": True, "FancyZones": True, "Workspaces": True, "File Explorer Preview": True}}}
            bridge.process.readAllStandardOutput.return_value = json.dumps(vendor).encode()
            bridge.configure(dict.fromkeys(("CmdPal", "FancyZones", "Workspaces"), False))
            bridge._finished(0, QProcess.ExitStatus.NormalExit)
            sent = json.loads(calls[-1][-1])
            bridge.native_path.write_text(json.dumps(sent["settings"]), encoding="utf-8")
            bridge.process.readAllStandardOutput.return_value = json.dumps(sent).encode()
            bridge._finished(0, QProcess.ExitStatus.NormalExit)
            after = json.loads(bridge.native_path.read_text(encoding="utf-8"))
            self.assertEqual(after["future"], before["future"])
            self.assertFalse(after["enabled"]["File Explorer"])
            self.assertNotIn("File Explorer Preview", after["enabled"])
            self.assertFalse(bridge._any_enabled)
            self.assertFalse(bridge.busy)

    def test_control_center_applies_preferences_and_stops_refresh_when_closed(self):
        w = IslandWindow(Settings(self.temp.name), services=False)
        try:
            w._notch_pointer_timer.stop()
            w.show_hub()
            hub = w.control_center
            QTest.qWait(30)
            QTest.mouseClick(hub.profile_buttons["game"], Qt.MouseButton.LeftButton)
            self.assertEqual(w._policy.profile, "game")
            self.assertFalse(w._policy.island)
            hub.checks["spectrum"].setChecked(False)
            QTest.mouseClick(hub.profile_buttons["work"], Qt.MouseButton.LeftButton)
            self.assertFalse(w._policy.spectrum)
            QTest.mouseClick(hub.pause_button, Qt.MouseButton.LeftButton)
            self.assertTrue(w.settings.get("paused"))
            hub.close()
            self.assertFalse(hub.refresh_timer.isActive())
            self.assertFalse((Path(self.temp.name)/"powertoys-before-cloud-hub.json").exists())
        finally:
            w.cleanup()
            w.hide()
            w.deleteLater()
            QTest.qWait(20)


if __name__ == "__main__":
    unittest.main()
