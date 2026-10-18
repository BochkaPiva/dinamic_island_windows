# SPDX-License-Identifier: GPL-3.0-only
"""Direct touchpad pixels; continuous damped movement for wheel notches."""
import time
from PyQt6.QtCore import Qt, QObject, QTimer
from .motion import DampedValue


class SmoothScroll(QObject):
    def __init__(self,view):
        super().__init__(view)
        self.view=view
        self.bar=view.verticalScrollBar()
        self.axis=DampedValue()
        self.target=0.
        self.timer=QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.frame)
        self.bar.sliderPressed.connect(self.stop)
        self.bar.actionTriggered.connect(lambda _:self.stop())
        self.bar.rangeChanged.connect(lambda *_:self.stop())
        self.bar.setSingleStep(18)

    def stop(self):
        self.timer.stop()
        self.axis.value=self.target=float(self.bar.value())
        self.axis.velocity=0.

    def wheel(self,event):
        pixel=event.pixelDelta().y()
        angle=event.angleDelta().y()
        if pixel:
            self.stop()
            self.bar.setValue(self.bar.value()-pixel)
        elif angle:
            running=self.timer.isActive()
            if not running:
                self.axis.value=self.target=float(self.bar.value())
                self.axis.velocity=0.
            self.target=max(self.bar.minimum(),min(self.bar.maximum(),self.target-angle/120*60))
            if self.target!=self.axis.value and not running:
                self.last=time.monotonic()
                self.timer.start(8 if self.view.screen().refreshRate()>=90 else 16)
        event.accept()

    def frame(self):
        now=time.monotonic()
        value=self.axis.step(self.target,now-self.last,24)
        self.last=now
        self.bar.setValue(round(value))
        if abs(value-self.target)<.08 and abs(self.axis.velocity)<1:
            self.bar.setValue(round(self.target))
            self.stop()
