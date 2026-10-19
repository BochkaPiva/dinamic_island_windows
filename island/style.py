# SPDX-License-Identifier: GPL-3.0-only
"""Original vector drawing for Cloud Island. Uses the Windows system font."""
import math
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget, QPushButton


_fonts_loaded = False


def font(size=12, weight=400):
    global _fonts_loaded
    if not _fonts_loaded:
        for path in (Path(__file__).parent / "assets" / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(path))
        _fonts_loaded = True
    value = QFont("Golos Text")
    value.setPixelSize(size)
    value.setWeight(QFont.Weight(weight))
    return value


def ease_out():
    return QEasingCurve(QEasingCurve.Type.OutCubic)


def rounded_art(data, size, radius=7, ratio=1.0):
    source = QPixmap()
    source.loadFromData(data or b"")
    result = QPixmap(round(size * ratio), round(size * ratio))
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(clip)
    if source.isNull():
        p.fillRect(QRectF(0, 0, size, size), QColor("#1c1d25"))
        # Original vector note: no dependency on a font's music glyph coverage.
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor("#B4DFF2"), max(1., size*.035),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(size*.56,size*.28),QPointF(size*.56,size*.65))
        p.drawLine(QPointF(size*.56,size*.28),QPointF(size*.72,size*.34))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#B4DFF2"))
        p.drawEllipse(QRectF(size*.34,size*.58,size*.24,size*.16))
    else:
        source = source.scaled(round(size * ratio), round(size * ratio),
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        left = (source.width() - size * ratio) / 2
        top = (source.height() - size * ratio) / 2
        p.drawPixmap(QRectF(0, 0, size, size), source,
                     QRectF(left, top, size * ratio, size * ratio))
    p.end()
    return result


def art_placeholder(size, radius=7, ratio=1.0):
    return rounded_art(b"", size, radius, ratio)


def app_icon():
    # Include every size so Windows and Qt choose a crisp native-resolution mark.
    return QIcon(str(Path(__file__).parent / 'assets' / 'brand' / 'Nelviro.ico'))


class TransportButton(QPushButton):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind, self.glyph = kind, 20
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_kind(self, kind):
        self.kind = kind
        self.setAccessibleName({"play": "Воспроизвести", "pause": "Пауза",
                                "next": "Следующий трек", "prev": "Предыдущий трек"}.get(kind, kind))
        self.update()

    def set_glyph(self, value):
        self.glyph = value

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width()/2, self.height()/2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f4f4f6" if self.isEnabled() else "#53535d"))
        s = self.glyph / 2
        if self.kind == "pause":
            for x in (-s*.65, s*.2):
                p.drawRoundedRect(QRectF(x, -s*.75, s*.4, s*1.5), 1.5, 1.5)
        else:
            if self.kind == "prev":
                p.scale(-1, 1)
            path = QPainterPath()
            path.moveTo(-s*.55, -s*.8)
            path.lineTo(s*.65, 0)
            path.lineTo(-s*.55, s*.8)
            path.closeSubpath()
            p.drawPath(path)
            if self.kind in ("next", "prev"):
                p.drawRoundedRect(QRectF(s*.65, -s*.8, s*.2, s*1.6), 1, 1)


class SpectrumMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.levels = (0.0,) * 5
        self.available = False
        self.setFixedSize(30, 18)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_spectrum(self, levels):
        self.levels = levels
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d7e3f6" if self.available else "#59616d"))
        for i, level in enumerate(self.levels):
            height = 2 + max(0, min(1, level)) * (self.height()-3)
            p.drawRoundedRect(QRectF(i*6, (self.height()-height)/2, 3, height), 1.5, 1.5)


def island_outline(w,h,floating=False):
    """Shared resting silhouette for the real surface and explanatory previews."""
    path=QPainterPath()
    if floating:
        path.addRoundedRect(QRectF(0,0,w,h),min(24.,h/2),min(24.,h/2));return path
    flare=min(18.,max(8.,h*.1));radius=min(30.,(h-flare)*.65)
    left,right=flare+radius,w-flare-radius
    path.moveTo(0,0);path.lineTo(w,0)
    path.cubicTo(w-flare*.55,0,w-flare,flare*.45,w-flare,flare)
    path.lineTo(w-flare,h-radius)
    path.cubicTo(w-flare,h-radius*.34,right+radius*.66,h,right,h)
    path.lineTo(left,h)
    path.cubicTo(left-radius*.66,h,flare,h-radius*.34,flare,h-radius)
    path.lineTo(flare,flare)
    path.cubicTo(flare,flare*.45,flare*.55,0,0,0);path.closeSubpath();return path


class NotchCard(QWidget):
    """An intact bezel silhouette compressed by a smooth material displacement."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._retreat = 0.0
        self._retreat_x = self._retreat_wake = .5
        self._retreat_spread = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_retreat(self, amount, x, wake=None, spread=0):
        values = (max(0, min(1, amount)), x, x if wake is None else wake, spread)
        old = (self._retreat, self._retreat_x, self._retreat_wake, self._retreat_spread)
        if max(abs(a-b) for a, b in zip(values, old)) < .0003:
            return False
        self._retreat, self._retreat_x, self._retreat_wake, self._retreat_spread = values
        self.update()
        return True

    def retreat_boundary(self, x):
        h, w = self.height(), self.width()
        sigma = w * (.285 + .085*self._retreat_spread)
        depth = (h-5) * self._retreat
        value = slope = 0.0
        for center, weight, width in ((self._retreat_x, .78, sigma), (self._retreat_wake, .22, sigma*1.12)):
            dx = x - w*center
            influence = weight*math.exp(-.5*(dx/width)**2)
            value += influence
            slope += influence*dx/width**2
        return h-depth*value, depth*slope

    def retreat_displacement(self, x):
        return (self.height()-self.retreat_boundary(x)[0])*1.32

    def notch_path(self):
        w, h = self.width(), self.height()
        stage=getattr(self.parentWidget(),'media_stage',None)
        if stage and stage.engaged:
            path=QPainterPath();path.addRoundedRect(QRectF(0,0,w,h),min(22,h/2),min(22,h/2));return path
        if self.parentWidget().floating_mode():
            t=self._retreat*self._retreat*(3-2*self._retreat)
            inset=w*.20*t
            bottom=h+(6-h)*t
            radius=min(24.,h/2)+(6-min(24.,h/2))*t
            path=QPainterPath()
            # Extend the top above the clip as the capsule docks, leaving a
            # flat attachment and soft lower corners instead of a floating line.
            path.addRoundedRect(QRectF(inset,-6*t,w-2*inset,bottom+6*t),radius,radius)
            return path
        if self._retreat<=.00001:return island_outline(w,h)
        flare = min(18., max(8., h*.1))
        radius = min(30., (h-flare)*.65)
        left, right = flare+radius, w-flare-radius
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w, 0)

        def warp(x, y, dx=0, dy=0):
            bottom, slope = self.retreat_boundary(x)
            return x, y*bottom/h, dx, (dy*bottom+y*slope*dx)/h

        def curve(points, count=8):
            def sample(t):
                a = 1-t
                xy = [a**3*points[0][i] + 3*a*a*t*points[1][i] +
                      3*a*t*t*points[2][i] + t**3*points[3][i] for i in (0, 1)]
                velocity = [3*a*a*(points[1][i]-points[0][i]) +
                            6*a*t*(points[2][i]-points[1][i]) +
                            3*t*t*(points[3][i]-points[2][i]) for i in (0, 1)]
                return warp(*xy, *velocity)
            previous = sample(0)
            step = 1/count/3
            for index in range(1, count+1):
                current = sample(index/count)
                path.cubicTo(previous[0]+previous[2]*step, previous[1]+previous[3]*step,
                             current[0]-current[2]*step, current[1]-current[3]*step,
                             current[0], current[1])
                previous = current
        curve([(w, 0), (w-flare*.55, 0), (w-flare, flare*.45), (w-flare, flare)])
        path.lineTo(*warp(w-flare, h-radius)[:2])
        curve([(w-flare, h-radius), (w-flare, h-radius*.34), (right+radius*.66, h), (right, h)])
        curve([(right, h), (right+(left-right)/3, h), (left+(right-left)/3, h), (left, h)], 24)
        curve([(left, h), (left-radius*.66, h), (flare, h-radius*.34), (flare, h-radius)])
        path.lineTo(*warp(flare, flare)[:2])
        curve([(flare, flare), (flare, flare*.45), (flare*.55, 0), (0, 0)])
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillPath(self.notch_path(), QColor("black"))
