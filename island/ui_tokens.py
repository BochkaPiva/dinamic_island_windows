# SPDX-License-Identifier: GPL-3.0-only
"""Shared quiet surfaces, type and original line icons for desktop tools."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget, QPushButton

SURFACE = "#202227"
TEXT = "#f4f4f6"
MUTED = "#989ca6"


def glyph(painter, name, rect, color=TEXT):
    p = painter
    p.save()
    p.translate(rect.x(),rect.y())
    p.scale(rect.width()/24,rect.height()/24)
    p.setPen(QPen(QColor(color),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "search":
        p.drawEllipse(QRectF(4,3,12,12)); p.drawLine(14,14,21,21)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3,8); path.lineTo(3,6); path.quadTo(3,4,5,4)
        path.lineTo(9,4); path.lineTo(12,7); path.lineTo(19,7)
        path.quadTo(21,7,21,9); path.lineTo(21,18); path.quadTo(21,20,19,20)
        path.lineTo(5,20); path.quadTo(3,20,3,18); path.closeSubpath()
        p.drawPath(path); p.drawLine(3,10,21,10)
    elif name == "timer":
        p.drawEllipse(QRectF(4,5,16,16)); p.drawLine(12,9,12,13); p.drawLine(12,13,15,13)
        p.drawLine(9,2,15,2)
    elif name == "island":
        p.drawRoundedRect(QRectF(2,7,20,10),5,5); p.drawLine(7,10,7,14); p.drawLine(10,9,10,15)
    elif name == "dots":
        p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
        for x in (5,12,19): p.drawEllipse(QRectF(x-1,11,2,2))
    elif name == "chevron":
        p.drawLine(7,14,12,9); p.drawLine(12,9,17,14)
    elif name == "add":
        p.drawLine(12,5,12,19); p.drawLine(5,12,19,12)
    elif name in {"hub","app","store"}:
        for x,y in ((4,4),(14,4),(4,14),(14,14)): p.drawRoundedRect(QRectF(x,y,6,6),1.5,1.5)
    elif name=='download':
        p.drawLine(12,3,12,15); p.drawLine(7,10,12,15); p.drawLine(12,15,17,10)
        p.drawLine(4,16,4,21); p.drawLine(4,21,20,21); p.drawLine(20,21,20,16)
    elif name=='keyboard':
        p.drawRoundedRect(QRectF(2,5,20,14),3,3)
        for x in (6,10,14,18):
            p.drawPoint(x,9); p.drawPoint(x,12)
        p.drawLine(7,16,17,16)
    elif name=='windows':
        p.drawRoundedRect(QRectF(3,3,18,18),3,3); p.drawLine(3,9,21,9); p.drawLine(12,9,12,21)
    elif name=='settings':
        for y,x in ((6,9),(12,16),(18,7)):
            p.drawLine(3,y,21,y); p.setBrush(QColor(color)); p.drawEllipse(QRectF(x-2,y-2,4,4))
    else:
        p.drawRoundedRect(QRectF(5,3,14,18),2,2)
        for y in (9,13,17): p.drawLine(9,y,15,y)
    p.restore()


class LineIcon(QWidget):
    def __init__(self,name,size=22,parent=None):
        super().__init__(parent)
        self.name = name
        self.setFixedSize(size,size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        glyph(p,self.name,QRectF(self.rect()),MUTED)


class IconButton(QPushButton):
    def __init__(self,name,tip,parent=None):
        super().__init__(parent)
        self.icon_name = name
        self.setFixedSize(28,28)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255,255,255,20))
            p.drawRoundedRect(QRectF(self.rect()),7,7)
        glyph(p,self.icon_name,QRectF(6,6,16,16),TEXT if self.underMouse() else MUTED)
