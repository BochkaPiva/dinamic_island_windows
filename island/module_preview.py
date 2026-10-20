# SPDX-License-Identifier: GPL-3.0-only
"""Lightweight previews over the existing models; no independent media services."""
from datetime import date, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QTimer, QVariantAnimation, QEasingCurve
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
        self.setCursor(Qt.CursorShape.PointingHandCursor if callback else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if callback else Qt.FocusPolicy.NoFocus)
        self.setAccessibleName({'island':'Открыть остров', 'desktop':'Наведи, чтобы раскрыть группу',
            'search':'Открыть быстрый поиск'}.get(kind,'Предпросмотр раздела'))
        self.display_style=None
        self.appearance_override=None
        self.reveal=0.
        self.hover_animation=QVariantAnimation(self)
        self.hover_animation.setDuration(320)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self.reveal_frame)
        self.cover_key = None
        self.cover = None
        self.pending = False
        # Coalesce audio events to at most 30 fps, only on the visible page.
        self.clock = QTimer(self)
        self.clock.setInterval(34)
        self.clock.timeout.connect(self.frame)
        if kind == 'island':
            owner.audio.levels_changed.connect(self.audio_changed)

    def reveal_frame(self,value):
        self.reveal=float(value)
        self.update()

    def enterEvent(self,event):
        self.animate_hover(1.)
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.animate_hover(0.)
        super().leaveEvent(event)

    def animate_hover(self,target):
        if self.kind!='desktop': return
        self.hover_animation.stop()
        if not self.owner.settings.get('hub_animations'):
            self.reveal_frame(target)
            return
        self.hover_animation.blockSignals(True)
        self.hover_animation.setStartValue(self.reveal)
        self.hover_animation.setEndValue(target)
        self.hover_animation.setCurrentTime(0)
        self.hover_animation.blockSignals(False)
        self.hover_animation.start()

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
        self.hover_animation.stop()
        self.reveal=0.
        self.pending = False
        super().hideEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.callback: self.callback()

    def keyPressEvent(self, event):
        if self.callback and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter): self.callback()
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
        elif self.kind=='search': self.search(p,c)
        else: self.illustration(p,c)
        p.end()

    def island(self, p, c):
        w = self.width()
        from .style import island_outline
        from .island_material import paint_island,effective_appearance,appearance_ink
        floating=self.display_style=='floating' if self.display_style else self.owner.floating_mode()
        p.save();p.translate(12,6 if floating else 0)
        paint_island(p,island_outline(w-24,self.height()-12 if floating else self.height()-6,floating),self.appearance_override or effective_appearance(self.owner))
        p.restore()
        snap = self.owner.snapshot
        data = snap.thumb if snap and snap.thumb else b''
        art_size=32 if self.height()<110 else 40
        cover_key=(data,art_size,self.devicePixelRatioF())
        if self.cover is None or cover_key != self.cover_key:
            self.cover_key=cover_key
            self.cover=rounded_art(data,art_size,8,self.devicePixelRatioF())
        art_y=(self.height()-art_size)/2-5
        p.drawPixmap(24,round(art_y),self.cover)
        p.setPen(appearance_ink(self.appearance_override or effective_appearance(self.owner))); p.setFont(font(12,500))
        calendar=w>=400
        width=max(35,int(w*.48)-75) if calendar else w-105
        title=snap.title if snap and snap.title else 'Нет воспроизведения'
        p.drawText(QRectF(74,self.height()/2-20,width,20),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(title,Qt.TextElideMode.ElideRight,width))
        p.setPen(QColor('#555555') if appearance_ink(self.appearance_override or effective_appearance(self.owner)).lightness()<128 else QColor('#BFC0C7')); p.setFont(font(10))
        artist=snap.artist if snap and snap.artist else 'Музыка появится здесь'
        p.drawText(QRectF(74,self.height()/2+2,width,18),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(artist,Qt.TextElideMode.ElideRight,width))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(appearance_ink(self.appearance_override or effective_appearance(self.owner)))
        levels=self.owner.status_mark.levels
        left=24+art_size/2-(len(levels)*3+max(0,len(levels)-1)*4)/2
        for i,level in enumerate(levels):
            h=3+max(0,min(1,level))*12
            p.drawRoundedRect(QRectF(left+i*7,art_y+art_size+8-h/2,3,h),1.5,1.5)
        if not calendar: return
        today=date.today(); left=w*.53; cell=(w-left-22)/7
        for i in range(7):
            day=today+timedelta(days=i-3)
            x=left+i*cell
            p.setPen(QColor('#AFB7C3')); p.setFont(font(8))
            p.drawText(QRectF(x,27,cell,15),Qt.AlignmentFlag.AlignCenter,
                ('Пн','Вт','Ср','Чт','Пт','Сб','Вс')[day.weekday()])
            if i==3:
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#333333'))
                p.drawRoundedRect(QRectF(x,46,cell,24),7,7)
            p.setPen(QColor('#E2E2E2') if i==3 else appearance_ink(self.appearance_override or effective_appearance(self.owner))); p.setFont(font(11,500))
            p.drawText(QRectF(x,46,cell,24),Qt.AlignmentFlag.AlignCenter,str(day.day))

    def groups(self,p,c):
        records=self.owner.modules.desktop.store.groups
        group=records[0] if records else {'title':'Создай свою группу','items':[]}
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c['raised']))
        p.drawRoundedRect(QRectF(20,16,self.width()-40,40+min(60,max(0,self.height()-64))*self.reveal),12,12)
        glyph(p,'folder',QRectF(34,28,18,18),c['muted'])
        p.setPen(QColor(c['text']));p.setFont(font(12,500))
        p.drawText(QRectF(62,27,self.width()-104,22),Qt.AlignmentFlag.AlignVCenter,
            p.fontMetrics().elidedText(group['title'],Qt.TextElideMode.ElideRight,self.width()-104))
        p.setClipRect(QRectF(20,56,self.width()-40,60*self.reveal))
        p.setOpacity(self.reveal)
        p.translate(0,-8*(1-self.reveal))
        items=group['items'][:3]
        for i,item in enumerate(items):
            cell=(self.width()-60)/3; x=30+i*cell
            compact=self.height()<110
            glyph(p,'note',QRectF(x+cell/2-(8 if compact else 10),59 if compact else 61,16 if compact else 20,16 if compact else 20),c['accent'])
            if compact:continue
            p.setFont(font(9));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(x,88,cell,16),Qt.AlignmentFlag.AlignCenter,
                p.fontMetrics().elidedText(Path(item).stem,Qt.TextElideMode.ElideRight,int(cell-8)))
        if not items:
            p.setFont(font(11));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(30,58 if self.height()<110 else 63,self.width()-60,18 if self.height()<110 else 35),Qt.AlignmentFlag.AlignCenter,'Перетащи файлы' if self.height()<110 else 'Приложения и файлы — вместе')

    def illustration(self,p,c):
        if self.kind=='shortcuts':
            keys=self.owner.settings.get('hotkey_search') or 'Alt+Space'
            p.setFont(font(18,500));p.setPen(QColor(c['text']))
            p.drawText(QRectF(12,20,self.width()-24,60),Qt.AlignmentFlag.AlignCenter,keys.replace('+','  +  '))
            p.setFont(font(11));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(12,80,self.width()-24,30),Qt.AlignmentFlag.AlignCenter,'Поиск — одним сочетанием')
            return
        if self.kind=='application':
            for i,color in enumerate((c['side'],c['surface'],c['raised'])):
                p.setPen(QPen(QColor(c['line']),1));p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(30+i*55,20+i*12,self.width()-160,65),12,12)
            return
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['raised']))
        if self.kind=='workspaces':
            for i in range(3): p.drawRoundedRect(QRectF(24+i*(self.width()-48)/3,24,(self.width()-60)/3,84),8,8)
            return
        # A note and file shelf: an illustration, never generated user content.
        p.drawRoundedRect(QRectF(24,18,90,96),12,12)
        glyph(p,'note',QRectF(42,34,26,26),c['accent'])
        p.setPen(QPen(QColor(c['muted']),2))
        for y,length in ((76,46),(86,32)): p.drawLine(42,y,42+length,y)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['surface']))
        p.drawRoundedRect(QRectF(100,42,self.width()-124,60),12,12)
        glyph(p,'folder',QRectF(116,60,22,22),c['accent'])
        p.setPen(QColor(c['text']));p.setFont(font(11))
        p.drawText(QRectF(150,49,self.width()-175,42),Qt.AlignmentFlag.AlignVCenter,'Под рукой')

    def search(self,p,c):
        box=QRectF(20,(self.height()-min(62,self.height()-24))/2,self.width()-40,min(62,self.height()-24))
        p.setPen(QPen(QColor(c['line']),1));p.setBrush(QColor(c['surface']))
        p.drawRoundedRect(box,18,18)
        glyph(p,'search',QRectF(38,box.center().y()-11.5,23,23),c['accent'])
        p.setPen(QColor(c['muted']));p.setFont(font(15))
        p.drawText(QRectF(76,box.top(),self.width()-110,box.height()),Qt.AlignmentFlag.AlignVCenter,'Что открыть?')


class FocusPreview(QWidget):
    """The shared timer inside its progress ring; editing remains native."""
    def __init__(self, hub, readout_size=24):
        from PySide6.QtWidgets import QVBoxLayout
        from .timer import TimerReadout
        super().__init__()
        self.hub=hub
        self.setFixedHeight(132)
        row=QVBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        self.readout=TimerReadout(hub,readout_size)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.readout.setFixedWidth(100)
        row.addWidget(self.readout,0,Qt.AlignmentFlag.AlignCenter)

    def paintEvent(self,event):
        c=self.window().colors
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=QRectF(self.width()/2-min(self.height(),self.width())*.41,self.height()/2-min(self.height(),self.width())*.41,min(self.height(),self.width())*.82,min(self.height(),self.width())*.82)
        p.setPen(QPen(QColor(c['line']),3));p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(box)
        total=max(60,self.hub.owner.settings.get('timer_minutes')*60)
        fraction=max(0,min(1,self.hub.timer_seconds()/total))
        p.setPen(QPen(QColor(c['accent']),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawArc(box,90*16,-round(360*16*fraction))
        p.end()


class FormPreview(ModulePreview):
    """Compact, live form demonstration with the same outline as the HWND."""
    def __init__(self,owner,style,callback=None):
        super().__init__(owner,'island',callback)
        self.display_style=style;self.setFixedHeight(80);self.setMinimumWidth(180)

    def paintEvent(self,event):
        from .style import island_outline
        c=getattr(self.window(),'colors',None)
        if c is None:
            from .brand import palette
            c=palette()
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(c['bg']))
        p.drawRoundedRect(QRectF(self.rect()),14,14)
        p.setClipRect(self.rect().adjusted(8,8,-8,-8))
        p.setBrush(QColor(c['raised']))

        width=min(210,self.width()-40);height=38
        x=(self.width()-width)/2;y=23 if self.display_style=='floating' else 8
        p.save();p.translate(x,y)
        path=island_outline(width,height,self.display_style=='floating')
        from .island_material import effective_appearance,paint_island,appearance_ink
        paint_island(p,path,self.appearance_override or effective_appearance(self.owner));p.setClipPath(path)
        data=self.owner.snapshot.thumb if self.owner and self.owner.snapshot else b''
        if self.cover is None or self.cover_key!=data:
            self.cover_key=data;self.cover=rounded_art(data,24,6,self.devicePixelRatioF())
        p.drawPixmap(20,7,self.cover)
        p.setPen(appearance_ink(self.appearance_override or effective_appearance(self.owner)));p.setFont(font(10,500))
        p.drawText(QRectF(52,0,max(20,width-118),38),Qt.AlignmentFlag.AlignCenter,
            self.owner.activities.text() if self.owner and self.owner.activities.current()!='media' else 'Музыка')
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(appearance_ink(self.appearance_override or effective_appearance(self.owner)))
        levels=self.owner.status_mark.levels if self.owner else (0,)*5
        for i,level in enumerate(levels):
            height=3+max(0,min(1,level))*15
            p.drawRoundedRect(QRectF(width-48+i*5,19-height/2,2.5,height),1.2,1.2)
        p.restore()
        if self.hasFocus():
            p.setClipping(False);p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(c['accent']),1))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),14,14)
        p.end()
