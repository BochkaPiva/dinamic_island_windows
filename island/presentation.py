# SPDX-License-Identifier: GPL-3.0-only
"""Reversible visibility, separate from expansion and media service lifetimes."""
from PySide6.QtCore import QObject, QVariantAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication
from .motion import floating_retreat


class IslandVisibility(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self.fraction=0. if owner._services else 1.
        self.desired=None
        self._clip_signature=None
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
        retreat_alpha=1.
        if w.floating_mode():
            _,retreat_alpha=floating_retreat(w._notch_stage.retreat,w.settings.get('island_gap'),w.settings.get('compact_height'))
        w.setWindowOpacity(w.settings.get('island_opacity')/100*self.fraction*retreat_alpha)
        w.move(w.x(),w._island_top())
        # Native screen-edge clipping keeps the rigid capsule from appearing on
        # a monitor above this one. Children move with the window, without a warp.
        clip=None
        if w.floating_mode():
            screen=next((s for s in QApplication.screens() if s.name()==w.settings.get('monitor')),QApplication.primaryScreen())
            local=screen.geometry().translated(-w.pos())
            visible=w.rect().intersected(local)
            if visible!=w.rect(): clip=visible
        signature=(clip.x(),clip.y(),clip.width(),clip.height()) if clip is not None else None
        if signature!=self._clip_signature:
            if clip is None: w.clearMask()
            elif not clip.isEmpty(): w.setMask(QRegion(clip))
            else: w.setWindowOpacity(0)
            self._clip_signature=signature

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
