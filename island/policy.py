# SPDX-License-Identifier: GPL-3.0-only
"""Pure runtime policy. Profiles never overwrite individual module preferences."""
from dataclasses import dataclass

PROFILES = {"auto": "Автоматически", "work": "Работа", "battery": "Батарея", "game": "Игра"}


@dataclass(frozen=True)
class Policy:
    profile: str
    island: bool
    spectrum: bool
    search: bool
    layouts: bool
    workspaces: bool


def runtime_policy(settings, plugged=None, expanded=False):
    profile = settings.get("profile")
    if profile not in PROFILES:
        profile = "auto"
    effective = ("battery" if plugged is False else "work") if profile == "auto" else profile
    active = not settings.get("paused") and effective != "game"
    island = active and settings.get("island_enabled")
    return Policy(effective, island,
                  island and settings.get("spectrum") and
                  (not settings.get("spectrum_battery_save") or effective == "work" or expanded),
                  active and settings.get("search_enabled"),
                  active and settings.get("layouts_enabled"),
                  active and settings.get("workspaces_enabled"))
