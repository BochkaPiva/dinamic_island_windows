# SPDX-License-Identifier: GPL-3.0-only
"""Cursor policy and native input routing for a fixed, centered notch."""
from __future__ import annotations

import ctypes
import math
import os
import time
from dataclasses import dataclass
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QObject, QTimer, QAbstractAnimation
from PySide6.QtGui import QCursor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QWidget
from .platform_win import is_desktop_window


@dataclass(frozen=True)
class PointerIntent:
    edge: bool = False
    retreat: float = 0.0
    local_x: float = 0.5


def pointer_intent(screen: QRect, width: int, point: QPoint, covered: bool) -> PointerIntent:
    """The one-pixel physical edge is a deliberate, separate activation target."""
    dx = point.x() - (screen.x() + screen.width() / 2)
    dy = point.y() - screen.top()
    edge = 0 <= dy <= 1 and abs(dx) <= width / 2 + 12
    if edge or not covered or dy < 0:
        return PointerIntent(edge=edge)
    # Start yielding before the pointer reaches a browser tab. Hysteresis is
    # handled by the controller; lateral motion changes the wave, not position.
    horizontal = max(0.0, min(1.0, (width / 2 + 86 - abs(dx)) / 64))
    vertical = max(0.0, min(1.0, (160 - dy) / 80))
    return PointerIntent(False, horizontal * vertical,
                         max(0.0, min(1.0, dx / max(width, 1) + 0.5)))


class DampedValue:
    """Exact critically damped response, continuous under target reversals."""
    def __init__(self):
        self.value = 0.0
        self.velocity = 0.0

    def step(self, target, dt, rate=22.0):
        dt = max(0.0, min(dt, 0.06))
        delta = self.value - target
        momentum = self.velocity + rate * delta
        decay = math.exp(-rate * dt)
        self.value = target + (delta + momentum * dt) * decay
        self.velocity = (self.velocity - rate * momentum * dt) * decay
        if abs(self.value - target) < 0.0005 and abs(self.velocity) < 0.01:
            self.value, self.velocity = target, 0.0
        return self.value


class CloudMotion:
    """A cursor-driven dent with a slower, dissipating material wake.

    Movement history changes the shape; a stationary pointer settles completely.
    No autonomous oscillator or per-frame random jitter is involved.
    """
    def __init__(self):
        self.amount = DampedValue()
        self.center = DampedValue()
        self.wake = DampedValue()
        self.spread = DampedValue()
        self.center.value = self.wake.value = 0.5
        self.previous_x = None

    def step(self, target, x, dt):
        dt = max(0.001, min(dt, 0.06))
        speed = 0 if self.previous_x is None else min(1.0, abs(x - self.previous_x) / dt / 2.5)
        self.previous_x = x
        # A fast sweep creates a broader cushion. The wake follows the already
        # filtered center, so changing direction never teleports the contour.
        amount = self.amount.step(target, dt, 10.5 if target > self.amount.value else 9.0)
        center = self.center.step(x, dt, 13.0)
        wake = self.wake.step(center, dt, 6.0)
        spread = self.spread.step(speed if target > 0.01 else 0, dt, 7.0)
        return amount, center, wake, spread


class SpringGeometry(QObject):
    """One persistent animation clock; retargeting preserves current velocity."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.axes = [DampedValue(), DampedValue()]
        self.target = owner.geometry()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.last_time = time.monotonic()

    def state(self):
        return QAbstractAnimation.State.Running if self.timer.isActive() else QAbstractAnimation.State.Stopped

    def stop(self):
        self.timer.stop()
        for axis in self.axes:
            axis.velocity = 0.0

    def start(self, target):
        if not self.owner.settings.get('hub_animations'):
            self.stop()
            self.target=QRect(target)
            self.owner._geo_anim_step(self.target)
            self.owner._after_geo_anim()
            return
        if not self.timer.isActive():
            for axis, value in zip(self.axes, (self.owner.width(), self.owner.height())):
                axis.value, axis.velocity = float(value), 0.0
        self.target = QRect(target)
        self.last_time = time.monotonic()
        self.timer.start(8 if self.owner.screen().refreshRate() >= 90 else 16)

    def tick(self):
        now = time.monotonic()
        dt, self.last_time = now - self.last_time, now
        targets = (self.target.width(), self.target.height())
        rate = 19.0 if self.owner._island_expanded else 24.0
        values = [a.step(v, dt, rate) for a, v in zip(self.axes, targets)]
        width, height = [max(1, round(v)) for v in values]
        screen = self.owner.screen().geometry()
        x = screen.x() + (screen.width() - width) // 2
        self.owner._geo_anim_step(QRect(x, self.owner._island_top(), width, height))
        if all(abs(a.value - t) < 0.04 and abs(a.velocity) < 0.8 for a, t in zip(self.axes, targets)):
            self.stop()
            self.owner._geo_anim_step(self.target)
            self.owner._after_geo_anim()


def set_mouse_passthrough(hwnd, enabled):
    """Layered-window transparency passes both clicks and hover to other apps.

    Does not recreate the Qt window, activate it, or modify other style bits.
    Returns the actual native flag, which lets the UI report a failed request.
    """
    if os.name != "nt":
        return False
    user = ctypes.windll.user32
    get_style = user.GetWindowLongPtrW
    set_style = user.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    current = get_style(ctypes.c_void_p(hwnd), -20)
    desired = current | 0x20 if enabled else current & ~0x20  # WS_EX_TRANSPARENT
    if current != desired:
        set_style(ctypes.c_void_p(hwnd), -20, desired)
    return bool(get_style(ctypes.c_void_p(hwnd), -20) & 0x20)


def top_application(owner):
    """Only yield over another app that really occupies the notch's monitor edge."""
    if os.name != "nt":
        return False
    user = ctypes.windll.user32
    fg = user.GetForegroundWindow()
    if not fg:
        return False
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(ctypes.c_void_p(fg), ctypes.byref(pid))
    if pid.value == os.getpid():
        user.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user.GetWindow.restype = ctypes.c_void_p
        candidate = user.GetWindow(ctypes.c_void_p(fg), 2)
        for _ in range(32):
            if not candidate:
                return False
            user.GetWindowThreadProcessId(candidate, ctypes.byref(pid))
            if pid.value != os.getpid() and user.IsWindowVisible(candidate):
                fg = candidate
                break
            candidate = user.GetWindow(candidate, 2)
        else:
            return False
    if user.IsIconic(ctypes.c_void_p(fg)):
        return False
    if is_desktop_window(fg, user):
        return False
    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    class Monitor(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("monitor", Rect), ("work", Rect), ("flags", ctypes.c_ulong)]
    user.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    user.MonitorFromWindow.restype = ctypes.c_void_p
    target = user.MonitorFromWindow(ctypes.c_void_p(int(owner.winId())), 2)
    if user.MonitorFromWindow(ctypes.c_void_p(fg), 2) != target:
        return False
    bounds = Rect()
    monitor = Monitor()
    monitor.size = ctypes.sizeof(monitor)
    if not user.GetWindowRect(ctypes.c_void_p(fg), ctypes.byref(bounds)):
        return False
    if not user.GetMonitorInfoW(ctypes.c_void_p(target), ctypes.byref(monitor)):
        return False
    center = (monitor.monitor.left + monitor.monitor.right) / 2
    return (bounds.left <= center <= bounds.right
            and bounds.top <= monitor.monitor.top + 8 * owner.devicePixelRatioF()
            and bounds.bottom > monitor.monitor.top + 80 * owner.devicePixelRatioF())


class PointerController:
    def __init__(self, owner):
        self.owner = owner
        self.cloud = CloudMotion()
        self.spring = self.cloud.amount
        self.wave_x = self.cloud.center
        self.last_time = time.monotonic()
        self.edge_since = None
        self.edge_blocked = False
        self.opened_at = 0.0
        self.context_at = 0.0
        self.covered = False
        self.passthrough = False
        self.enabled = True
        self.cursor_provider = QCursor.pos
        self.context_provider = lambda: top_application(owner)

    def route_input(self, enabled):
        if enabled != self.passthrough:
            actual = set_mouse_passthrough(int(self.owner.winId()), enabled)
            self.passthrough = actual if os.name == "nt" else enabled

    def tick(self, now=None):
        w = self.owner
        now = time.monotonic() if now is None else now
        dt, self.last_time = now - self.last_time, now
        if not self.enabled or w.current_scale_pct != 200 or not w.isVisible() or w._fs_hidden:
            self.route_input(False)
            return
        screen = w.screen().geometry()
        point = self.cursor_provider()
        near = abs(point.x() - (screen.x() + screen.width() / 2)) < w.width() / 2 + 150 and screen.top() <= point.y() < screen.top() + max(180, w.height() + 20)
        relaxing = any(abs(axis.velocity) > .01 for axis in
                       (self.cloud.amount, self.cloud.center, self.cloud.wake, self.cloud.spread))
        fast = 16 if getattr(w, "_economy", False) else (8 if w.screen().refreshRate() >= 90 else 16)
        interval = fast if near or relaxing else 80
        if w._notch_pointer_timer.interval() != interval:
            w._notch_pointer_timer.setInterval(interval)
        if now - self.context_at >= 0.12:
            self.covered, self.context_at = self.context_provider(), now
        width = w._scale_window_size(50)[0]
        intent = pointer_intent(screen, width, point, self.covered and w.settings.get("cursor_retreat"))
        # The tucked silhouette itself is an entry point, not just the last
        # physical pixel of the screen. Outside it, browser tabs keep all input.
        tab_entry = (w.floating_mode() and (self.spring.value > .85 or self.edge_since is not None)
                     and 0 <= point.y()-screen.top() <= 6
                     and abs(point.x()-screen.center().x()) <= width*.30-6)
        entry = intent.edge or tab_entry
        expanded = w._island_expanded
        if entry and not self.edge_blocked:
            self.edge_since = self.edge_since or now
            if not expanded and now - self.edge_since >= 0.09:
                self.route_input(False)
                w._set_island_expanded(True)
                self.opened_at = now
                expanded = True
        else:
            self.edge_since = None
            if not entry:
                self.edge_blocked = False
        if expanded:
            # Use final bounds during expansion, so following the new panel
            # downward does not cancel an animation halfway through.
            tw, th = w._scale_window_size(100)
            panel = QRect(screen.x() + (screen.width() - tw) // 2, w._island_top(), tw, th)
            inside = entry or panel.adjusted(-5, 0, 5, 8).contains(point)
            w._hovering = inside
            if inside or now - self.opened_at < 0.35:
                w._island_auto_timer.stop()
            elif not w._island_auto_timer.isActive():
                w._island_auto_timer.start(w.settings.get("collapse_delay"))
            target = 0.0
        else:
            target = 0.0 if entry else intent.retreat
            if self.covered and w.settings.get("cursor_retreat"):
                w._notch_hover_timer.stop()
            yielding = self.covered and not entry and (target > 0.015 or self.spring.value > 0.04)
            self.route_input(yielding)
        # Outside the interaction zone retain the final dent location while it
        # relaxes, instead of pulling every exit toward an arbitrary center.
        local_x = intent.local_x if target > 0.001 else self.wave_x.value
        amount, wave_x, wake, spread = self.cloud.step(target, local_x, dt)
        changed = w.card.set_retreat(amount, wave_x, wake, spread)
        w._notch_set_compact_retreat(amount)
        if changed and w._notch_stage.active:
            w._notch_stage.surface.update()
        if expanded:
            self.route_input(False)


def smoothstep(value):
    x = max(0.0, min(1.0, value))
    return x * x * (3 - 2 * x)


def floating_retreat(amount, gap, height):
    """Attach to the bezel without dissolving the visible six-pixel tab.

    Geometry inside the card contracts; the HWND stays on the chosen monitor.
    Fullscreen visibility owns opacity independently of cursor avoidance.
    """
    return gap*smoothstep(amount), 1.0


class CompactSurface(QWidget):
    """Warp the artwork, spectrum and labels as one continuous material layer."""
    def __init__(self, stage):
        super().__init__(stage.owner.card)
        self.stage = stage
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        stage = self.stage
        if not stage.active:
            return
        image = stage.compact.grab()
        ratio = image.devicePixelRatioF()
        card = stage.owner.card
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setClipPath(card.notch_path().translated(-self.x(), -self.y()))
        p.setOpacity(stage.compact_alpha)
        if stage.owner.floating_mode():
            # Transport the complete live texture upward through the shrinking
            # silhouette, rather than leaving artwork in place with a fade.
            shift = (card.height()-6)*smoothstep(card._retreat)
            p.drawPixmap(QPointF(0, -shift), image)
        elif card._retreat <= 0.0005:
            p.drawPixmap(0, 0, image)
        else:
            # One-pixel strips carry the whole live texture upward along the
            # same flowing contour as the shell, including the real FFT bars.
            for x in range(self.width()):
                width = 1
                shift = card.retreat_displacement(self.x() + x + width / 2)
                p.drawPixmap(QRectF(x, -shift, width, self.height()), image,
                             QRectF(x * ratio, 0, width * ratio, self.height() * ratio))
        p.end()


class RevealSurface(QWidget):
    """One cached texture transformed by the very same geometry as its shell.

    Live controls retain their final layout. Only the short transition uses a
    snapshot, so text never reflows or escapes the changing silhouette.
    """
    def __init__(self, stage):
        super().__init__(stage.owner.card)
        self.stage = stage
        self.image = QPixmap()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def capture(self):
        hub = self.stage.owner.notch_hub
        hub.ensurePolished()
        hub.layout().activate()
        hub.stack.currentWidget().layout().activate()
        hub.refresh_position()
        self.image = hub.grab()

    def paintEvent(self, event):
        if self.image.isNull():
            return
        w = self.stage.owner
        pw, ph = w._scale_window_size(100)
        scale = min(self.width()/pw, self.height()/ph)
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        p.setClipPath(w.card.notch_path())
        p.setOpacity(smoothstep(self.stage.progress / .65))
        p.translate((self.width()-pw*scale)/2, 0)
        p.scale(scale, scale)
        p.drawPixmap(0, 0, self.image)


class NotchStage:
    """Two persistent content layers; neither is resized during a morph."""
    def __init__(self, owner):
        self.owner = owner
        self.active = False
        self.panel_was_visible = False
        self.retreat = 0.0
        self.progress = 0.0
        self.compact_alpha = 1.0
        self.compact = QWidget(owner.card)
        self.compact.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.compact.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.surface = CompactSurface(self)
        self.reveal = RevealSurface(self)
        self.compact.hide()
        self.surface.hide()
        owner.art_label._anim.valueChanged.connect(lambda _: self.surface.update())

    def prepare(self):
        if not self.reveal.isVisible() or self.reveal.image.isNull():
            self.reveal.capture()
        self.owner.notch_hub.hide()
        self._signature = None

    def refresh(self):
        if self.reveal.isVisible():
            self.reveal.capture()
            self.reveal.update()

    def enter(self):
        w = self.owner
        if not self.active:
            for child in (w.art_label, w.status_mark, w.notch_idle, w.notch_notice):
                child.setParent(self.compact)
            self.active = True
        self.sync()

    def leave(self):
        if self.active:
            for child in (self.owner.art_label, self.owner.status_mark, self.owner.notch_idle, self.owner.notch_notice):
                child.setParent(self.owner.card)
                child.hide()
        self.active = False
        self.panel_was_visible = False
        self.compact.hide()
        self.surface.hide()
        self.reveal.hide()
        self.owner.notch_hub.hide()

    def sync(self):
        if not self.active:
            return
        w = self.owner
        # Layout only when its inputs change. FFT packets repaint the texture
        # directly instead of repeatedly relaying out every child at 40 Hz.
        signature = (w.width(), w.height(), w._island_expanded, w._notch_notice,
                     w.snapshot.has_session, w._notch_audio_active, bool(w.notch_hub._timer_end),
                     w.notch_idle.text(), w.settings.get("spectrum"), w._geometry.timer.isActive())
        if signature == getattr(self, "_signature", None):
            return
        self._signature = signature
        cw, ch = w._scale_window_size(50)
        pw, ph = w._scale_window_size(100)
        self.compact.setGeometry((w.width() - cw) // 2, 0, cw, ch)
        self.surface.setGeometry(self.compact.geometry())
        hub = w.notch_hub
        if (hub.width(), hub.height()) != (pw, ph):
            hub.resize(pw, ph)
        progress = max(0.0, min(1.0, (w.height() - ch) / max(1, ph - ch)))
        self.progress = progress
        self.panel_was_visible = self.panel_was_visible or w._island_expanded
        if progress <= 0.001 and not w._island_expanded:
            self.panel_was_visible = False
        hub.move((w.width() - pw) // 2, 0)
        moving = w._geometry.timer.isActive()
        live = w._island_expanded and not moving and progress >= 1
        hub.setVisible(live)
        if live:
            hub.setMask(QRegion(w.card.notch_path().toFillPolygon().toPolygon()))
        self.reveal.setGeometry(w.card.rect())
        self.reveal.setVisible(self.panel_was_visible and not live and progress > .001)
        self.reveal.update()
        self.compact.hide()
        self.surface.show()
        self.surface.raise_()
        compact_alpha = 1 - smoothstep(progress / 0.32) if self.panel_was_visible else 1.0
        self.compact_alpha = compact_alpha
        notice = bool(w._notch_notice)
        session = w.snapshot.has_session
        timer = bool(hub._timer_end)
        w.art_label.setVisible(session and not notice)
        audio = w._notch_audio_active
        w.status_mark.setVisible((session or audio) and not notice and w.settings.get("spectrum"))
        art_size = min(40,ch-12)
        w.art_label.setFixedSize(art_size, art_size)
        w.art_label.move(20, max(2, (ch - art_size) // 2 - 1))
        w.status_mark.move(cw - w.status_mark.width() - 20, (ch - w.status_mark.height()) // 2)
        w.notch_notice.setVisible(notice)
        w.notch_notice.setGeometry(20, 0, cw - 40, ch - 2)
        if notice:
            w.notch_notice.setText(w.notch_notice.fontMetrics().elidedText(w._notch_notice, Qt.TextElideMode.ElideRight, cw - 40))
            w.notch_notice.setToolTip(w._notch_notice)
        w.notch_idle.setVisible(not notice and (not session or timer))
        left = 25+art_size if session else 16
        right = cw - 52 if session or audio else cw - 16
        w.notch_idle.setGeometry(left, 0, right - left, ch - 2)
        self.surface.update()
