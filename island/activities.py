# SPDX-License-Identifier: GPL-3.0-only
"""Local display selection; gestures never send transport commands."""
import time
from PySide6.QtCore import QObject, QEvent, Qt, QPointF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget
from .hub import fmt


class ActivitySlide(QWidget):
    def __init__(self, surface):
        super().__init__(surface)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(240)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self.done)
        self.old=self.new=None
        self.fraction=1.
        self.hide()

    def frame(self,value): self.fraction=float(value);self.update()

    def done(self):self.hide();self.old=self.new=None

    def start(self, old, new, direction):
        self.animation.stop();self.old,self.new=old,new;self.direction=direction
        self.setGeometry(self.parentWidget().rect());self.show();self.raise_()
        self.animation.setStartValue(0.);self.animation.setEndValue(1.);self.animation.start()

    def paintEvent(self,event):
        if self.old is None:return
        p=QPainter(self);p.setClipPath(self.window().card.notch_path())
        p.fillRect(self.rect(),QColor('black'))
        distance=min(48,self.width()/4)*self.direction
        p.setOpacity(1-self.fraction);p.drawPixmap(round(-distance*self.fraction),0,self.old)
        p.setOpacity(self.fraction);p.drawPixmap(round(distance*(1-self.fraction)),0,self.new)


class ActivityController(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner;self.selected=None;self.pinned=False
        self.selection_until=0.
        self.press=None;self.locked=False;self.wheel_sum=0.;self.wheel_at=0.;self.switched_at=0.
        self.slide=ActivitySlide(owner._notch_stage.surface)
        owner.installEventFilter(self)
        owner.access.changed.connect(self.access_changed)

    def available(self):
        result=['clock']
        if self.owner.snapshot.has_session or self.owner._notch_audio_active:result.insert(0,'media')
        hub=self.owner.notch_hub
        if hub._timer_end or hub._timer_remaining!=self.owner.settings.get('timer_minutes')*60:result.append('timer')
        return result

    def current(self):
        available=self.available()
        if not self.pinned and time.monotonic()>self.selection_until:self.selected=None
        if self.selected in available:return self.selected
        self.selected=None;self.pinned=False
        return 'timer' if self.owner.notch_hub._timer_end else available[0]

    def access_changed(self):
        if not self.owner.access.feature('island.activities.pin').allowed:self.pinned=False

    def toggle_pin(self):
        if not self.owner.access.feature('island.activities.pin').allowed:
            self.owner.show_hub();self.owner.control_center.navigate('account');return
        current=self.current();self.pinned=not self.pinned;self.selected=current
        if not self.pinned:self.selected=None
        self.owner.notice('Карточка закреплена' if self.pinned else 'Автоматический выбор карточки')

    def step(self,direction):
        w=self.owner
        available=self.available();current=self.current()
        if len(available)<2:return
        surface=w._notch_stage.surface
        old=surface.grab();self.slide.hide()
        self.selected=available[(available.index(current)+direction)%len(available)]
        self.selection_until=time.monotonic()+20
        self.pinned=False
        w._notch_stage._signature=None;w._notch_stage.sync()
        old_notice=w._notch_notice
        if old_notice:w.notice('')
        new=surface.grab()
        if w.settings.get('hub_animations'):self.slide.start(old,new,direction)

    def text(self):
        if self.current()=='timer':return fmt(self.owner.notch_hub.timer_seconds())
        if self.current()=='media':return self.owner.snapshot.title or 'Звук Windows'
        from datetime import datetime
        return datetime.now().strftime('%H:%M')

    def eventFilter(self,watched,event):
        w=self.owner
        if w._island_expanded or getattr(w,'media_stage',None) and w.media_stage.engaged:return False
        kind=event.type()
        if kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            w._notch_hover_timer.stop()
            self.press=QPointF(event.position());self.locked=False
            return True
        if kind==QEvent.Type.MouseMove and self.press is not None:
            delta=event.position()-self.press
            if abs(delta.x())>12 and abs(delta.x())>abs(delta.y())*1.5:self.locked=True
            return True
        if kind==QEvent.Type.MouseButtonRelease and self.press is not None:
            delta=event.position()-self.press;self.press=None
            if self.locked and abs(delta.x())>28:self.step(1 if delta.x()<0 else -1)
            elif not self.locked:w._set_island_expanded(True)
            self.locked=False;return True
        if kind in (QEvent.Type.Hide,QEvent.Type.WindowDeactivate):self.press=None;self.locked=False
        if kind==QEvent.Type.Wheel:
            delta=event.pixelDelta() if not event.pixelDelta().isNull() else event.angleDelta()
            if abs(delta.x())<=abs(delta.y())*1.5:return False
            now=time.monotonic()
            if now-self.wheel_at>.24:self.wheel_sum=0.
            self.wheel_at=now;self.wheel_sum+=delta.x()
            threshold=36 if not event.pixelDelta().isNull() else 100
            if abs(self.wheel_sum)>=threshold and now-self.switched_at>.4:
                self.step(1 if self.wheel_sum<0 else -1);self.switched_at=now;self.wheel_sum=0.
            event.accept();return True
        if kind==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self.step(1 if event.key()==Qt.Key.Key_Right else -1);return True
        return False
