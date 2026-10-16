# SPDX-License-Identifier: GPL-3.0-only
"""Built-in module catalog and a shared, explicit service lifecycle."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    detail: str
    setting: str


MODULES = (
    ModuleSpec("island", "Dynamic Island", "Музыка, звук и инструменты у верхней рамки", "island_enabled"),
    ModuleSpec("search", "Быстрый поиск", "Приложения, команды и индекс Windows", "search_enabled"),
    ModuleSpec("desktop", "Группы рабочего стола", "Сворачиваемые панели с ярлыками и файлами", "desktop_enabled"),
    ModuleSpec("layouts", "Раскладки окон", "Зоны размещения через PowerToys FancyZones", "layouts_enabled"),
    ModuleSpec("workspaces", "Рабочие наборы", "Запуск наборов приложений через PowerToys", "workspaces_enabled"),
)


class ModuleRuntime:
    def __init__(self, owner):
        from .search import SearchPalette
        from .desktop_groups import DesktopGroups
        self.owner = owner
        self.search = SearchPalette(owner)
        self.desktop = DesktopGroups(owner)

    def sync(self):
        w = self.owner
        active = not w.settings.get("paused") and w._policy.profile != "game"
        self.search.set_enabled(active and w._policy.search)
        self.desktop.set_enabled(active and w.settings.get("desktop_enabled"))

    def close(self):
        self.search.shutdown()
        self.desktop.shutdown()
