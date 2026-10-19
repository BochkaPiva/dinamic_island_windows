# SPDX-License-Identifier: GPL-3.0-only
"""Lightweight previews over the existing models; no independent media services."""
from datetime import date, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .style import font, rounded_art
from .ui_tokens import glyph


class ModulePreview(QWidget):
    def __init__(self, owner, kind, callback):
        super().__init__()
        self.owner, self.kind, self.callback = owner, kind, callback
        self.setFixedHeight(132)
        self.setMinimumWidth(240)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName({'island':'Открыть остров', 'desktop':'Настроить группы',
            'search':'Открыть быстрый поиск'}[kind])
        self.cover_key = None
        self.cover = None
        self.pending = False
        # Coalesce audio events to at most 30 fps, only on the visible page.
        self.clock = QTimer(self)
        self.clock.setInterval(34)
        self.clock.timeout.connect(self.frame)
        if kind == 'island':
            owner.audio.levels_changed.connect(self.audio_changed)

    def audio_changed(self, _):
        if self.isVisible():
            self.pending = True
            if not self.clock.isActive(): self.clock.start()

    def frame(self):
        if not self.isVisible() or not self.pending:
            self.clock.stop()
            return
        self.pending = False
        self.update()

    def hideEvent(self, event):
        self.clock.stop()
        self.pending = False
        super().hideEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.callback()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter): self.callback()
        else: super().keyPressEvent(event)

    def paintEvent(self, event):
        c = self.window().colors
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['bg']))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        if self.hasFocus():
            p.setPen(QPen(QColor(c['accent']), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),14,14)
        if self.kind == 'island': self.island(p,c)
        elif self.kind == 'desktop': self.groups(p,c)
        else: self.search(p,c)
        p.end()

    def island(self, p, c):
        w = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#000000'))
        p.drawRoundedRect(QRectF(12,-22,w-24,130),22,22)
        snap = self.owner.snapshot
        data = snap.thumb if snap and snap.thumb else b''
        if self.cover is None or data != self.cover_key:
            self.cover_key=data
            self.cover=rounded_art(data,40,10,self.devicePixelRatioF())
        p.drawPixmap(24,24,self.cover)
        p.setPen(QColor('#F5F6F8')); p.setFont(font(12,500))
        calendar=w>=320
        width=max(35,int(w*.48)-75) if calendar else w-105
        title=snap.title if snap and snap.title else 'Нет воспроизведения'
        p.drawText(QRectF(74,25,width,20),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,width))
        p.setPen(QColor('#AFB7C3')); p.setFont(font(10))
        artist=snap.artist if snap and snap.artist else 'Музыка появится здесь'
        p.drawText(QRectF(74,47,width,18),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(artist,Qt.TextElideMode.ElideRight,width))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#B4DFF2'))
        for i,level in enumerate(self.owner.status_mark.levels):
            h=3+max(0,min(1,level))*16
            p.drawRoundedRect(QRectF(26+i*7,82-h/2,3,h),1.5,1.5)
        if not calendar: return
        today=date.today(); left=w*.53; cell=(w-left-22)/7
        for i in range(7):
            day=today+timedelta(days=i-3)
            x=left+i*cell
            p.setPen(QColor('#AFB7C3')); p.setFont(font(8))
            p.drawText(QRectF(x,27,cell,15),Qt.AlignmentFlag.AlignCenter,
                ('Пн','Вт','Ср','Чт','Пт','Сб','Вс')[day.weekday()])
            if i==3:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#233C49'))
                p.drawRoundedRect(QRectF(x,46,cell,24),7,7)
            p.setPen(QColor('#B4DFF2' if i==3 else '#F5F6F8')); p.setFont(font(11,500))
            p.drawText(QRectF(x,46,cell,24),Qt.AlignmentFlag.AlignCenter,str(day.day))

    def groups(self,p,c):
        records=self.owner.modules.desktop.store.groups
        group=records[0] if records else {'title':'Создай свою группу','items':[]}
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c['raised']))
        p.drawRoundedRect(QRectF(20,16,self.width()-40,100),12,12)
        glyph(p,'folder',QRectF(34,28,18,18),c['muted'])
        p.setPen(QColor(c['text']));p.setFont(font(12,500))
        p.drawText(QRectF(62,27,self.width()-104,22),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(group['title'],Qt.TextElideMode.ElideRight,self.width()-104))
        items=group['items'][:3]
        for i,item in enumerate(items):
            cell=(self.width()-60)/3; x=30+i*cell
            glyph(p,'note',QRectF(x+cell/2-10,61,20,20),c['accent'])
            p.setFont(font(9));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(x,88,cell,16),Qt.AlignmentFlag.AlignCenter,
                p.fontMetrics().elidedText(Path(item).stem,Qt.TextElideMode.ElideRight,int(cell-8)))
        if not items:
            p.setFont(font(11));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(30,63,self.width()-60,35),Qt.AlignmentFlag.AlignCenter,'Приложения и файлы — вместе')

    def search(self,p,c):
        p.setPen(QPen(QColor(c['line']),1));p.setBrush(QColor(c['surface']))
        p.drawRoundedRect(QRectF(20,35,self.width()-40,62),18,18)
        glyph(p,'search',QRectF(38,54,23,23),c['accent'])
        p.setPen(QColor(c['muted']));p.setFont(font(15))
        p.drawText(QRectF(76,40,self.width()-110,52),Qt.AlignmentFlag.AlignVCenter,'Что открыть?')


class FocusPreview(QWidget):
    """The shared timer inside its progress ring; editing remains native."""
    def __init__(self, hub):
        from PySide6.QtWidgets import QVBoxLayout
        from .timer import TimerReadout
        super().__init__()
        self.hub=hub
        self.setFixedHeight(132)
        row=QVBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        self.readout=TimerReadout(hub,24)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.readout.setFixedWidth(100)
        row.addWidget(self.readout,0,Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self,event):
        c=self.window().colors
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=QRectF(self.width()/2-58,8,116,116)
        p.setPen(QPen(QColor(c['line']),3));p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(box)
        total=max(60,self.hub.owner.settings.get('timer_minutes')*60)
        fraction=max(0,min(1,self.hub.timer_seconds()/total))
        p.setPen(QPen(QColor(c['accent']),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawArc(box,90*16,-round(360*16*fraction))
        p.end()
