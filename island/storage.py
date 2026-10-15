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
                "spectrum": True, "source": "", "monitor": ""}

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self.values = dict(self.DEFAULTS)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            for key, default in self.DEFAULTS.items():
                if key in saved and isinstance(saved[key], type(default)):
                    self.values[key] = saved[key]
        except (OSError, ValueError, TypeError):
            pass

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
