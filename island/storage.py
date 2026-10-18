# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path


def data_dir():
    path = Path(os.environ.get("CLOUD_ISLAND_DATA_DIR") or
                Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cloud Island")
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    DEFAULTS = {"updates": True, "autostart": False, "hide_fullscreen": True,
                "spectrum": True, "spectrum_battery_save": False,
                "timer_sound": True, "timer_alarm_seconds": 12,
                "source": "", "monitor": "", "volume_scroll_reverse": False,
                "profile": "auto", "paused": False, "island_enabled": True,
                "search_enabled": True, "layouts_enabled": True, "workspaces_enabled": True,
                "manage_powertoys": False,
                "compact_width": 180, "compact_height": 38,
                "expanded_width": 560, "expanded_height": 170, "island_opacity": 100,
                "island_files": False,
                "overview_calendar": True, "overview_focus": True,
                "hover_delay": 180, "collapse_delay": 600, "cursor_retreat": True,
                "timer_minutes": 25, "search_apps": True, "search_files": True, "search_glass": True,
                "desktop_enabled": True, "group_width": 300, "group_columns": 3,
                "group_opacity": 90, "group_hover_delay": 220, "group_collapse_delay": 650,
                "groups_locked": False, "group_collect_shortcuts": True, "hotkey_hub": "Ctrl+Alt+H",
                "hotkey_search": "Alt+Space", "hotkey_island": "Ctrl+Alt+I"}

    RANGES = {"compact_width": (140, 360), "compact_height": (32, 64),
              "expanded_width": (520, 1000), "expanded_height": (160, 460),
              "island_opacity": (55, 100), "hover_delay": (80, 1500),
              "collapse_delay": (200, 3000), "timer_minutes": (1, 1440),
              "timer_alarm_seconds": (3, 30),
              "group_width": (240, 480), "group_columns": (2, 5),
              "group_opacity": (40, 100), "group_hover_delay": (80, 1500),
              "group_collapse_delay": (200, 3000)}

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self.values = dict(self.DEFAULTS)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for key, default in self.DEFAULTS.items():
                if key in saved and type(saved[key]) is type(default) and (
                    key not in self.RANGES or self.RANGES[key][0] <= saved[key] <= self.RANGES[key][1]):
                    self.values[key] = saved[key]
        except (OSError, ValueError, TypeError):
            pass
        if self.values["profile"] not in {"auto", "work", "battery", "game"}:
            self.values["profile"] = "auto"

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        if key not in self.DEFAULTS or type(value) is not type(self.DEFAULTS[key]):
            raise ValueError("Invalid setting")
        if key == "profile" and value not in {"auto", "work", "battery", "game"}:
            raise ValueError("Unknown profile")
        if key in self.RANGES and not self.RANGES[key][0] <= value <= self.RANGES[key][1]:
            raise ValueError("Setting is outside its range")
        if self.values.get(key) == value:
            return
        updated = {**self.values, key: value}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        self.values = updated
