# SPDX-License-Identifier: GPL-3.0-only
"""Windows notch hub: local utilities and real SMTC controls, no service accounts."""
from __future__ import annotations

import calendar
import ctypes
import json
import math
from pathlib import Path
import time

from PyQt6.QtCore import Qt, QDate, QLocale, QMimeData, QPoint, QRectF, QTimer, QUrl, QVariantAnimation, pyqtSignal, QFileInfo
from PyQt6.QtGui import QColor, QDesktopServices, QDrag, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget,
    QSpinBox, QFileDialog, QFileIconProvider, QMenu)
from . import style as gs
from .timer import TimerReadout, TimerAlarm


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
    """Seven-day strip, centered on today; animated touchpad/drag navigation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(142,80)
        self.setMouseTracking(True)
        self.setToolTip("Листай колёсиком, тачпадом или перетаскиванием. Нажми месяц — вернуться к сегодня.")
        self.position = 0.0
        self.target = 0.0
        self.today = QDate.currentDate()
        self.drag_at = None
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(260)
        self.animation.setEasingCurve(gs.ease_out())
        self.animation.valueChanged.connect(self._frame)
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.timeout.connect(lambda:self.scroll_to(round(self.target)))

    def _frame(self,value):
        self.position = float(value)
        self.update()

    def scroll_to(self,offset):
        self.target = max(-3650,min(3650,offset))
        self.animation.stop()
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(self.target))
        self.animation.start()

    def wheelEvent(self,event):
        delta = event.pixelDelta()
        if not delta.isNull():
            amount = (delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y())/32
        else:
            delta = event.angleDelta()
            amount = (delta.x() if abs(delta.x()) > abs(delta.y()) else delta.y())/120
        self.scroll_to(self.target-amount)
        self.snap_timer.start(180)
        event.accept()

    def mousePressEvent(self,event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.animation.stop()
        self.snap_timer.stop()
        self.drag_at = (event.position().x(),self.position,event.position().y())

    def mouseMoveEvent(self,event):
        if self.drag_at:
            self.position = max(-3650,min(3650,self.drag_at[1]-(event.position().x()-self.drag_at[0])/(self.width()/7)))
            self.target = self.position
            self.update()

    def mouseReleaseEvent(self,event):
        if not self.drag_at:
            return
        moved = abs(event.position().x()-self.drag_at[0])
        self.drag_at = None
        if moved < 4:
            if event.position().y() < 22:
                if event.position().x() > self.width()-18:
                    self.scroll_to(round(self.position)+7)
                elif event.position().x() > self.width()-38:
                    self.scroll_to(round(self.position)-7)
                else:
                    self.scroll_to(0)
            elif 25 <= event.position().y() <= 70:
                self.scroll_to(round(self.position+(event.position().x()/self.width()*7-3.5)))
        else:
            self.scroll_to(round(self.position))

    def paintEvent(self,event):
        now = QDate.currentDate()
        if now != self.today:
            self.today = now
        loc = QLocale(QLocale.Language.Russian)
        center = self.today.addDays(round(self.position))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#e1e1e7"))
        painter.setFont(gs.font(10,600))
        painter.drawText(0,15,loc.toString(center,"MMM").capitalize())
        painter.setPen(QColor("#64646f"))
        painter.drawText(self.width()-34,15,"‹")
        painter.drawText(self.width()-14,15,"›")
        cell = self.width()/7
        first = math.floor(self.position)-4
        painter.save()
        painter.setClipRect(QRectF(0,22,self.width(),51))
        for offset in range(first,first+10):
            date = self.today.addDays(offset)
            x = (offset-self.position+3)*cell
            edge = min(1.,max(.15, min(x+cell,self.width()-x)/cell))
            painter.setOpacity(edge)
            painter.setFont(gs.font(8,500))
            painter.setPen(QColor("#6e6e7a"))
            painter.drawText(QRectF(x,24,cell,16),Qt.AlignmentFlag.AlignCenter,loc.toString(date,"ddd")[:2])
            rect = QRectF(x,43,cell,23)
            if offset == 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#4e86ff"))
                painter.drawEllipse(rect.center(),10.5,10.5)
            painter.setPen(QColor("#ffffff" if offset == 0 else "#a9a9b4"))
            painter.setFont(gs.font(9,600 if offset == 0 else 400))
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,str(date.day()))
        painter.restore()
        painter.setFont(gs.font(8,400))
        painter.setPen(QColor("#666671"))
        caption = "Сегодня" if round(self.position) == 0 else loc.toString(center,"d MMMM")
        painter.drawText(QRectF(0,73,self.width(),16),Qt.AlignmentFlag.AlignCenter,caption)


class FileShelf(QListWidget):
    changed = pyqtSignal()

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.store = path
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setSpacing(3)
        self.itemDoubleClicked.connect(self.open_item)
        self.icons = QFileIconProvider()
        if path is not None:
            self.reload()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context_menu)
        self.setToolTip("Перетащи файлы сюда. Двойной щелчок — открыть. Delete — убрать ссылку.")

    def reload(self):
        try:
            paths = json.loads(self.store.read_text(encoding="utf-8"))
            if isinstance(paths, list):
                self.clear()
                self.add_paths([p for p in paths if isinstance(p, str)], save=False, keep_missing=True)
        except (OSError, ValueError, TypeError):
            pass

    def paths(self):
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def add_paths(self, paths, save=True, keep_missing=False):
        existing = set(self.paths())
        for name in paths:
            path = Path(name)
            if (not keep_missing and not path.exists()) or str(path) in existing or self.count() >= 100:
                continue
            item = QListWidgetItem(("Папка · " if path.is_dir() else "") + path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setIcon(self.icon_for(path))
            self.addItem(item)
            existing.add(str(path))
        if save:
            self.persist()

    def icon_for(self,path):
        return self.icons.icon(QFileInfo(str(path)))

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Добавить ссылки на файлы")
        if paths:
            self.add_paths(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Добавить ссылку на папку")
        if path:
            self.add_paths([path])

    def remove_selected(self):
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.persist()

    def context_menu(self, point):
        item = self.itemAt(point)
        menu = QMenu(self)
        if item:
            menu.addAction("Открыть", lambda: self.open_item(item))
            menu.addAction("Открыть расположение", lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(item.data(Qt.ItemDataRole.UserRole)).parent))))
            menu.addAction("Убрать ссылку из списка", self.remove_selected)
            self.extra_context_actions(menu,item)
            menu.addSeparator()
        menu.addAction("Добавить файлы…", self.add_files)
        menu.addAction("Добавить папку…", self.add_folder)
        menu.exec(self.viewport().mapToGlobal(point))

    def extra_context_actions(self,menu,item):
        pass

    def persist(self):
        if self.store is None:
            return
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            temp = self.store.with_suffix(".tmp")
            temp.write_text(json.dumps(self.paths(), ensure_ascii=False), encoding="utf-8")
            temp.replace(self.store)
            self.changed.emit()
        except OSError:
            self.setToolTip("Не удалось сохранить полку на диск")

    def open_item(self, item):
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.setToolTip("Файл сейчас недоступен. Ссылка сохранена; подключи диск или убери её из списка.")

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
            self.remove_selected()
        else:
            super().keyPressEvent(event)


class PageTransition(QWidget):
    """Paint transition snapshots without nesting Qt graphics effects."""
    def __init__(self,parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.old = self.new = None
        self.fraction = 1.
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(gs.ease_out())
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self.hide)
        self.hide()

    def frame(self,value):
        self.fraction = float(value)
        self.update()

    def start(self,old,new):
        self.animation.stop()
        self.old,self.new = old,new
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.start()

    def paintEvent(self,event):
        p = QPainter(self)
        p.fillRect(self.rect(),QColor("black"))
        p.setOpacity(1-self.fraction)
        p.drawPixmap(round(-6*self.fraction),0,self.old)
        p.setOpacity(self.fraction)
        p.drawPixmap(round(6*(1-self.fraction)),0,self.new)


class NotchHub(QWidget):
    timer_finished = pyqtSignal()
    source_selected = pyqtSignal(str)

    def __init__(self, owner, store: Path):
        super().__init__(owner.card)
        self.owner, self.store = owner, store
        self.snap, self._art_data, self._sources = None, None, None
        self._position_at = time.monotonic()
        self._timer_end = None
        self._timer_remaining = owner.settings.get("timer_minutes")*60
        self.alarm = TimerAlarm(owner.settings,self)
        self.setObjectName("notchHub")
        self.setStyleSheet("""
            QWidget#notchHub {background:transparent;}
            QLabel {background:transparent;color:#eeeeef;}
            QPushButton {color:#92929c;background:transparent;border:0;border-radius:9px;padding:5px 11px;}
            QPushButton:hover {background:#1b1b20;color:white;}
            QPushButton:checked {background:#222229;color:white;}
            QComboBox, QSpinBox {color:#dddde5;background:#131318;border:0;border-radius:7px;padding:5px;}
            QComboBox::drop-down {border:0;width:14px;}
            QComboBox QAbstractItemView {color:white;background:#17171b;selection-background-color:#303039;}
            QSlider::groove:horizontal {height:3px;background:#29292e;border-radius:1px;}
            QSlider::sub-page:horizontal {background:#dddde2;}
            QSlider::handle:horizontal {width:9px;margin:-3px 0;background:white;border-radius:4px;}
            QListWidget, QPlainTextEdit {background:#111115;color:#d0d0d6;border:0;border-radius:10px;padding:8px;selection-background-color:#2d4b8e;}
            QListWidget::item {padding:5px;} QListWidget::item:selected {background:#263559;}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 10, 22, 13)
        root.setSpacing(9)
        bar = QHBoxLayout()
        self.tabs = []
        # Files are optional; the default island is music, focus and a quick note.
        for index, name in enumerate(("Обзор", "Фокус", "Заметка", "Полка")):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFont(gs.font(10, 500))
            btn.clicked.connect(lambda _, i=index: self.select_tab(i))
            bar.addWidget(btn)
            self.tabs.append(btn)
        self.tabs[3].setVisible(owner.settings.get("island_files"))
        bar.addStretch()
        self.battery = QLabel()
        self.battery.setFont(gs.font(9,500))
        self.battery.setStyleSheet("color:#707079")
        bar.addWidget(self.battery)
        source_button = QPushButton("♫")
        source_button.setToolTip("Выбрать плеер")
        source_button.clicked.connect(self.choose_source)
        bar.addWidget(source_button)
        settings_button = QPushButton("•••")
        settings_button.setToolTip("Открыть Cloud Hub")
        settings_button.clicked.connect(owner.show_hub)
        bar.addWidget(settings_button)
        root.addLayout(bar)
        self.stack = QStackedWidget()
        self._page_transition = PageTransition(self.stack)
        root.addWidget(self.stack,1)

        dashboard = QWidget()
        columns = QHBoxLayout(dashboard)
        columns.setContentsMargins(0,0,0,0)
        columns.setSpacing(16)
        player = QWidget()
        player.setMinimumWidth(215)
        player.setMaximumWidth(320)
        media = QVBoxLayout(player)
        media.setContentsMargins(0,0,0,0)
        media.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.art = QLabel()
        self.art.setFixedSize(64,64)
        self.art.setPixmap(gs.art_placeholder(64,12,self.devicePixelRatioF()))
        top.addWidget(self.art)
        info = QVBoxLayout()
        info.setSpacing(2)
        self.title = QLabel("Ничего не играет")
        self.title.setFont(gs.font(11,600))
        self.artist = QLabel("Запусти музыку")
        self.artist.setFont(gs.font(9,400))
        self.artist.setStyleSheet("color:#858591")
        info.addWidget(self.title)
        info.addWidget(self.artist)
        transport = QHBoxLayout()
        transport.setContentsMargins(0,0,0,0)
        transport.setSpacing(6)
        self.buttons = []
        for kind,action,size in (("prev","previous",13),("play","play_pause",17),("next","next",13)):
            btn = gs.TransportButton(kind)
            btn.setFixedSize(25,23)
            btn.set_glyph(size)
            btn.clicked.connect(lambda _,a=action: owner.send_control(a))
            transport.addWidget(btn)
            self.buttons.append(btn)
        transport.addStretch()
        info.addLayout(transport)
        top.addLayout(info,1)
        media.addLayout(top)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0,1000)
        self.seek.sliderReleased.connect(self._seek)
        self.seek.setToolTip("Перемотка текущего плеера")
        media.addWidget(self.seek)
        times = QHBoxLayout()
        self.elapsed,self.duration = QLabel("0:00"),QLabel("0:00")
        for label in (self.elapsed,self.duration):
            label.setFont(gs.font(8,400))
            label.setStyleSheet("color:#60606c")
        times.addWidget(self.elapsed)
        times.addStretch()
        times.addWidget(self.duration)
        media.addLayout(times)
        self.sources = QComboBox(self)
        self.sources.hide()
        self.sources.currentIndexChanged.connect(lambda _:self.source_selected.emit(self.sources.currentData() or ""))
        columns.addWidget(player,5)
        self.calendar = CalendarPeek(dashboard)
        self.calendar.setVisible(owner.settings.get("overview_calendar"))
        columns.addWidget(self.calendar,4)
        self.focus_preview = QWidget(dashboard)
        self.focus_preview.setMinimumWidth(70)
        self.focus_preview.setMaximumWidth(100)
        focus_preview = QVBoxLayout(self.focus_preview)
        focus_preview.setContentsMargins(0,0,0,0)
        focus_preview.setSpacing(4)
        focus_preview.addStretch()
        self.focus_caption = QLabel("ФОКУС")
        self.focus_caption.setFont(gs.font(8,500))
        self.focus_caption.setStyleSheet("color:#666673")
        self.focus_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_preview.addWidget(self.focus_caption)
        self.mini_time = TimerReadout(self,18)
        self.mini_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini_time.setFont(gs.font(18,500))
        focus_preview.addWidget(self.mini_time)
        self.mini_start = QPushButton("Начать")
        self.mini_start.setFont(gs.font(8,500))
        self.mini_start.clicked.connect(self.toggle_timer)
        focus_preview.addWidget(self.mini_start)
        focus_preview.addStretch()
        self.focus_preview.setVisible(owner.settings.get("overview_focus"))
        columns.addWidget(self.focus_preview,2)
        self.stack.addWidget(dashboard)

        focus = QWidget()
        focus_layout = QVBoxLayout(focus)
        focus_layout.setContentsMargins(0,0,0,0)
        self.timer_display = TimerReadout(self,30)
        self.timer_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_display.setFont(gs.font(30,500))
        focus_layout.addWidget(self.timer_display,1)
        timer_bar = QHBoxLayout()
        timer_bar.addStretch()
        self.preset = QSpinBox()
        self.preset.setRange(1,1440)
        self.preset.setSuffix(" мин")
        self.preset.setValue(owner.settings.get("timer_minutes"))
        self.preset.setToolTip("Изменение длительности сбрасывает таймер")
        self.preset.valueChanged.connect(self.set_timer_minutes)
        timer_bar.addWidget(self.preset)
        self.timer_button = QPushButton("Начать")
        self.timer_button.clicked.connect(self.toggle_timer)
        timer_bar.addWidget(self.timer_button)
        self.reset_button = QPushButton("Сбросить")
        self.reset_button.clicked.connect(self.reset_timer)
        timer_bar.addWidget(self.reset_button)
        timer_bar.addStretch()
        focus_layout.addLayout(timer_bar)
        self.timer_notice = QLabel("Колесо на цифрах — минуты · щелчок — ввести число")
        self.timer_notice.setFont(gs.font(9,400))
        self.timer_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_notice.setStyleSheet("color:#747484")
        focus_layout.addWidget(self.timer_notice)
        self.stack.addWidget(focus)

        notes_page = QWidget()
        note_layout = QVBoxLayout(notes_page)
        note_layout.setContentsMargins(0,0,0,0)
        self.notes = QPlainTextEdit()
        self.notes.setFont(gs.font(11,400))
        self.notes.setPlaceholderText("Запиши мысль… Сохраняется автоматически.")
        try:
            self.notes.setPlainText((store/"notch-notes.txt").read_text(encoding="utf-8"))
        except OSError:
            pass
        self._note_save = QTimer(self)
        self._note_save.setSingleShot(True)
        self._note_save.timeout.connect(self.save_notes)
        self.notes.textChanged.connect(lambda: self._note_save.start(500))
        note_layout.addWidget(self.notes,1)
        actions = QHBoxLayout()
        self.note_status = QLabel("Только на этом компьютере")
        self.note_status.setFont(gs.font(9,400))
        self.note_status.setStyleSheet("color:#73737e")
        actions.addWidget(self.note_status,1)
        for title,callback in (("Копировать",lambda: QApplication.clipboard().setText(self.notes.toPlainText())),
                               ("Экспорт…",self.export_notes)):
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            actions.addWidget(btn)
        note_layout.addLayout(actions)
        self.stack.addWidget(notes_page)

        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(0,0,0,0)
        hint = QLabel("Временная полка: перетащи сюда файлы, затем перетяни в другое приложение.")
        hint.setWordWrap(True)
        hint.setFont(gs.font(10,400))
        files_layout.addWidget(hint)
        self.shelf = FileShelf(store/"notch-files.json")
        files_layout.addWidget(self.shelf,1)
        file_actions = QHBoxLayout()
        for title,callback in (("Добавить…",self.shelf.add_files),("Убрать ссылки",self.shelf.remove_selected)):
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            file_actions.addWidget(btn)
        files_layout.addLayout(file_actions)
        self.stack.addWidget(files_page)
        self.select_tab(0)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.clock.start(1000)
        self.alarm.changed.connect(self.tick)

    def choose_source(self):
        menu = QMenu(self)
        for index in range(self.sources.count()):
            action = menu.addAction(self.sources.itemText(index))
            action.setCheckable(True)
            action.setChecked(index == self.sources.currentIndex())
            action.triggered.connect(lambda _,i=index:self.sources.setCurrentIndex(i))
        from PyQt6.QtGui import QCursor
        menu.exec(QCursor.pos())

    def select_tab(self, index):
        changed = index != self.stack.currentIndex()
        old = self.stack.currentWidget().grab() if changed and self.isVisible() else None
        self.stack.setCurrentIndex(index)
        if old is not None:
            page = self.stack.currentWidget()
            page.layout().activate()
            self._page_transition.start(old,page.grab())
        for i, button in enumerate(self.tabs):
            button.setChecked(i == index)
        self.owner._island_auto_timer.stop()
        stage = getattr(self.owner, "_notch_stage", None)
        if stage is not None:
            stage.refresh()

    def save_notes(self):
        try:
            self.store.mkdir(parents=True, exist_ok=True)
            target = self.store / "notch-notes.txt"
            temp = target.with_suffix(".tmp")
            temp.write_text(self.notes.toPlainText(), encoding="utf-8")
            temp.replace(target)
            self.note_status.setText("Сохранено · "+time.strftime("%H:%M"))
        except OSError:
            self.notes.setToolTip("Не удалось сохранить заметку на диск")
            self.note_status.setText("Ошибка сохранения — скопируй или экспортируй текст")

    def export_notes(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт заметки", "Заметка.txt", "Текст (*.txt)")
        if path:
            try:
                Path(path).write_text(self.notes.toPlainText(),encoding="utf-8")
                self.note_status.setText("Экспортировано")
            except OSError:
                self.note_status.setText("Не удалось экспортировать заметку")

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
                pix = gs.art_placeholder(64, 12, self.devicePixelRatioF())
            else:
                pix = self.owner._notch_art(snap.thumb, 64, 12)
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
        width = max(100, min(186, round((self.width()-44)*.43)-74))
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
        if self.alarm.active:
            self.alarm.dismiss()
            return
        if self._timer_end:
            self._timer_remaining = self.timer_seconds()
            self._timer_end = None
        else:
            if self._timer_remaining <= 0:
                self.reset_timer()
            self._timer_end = time.monotonic() + self._timer_remaining
        self.tick()
        self.clock.start(1000)

    def set_timer_minutes(self, minutes):
        self.owner.settings.set("timer_minutes", minutes)
        self.preset.blockSignals(True)
        self.preset.setValue(minutes)
        self.preset.blockSignals(False)
        self.reset_timer()

    def reset_timer(self, *args):
        self._timer_end = None
        self._timer_remaining = self.owner.settings.get("timer_minutes") * 60
        self.alarm.dismiss()
        self.tick()

    def tick(self):
        if self.calendar.today != QDate.currentDate():
            self.calendar.update()
        if self._timer_end and self.timer_seconds() <= 0:
            self._timer_end = None
            self._timer_remaining = 0
            self.alarm.start()
            self.timer_finished.emit()
        self.timer_button.setText("Остановить" if self.alarm.active else "Пауза" if self._timer_end else "Продолжить" if 0 < self.timer_seconds() < self.owner.settings.get("timer_minutes")*60 else "Начать")
        self.timer_display.refresh()
        self.mini_time.refresh()
        self.mini_start.setText("Стоп" if self.alarm.active else "Пауза" if self._timer_end else "Начать")
        self.focus_caption.setText("ГОТОВО" if self.alarm.active else "ФОКУС")
        self.timer_notice.setText(("Время вышло · нажми «Остановить»" if not self.alarm.sound_error else
                                  "Время вышло · звук недоступен") if self.alarm.active else
                                 "Колесо на цифрах — минуты · щелчок — ввести число")
        self.timer_notice.setStyleSheet("color:#94b7ff" if self.alarm.active else "color:#747484")
        if self.snap and self.isVisible():
            self.refresh_position()

    def refresh_position(self):
        if self.snap:
            snap = self.snap
            playing = "play" in snap.status.lower() and "pause" not in snap.status.lower()
            pos = max(0, snap.pos_sec + (time.monotonic() - self._position_at if playing else 0))
            dur = max(0, snap.dur_sec)
            pos = min(pos, dur) if dur else 0
            if not self.seek.isSliderDown():
                self.seek.setValue(round(pos / dur * 1000) if dur else 0)
            self.elapsed.setText(fmt(pos))
            self.duration.setText(fmt(dur))


    def busy(self):
        return (self.seek.isSliderDown() or self.notes.hasFocus() or self.calendar.drag_at is not None or
                self.timer_display.hasFocus() or self.mini_time.hasFocus() or self.preset.hasFocus() or
                self.shelf.state() == self.shelf.State.DraggingState)
