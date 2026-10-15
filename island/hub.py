# SPDX-License-Identifier: GPL-3.0-only
"""Windows notch hub: local utilities and real SMTC controls, no service accounts."""
from __future__ import annotations

import calendar
import ctypes
import json
import math
from pathlib import Path
import time

from PyQt6.QtCore import Qt, QDate, QLocale, QMimeData, QPoint, QRectF, QTimer, QUrl, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget, QGraphicsOpacityEffect)
from . import style as gs


def battery_state():
    class Power(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                    ("percent", ctypes.c_ubyte), ("reserved", ctypes.c_ubyte),
                    ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
    p = Power()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)):
            return None
        if p.flags == 255 or p.flags & 128 or p.percent > 100:
            return None
        return p.percent, p.ac == 1
    except Exception:
        return None


def fmt(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02}"


class CalendarPeek(QWidget):
    """Local calendar; deliberately does not imply access to account events."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.day = QDate.currentDate()
        self.setMinimumSize(210, 128)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self.day = QDate.currentDate()
        loc = QLocale(QLocale.Language.Russian)
        p.setPen(QColor("#fafafa"))
        p.setFont(gs.font(16, 600))
        p.drawText(0, 21, loc.toString(d, "d MMMM"))
        p.setFont(gs.font(10, 500))
        p.setPen(QColor("#707078"))
        cell = self.width() / 7
        for col, name in enumerate(("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")):
            p.drawText(QRectF(col * cell, 32, cell, 18), Qt.AlignmentFlag.AlignCenter, name)
        rows = calendar.monthcalendar(d.year(), d.month())
        height = min(21, (self.height() - 52) / len(rows))
        for row, week in enumerate(rows):
            for col, value in enumerate(week):
                if not value:
                    continue
                rect = QRectF(col * cell, 52 + row * height, cell, height)
                selected = value == d.day()
                if selected:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#477bff"))
                    size = min(height - 1, 22)
                    p.drawEllipse(rect.center(), size / 2, size / 2)
                p.setPen(QColor("#ffffff" if selected else "#a3a3ab"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(value))


class FileShelf(QListWidget):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.store = path
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setSpacing(3)
        self.itemDoubleClicked.connect(self.open_item)
        try:
            self.add_paths(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            pass
        self.setToolTip("Перетащи файлы сюда. Двойной щелчок — открыть. Delete — убрать ссылку.")

    def paths(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def add_paths(self, paths):
        existing = set(self.paths())
        for name in paths:
            path = Path(name)
            if not path.exists() or str(path) in existing or self.count() >= 100:
                continue
            item = QListWidgetItem(("Папка · " if path.is_dir() else "") + path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.addItem(item)
            existing.add(str(path))
        self.persist()

    def persist(self):
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            temp = self.store.with_suffix(".tmp")
            temp.write_text(json.dumps(self.paths(), ensure_ascii=False), encoding="utf-8")
            temp.replace(self.store)
        except OSError:
            self.setToolTip("Не удалось сохранить полку на диск")

    def open_item(self, item):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
            if hasattr(self.window(), "_island_auto_timer"):
                self.window()._island_auto_timer.stop()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        self.add_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if hasattr(self.window(), "_island_auto_timer"):
            self.window()._island_auto_timer.start(2400)

    def dragLeaveEvent(self, event):
        if hasattr(self.window(), "_island_auto_timer"):
            self.window()._island_auto_timer.start(700)
        event.accept()

    def startDrag(self, actions):
        urls = [QUrl.fromLocalFile(i.data(Qt.ItemDataRole.UserRole)) for i in self.selectedItems()]
        mime = QMimeData()
        mime.setUrls(urls)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            self.persist()
        else:
            super().keyPressEvent(event)


class NotchHub(QWidget):
    timer_finished = pyqtSignal()
    source_selected = pyqtSignal(str)

    def __init__(self, owner, store: Path):
        super().__init__(owner.card)
        self.owner = owner
        self.store = store
        self.snap = None
        self._art_data = None
        self._position_at = time.monotonic()
        self._timer_end = None
        self._timer_remaining = 25 * 60
        self._sources = None
        self._fade_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fade_effect)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(240)
        self._fade.setEasingCurve(gs.ease_out())
        self._fade.valueChanged.connect(self._fade_effect.setOpacity)
        self.setObjectName("notchHub")
        self.setStyleSheet("""
            QWidget#notchHub { background: transparent; }
            QLabel { background: transparent; color: #eeeeef; }
            QPushButton { color: #9999a2; background: transparent; border: none;
                          border-radius: 10px; padding: 5px 10px; }
            QPushButton:hover { background: #19191c; color: white; }
            QPushButton:checked { background: #202025; color: white; }
            QComboBox { color: #9999a2; background: #101013; border: none; border-radius: 7px; padding: 4px; }
            QComboBox::drop-down { border: none; width: 14px; }
            QComboBox QAbstractItemView { color: white; background: #17171b; selection-background-color: #303039; }
            QSlider::groove:horizontal { height: 3px; background: #29292e; border-radius: 1px; }
            QSlider::sub-page:horizontal { background: #dddde2; border-radius: 1px; }
            QSlider::handle:horizontal { width: 9px; margin: -3px 0; background: #ffffff; border-radius: 4px; }
            QListWidget, QPlainTextEdit { background: #101013; color: #d0d0d6; border: none;
                                        border-radius: 12px; padding: 8px; selection-background-color: #2d4b8e; }
            QListWidget::item { padding: 6px; border-radius: 6px; }
            QListWidget::item:selected { background: #263559; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 15, 26, 16)
        root.setSpacing(10)
        bar = QHBoxLayout()
        self.tabs = []
        for index, name in enumerate(("Обзор", "Файлы", "Заметки")):
            button = QPushButton(name)
            button.setCheckable(True)
            button.clicked.connect(lambda _, i=index: self.select_tab(i))
            bar.addWidget(button)
            self.tabs.append(button)
        bar.addStretch(1)
        self.battery = QLabel()
        self.battery.setFont(gs.font(10, 500))
        bar.addWidget(self.battery)
        root.addLayout(bar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        dashboard = QWidget()
        columns = QHBoxLayout(dashboard)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(28)
        media = QVBoxLayout()
        media.setSpacing(7)
        heading = QHBoxLayout()
        self.art = QLabel()
        self.art.setFixedSize(54, 54)
        self.art.setCursor(Qt.CursorShape.PointingHandCursor)
        self.art.mouseReleaseEvent = lambda e: owner.open_source()
        labels = QVBoxLayout()
        labels.setSpacing(2)
        self.title = QLabel("Ничего не играет")
        self.title.setFont(gs.font(14, 600))
        self.artist = QLabel("Запусти музыку или видео")
        self.artist.setFont(gs.font(11, 400))
        self.artist.setStyleSheet("color: #8b8b95")
        labels.addWidget(self.title)
        labels.addWidget(self.artist)
        heading.addWidget(self.art)
        heading.addLayout(labels, 1)
        media.addLayout(heading)
        self.sources = QComboBox()
        self.sources.setFont(gs.font(10, 500))
        self.sources.activated.connect(lambda i: self.source_selected.emit(self.sources.itemData(i) or ""))
        media.addWidget(self.sources)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.sliderReleased.connect(self._seek)
        media.addWidget(self.seek)
        times = QHBoxLayout()
        self.elapsed = QLabel("0:00")
        self.duration = QLabel("0:00")
        for label in (self.elapsed, self.duration):
            label.setFont(gs.font(9, 400))
            label.setStyleSheet("color: #666670")
        times.addWidget(self.elapsed)
        times.addStretch(1)
        times.addWidget(self.duration)
        media.addLayout(times)
        transport = QHBoxLayout()
        transport.addStretch(1)
        self.buttons = []
        for kind, action, size in (("prev", "previous", 20), ("play", "play_pause", 26), ("next", "next", 20)):
            button = gs.TransportButton(kind)
            button.setFixedSize(40, 34)
            button.set_glyph(size)
            button.clicked.connect(lambda _, a=action: owner.send_control(a))
            transport.addWidget(button)
            self.buttons.append(button)
        transport.addStretch(1)
        media.addLayout(transport)
        columns.addLayout(media, 6)
        right = QVBoxLayout()
        self.calendar = CalendarPeek()
        right.addWidget(self.calendar, 1)
        timer_bar = QHBoxLayout()
        self.timer_button = QPushButton("Старт 25:00")
        self.timer_button.clicked.connect(self.toggle_timer)
        self.reset_button = QPushButton("Сброс")
        self.reset_button.clicked.connect(self.reset_timer)
        self.preset = QComboBox()
        self.preset.addItems(["25 мин", "5 мин", "15 мин", "60 мин"])
        self.preset.currentIndexChanged.connect(self.reset_timer)
        timer_bar.addWidget(self.timer_button)
        timer_bar.addWidget(self.reset_button)
        timer_bar.addWidget(self.preset)
        right.addLayout(timer_bar)
        columns.addLayout(right, 5)
        self.stack.addWidget(dashboard)

        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel("Перетащи файлы в остров · двойной щелчок — открыть · Delete — убрать")
        hint.setFont(gs.font(10, 400))
        files_layout.addWidget(hint)
        self.shelf = FileShelf(store / "notch-files.json")
        files_layout.addWidget(self.shelf)
        self.stack.addWidget(files_page)
        self.notes = QPlainTextEdit()
        self.notes.setFont(gs.font(12, 400))
        self.notes.setPlaceholderText("Быстрая заметка… Сохраняется на этом компьютере.")
        try:
            self.notes.setPlainText((store / "notch-notes.txt").read_text(encoding="utf-8"))
        except OSError:
            pass
        self._note_save = QTimer(self)
        self._note_save.setSingleShot(True)
        self._note_save.timeout.connect(self.save_notes)
        self.notes.textChanged.connect(lambda: self._note_save.start(500))
        self.stack.addWidget(self.notes)
        self.select_tab(0)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(500)

    def select_tab(self, index):
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.tabs):
            button.setChecked(i == index)
        self.owner._island_auto_timer.stop()

    def save_notes(self):
        try:
            self.store.mkdir(parents=True, exist_ok=True)
            target = self.store / "notch-notes.txt"
            temp = target.with_suffix(".tmp")
            temp.write_text(self.notes.toPlainText(), encoding="utf-8")
            temp.replace(target)
        except OSError:
            self.notes.setToolTip("Не удалось сохранить заметку на диск")

    def showEvent(self, event):
        super().showEvent(event)
        stage = getattr(self.owner, "_notch_stage", None)
        if stage is not None and stage.active:
            return
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.snap is not None:
            self._refresh_text()

    def update_snapshot(self, snap):
        self.snap = snap
        self._position_at = time.monotonic()
        self._refresh_text()
        title = snap.title or ("Неизвестный трек" if snap.has_session else "Ничего не играет")
        artist = snap.artist or ("" if snap.has_session else "Запусти музыку или видео")
        if snap.thumb != self._art_data:
            self._art_data = snap.thumb
            pix = QPixmap()
            pix.loadFromData(snap.thumb)
            if pix.isNull():
                pix = gs.art_placeholder(54, 10, self.devicePixelRatioF())
            else:
                pix = self.owner._notch_art(snap.thumb, 54, 10)
            self.art.setPixmap(pix)
        playing = "play" in snap.status.lower() and "pause" not in snap.status.lower()
        self.buttons[1].set_kind("pause" if playing else "play")
        for button, enabled in zip(self.buttons, (snap.can_prev, snap.can_play or snap.can_pause, snap.can_next)):
            button.setEnabled(snap.has_session and enabled)
        self.seek.setEnabled(snap.can_seek and snap.dur_sec > 0)
        sources = tuple(getattr(snap, "sources", ()))
        if sources != self._sources:
            self._sources = sources
            selected = self.owner.worker.preferred_source if hasattr(self.owner, "worker") else ""
            self.sources.clear()
            self.sources.addItem("Автоматически · активный плеер", "")
            for aumid in sources:
                self.sources.addItem(self.owner._notch_source_name(aumid), aumid)
            self.sources.setCurrentIndex(max(0, self.sources.findData(selected)))
        self.tick()

    def _refresh_text(self):
        snap = self.snap
        title = snap.title or ("Неизвестный трек" if snap.has_session else "Ничего не играет")
        artist = snap.artist or ("" if snap.has_session else "Запусти музыку или видео")
        width = max(120, self.width() // 2 - 110)
        self.title.setText(self.title.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, width))
        self.title.setToolTip(title)
        self.artist.setText(self.artist.fontMetrics().elidedText(artist, Qt.TextElideMode.ElideRight, width))
        self.artist.setToolTip(artist)

    def _seek(self):
        if self.snap and self.seek.isEnabled():
            position = self.seek.value() / 1000 * self.snap.dur_sec
            self.owner.send_seek(position + self.snap.start_sec)
            self.snap.pos_sec = position
            self._position_at = time.monotonic()

    def timer_seconds(self):
        return max(0, math.ceil(self._timer_end - time.monotonic())) if self._timer_end else self._timer_remaining

    def toggle_timer(self):
        if self._timer_end:
            self._timer_remaining = self.timer_seconds()
            self._timer_end = None
        else:
            if self._timer_remaining <= 0:
                self.reset_timer()
            self._timer_end = time.monotonic() + self._timer_remaining
        self.tick()

    def reset_timer(self, *args):
        self._timer_end = None
        self._timer_remaining = (25, 5, 15, 60)[self.preset.currentIndex()] * 60
        self.tick()

    def tick(self):
        if self._timer_end and self.timer_seconds() <= 0:
            self._timer_end = None
            self._timer_remaining = 0
            self.timer_finished.emit()
        self.timer_button.setText(("Пауза " if self._timer_end else "Старт ") + fmt(self.timer_seconds()))
        if self.snap and self.isVisible():
            snap = self.snap
            playing = "play" in snap.status.lower() and "pause" not in snap.status.lower()
            pos = max(0, snap.pos_sec + (time.monotonic() - self._position_at if playing else 0))
            dur = max(0, snap.dur_sec)
            pos = min(pos, dur) if dur else 0
            if not self.seek.isSliderDown():
                self.seek.setValue(round(pos / dur * 1000) if dur else 0)
            self.elapsed.setText(fmt(pos))
            self.duration.setText(fmt(dur))
            self.calendar.update()

    def busy(self):
        return self.seek.isSliderDown() or self.notes.hasFocus() or self.shelf.state() == self.shelf.State.DraggingState
