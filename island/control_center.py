# SPDX-License-Identifier: GPL-3.0-only
"""Cloud Hub: native, local module settings and optional PowerToys integration."""
import ctypes
import os
from pathlib import Path
import time
import winreg
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QListWidget, QStackedWidget, QFrame, QScrollArea, QComboBox)
from . import __version__, REPO_URL
from .integrations import load_workspaces, powertoys_root
from .policy import PROFILES
from .style import app_icon


def text(value, secondary=False):
    label = QLabel(value)
    label.setWordWrap(True)
    if secondary:
        label.setObjectName("secondary")
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def button(title, callback):
    widget = QPushButton(title)
    widget.clicked.connect(callback)
    return widget


def section(layout, title, detail=""):
    heading = text(title)
    heading.setObjectName("heading")
    layout.addWidget(heading)
    if detail:
        layout.addWidget(text(detail, True))


class ProcessUsage:
    def __init__(self):
        self.last = None

    def sample(self):
        class Times(ctypes.Structure):
            _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]
            @property
            def number(self):
                return self.low+(self.high << 32)
        class Memory(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("peak", "working", "quota_peak_paged",
                "quota_paged", "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")]
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        handle = ctypes.c_void_p(kernel.GetCurrentProcess())
        creation, end, system, user = Times(), Times(), Times(), Times()
        memory = Memory()
        memory.size = ctypes.sizeof(memory)
        if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(end),
                                      ctypes.byref(system), ctypes.byref(user)):
            return "Нагрузка временно недоступна"
        getter = ctypes.windll.psapi.GetProcessMemoryInfo
        getter.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        if not getter(handle, ctypes.byref(memory), memory.size):
            return "Память временно недоступна"
        now, cpu = time.monotonic(), (system.number+user.number)/10_000_000
        percent = None if self.last is None else 100*(cpu-self.last[1])/max(.01, now-self.last[0])/(os.cpu_count() or 1)
        self.last = now, cpu
        return f"{memory.working/1024**2:.0f} МБ RAM · " + (f"{percent:.2f}% CPU" if percent is not None else "измеряю CPU…")


class ControlCenter(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowTitle("Cloud Hub")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(760, 540)
        self.resize(980, 660)
        self.usage = ProcessUsage()
        self._workspace_ids = []
        self._apply_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(16)
        header = QHBoxLayout()
        title = text("Cloud Hub")
        title.setObjectName("title")
        header.addWidget(title)
        header.addWidget(text("Твоё рабочее окружение", True))
        header.addStretch()
        self.pause_button = button("Приостановить", self._pause)
        header.addWidget(self.pause_button)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.navigation = QListWidget()
        self.navigation.addItems(["Модули и профили", "Рабочие наборы", "Windows и HONOR"])
        self.navigation.setFixedWidth(190)
        self.navigation.setObjectName("navigation")
        self.pages = QStackedWidget()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        body.addWidget(self.navigation)
        body.addWidget(self.pages, 1)
        layout.addLayout(body, 1)
        self.checks = {}
        self._modules_page()
        self._workspaces_page()
        self._windows_page()
        self.navigation.setCurrentRow(0)
        self.feedback = text("", True)
        layout.addWidget(self.feedback)
        footer = QHBoxLayout()
        self.resource_label = text("", True)
        footer.addWidget(self.resource_label)
        footer.addStretch()
        self.shortcut_label = text("Ctrl + Alt + H", True)
        footer.addWidget(self.shortcut_label)
        footer.addWidget(text(f"v{__version__}", True))
        layout.addLayout(footer)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(3000)
        self.refresh_timer.timeout.connect(self.refresh)
        owner.powertoys.changed.connect(self.refresh)
        owner.powertoys.message.connect(self._message)

    def _page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 12, 4)
        layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        return layout

    def _module(self, layout, key, name, detail):
        row = QHBoxLayout()
        description = QVBoxLayout()
        description.setSpacing(2)
        description.addWidget(text(name))
        description.addWidget(text(detail, True))
        row.addLayout(description, 1)
        checkbox = QCheckBox("Включён")
        checkbox.setObjectName(key)
        checkbox.toggled.connect(lambda value, k=key: self._setting(k, value))
        row.addWidget(checkbox)
        self.checks[key] = checkbox
        layout.addLayout(row)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

    def _modules_page(self):
        layout = self._page()
        section(layout, "Профиль", "Автоматически: от сети — «Работа», без зарядки — «Батарея». «Игра» включается вручную.")
        self.profile_buttons = {}
        row = QHBoxLayout()
        for key, title in PROFILES.items():
            widget = button(title, lambda checked=False, value=key: self._setting("profile", value))
            widget.setCheckable(True)
            self.profile_buttons[key] = widget
            row.addWidget(widget)
        layout.addLayout(row)
        self.policy_label = text("", True)
        layout.addWidget(self.policy_label)
        section(layout, "Cloud Island")
        self._module(layout, "island_enabled", "Чёлка у верхней рамки", "Музыка, календарь, таймер, заметки и полка файлов")
        self._module(layout, "spectrum", "Настоящий спектр звука", "В профиле «Батарея» захват включается только при раскрытии чёлки")
        row = QHBoxLayout()
        row.addWidget(button("Открыть чёлку", self.owner._show_panel))
        row.addWidget(button("Папка заметок и настроек", lambda: self._url(QUrl.fromLocalFile(str(self.owner.settings.directory)))))
        layout.addLayout(row)
        section(layout, "PowerToys", "Подключение управляет тремя модулями. Их переключение перезапускает PowerToys и закрывает его окно настроек. При выходе из Cloud Hub исходное подключение восстанавливается.")
        self.integration_status = text("", True)
        layout.addWidget(self.integration_status)
        self._module(layout, "search_enabled", "Быстрый поиск", "Command Palette · Win + Alt + Space")
        self._module(layout, "layouts_enabled", "Раскладки окон", "FancyZones · Shift при перетаскивании окна")
        self._module(layout, "workspaces_enabled", "Рабочие наборы", "Workspaces · сохранить приложения и расположение окон")
        row = QHBoxLayout()
        self.connect_button = button("Подключить PowerToys", self._connect)
        row.addWidget(self.connect_button)
        self.restore_button = button("Восстановить исходное подключение", self._restore)
        row.addWidget(self.restore_button)
        layout.addLayout(row)
        layout.addWidget(button("Открыть параметры PowerToys", lambda: self.owner.powertoys.launch("PowerToys.exe", ["--open-settings"])))
        section(layout, "Приложение")
        self._module(layout, "autostart", "Запускать Cloud Hub с Windows", "При входе в систему окно настроек остаётся закрытым")
        self._module(layout, "hide_fullscreen", "Скрывать чёлку в полноэкранном режиме", "После выхода из приложения чёлка возвращается")
        self._module(layout, "volume_scroll_reverse", "Обратить направление громкости", "Дополнительная настройка для нестандартных драйверов тачпада")
        self._module(layout, "updates", "Проверять обновления", "Раз в день; установка запускается тобой")
        layout.addWidget(button("Проверить обновления сейчас", self.owner._check_update))
        layout.addStretch()

    def _workspaces_page(self):
        layout = self._page()
        section(layout, "Рабочие наборы", "Расставь нужные окна, открой редактор Workspaces и сохрани набор. Он появится здесь. Набор запускается только по нажатию кнопки.")
        row = QHBoxLayout()
        row.addWidget(button("Создать или изменить набор", self._workspace_editor))
        row.addWidget(button("Обновить список", self._refresh_workspaces))
        layout.addLayout(row)
        self.workspaces = QListWidget()
        self.workspaces.setMinimumHeight(140)
        self.workspaces.itemDoubleClicked.connect(lambda _: self._launch_workspace())
        layout.addWidget(self.workspaces)
        self.launch_button = button("Запустить выбранный набор", self._launch_workspace)
        layout.addWidget(self.launch_button)
        self.workspace_empty = text("", True)
        layout.addWidget(self.workspace_empty)
        section(layout, "Раскладки окон", "Открой редактор FancyZones, чтобы сделать схему 60/40 или большое окно и два вспомогательных. Сохранённые окна раскладывает PowerToys.")
        layout.addWidget(button("Настроить зоны окон", self._zones_editor))
        layout.addWidget(text("Workspaces размещает окна после запуска. Некоторые приложения могут открыть новое окно; программы с правами администратора имеют ограничения размещения.", True))
        layout.addStretch()

    def _windows_page(self):
        layout = self._page()
        section(layout, "Windows и HONOR", "Быстрый доступ к штатным настройкам. Они меняются в соответствующем приложении.")
        for name, detail, target in (
            ("Панель задач и Пуск", "Закрепления, расположение и поведение панели", "ms-settings:taskbar"),
            ("Цвета и прозрачность", "Тема Windows, акцентный цвет и системные эффекты", "ms-settings:colors"),
            ("Тачпад", "Жесты тремя и четырьмя пальцами", "ms-settings:devices-touchpad"),
            ("Экран", "Масштаб, разрешение и частота обновления", "ms-settings:display"),
            ("Звук", "Выходное устройство, микрофон и громкость приложений", "ms-settings:sound"),
            ("Питание и батарея", "Системный режим питания и энергосбережение", "ms-settings:powersleep")):
            layout.addWidget(button(name, lambda checked=False, url=target: self._url(QUrl(url))))
            layout.addWidget(text(detail, True))
        layout.addWidget(button("Открыть HONOR PC Manager", self._honor))
        section(layout, "Оформление панели задач", "TranslucentTB можно оставить установленным. Cloud Hub 0.2 не меняет его параметры. Не включай одновременно TranslucentTB и Windhawk Taskbar Styler: они используют один механизм оформления.")
        layout.addWidget(button("Страница проекта и обновления ↗", lambda: self._url(QUrl(REPO_URL))))
        layout.addStretch()

    def _honor(self):
        from PyQt6.QtCore import QProcess
        roots = [Path(os.environ.get("ProgramFiles", ""))/"HONOR/PCManager",
                 Path(os.environ.get("ProgramFiles(x86)", ""))/"HONOR/PCManager"]
        for root in roots:
            for name in ("PCManager.exe", "PCManagerMain.exe", "PCManagerTray.exe"):
                if (root/name).is_file():
                    ok, _ = QProcess.startDetached(str(root/name), [])
                    self._message("" if ok else "Не удалось открыть HONOR PC Manager")
                    return
        self._message("HONOR PC Manager не найден в стандартной папке установки")

    def _setting(self, key, value):
        self.owner._toggle_setting(key, value)
        self.refresh()

    def _pause(self):
        self._setting("paused", not self.owner.settings.get("paused"))

    def _connect(self):
        if not self.owner.powertoys.root:
            self._url(QUrl("https://learn.microsoft.com/windows/powertoys/install"))
            return
        if not self.owner.settings.get("manage_powertoys") and not self.owner.powertoys.new_connection():
            return
        self.owner.powertoys.launch("PowerToys.exe")
        self._setting("manage_powertoys", True)

    def _restore(self):
        if self.owner.powertoys.restore():
            self.owner.settings.set("manage_powertoys", False)
            self.refresh()

    def _workspace_editor(self):
        if self._require("workspaces_enabled"):
            self.owner.powertoys.launch("PowerToys.WorkspacesEditor.exe")

    def _zones_editor(self):
        if self._require("layouts_enabled"):
            self.owner.powertoys.launch("FancyZonesCLI.exe", ["open-editor"])

    def _require(self, key):
        policy = self.owner._policy
        active = policy.workspaces if key == "workspaces_enabled" else policy.layouts
        if not self.owner.settings.get("manage_powertoys") or not active:
            self._message("Подключи PowerToys и включи нужный модуль в рабочем профиле.")
            return False
        if self.owner.powertoys.busy:
            self._message("Дождись применения настроек PowerToys.")
            return False
        return True

    def _refresh_workspaces(self):
        items = load_workspaces()
        if items == getattr(self, "_workspace_items", None):
            return
        self._workspace_items = items
        self._workspace_ids = [item[0] for item in items]
        self.workspaces.clear()
        self.workspaces.addItems([f"{name} · приложений: {count}" for _, name, count in items])
        if items:
            self.workspaces.setCurrentRow(0)
        self.launch_button.setEnabled(bool(items))
        self.workspace_empty.setText("" if items else "Сохранённых наборов пока нет. Создай первый в редакторе Workspaces.")

    def _launch_workspace(self):
        row = self.workspaces.currentRow()
        if self._require("workspaces_enabled") and 0 <= row < len(self._workspace_ids):
            self.owner.powertoys.launch_workspace(self._workspace_ids[row])

    def _url(self, url):
        if not QDesktopServices.openUrl(url):
            self._message("Не удалось открыть настройки или ссылку")

    def _message(self, message):
        self.feedback.setText(message)

    def refresh(self):
        w = self.owner
        for key, checkbox in self.checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(w.settings.get(key))
            checkbox.blockSignals(False)
            checkbox.setEnabled(key not in {"search_enabled", "layouts_enabled", "workspaces_enabled"} or w.settings.get("manage_powertoys"))
        for key, widget in self.profile_buttons.items():
            widget.setChecked(w.settings.get("profile") == key)
        self.pause_button.setText("Возобновить" if w.settings.get("paused") else "Приостановить")
        self.policy_label.setText(f"Сейчас: {PROFILES[w._policy.profile]}. " +
            ("Модули на паузе." if w.settings.get("paused") else
             "Чёлка и медиаслужбы остановлены." if not w._policy.island else
             "Спектр включается при раскрытии чёлки." if w._policy.profile == "battery" else "Все выбранные модули доступны."))
        bridge = w.powertoys
        bridge.root = powertoys_root()
        self.integration_status.setText(bridge.status if w.settings.get("manage_powertoys") or bridge.busy else "Не подключён · изменения PowerToys не применяются")
        self.connect_button.setText("Обновить подключение" if w.settings.get("manage_powertoys") else "Подключить PowerToys" if bridge.root else "Установить PowerToys ↗")
        self.connect_button.setEnabled(not bridge.busy)
        self.restore_button.setEnabled(w.settings.get("manage_powertoys") and not bridge.busy and bridge.backup.exists())
        if self.isVisible():
            self.resource_label.setText(self.usage.sample()+" · процесс Cloud Hub")
            hotkey = getattr(w, "_hub_hotkey", None)
            self.shortcut_label.setText("Ctrl + Alt + H" if hotkey and hotkey.registered else "Открытие через трей · горячая клавиша занята")
        self._refresh_workspaces()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.refresh_timer.start()

    def hideEvent(self, event):
        self.refresh_timer.stop()
        super().hideEvent(event)

    def _apply_theme(self):
        dark = True
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                dark = not winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
        except OSError:
            pass
        bg, surface, fg, muted, line, selected = (("#171c24", "#232b37", "#edf0f6", "#abb8cb", "#354153", "#344f73") if dark else
            ("#f4f6f9", "#ffffff", "#202934", "#536378", "#d6dee8", "#dae7fa"))
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QLabel#title {{ font-size: 25px; font-weight: 600; }}
            QLabel#heading {{ font-size: 17px; font-weight: 600; margin-top: 8px; }}
            QLabel#secondary {{ color: {muted}; font-size: 12px; }}
            QPushButton {{ background: {surface}; border: 1px solid {line}; border-radius: 8px; padding: 9px 13px; }}
            QPushButton:hover, QPushButton:checked {{ background: {selected}; }}
            QPushButton:disabled, QCheckBox:disabled {{ color: {muted}; }}
            QPushButton:focus, QCheckBox:focus {{ outline: 1px solid #79a9eb; }}
            QListWidget {{ background: {surface}; border: 1px solid {line}; border-radius: 9px; padding: 6px; }}
            QListWidget#navigation {{ background: transparent; border: none; padding: 0; }}
            QListWidget::item {{ padding: 12px 8px; border-radius: 7px; }}
            QListWidget::item:selected {{ background: {selected}; color: {fg}; }}
            QCheckBox {{ spacing: 7px; padding: 5px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
            QFrame[frameShape="4"] {{ color: {line}; }}
            QScrollArea {{ border: none; }}
        """)
