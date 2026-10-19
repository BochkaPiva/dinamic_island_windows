# SPDX-License-Identifier: GPL-3.0-only
"""A small, keyboard-first shortcut sheet; no global keyboard hooks."""
from PySide6.QtCore import Qt,QPoint,QRectF,QEvent,Signal
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QRegion,QKeySequence
from PySide6.QtWidgets import QWidget,QPushButton,QDialog,QVBoxLayout,QHBoxLayout,QLabel
from .style import font
from .brand import resolved_palette
from .hub_ui import icon
from .hotkey import parse_shortcut


def draw_keycaps(p,rect,sequence,colors,*,large=False):
    tokens=sequence.replace('Meta+','Win+').split('+') if sequence else ['Записать…']
    p.setFont(font(20 if large else 12,400))
    height=36 if large else 26
    gap=6 if large else 4
    widths=[max(height,p.fontMetrics().horizontalAdvance(t)+18) for t in tokens]
    x=rect.center().x()-(sum(widths)+gap*(len(tokens)-1))/2
    y=rect.center().y()-height/2
    for token,width in zip(tokens,widths):
        box=QRectF(x,y,width,height)
        p.setPen(QPen(QColor(255,255,255,18) if colors['bg']=='#161616' else QColor(0,0,0,20),1))
        p.setBrush(QColor(255,255,255,22) if colors['bg']=='#161616' else QColor(0,0,0,12))
        p.drawRoundedRect(box,5,5)
        p.setPen(QColor(colors['text']))
        if token=='Win':
            # A generic four-pane keyboard symbol, drawn with our own primitives.
            size=15 if large else 12
            left=box.center().x()-size/2;top=box.center().y()-size/2
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(colors['text']))
            for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
                p.drawRect(QRectF(left+dx*(size/2+1),top+dy*(size/2+1),size/2-1,size/2-1))
        else:
            p.drawText(box,Qt.AlignmentFlag.AlignCenter,token)
        x+=width+gap


class ShortcutButton(QPushButton):
    def __init__(self,value,parent=None):
        super().__init__(parent)
        self.value=value
        self.setFixedHeight(38);self.setMinimumWidth(190)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def keySequence(self): return QKeySequence(self.value.replace('Win+','Meta+'))

    def setKeySequence(self,value):
        self.value=value.toString(QKeySequence.SequenceFormat.PortableText)
        self.setAccessibleDescription(self.value or 'Не назначено')
        self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=self.window().colors
        if self.underMouse() or self.hasFocus():
            p.setBrush(QColor(c['raised']));p.setPen(QPen(QColor(c['muted'] if self.hasFocus() else c['line']),1))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),6,6)
        draw_keycaps(p,QRectF(self.rect()),self.value,c)


class ShortcutCapture(QWidget):
    changed=Signal()
    save=Signal()
    cancel=Signal()
    def __init__(self,value,colors):
        super().__init__()
        self.value=value;self.colors=colors;self.modifiers=''
        self.setMinimumHeight(112)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Нажми новое сочетание клавиш')
        self.setAccessibleDescription(value)

    def keyPressEvent(self,event):
        if event.isAutoRepeat(): event.accept();return
        key=event.key()
        mods=event.modifiers()
        if key==Qt.Key.Key_Escape: self.cancel.emit();return
        if key in (Qt.Key.Key_Enter,Qt.Key.Key_Return) and not mods:
            self.save.emit();return
        names=[]
        for mask,name in ((Qt.KeyboardModifier.MetaModifier,'Meta'),(Qt.KeyboardModifier.ControlModifier,'Ctrl'),
                (Qt.KeyboardModifier.AltModifier,'Alt'),(Qt.KeyboardModifier.ShiftModifier,'Shift')):
            if mods & mask:names.append(name)
        if key in (Qt.Key.Key_Control,Qt.Key.Key_Alt,Qt.Key.Key_Shift,Qt.Key.Key_Meta):
            self.modifiers='+'.join(names);self.update();event.accept();return
        self.modifiers=''
        # Windows virtual letter keys are layout-independent (also on Cyrillic layouts).
        native=event.nativeVirtualKey()
        if 0x41<=native<=0x5A:key=native
        suffix=QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)
        self.value='+'.join(names+[suffix])
        self.setAccessibleDescription(self.value)
        self.changed.emit();self.update();event.accept()

    def keyReleaseEvent(self,event):
        if not event.modifiers():self.modifiers='';self.update()
        event.accept()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_keycaps(p,QRectF(self.rect()),self.modifiers or self.value,self.colors,large=True)


class ShortcutDialog(QDialog):
    def __init__(self,center,key,title,anchor=None):
        super().__init__(center,Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint)
        self.center=center;self.owner=center.owner;self.key=key;self.anchor=anchor
        self.colors=resolved_palette(self.owner.settings)
        self.material=False;self._restored=False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle('Сочетание · '+title)
        self.setAccessibleName('Назначить сочетание: '+title)
        self.setFixedWidth(474)
        from .hub_ui import stylesheet
        self.setStyleSheet(stylesheet(self.colors)+"QDialog {background:transparent;} QLabel#sheetAction {font-size:14px;} QPushButton#sheetSave {padding:4px 12px;font-size:14px;} QPushButton#sheetCancel {background:transparent;border:0;font-size:14px;}")
        root=QVBoxLayout(self);root.setContentsMargins(16,8,16,10);root.setSpacing(0)
        self.capture=ShortcutCapture(self.owner.settings.get(key),self.colors)
        root.addWidget(self.capture)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setObjectName('sheetAction')
        self.error.hide();root.addWidget(self.error)
        footer=QHBoxLayout();footer.setContentsMargins(0,12,0,0);footer.setSpacing(8)
        emblem=QLabel();emblem.setPixmap(icon({'hotkey_search':'search','hotkey_island':'island','hotkey_hub':'settings'}[key],self.colors['muted'],16).pixmap(16,16))
        footer.addWidget(emblem)
        label=QLabel(title);label.setObjectName('sheetAction');footer.addWidget(label,1)
        self.save_button=QPushButton('Сохранить  ↵');self.save_button.setObjectName('sheetSave')
        self.save_button.clicked.connect(self.apply);footer.addWidget(self.save_button)
        cancel=QPushButton('Отмена  Esc');cancel.setObjectName('sheetCancel');cancel.clicked.connect(self.reject)
        footer.addWidget(cancel);root.addLayout(footer)
        self.capture.save.connect(self.apply);self.capture.cancel.connect(self.reject)
        self.capture.changed.connect(self.validate)
        self.resize(474,178)

    def suspend(self):
        for binding in self.owner.hotkeys.values():binding.suspend()
        self._restored=False

    def restore(self):
        if not self._restored and not self.owner._closed:
            for key,binding in self.owner.hotkeys.items():binding.rebind(self.owner.settings.get(key))
        self._restored=True

    def validate(self):
        try:
            if not self.capture.value:raise ValueError('Нажми сочетание с Ctrl, Alt или Win')
            parse_shortcut(self.capture.value)
            error=''
        except ValueError as exc:error=str(exc)
        self.error.setText(error);self.error.setVisible(bool(error))
        self.save_button.setEnabled(not error)
        self.adjustSize()
        return not error

    def apply(self):
        if not self.validate():return
        self.restore()
        if self.owner._toggle_setting(self.key,self.capture.value):
            self.center.refresh();self.accept()
        else:
            self.suspend()
            binding=self.owner.hotkeys.get(self.key)
            self.error.setText(self.center.feedback.text() or (binding.error if binding else '') or 'Не удалось сохранить сочетание. Попробуй ещё раз.')
            self.center.feedback.hide()
            self.error.show();self.adjustSize();self.capture.setFocus()

    def showEvent(self,event):
        super().showEvent(event)
        self.suspend()
        from .native_material import apply_acrylic
        self.material=apply_acrylic(self,light=QColor(self.colors['bg']).lightness()>127)
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),12,12)
        if self.material:self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        anchor=self.anchor if self.anchor is not None else self.center.key_editors.get(self.key)
        if anchor is not None and anchor.isVisible():
            edge=anchor.mapToGlobal(QPoint(anchor.width(),anchor.height()))
            bounds=anchor.screen().availableGeometry()
            x=max(bounds.left()+8,min(edge.x()-self.width(),bounds.right()-self.width()-8))
            y=edge.y()+8
            if y+self.height()>bounds.bottom()-8:
                y=anchor.mapToGlobal(QPoint(0,0)).y()-self.height()-8
            self.move(x,max(bounds.top()+8,y))
        else:self.move(self.center.geometry().center()-self.rect().center())
        self.capture.setFocus()

    def changeEvent(self,event):
        if event.type()==QEvent.Type.ActivationChange and hasattr(self,'_restored'):
            if self.isActiveWindow():
                self.capture.modifiers='';self.capture.update();self.suspend()
            else:self.restore()
        super().changeEvent(event)

    def hideEvent(self,event):
        self.restore();super().hideEvent(event)

    def resizeEvent(self,event):
        if self.material:
            path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),12,12)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(event)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill=QColor(self.colors['surface']);fill.setAlpha(48 if self.material else 255)
        p.setBrush(fill);p.setPen(QPen(QColor(self.colors['muted'] if self.material else self.colors['line']),.7))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)
        p.setPen(QPen(QColor(255,255,255,16) if self.colors['bg']=='#161616' else QColor(0,0,0,20),1))
        p.drawLine(1,self.height()-52,self.width()-1,self.height()-52)
