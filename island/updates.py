# SPDX-License-Identifier: GPL-3.0-only
"""Read stable releases from this project. Updating is initiated by the user."""
import json
import re
import threading
import urllib.request
from PyQt6.QtCore import QObject, pyqtSignal
from . import __version__, APP_NAME, REPOSITORY, REPO_URL


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def release_info(payload, current=__version__):
    if payload.get("draft") or payload.get("prerelease"):
        return None
    version = version_tuple(str(payload.get("tag_name", "")))
    if not version or version <= version_tuple(current):
        return None
    url = payload.get("html_url", "")
    if not url.startswith(REPO_URL + "/releases/tag/"):
        return None
    return {"version": ".".join(map(str, version)), "url": url}


class UpdateChecker(QObject):
    finished = pyqtSignal(object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False

    def check(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        result = {"status": "current"}
        try:
            request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
                         headers={"Accept": "application/vnd.github+json", "User-Agent": f"{APP_NAME}/{__version__}"})
            with urllib.request.urlopen(request, timeout=8) as response:
                info = release_info(json.loads(response.read(1_000_000).decode("utf-8")))
            if info:
                result = {"status": "available", **info}
        except Exception:
            result = {"status": "unavailable"}
        finally:
            self.running = False
        self.finished.emit(result)
