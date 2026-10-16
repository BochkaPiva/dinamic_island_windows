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
from .settings_pages import SettingsPages, PAGES
from .modules import MODULES


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


class ControlCenter(QWidget, SettingsPages):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowTitle("Cloud Hub")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600)
        self.resize(1100, 740)
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
        subtitle = text("Рабочее пространство Windows", True)
        subtitle.setMinimumWidth(260)
        subtitle.setWordWrap(False)
        header.addWidget(subtitle)
        header.addStretch()
        self.pause_button = button("Приостановить", self._pause)
        header.addWidget(self.pause_button)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.navigation = QListWidget()
        self.navigation.addItems([title for _,title,_ in PAGES])
        self.navigation.setFixedWidth(202)
        self.navigation.setObjectName("navigation")
        self.pages = QStackedWidget()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        body.addWidget(self.navigation)
        body.addWidget(self.pages, 1)
        layout.addLayout(body, 1)
        self.checks = {}
        self.values = {}
        self.sliders = {}
        self.page_indices = {key:i for i,(key,_,_) in enumerate(PAGES)}
        self.feedback = text("", True)
        for _,_,factory in PAGES:
            getattr(self,factory)()
        self.navigation.setCurrentRow(0)
        layout.addWidget(self.feedback)
        footer = QHBoxLayout()
        self.resource_label = text("", True)
        self.resource_label.setWordWrap(False)
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

    def navigate(self,key):
        self.navigation.setCurrentRow(self.page_indices.get(key,0))


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
        section(layout, "Оформление панели задач", "Настройки прозрачности панели задач остаются в TranslucentTB. Cloud Hub не заменяет оболочку Windows и не меняет параметры стороннего оформления.")
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
        if self.owner._toggle_setting(key, value):
            self._message("Сохранено")
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
            checkbox.setEnabled(key not in {"layouts_enabled", "workspaces_enabled"} or w.settings.get("manage_powertoys"))
        for key,widget in self.values.items():
            widget.blockSignals(True)
            widget.setValue(w.settings.get(key))
            widget.blockSignals(False)
        for key,widget in self.sliders.items():
            widget.blockSignals(True)
            widget.setValue(w.settings.get(key))
            widget.blockSignals(False)
        self.screen_picker.blockSignals(True)
        self.screen_picker.setCurrentIndex(max(0,self.screen_picker.findData(w.settings.get("monitor"))))
        self.screen_picker.blockSignals(False)
        for key, widget in self.profile_buttons.items():
            widget.setChecked(w.settings.get("profile") == key)
        self.pause_button.setText("Возобновить" if w.settings.get("paused") else "Приостановить")
        self.policy_label.setText(f"Сейчас: {PROFILES[w._policy.profile]}. " +
            ("Модули на паузе." if w.settings.get("paused") else
             "Чёлка и медиаслужбы остановлены." if not w._policy.island else
             "Спектр в свёрнутой чёлке отключён настройкой экономии." if w._policy.profile == "battery" and w.settings.get("spectrum_battery_save") else "Все выбранные модули доступны."))
        bridge = w.powertoys
        bridge.root = powertoys_root()
        self.integration_status.setText(bridge.status if w.settings.get("manage_powertoys") or bridge.busy else "Не подключён · изменения PowerToys не применяются")
        self.connect_button.setText("Обновить подключение" if w.settings.get("manage_powertoys") else "Подключить PowerToys" if bridge.root else "Установить PowerToys ↗")
        self.connect_button.setEnabled(not bridge.busy)
        self.restore_button.setEnabled(w.settings.get("manage_powertoys") and not bridge.busy and bridge.backup.exists())
        active = not w.settings.get("paused") and w._policy.profile != "game"
        for module in MODULES:
            enabled = w.settings.get(module.setting)
            external = module.key in {"layouts","workspaces"}
            self.module_status[module.key].setText("Выключен" if not enabled else "На паузе" if not active else
                "Требуется подключение PowerToys" if external and not w.settings.get("manage_powertoys") else "Включён")
        for key,status in self.key_status.items():
            binding = w.hotkeys.get(key)
            value = w.settings.get(key)
            status.setText("Отключена" if not value else (value+" · работает") if binding and binding.registered else
                           ((binding.error or "Редактирование сочетания…") if binding else value+" · доступна при запуске приложения"))
        self.refresh_timer_display()
        if self.isVisible():
            self.resource_label.setText(self.usage.sample()+" · процесс Cloud Hub")
            hotkey = getattr(w, "_hub_hotkey", None)
            self.shortcut_label.setText(w.settings.get("hotkey_hub") if hotkey and hotkey.registered else "Открытие через трей")
        self._refresh_workspaces()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.refresh_timer.start()
        self.sync_focus_timer()

    def hideEvent(self, event):
        self.refresh_timer.stop()
        if hasattr(self,"focus_tick"):
            self.focus_tick.stop()
        if hasattr(self,"notebook"):
            self.notebook.flush()
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
            QLabel#cardTitle {{ font-size: 15px; font-weight: 600; background: transparent; }}
            QLabel#timer {{ font-size: 56px; font-weight: 500; padding: 22px; }}
            QFrame#card {{ background: {surface}; border: 1px solid {line}; border-radius: 12px; }}
            QFrame#card QLabel {{ background: transparent; }}
            QFrame#card QWidget {{ background: transparent; }}
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
            QSpinBox, QLineEdit, QComboBox, QKeySequenceEdit {{ background:{surface}; border:1px solid {line}; border-radius:7px; padding:7px; selection-background-color:{selected}; }}
            QPlainTextEdit {{ background:{surface}; border:1px solid {line}; border-radius:9px; padding:10px; selection-background-color:{selected}; }}
            QTabWidget::pane {{ border:0; }}
            QTabBar::tab {{ background:{surface}; padding:10px 18px; border-radius:6px; margin:0 5px 8px 0; }}
            QTabBar::tab:selected {{ background:{selected}; }}
            QSlider::groove:horizontal {{ height:4px;background:{line};border-radius:2px; }}
            QSlider::sub-page:horizontal {{ background:#729de1;border-radius:2px; }}
            QSlider::handle:horizontal {{ width:14px;margin:-5px 0;background:#9fbeef;border-radius:7px; }}
            QScrollBar:vertical {{ width:8px;background:transparent;margin:0; }}
            QScrollBar::handle:vertical {{ background:{line};border-radius:4px;min-height:28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background:transparent; }}
        """)
