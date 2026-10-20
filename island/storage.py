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
                "island_style": "notch", "island_material":"black", "island_color":"#000000", "island_gap": 16, "expanded_width": 560, "expanded_height": 170, "island_opacity": 100,
                "island_files": False,
                "overview_calendar": True, "overview_focus": True,
                "hover_delay": 180, "collapse_delay": 600, "cursor_retreat": True,
                "timer_minutes": 25, "search_apps": True, "search_files": True, "search_glass": True,
                "desktop_enabled": True, "group_width": 300, "group_columns": 3,
                "group_opacity": 90, "group_hover_delay": 220, "group_collapse_delay": 650,
                "groups_locked": False, "group_collect_shortcuts": True, "hub_theme": "dark", "hub_animations": True, "hotkey_hub": "Ctrl+Alt+H",
                "hotkey_search": "Alt+Space", "hotkey_island": "Ctrl+Alt+I"}

    RANGES = {"island_gap": (8, 48),"compact_width": (140, 360), "compact_height": (32, 64),
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
        if self.values['island_style'] not in {'notch','floating'}: self.values['island_style']='notch'
        from .island_material import valid_color
        if self.values['island_material'] not in {'black','glass'}:self.values['island_material']='black'
        if not valid_color(self.values['island_color']):self.values['island_color']='#000000'
        if self.values['hub_theme'] not in {'dark','light','system'}: self.values['hub_theme']='dark'

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        if key not in self.DEFAULTS or type(value) is not type(self.DEFAULTS[key]):
            raise ValueError("Invalid setting")
        from .island_material import valid_color
        if key=='island_material' and value not in {'black','glass'}:raise ValueError('Unknown island material')
        if key=='island_color' and not valid_color(value):raise ValueError('Invalid RGB color')
        if key=='island_color':value=value.upper()
        if key == "profile" and value not in {"auto", "work", "battery", "game"}:
            raise ValueError("Unknown profile")
        if key=='island_style' and value not in {'notch','floating'}: raise ValueError('Unknown island style')
        if key=='hub_theme' and value not in {'dark','light','system'}: raise ValueError('Unknown theme')
        if key in self.RANGES and not self.RANGES[key][0] <= value <= self.RANGES[key][1]:
            raise ValueError("Setting is outside its range")
        if self.values.get(key) == value:
            return
        updated = {**self.values, key: value}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        self.values = updated
