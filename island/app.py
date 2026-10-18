# SPDX-License-Identifier: GPL-3.0-only
"""Cloud Island's independent application shell and lifecycle."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from PyQt6.QtCore import (Qt, QRect, QTimer, QUrl, QVariantAnimation,
                          QSharedMemory, QEasingCurve)
from PyQt6.QtGui import QColor, QDesktopServices, QPainter
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMenu, QSystemTrayIcon
from . import APP_NAME, __version__, REPO_URL
from .audio import AudioSpectrum
from .hub import NotchHub, battery_state, fmt
from .media import MediaWorker, Snapshot
from .motion import NotchStage, PointerController, SpringGeometry
from .platform_win import (autostart, is_fullscreen, adjust_volume,
                           desktop_is_foreground, keep_desktop_visible, exclude_from_peek)
from .storage import Settings
from .style import NotchCard, SpectrumMark, rounded_art, app_icon, font
from .updates import UpdateChecker
from .instance import InstanceServer, notify_existing, server_name
from .volume_scroll import NativeWheelSource, VolumeScroll
from .policy import runtime_policy, PROFILES
from .integrations import PowerToysBridge


class ArtLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = self.previous = None
        self.fraction = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._frame)

    def _frame(self, value):
        self.fraction = float(value)
        self.update()

    def set_image(self, image):
        self.previous, self.image = self.image, image
        self._anim.stop()
        self._anim.setStartValue(0.0 if self.previous is not None else 1.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        if self.previous is not None:
            p.setOpacity(1-self.fraction)
            p.drawPixmap(0, 0, self.previous)
        if self.image is not None:
            p.setOpacity(self.fraction)
            p.drawPixmap(0, 0, self.image)


class IslandWindow(QWidget):
    def __init__(self, settings=None, services=True):
        super().__init__(flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMouseTracking(True)
        self.settings = settings or Settings()
        self.setWindowOpacity(self.settings.get("island_opacity")/100)
        self._wheel_source = NativeWheelSource(QApplication.instance())
        self._volume_scroll = VolumeScroll(adjust_volume, self._wheel_source)
        self._services = services
        self._closed = False
        self.snapshot = Snapshot()
        self.current_scale_pct = 200
        self._island_expanded = self._fs_hidden = self._hovering = False
        self._notch_audio_active = False
        self._last_audio = 0.0
        self._notch_notice = ""
        self._hidden_by_user = False
        self._last_thumb = None
        self._last_battery = battery_state()
        self._policy = runtime_policy(self.settings, self._last_battery[1] if self._last_battery else None)
        self._economy = self._policy.profile == "battery"
        self._external_policy = None
        self.control_center = None
        self._hub_hotkey = None
        self.hotkeys = {}
        self.powertoys = PowerToysBridge(self.settings.directory, self)
        self._update_info = None
        self._manual_update = False
        self.resize(180, 38)
        self.card = NotchCard(self)
        self.card.setGeometry(self.rect())
        self.art_label = ArtLabel(self.card)
        self.status_mark = SpectrumMark(self.card)
        self.notch_idle, self.notch_notice = QLabel(self.card), QLabel(self.card)
        for label in (self.notch_idle, self.notch_notice):
            label.setFont(font(11, 500))
            label.setStyleSheet("color: #d5d5df; background: transparent")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._island_auto_timer = QTimer(self)
        self._island_auto_timer.setSingleShot(True)
        self._island_auto_timer.timeout.connect(self._close_if_allowed)
        self._notch_hover_timer = QTimer(self)
        self._notch_hover_timer.setSingleShot(True)
        self._notch_hover_timer.timeout.connect(lambda: self._set_island_expanded(True))
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(lambda: self.notice(""))
        self.worker = MediaWorker(self.settings.get("source"), self)
        self.worker.snapshot_updated.connect(self._handle_snapshot)
        self.worker.failure.connect(self._media_error)
        self.notch_hub = NotchHub(self, self.settings.directory)
        self.notch_hub.source_selected.connect(self._select_source)
        self.notch_hub.timer_finished.connect(self._timer_finished)
        self._notch_stage = NotchStage(self)
        self._geometry = SpringGeometry(self)
        self._notch_pointer = PointerController(self)
        self._notch_pointer_timer = QTimer(self)
        self._notch_pointer_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._notch_pointer_timer.timeout.connect(self._notch_pointer.tick)
        self._notch_pointer_timer.start(16)
        self._system_timer = QTimer(self)
        self._system_timer.timeout.connect(self._system_tick)
        self._system_timer.start(500)
        self.audio = AudioSpectrum(self)
        self.audio.levels_changed.connect(self._audio_levels)
        self.audio.availability_changed.connect(self._audio_available)
        self.updates = UpdateChecker(self)
        self.updates.finished.connect(self._update_result)
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._scheduled_update)
        self._update_timer.start(24*60*60*1000)
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"Cloud Hub · Cloud Island {__version__}")
        self.tray.activated.connect(self._tray_activate)
        self._build_menu()
        from .modules import ModuleRuntime
        self.modules = ModuleRuntime(self)
        if services:
            self.tray.show()
        self._notch_stage.enter()
        self.notch_hub.update_snapshot(self.snapshot)
        self._place()
        self._system_tick()
        if services:
            self.worker.start()
            self.audio.start()
            from .hotkey import HubHotkey
            for index, (key, callback) in enumerate((("hotkey_hub", self.show_hub),
                    ("hotkey_search", self.show_search), ("hotkey_island", self._show_panel))):
                self.hotkeys[key] = HubHotkey(QApplication.instance(), callback,
                    self.settings.get(key), 0x4348+index)
            self._hub_hotkey = self.hotkeys["hotkey_hub"]
            if self.settings.get("autostart"):
                autostart(True)
            QTimer.singleShot(5000, self._scheduled_update)
        from .update_helper import resume_timer
        restored=resume_timer(self.settings.directory)
        if restored:
            self.notch_hub._timer_remaining=restored['remaining']
            if restored['running']:
                self.notch_hub._timer_end=time.monotonic()+restored['remaining'] if restored['remaining'] else time.monotonic()-.01
            self.notch_hub.tick()
            if restored['running']: self.notch_hub.clock.start(1000)
        app = QApplication.instance()
        app.screenAdded.connect(lambda _: self._screens_changed())
        app.screenRemoved.connect(lambda _: self._screens_changed())
        for screen in app.screens():
            screen.geometryChanged.connect(lambda _: self._place())

    def _scale_window_size(self, scale):
        prefix = "expanded" if scale == 100 else "compact"
        screen = next((s for s in QApplication.screens() if s.name() == self.settings.get("monitor")),
                      QApplication.primaryScreen()).geometry()
        return (min(self.settings.get(prefix+"_width"),screen.width()),
                min(self.settings.get(prefix+"_height"),screen.height()))

    def _place(self):
        app = QApplication.instance()
        screen = next((s for s in app.screens() if s.name() == self.settings.get("monitor")), app.primaryScreen())
        self._geometry.stop()
        width, height = self._scale_window_size(100 if self._island_expanded else 50)
        bounds = screen.geometry()
        self.setGeometry(bounds.x()+(bounds.width()-width)//2, bounds.top(), width, height)
        self._notch_stage.sync()

    def _screens_changed(self):
        self._place()
        self._build_menu()

    def _geo_anim_step(self, rect):
        self.setGeometry(rect)
        self._notch_stage.sync()

    def _after_geo_anim(self):
        self._notch_stage.sync()

    def _notch_set_compact_retreat(self, value):
        self._notch_stage.retreat = value

    def _set_island_expanded(self, expanded):
        if expanded == self._island_expanded or self._closed:
            return
        self._notch_stage.prepare()
        self._island_expanded = expanded
        if expanded:
            self._notch_pointer.opened_at = time.monotonic()
            self._notch_pointer.route_input(False)
        width, height = self._scale_window_size(100 if expanded else 50)
        screen = self.screen().geometry()
        self._geometry.start(QRect(screen.x()+(screen.width()-width)//2, screen.top(), width, height))
        self._apply_policy()
        self._update_services()

    def _close_if_allowed(self):
        if self.notch_hub.alarm.active and time.monotonic() < self.notch_hub.alarm.hold_until:
            self._island_auto_timer.start(1000)
            return
        if QApplication.activePopupWidget() or (self.notch_hub.busy() and self.isActiveWindow()):
            self._island_auto_timer.start(600)
        else:
            self._set_island_expanded(False)

    def showEvent(self, event):
        super().showEvent(event)
        # DWM owns taskbar Peek fading, independently of Qt visibility/z-order.
        # Apply to the real HWND on every show, including a recreated window.
        exclude_from_peek(self)

    def resizeEvent(self, event):
        self.card.setGeometry(self.rect())
        if hasattr(self, "_notch_stage"):
            self._notch_stage.sync()

    def enterEvent(self, event):
        if not self._notch_pointer.covered and not self._island_expanded:
            self._notch_hover_timer.start(self.settings.get("hover_delay"))

    def leaveEvent(self, event):
        self._notch_hover_timer.stop()
        if self._island_expanded:
            self._island_auto_timer.start(self.settings.get("collapse_delay"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._island_expanded:
            self._set_island_expanded(True)

    def wheelEvent(self, event):
        self._volume_scroll.handle(event, reverse=self.settings.get("volume_scroll_reverse"))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._notch_pointer.edge_blocked = True
            self._notch_pointer.edge_since = None
            self.clearFocus()
            self._set_island_expanded(False)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        self._notch_hover_timer.stop()
        self._island_auto_timer.stop()
        self._build_menu()
        self.menu.exec(event.globalPos())

    def _handle_snapshot(self, snap):
        self.snapshot = snap
        art_size = min(40,self.settings.get("compact_height")-12)
        if snap.thumb != self._last_thumb:
            self._last_thumb = snap.thumb
            self.art_label.set_image(self._notch_art(snap.thumb, art_size, 7))
        elif self.art_label.image is None:
            self.art_label.set_image(self._notch_art(b"", art_size, 7))
        self.notch_hub.update_snapshot(snap)
        self._notch_stage.sync()
        self._notch_stage.surface.update()

    def _notch_art(self, data, size, radius):
        return rounded_art(data, size, radius, self.devicePixelRatioF())

    def _notch_source_name(self, source):
        name = source.split("!")[0]
        return name if len(name) < 45 else name[:42]+"…"

    def _select_source(self, source):
        self.worker.preferred_source = source
        self.settings.set("source", source)

    def send_control(self, action):
        if self.snapshot.has_session:
            self.worker.command(self.snapshot.aumid, action)

    def send_seek(self, position):
        if self.snapshot.has_session and self.snapshot.can_seek:
            self.worker.command(self.snapshot.aumid, "seek", position)

    def open_source(self):
        # Focus an existing player; never execute arbitrary media metadata.
        if self.snapshot.aumid:
            import ctypes
            user = ctypes.windll.user32
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            target = self.snapshot.aumid.lower().split(".")[0]
            candidates = []
            def visit(hwnd, data):
                if user.IsWindowVisible(ctypes.c_void_p(hwnd)) and hwnd != int(self.winId()):
                    title = ctypes.create_unicode_buffer(512)
                    user.GetWindowTextW(ctypes.c_void_p(hwnd), title, 512)
                    if target and target in title.value.lower():
                        candidates.append(hwnd)
                return True
            user.EnumWindows(callback_type(visit), None)
            if candidates:
                user.ShowWindow(ctypes.c_void_p(candidates[0]), 9)
                user.SetForegroundWindow(ctypes.c_void_p(candidates[0]))

    def _audio_levels(self, levels):
        if not self._policy.spectrum:
            levels = (0.,)*5
        if max(levels) > .025:
            self._last_audio = time.monotonic()
        self._notch_audio_active = time.monotonic()-self._last_audio < .8
        self.status_mark.set_spectrum(levels)
        self._notch_stage.sync()
        if self.isVisible():
            self._notch_stage.surface.update()

    def _audio_available(self, available):
        self.status_mark.available = available
        reason = ("Спектр системного звука" if available else
                  "Спектр выключен в настройках" if not self.settings.get("spectrum") else
                  "Спектр приостановлен для экономии батареи" if not self._policy.spectrum else
                  "Выходное аудиоустройство недоступно")
        self.status_mark.setToolTip(reason)
        self.setToolTip(reason)
        self.status_mark.update()
        if self.isVisible():
            self._notch_stage.surface.update()

    def _media_error(self, message):
        self.notch_hub.title.setToolTip("Медиасессии Windows временно недоступны")

    def notice(self, text):
        self._notch_notice = text
        self._notice_timer.stop()
        if text:
            self._notice_timer.start(2600)
        self._notch_stage.sync()

    def _timer_finished(self):
        self.notice("Таймер завершён")
        if self._services:
            self.tray.showMessage(APP_NAME, "Время таймера истекло")
            if self._policy.island and not self._hidden_by_user and not self._fs_hidden:
                self._show_panel()
                self.notch_hub.select_tab(1)

    def _system_tick(self):
        self._notch_audio_active = time.monotonic()-self._last_audio < .8
        self.notch_idle.setText(fmt(self.notch_hub.timer_seconds()) if self.notch_hub._timer_end else datetime.now().strftime("%H:%M"))
        state = battery_state()
        self.notch_hub.battery.setText(("⚡ " if state and state[1] else "") + f"{state[0]}%" if state else "")
        if state and self._last_battery and state[1] != self._last_battery[1]:
            self.notice(("Зарядка · " if state[1] else "Батарея · ")+f"{state[0]}%")
        self._last_battery = state
        self._apply_policy()
        if self._services:
            self._sync_visibility()
            self._update_services()
        self._notch_stage.sync()

    def _apply_policy(self):
        plugged = self._last_battery[1] if self._last_battery else None
        self._policy = runtime_policy(self.settings, plugged, self._island_expanded)
        self._economy = self._policy.profile == "battery"
        # Search is native now. Keep Command Palette off while we own this connection.
        external = (False, self._policy.layouts, self._policy.workspaces)
        if hasattr(self, "modules"):
            self.modules.sync()
        if self._services and self.settings.get("manage_powertoys") and external != self._external_policy:
            self._external_policy = external
            self.powertoys.configure(dict(zip(("CmdPal", "FancyZones", "Workspaces"), external)))

    def _update_services(self):
        if not self._services:
            return
        active = self._policy.island and not self._hidden_by_user and not self._fs_hidden and self.isVisible()
        spectrum = active and self._policy.spectrum
        self.audio.set_economy(self._economy and not self._island_expanded)
        if self.worker.enabled.is_set() != active:
            self.worker.set_enabled(active)
        if self.audio.enabled.is_set() != spectrum:
            self.audio.set_enabled(spectrum)
            if not spectrum:
                self._audio_levels((0.,)*5)
        if active and not self._notch_pointer_timer.isActive():
            self._notch_pointer.last_time = time.monotonic()
            self._notch_pointer_timer.start(16)
        elif not active:
            self._notch_pointer_timer.stop()
            self._notch_pointer.route_input(False)
            self._geometry.stop()
            self._notch_hover_timer.stop()
            self._island_auto_timer.stop()
            if self._island_expanded or (self.width(), self.height()) != self._scale_window_size(50):
                self._island_expanded = False
                self._place()
        self._system_timer.setInterval(500 if active else 2000)
        clock = self.notch_hub.clock
        if (active and self._island_expanded) or self.notch_hub._timer_end:
            if not clock.isActive():
                clock.start(1000)
        else:
            clock.stop()

    def _sync_visibility(self):
        if self._closed:
            return
        if self._hidden_by_user or not self._policy.island:
            self.hide()
            return
        fullscreen = self.settings.get("hide_fullscreen") and is_fullscreen(self)
        if fullscreen:
            self._fs_hidden = True
            self.hide()
            return
        if self._fs_hidden:
            self._fs_hidden = False
            self.show()
        if desktop_is_foreground():
            if not self.isVisible():
                self.show()
            keep_desktop_visible(self)

    def _toggle_setting(self, key, enabled):
        if key.startswith("hotkey_"):
            from .hotkey import parse_shortcut
            try:
                parsed = parse_shortcut(enabled)
                duplicate = parsed and any(k != key and parse_shortcut(v) == parsed
                    for k,v in self.settings.values.items() if k.startswith("hotkey_"))
                if duplicate:
                    raise ValueError("Это сочетание уже назначено другому действию Cloud Hub")
                binding = self.hotkeys.get(key)
                if binding and not binding.rebind(enabled):
                    raise ValueError(binding.error)
            except ValueError as error:
                if self.control_center:
                    self.control_center._message(str(error))
                return False
        if key == "autostart" and not autostart(enabled):
            self.tray.showMessage(APP_NAME, "Не удалось изменить автозапуск")
            return
        try:
            self.settings.set(key, enabled)
        except OSError:
            if key in self.hotkeys:
                self.hotkeys[key].rebind(self.settings.get(key))
            if self.control_center:
                self.control_center._message("Не удалось записать настройки на диск. Изменение не сохранено.")
            return False
        if key.endswith(("_width", "_height")) and key.startswith(("compact", "expanded")):
            self.art_label.set_image(self._notch_art(self.snapshot.thumb, min(40,self.settings.get("compact_height")-12),7))
            self._notch_stage._signature = None
            self._place()
        if key == "island_opacity":
            self.setWindowOpacity(enabled/100)
        if key == "timer_minutes":
            self.notch_hub.set_timer_minutes(enabled)
        if key == "monitor":
            self._place()
        if key == "overview_calendar":
            self.notch_hub.calendar.setVisible(enabled)
        if key == "overview_focus":
            self.notch_hub.focus_preview.setVisible(enabled)
        if key == "island_files":
            self.notch_hub.tabs[3].setVisible(enabled)
            if not enabled and self.notch_hub.stack.currentIndex() == 3:
                self.notch_hub.select_tab(0)
        if key.startswith("group"):
            self.modules.desktop.reconcile()
            self.modules.desktop.reposition()
        if key == "manage_powertoys":
            self._external_policy = None
        self._apply_policy()
        if key == "hide_fullscreen" and not enabled and self._fs_hidden:
            self._fs_hidden = False
            self.show()
        if self._services:
            self._sync_visibility()
            # A module can be enabled while a previously hidden window has no
            # desktop foreground: explicitly restore it, then check full-screen.
            if self._policy.island and not self._hidden_by_user and not self._fs_hidden:
                self.show()
            self._update_services()
        self._notch_stage.sync()
        if self.control_center:
            self.control_center.refresh()
        self._build_menu()
        return True

    def show_search(self):
        self.modules.search.toggle()

    def _build_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: #17171c; color: #eeeeef; padding: 6px; border: 1px solid #35353d; } QMenu::item { padding: 7px 18px; } QMenu::item:selected { background: #33333e; }")
        menu.addAction(f"Cloud Hub {__version__}").setEnabled(False)
        menu.addAction("Центр управления", self.show_hub)
        menu.addAction("Открыть остров", self._show_panel)
        profiles = menu.addMenu("Профиль")
        for value, title in PROFILES.items():
            action = profiles.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.settings.get("profile") == value)
            action.triggered.connect(lambda checked=False, p=value: self._toggle_setting("profile", p))
        action = menu.addAction("Приостановить модули")
        action.setCheckable(True)
        action.setChecked(self.settings.get("paused"))
        action.triggered.connect(lambda value: self._toggle_setting("paused", value))
        menu.addSeparator()
        for key, title in (("autostart", "Запускать с Windows"), ("spectrum", "Живой спектр звука"),
                           ("volume_scroll_reverse", "Обратить громкость при прокрутке"),
                           ("hide_fullscreen", "Скрывать в полноэкранных приложениях"), ("updates", "Проверять обновления")):
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.settings.get(key))
            action.triggered.connect(lambda enabled, k=key: self._toggle_setting(k, enabled))
        displays = menu.addMenu("Экран")
        for screen in QApplication.screens():
            action = displays.addAction(screen.name())
            action.setCheckable(True)
            action.setChecked(screen.name() == self.screen().name())
            action.triggered.connect(lambda _, name=screen.name(): self._choose_monitor(name))
        menu.addSeparator()
        menu.addAction("Проверить обновления сейчас", self._check_update)
        if self._update_info:
            menu.addAction(f"Обновить до {self._update_info['version']}…", self._show_updates)
        menu.addAction("Страница проекта ↗", lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        menu.addAction("Открыть папку данных", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.settings.directory))))
        menu.addSeparator()
        menu.addAction("Скрыть", self._hide_user)
        menu.addAction("Выход", QApplication.instance().quit)
        previous = getattr(self, "menu", None)
        self.menu = menu
        self.tray.setContextMenu(menu)
        if previous:
            previous.deleteLater()

    def _choose_monitor(self, name):
        self.settings.set("monitor", name)
        self._place()

    def _hide_user(self):
        self._hidden_by_user = True
        self.hide()
        self._update_services()

    def _show_panel(self):
        if not self._policy.island:
            self.show_hub()
            self.control_center._message("Включи чёлку и выбери рабочий профиль или сними паузу.")
            return
        self._hidden_by_user = self._fs_hidden = False
        self.show()
        self._set_island_expanded(True)
        self.raise_()
        self._update_services()

    def show_hub(self):
        if self.control_center is None:
            from .control_center import ControlCenter
            self.control_center = ControlCenter(self)
        self.control_center.showNormal()
        self.control_center.raise_()
        self.control_center.activateWindow()

    def _tray_activate(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_hub()

    def _scheduled_update(self):
        if self.settings.get("updates"):
            self.updates.check()

    def _check_update(self):
        self._show_updates()
        self._manual_update = True
        self.updates.check()

    def _show_updates(self):
        self.show_hub()
        self.control_center.navigate('updates')

    def _install_update(self):
        if self.control_center:
            if not self.control_center.group_editor.rename_current():
                self.control_center.navigate('desktop')
                return
            self.control_center.notebook.flush()
        self.notch_hub.save_notes()
        remaining=self.notch_hub.timer_seconds()
        self.updates.install({'source_exe':sys.executable,'parent_pid':os.getpid(),
            'timer':{'remaining':remaining,'running':bool(self.notch_hub._timer_end),'deadline':time.time()+remaining}})

    def _update_result(self, result):
        if result["status"] == "available":
            self._update_info = result
            self._build_menu()
            if not (self.control_center and self.control_center.isVisible()):
                self.tray.showMessage(APP_NAME, f"Доступна версия {result['version']}. Обновиться можно в Cloud Hub → Обновления.")
        self._manual_update = False

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        self._wheel_source.close()
        for binding in self.hotkeys.values():
            binding.close()
        self.modules.close()
        if self.control_center:
            self.control_center.close()
        self.powertoys.close(restore=self._services and self.settings.get("manage_powertoys"))
        self.notch_hub.save_notes()
        self.notch_hub._timer_end = None
        self.notch_hub.alarm.dismiss()
        self.notch_hub.clock.stop()
        self.notch_hub._note_save.stop()
        self._notch_pointer_timer.stop()
        self._system_timer.stop()
        self._geometry.stop()
        self._notch_pointer.route_input(False)
        self.worker.stop()
        self.audio.stop()
        for thread in (self.worker, self.audio):
            if thread.isRunning():
                thread.wait(10000)
        self.tray.hide()


def run(background=False, island=False, updated=False):
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BochkaPiva")
    app.setFont(font(12))
    app.setQuitOnLastWindowClosed(False)
    if notify_existing("ping" if background else "show" if island else "hub"):
        return 0
    lock = QSharedMemory(server_name())
    if not lock.create(1):
        return 0
    window = IslandWindow()
    server = InstanceServer(window, app)
    if not server.listen():
        window.cleanup()
        return 1
    app.aboutToQuit.connect(window.cleanup)
    window._sync_visibility()
    if window._policy.island and not window._hidden_by_user and not window._fs_hidden:
        window.show()
    window._update_services()
    if not background:
        window._show_panel() if island else window.show_hub()
        if updated and window.control_center:
            window.control_center.navigate('updates')
    return app.exec()
