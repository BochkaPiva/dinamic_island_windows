# SPDX-License-Identifier: GPL-3.0-only
"""Editable duration readout and a bounded, dismissible local timer alarm."""
import math
from pathlib import Path
import time
import winsound
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QLineEdit
from .style import font


class TimerAlarm(QObject):
    changed = pyqtSignal()

    def __init__(self, settings, parent=None, player=None):
        super().__init__(parent)
        self.settings = settings
        self.player = player or winsound.PlaySound
        self.active = self.sounding = False
        self.hold_until = 0.
        self.sound_error = False
        self.limit = QTimer(self)
        self.limit.setSingleShot(True)
        self.limit.timeout.connect(self.stop_sound)

    def start(self):
        self.dismiss()
        self.active = True
        self.hold_until = time.monotonic()+12
        self.sound_error = False
        if self.settings.get("timer_sound"):
            try:
                self.player(str(Path(__file__).parent/"assets/timer-chime.wav"),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP | winsound.SND_NODEFAULT)
                self.sounding = True
                self.limit.start(self.settings.get("timer_alarm_seconds")*1000)
            except (RuntimeError, OSError):
                self.sound_error = True
        self.changed.emit()

    def stop_sound(self):
        self.limit.stop()
        if self.sounding:
            try:
                self.player(None,0)
            except (RuntimeError,OSError):
                self.sound_error=True
            self.sounding = False
        self.changed.emit()

    def dismiss(self):
        self.stop_sound()
        self.active = False
        self.hold_until = 0.
        self.changed.emit()


class TimerReadout(QLineEdit):
    """Normal view is MM:SS; focus edits integer minutes. Wheel edits directly."""
    def __init__(self, hub, size=30):
        super().__init__()
        self.hub = hub
        self._editing = self._dirty = False
        self._wheel = 0.
        self.setFont(font(size,500))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrame(False)
        self.setMinimumWidth(58)
        self.setObjectName("timerReadout")
        self.setAccessibleName("Таймер: щёлкни для ввода минут, прокрути для изменения")
        self.setToolTip("Колесо — изменить минуты. Щелчок — ввести минуты (1–1440), Enter — применить, Esc — отменить. Изменение сбрасывает отсчёт.")
        self.setStyleSheet("""QLineEdit#timerReadout {color:#f1f2f6;background:transparent;border:1px solid transparent;border-radius:8px;padding:2px;}
            QLineEdit#timerReadout:hover {background:rgba(135,150,185,15);}
            QLineEdit#timerReadout:focus {border-color:#648ac9;background:rgba(65,85,125,36);selection-background-color:#426498;}"""+
            f"QLineEdit#timerReadout {{font-size:{size}px;font-family:'Golos Text';font-weight:500;}}")
        self.textEdited.connect(lambda _:setattr(self,"_dirty",True))
        self.refresh()

    def refresh(self):
        if not self._editing:
            seconds = self.hub.timer_seconds()
            self.setText(f"{seconds//60}:{seconds%60:02}")

    def focusInEvent(self,event):
        self._editing, self._dirty = True, False
        self.setValidator(QIntValidator(1,1440,self))
        self.setMaxLength(4)
        self.setText(str(max(1,math.ceil(self.hub.timer_seconds()/60))))
        super().focusInEvent(event)
        self.selectAll()
        QTimer.singleShot(0,self.selectAll)

    def mousePressEvent(self,event):
        was_editing = self._editing
        super().mousePressEvent(event)
        if not was_editing:
            self.selectAll()

    def finish_edit(self,commit=True):
        if not self._editing:
            return
        value = int(self.text()) if self.text().isdigit() else None
        dirty = self._dirty
        self._editing, self._dirty = False, False
        self.setValidator(None)
        self.setMaxLength(16)
        if commit and dirty and value is not None and 1 <= value <= 1440:
            self.hub.owner._toggle_setting("timer_minutes",value)
        self.refresh()

    def focusOutEvent(self,event):
        self.finish_edit()
        super().focusOutEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Escape):
            self.finish_edit(event.key()!=Qt.Key.Key_Escape)
            self.clearFocus()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self,event):
        angle,pixel = event.angleDelta(),event.pixelDelta()
        delta = angle.y()/120 if angle.y() else pixel.y()/32
        if not delta:
            event.ignore()
            return
        if self._wheel*delta < 0:
            self._wheel = 0.
        self._wheel += delta
        steps = math.trunc(self._wheel)
        self._wheel -= steps
        if steps:
            self.finish_edit(False)
            minutes = max(1,min(1440,math.ceil(self.hub.timer_seconds()/60)+steps))
            self.hub.owner._toggle_setting("timer_minutes",minutes)
            self.clearFocus()
        event.accept()
