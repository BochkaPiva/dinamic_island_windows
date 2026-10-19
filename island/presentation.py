# SPDX-License-Identifier: GPL-3.0-only
"""Reversible visibility, separate from expansion and media service lifetimes."""
from PySide6.QtCore import QObject, QVariantAnimation, QEasingCurve, QAbstractAnimation


class IslandVisibility(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self.fraction=0. if owner._services else 1.
        self.desired=None
        self.animation=QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self.finish)

    @property
    def moving(self):
        return self.animation.state()==QAbstractAnimation.State.Running

    def frame(self, value):
        self.fraction=float(value)
        self.apply()

    def apply(self):
        w=self.owner
        w.setWindowOpacity(w.settings.get('island_opacity')/100*self.fraction)
        w.move(w.x(),w._island_top())

    def set_visible(self, visible):
        if self.desired==visible and (self.moving or self.owner.isVisible()==visible): return
        self.desired=visible
        self.animation.stop()
        if visible:
            self.apply()
            self.owner.show()
            if self.desired!=visible: return
            self.owner._notch_pointer.route_input(False)
        else:
            self.owner._notch_pointer.route_input(True)
        if not self.owner.settings.get('hub_animations') or not self.owner.isVisible():
            self.frame(float(visible))
            self.finish()
            return
        start=self.fraction
        # QVariantAnimation emits valueChanged while its endpoints/duration are
        # configured, even when stopped. Preserve the on-screen fraction until
        # the complete reversed timeline starts at time zero.
        self.animation.blockSignals(True)
        self.animation.setDuration(max(100,round((320 if visible else 220)*abs(float(visible)-start))))
        self.animation.setStartValue(start)
        self.animation.setEndValue(float(visible))
        self.animation.setCurrentTime(0)
        self.animation.blockSignals(False)
        self.animation.start()

    def finish(self):
        if not self.desired:
            self.owner.hide()
        self.owner._update_services()

    def close(self):
        self.animation.stop()
