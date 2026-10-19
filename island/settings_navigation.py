# SPDX-License-Identifier: GPL-3.0-only
"""Native settings navigation: one task per detail screen, with persistent controls."""
from PySide6.QtCore import Qt,QRectF,QSize
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QPushButton,QComboBox
from .style import font

class SettingsLink(QPushButton):
    def __init__(self,title,callback,summary='',parent=None):
        super().__init__(parent)
        self.title,self.summary=title,summary
        self.setObjectName('settingsLink')
        self.setAccessibleName(title)
        self.setMinimumHeight(52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)
    def sizeHint(self):return QSize(280,52)
    def paintEvent(self,event):
        c=self.window().colors;p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect())
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['raised']));p.drawRoundedRect(rect.adjusted(0,2,0,-2),8,8)
        p.setFont(font(15));p.setPen(QColor(c['text']))
        reserve=min(self.width()//2,220) if self.summary else 28
        p.drawText(rect.adjusted(0,0,-reserve,0),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.title,Qt.TextElideMode.ElideRight,max(1,self.width()-reserve)))
        p.setFont(font(13));p.setPen(QColor(c['muted']))
        p.drawText(rect.adjusted(self.width()//2,0,-27,0),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.summary,Qt.TextElideMode.ElideRight,max(1,self.width()//2-27)))
        p.setFont(font(23));p.drawText(rect.adjusted(self.width()-20,0,0,0),Qt.AlignmentFlag.AlignCenter,'›')
        if self.hasFocus():
            p.setPen(QPen(QColor(c['muted']),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(rect.adjusted(.5,2,-.5,-2),8,8)

class SettingsSubpage(SettingsLink):
    def __init__(self,center,title):
        super().__init__(title,lambda:center.open_detail(self))
        self.center=center
        self.body=QWidget(center)
        self.content=QVBoxLayout(self.body)
        self.content.setContentsMargins(0,0,8,8);self.content.setSpacing(22)
        self.body.hide()
        self.parent_index=center.pages.count()-1
        center.subpages.append(self)


class SettingsSurface(QFrame):
    def paintEvent(self,event):
        super().paintEvent(event)
        from .brand import palette
        c=getattr(self.window(),'colors',palette())
        p=QPainter(self);color=QColor(c['line']);color.setAlpha(130);p.setPen(QPen(color,1))
        layout=self.layout()
        if not layout:return
        for i in range(layout.count()-1):
            item=layout.itemAt(i);child=item.widget()
            if child and child.isVisible() and (child.objectName()=='settingRow' or isinstance(child,SettingsLink)):
                y=child.geometry().bottom()+1;p.drawLine(18,y,self.width()-18,y)

class SettingsCombo(QComboBox):
    def paintEvent(self,event):
        super().paintEvent(event)
        from .brand import palette
        c=getattr(self.window(),'colors',palette())
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(c['muted']),1.3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        x=self.width()-12;y=self.height()//2
        p.drawLine(x-3,y-1,x,y+2);p.drawLine(x,y+2,x+3,y-1)
