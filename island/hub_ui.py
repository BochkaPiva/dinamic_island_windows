# SPDX-License-Identifier: GPL-3.0-only
"""Quiet native surfaces, switches, navigation and short-lived transitions."""
from PySide6.QtCore import Qt,QRectF,QSize,QVariantAnimation,QEasingCurve,QAbstractAnimation
from PySide6.QtGui import QColor,QPainter,QPen,QIcon,QPixmap,QPalette
from PySide6.QtWidgets import QWidget,QCheckBox,QListWidget,QStyledItemDelegate,QStyle,QFrame,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QSizePolicy
from .ui_tokens import glyph
from .style import font,rounded_art

NAV_ICONS={'hub':'hub','island':'island','search':'search','desktop':'folder','library':'note',
    'timer':'timer','shortcuts':'keyboard','workspaces':'windows','integrations':'settings','updates':'download','windows':'windows','account':'community'}


def motion_allowed(widget):
    window=widget.window()
    return bool(not hasattr(window,'owner') or window.owner.settings.get('hub_animations'))


from .brand import palette, MOTION


def icon(name,color='#a6abbc',size=20):
    pix=QPixmap(size*2,size*2)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    glyph(painter,name,QRectF(0,0,size,size),color)
    painter.end()
    return QIcon(pix)


class HintButton(QPushButton):
    """A real action with individually readable keyboard hints."""
    def __init__(self,title,keys,callback,parent=None):
        super().__init__(parent)
        self.setObjectName('hintAction')
        self.setAccessibleName(title)
        self.clicked.connect(callback)
        row=QHBoxLayout(self);row.setContentsMargins(8,4,8,4);row.setSpacing(5)
        self.caption=QLabel(title);self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.caption)
        for key in keys:
            label=QLabel(key);label.setObjectName('keyHint')
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):return self.layout().sizeHint()
    def minimumSizeHint(self):return self.sizeHint()


class ActionFooter(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('actionFooter')
        self.row=QHBoxLayout(self);self.row.setContentsMargins(12,5,10,5);self.row.setSpacing(6)
        self.context=ElidedLabel('');self.context.setObjectName('secondary')
        self.row.addWidget(self.context,1)

    def add_action(self,title,keys,callback):
        action=HintButton(title,keys,callback,self);self.row.addWidget(action)
        return action


class ElidedLabel(QLabel):
    """Keep full accessible text without letting a long token expand its row."""
    def __init__(self,value='',parent=None):
        super().__init__(value,parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setToolTip(value)

    def setText(self,value):
        super().setText(value)
        self.setToolTip(value)

    def paintEvent(self,event):
        p=QPainter(self);p.setFont(self.font())
        p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        if not self.isEnabled():p.setOpacity(.5)
        rect=self.contentsRect()
        p.drawText(rect,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
            self.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(0,rect.width())))


class ToggleSwitch(QCheckBox):
    def __init__(self,label='',parent=None):
        super().__init__(parent)
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setFixedSize(42,26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position=0.
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(MOTION["toggle"])
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.toggled.connect(self.retarget)

    def sizeHint(self): return QSize(42,26)
    def hitButton(self,point): return self.rect().contains(point)

    def frame(self,value):
        self.position=float(value)
        self.update()

    def retarget(self,value):
        self.animation.stop()
        if not self.isVisible() or not motion_allowed(self):
            self.position=float(value)
            self.update()
            return
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(value))
        self.animation.start()

    def showEvent(self,event):
        self.position=float(self.isChecked())
        super().showEvent(event)

    def hideEvent(self,event):
        self.animation.stop()
        super().hideEvent(event)

    def paintEvent(self,event):
        if self.animation.state()!=QAbstractAnimation.State.Running: self.position=float(self.isChecked())
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled(): p.setOpacity(.35)
        colors=getattr(self.window(),'colors',palette())
        off=QColor(colors['line']); on=QColor(colors['accent'])
        t=self.position
        color=QColor(round(off.red()*(1-t)+on.red()*t),round(off.green()*(1-t)+on.green()*t),round(off.blue()*(1-t)+on.blue()*t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(1,2,40,22),11,11)
        p.setBrush(QColor(colors['onAccent'] if self.isChecked() else colors['text']))
        p.drawEllipse(QRectF(4+18*t,5,16,16))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(colors['accent']),1))
            p.drawRoundedRect(QRectF(.5,.5,41,25),12,12)


class NavDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index): return QSize(205,64 if index.data(Qt.ItemDataRole.UserRole)=="shortcuts" else 42)

    def paint(self,p,option,index):
        colors=self.parent().window().colors
        selected=index.row()==self.parent().currentRow()
        current=self.parent().currentItem()
        if index.data(Qt.ItemDataRole.UserRole)=='integrations' and current and current.data(Qt.ItemDataRole.UserRole) in {'updates','shortcuts'}:selected=True
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(2,2,-2,-2)
        if index.data(Qt.ItemDataRole.UserRole)=='shortcuts':
            if not self.parent().property('collapsed'):
                p.setFont(font(10,500));p.setPen(QColor(colors['muted']))
                p.drawText(rect.adjusted(12,0,0,0),Qt.AlignmentFlag.AlignTop,'Настройки')
            rect.setTop(rect.top()+22)
        p.setPen(Qt.PenStyle.NoPen)
        if selected or hovered:
            p.setBrush(QColor(colors['selection'] if selected else colors['raised']))
            p.drawRoundedRect(rect,7,7)
        if option.state & QStyle.StateFlag.State_HasFocus:
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(colors['accent']),1))
            p.drawRoundedRect(rect.adjusted(.5,.5,-.5,-.5),6,6)
        color=colors['text'] if selected else colors['muted']
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(colors['raised']))
        tile=QRectF(rect.x()+8,rect.center().y()-13,26,26);p.drawRoundedRect(tile,6,6)
        glyph(p,NAV_ICONS.get(index.data(Qt.ItemDataRole.UserRole),'hub'),tile.adjusted(5,5,-5,-5),color)
        p.setFont(font(15,500 if selected else 400))
        p.setPen(QColor(color))
        if not self.parent().property("collapsed"):
            p.drawText(QRectF(rect.x()+44,rect.y(),rect.width()-52,rect.height()),Qt.AlignmentFlag.AlignVCenter,index.data())
        if index.data(Qt.ItemDataRole.UserRole)=='updates' and self.parent().window().owner.updates.state in {'available','ready'}:
            p.setBrush(QColor(colors['accent']))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(rect.right()-13,rect.center().y()-2,4,4))
        p.restore()


class Navigation(QListWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setItemDelegate(NavDelegate(self))
        self.setMouseTracking(True)
        self.setSpacing(2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)


class ContentTransition(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.old=self.new=None
        self.value=1.
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(MOTION["response"])
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.frame)
        self.animation.finished.connect(self.done)
        self.hide()

    def frame(self,value):
        self.value=float(value)
        self.update()

    def done(self):
        self.hide()
        self.old=self.new=None

    def start(self,old,new):
        self.animation.stop()
        self.old,self.new=old,new
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.animation.setStartValue(0.)
        self.animation.setEndValue(1.)
        self.animation.start()

    def paintEvent(self,event):
        if self.old is None or self.new is None: return
        p=QPainter(self)
        colors=self.window().colors
        p.fillRect(self.rect(),QColor(colors['bg']))
        p.setOpacity(1-self.value)
        p.drawPixmap(0,round(-8*self.value),self.old)
        p.setOpacity(self.value)
        p.drawPixmap(0,round(10*(1-self.value)),self.new)


class ModuleCard(QFrame):
    def __init__(self,callback,parent=None):
        super().__init__(parent)
        self.callback=callback
        self.setObjectName('moduleCard')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hover=0.
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(170)
        self.animation.valueChanged.connect(self.frame)

    def frame(self,value):
        self.hover=float(value)
        self.update()

    def point(self,target):
        self.animation.stop()
        if motion_allowed(self):
            self.animation.setStartValue(self.hover)
            self.animation.setEndValue(target)
            self.animation.start()
        else: self.frame(target)

    def enterEvent(self,event): self.point(1.)
    def leaveEvent(self,event): self.point(0.)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()): self.callback()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space): self.callback()
        else: super().keyPressEvent(event)

    def hideEvent(self,event):
        self.animation.stop()
        self.hover=0.
        super().hideEvent(event)

    def paintEvent(self,event):
        colors=self.window().colors
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        p.setBrush(QColor(colors['surface']))
        selected=self.hasFocus() or bool(self.property('selected'))
        edge=QColor(colors['accent'] if selected else colors['line'])
        edge.setAlpha(255 if selected else round(150+100*self.hover))
        p.setPen(QPen(edge,1))
        p.drawRoundedRect(rect,20,20)



class CatalogRow(QPushButton):
    def __init__(self,title,detail,callback):
        super().__init__()
        self.title,self.detail=title,detail
        self.setCheckable(True)
        self.setMinimumHeight(56)
        self.setAccessibleName(title+' — '+detail)
        self.setToolTip(title+' — '+detail)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)

    def mouseDoubleClickEvent(self,event):
        destination=self.property('destination')
        if event.button()==Qt.MouseButton.LeftButton and destination:
            self.window().navigate(destination);event.accept()
        else:super().mouseDoubleClickEvent(event)

    def paintEvent(self,event):
        c=self.window().colors
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box=QRectF(self.rect()).adjusted(1,1,-1,-1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['selection'] if self.isChecked() else c['raised'] if self.underMouse() else c['surface']))
        p.drawRoundedRect(box,6,6)
        p.setBrush(QColor(c['raised']));p.drawRoundedRect(QRectF(10,(self.height()-32)/2,32,32),7,7)
        self.icon().paint(p,16,(self.height()-20)//2,20,20)
        width=max(1,self.width()-68)
        p.setPen(QColor(c['text']));p.setFont(font(15,400))
        p.drawText(QRectF(54,9 if self.detail else 0,width,20 if self.detail else self.height()),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.title,Qt.TextElideMode.ElideRight,width))
        p.setPen(QColor(c['muted']));p.setFont(font(12))
        p.drawText(QRectF(54,30,width,18),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.detail,Qt.TextElideMode.ElideRight,width))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(c['accent']),1))
            p.drawRoundedRect(box,6,6)


class CollectionDelegate(QStyledItemDelegate):
    """Compact icon/title/detail rows shared by saved collections."""
    def sizeHint(self,option,index):return QSize(160,58)
    def paint(self,p,option,index):
        c=getattr(self.parent().window(),'colors',palette())
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(option.rect).adjusted(1,1,-1,-1)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c['selection'] if selected else c['raised'] if option.state & QStyle.StateFlag.State_MouseOver else c['field']))
        p.drawRoundedRect(rect,6,6)
        emblem=index.data(Qt.ItemDataRole.DecorationRole)
        if emblem:emblem.paint(p,round(rect.x()+10),round(rect.center().y()-10),20,20)
        lines=str(index.data()).split('\n',1);x=rect.x()+40;width=max(1,round(rect.width()-50))
        p.setFont(font(14));p.setPen(QColor(c['text']))
        p.drawText(QRectF(x,rect.y()+8,width,21),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(lines[0],Qt.TextElideMode.ElideRight,width))
        if len(lines)>1:
            p.setFont(font(11));p.setPen(QColor(c['muted']))
            p.drawText(QRectF(x,rect.y()+30,width,18),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(lines[1],Qt.TextElideMode.ElideRight,width))
        if option.state & QStyle.StateFlag.State_HasFocus:
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(c['muted']),1));p.drawRoundedRect(rect,6,6)
        p.restore()


class WindowHeader(QWidget):
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle(): self.window().windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        window=self.window()
        window.showNormal() if window.isMaximized() else window.showMaximized()


class SettingsSection(QFrame):
    def __init__(self,title,opened=False):
        super().__init__()
        self.setObjectName('card')
        self.opened=opened
        root=QVBoxLayout(self)
        root.setContentsMargins(14,6,14,6)
        self.title=title
        self.button=QPushButton(title+('  −' if opened else '  +'))
        self.button.setObjectName('disclosure')
        self.button.setCheckable(True)
        self.button.setChecked(opened)
        self.button.setAccessibleName(title)
        root.addWidget(self.button)
        self.body=QWidget()
        self.content=QVBoxLayout(self.body)
        self.content.setContentsMargins(0,8,0,8)
        self.content.setSpacing(12)
        root.addWidget(self.body)
        self.body.setVisible(opened)
        self.animation=QVariantAnimation(self)
        self.animation.setDuration(MOTION["toggle"])
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda v:self.body.setMaximumHeight(round(v)))
        self.animation.finished.connect(self.done)
        self.button.toggled.connect(self.toggle)

    def toggle(self,value):
        self.opened=value
        self.button.setText(self.title+('  −' if value else '  +'))
        self.animation.stop()
        start=self.body.height() if self.body.isVisible() else 0
        self.body.setMaximumHeight(16777215)
        target=self.body.sizeHint().height() if value else 0
        self.body.show()
        if not self.isVisible() or not motion_allowed(self):
            self.done()
            return
        self.body.setMaximumHeight(start)
        self.animation.blockSignals(True)
        self.animation.setStartValue(float(start))
        self.animation.setEndValue(float(target))
        self.animation.setCurrentTime(0)
        self.animation.blockSignals(False)
        self.animation.start()

    def done(self):
        self.body.setVisible(self.opened)
        self.body.setMaximumHeight(16777215)

    def hideEvent(self,event):
        self.animation.stop()
        self.done()
        super().hideEvent(event)


def stylesheet(c,*,glass=False):
    sidebar="transparent" if glass else c["side"]
    return f"""
        QWidget {{background:transparent;color:{c['text']};font-family:'Golos Text';font-size:15px;}}
        QDialog,QMessageBox {{background:{c['surface']};color:{c['text']};}}
        QMenu,QToolTip {{background:{c['raised']};color:{c['text']};border:1px solid {c['line']};border-radius:12px;padding:6px;}}
        QMenu::item {{padding:8px 14px;border-radius:5px;}}
        QMenu::item:selected {{background:{c['selection']};}}
        QLabel#brand {{font-size:15px;font-weight:600;}}
        QLabel#heading {{font-size:20px;font-weight:500;margin:0 0 4px 0;}}
        QLabel#heroTitle {{font-size:22px;font-weight:600;}}
        QLabel#cardTitle {{font-size:16px;font-weight:600;}}
        QLabel#secondary,QLabel#hint {{color:{c['muted']};font-size:12px;}}
        QLabel#eyebrow {{color:{c['muted']};font-size:10px;letter-spacing:1px;}}
        QLabel#paneTitle {{font-size:14px;font-weight:500;}}
        QLabel#keyHint {{background:{c['raised']};border:1px solid {c['line']};border-radius:4px;padding:2px 4px;font-size:11px;color:{c['muted']};}}
        QFrame#actionFooter {{border:0;border-top:1px solid {c['line']};background:transparent;}}
        QPushButton#hintAction {{background:transparent;border:0;padding:0;}}
        QPushButton#hintAction:hover,QPushButton#hintAction:focus {{background:{c['selection']};}}
        QFrame#sectionWrapper {{background:transparent;border:0;}}
        QFrame#inspector {{background:{c['surface']};border:0;border-radius:13px;}}
        QLabel#tableHeading {{color:{c['muted']};font-size:12px;padding:5px 10px;}}
        QLabel#toast {{background:{c['raised']};border:1px solid {c['line']};border-radius:10px;padding:10px 15px;color:{c['text']};}}
        QLabel#resource {{color:{c['muted']};font-size:10px;}}
        QFrame#card {{background:transparent;border:0;border-radius:18px;}}
        QFrame#groupPane {{background:transparent;border:0;}}
        QFrame#sidebar {{background:{sidebar};border:0;border-radius:0;}}
        QFrame#hero {{background:{c['surface']};border:0;border-radius:8px;}}
        QFrame#segments {{background:{c['field']};border:1px solid {c['line']};border-radius:10px;}}
        QFrame#settingRow {{border:0;}}
        QPushButton {{background:{c['raised']};border:0;border-radius:7px;padding:7px 12px;}}
        QPushButton:hover {{background:{c['selection']};}}
        QPushButton:pressed {{background:{c['line']};}}
        QPushButton:checked {{background:{c['selection']};border-color:{c['accent']};}}
        QPushButton:disabled {{color:{c['muted']};}}
        QPushButton:focus {{border-color:{c['accent']};}}
        QPushButton#primary {{background:{c['raised']};color:{c['text']};border:1px solid {c['line']};font-weight:600;}}
        QPushButton#primary:hover {{background:{c['selection']};border-color:{c['muted']};}}
        QPushButton#disclosure {{background:transparent;border:0;text-align:left;font-size:13px;font-weight:500;padding:8px 0;}}
        QPushButton#disclosure:hover {{color:{c['accent']};}}
        QPushButton#tileTitle {{background:transparent;border:0;text-align:left;padding:0;font-size:14px;font-weight:500;}}
        QPushButton#demoResult {{background:transparent;border:0;text-align:left;padding:9px 6px;}}
        QPushButton#demoResult:hover {{background:{c['selection']};}}
        QLabel#noteSample {{font-size:17px;color:{c['muted']};padding:8px;}}
        QPushButton#iconButton {{padding:0;}}
        QPushButton#iconButton::menu-indicator {{width:0;}}
        QPushButton#quiet {{background:transparent;border:0;color:{c['muted']};padding:5px 0;}}
        QPushButton#quiet:hover {{color:{c['text']};}}
        QPushButton#windowButton {{background:transparent;border:0;border-radius:7px;padding:0;font-family:'Segoe UI';font-size:15px;}}
        QPushButton#windowButton:hover {{background:{c['raised']};}}
        QPushButton#closeButton {{background:transparent;border:0;border-radius:7px;padding:0;font-size:20px;}}
        QPushButton#closeButton:hover {{background:#ac4055;color:white;}}
        QPushButton#deleteGroup {{color:{c['danger']};}}
        QPushButton#catalogRow {{background:transparent;border:0;text-align:left;padding:12px;}}
        QPushButton#catalogRow:checked {{background:{c["selection"]};}}
        QPushButton#catalogRow:focus {{border:1px solid {c["accent"]};}}
        QPushButton#segment {{background:transparent;border:0;padding:7px 10px;color:{c['muted']};}}
        QPushButton#segment:checked {{background:{c['selection']};color:{c['text']};}}
        QLineEdit,QComboBox,QSpinBox,QKeySequenceEdit {{background:{c['field']};border:0;border-radius:6px;padding:7px;selection-background-color:{c['selection']};}}
        QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QKeySequenceEdit:focus {{border:1px solid {c['muted']};}}
        QFrame#settingRow QSpinBox,QFrame#settingRow QComboBox {{background:transparent;}}
        QFrame#settingRow QComboBox:hover,QFrame#settingRow QSpinBox:hover {{background:{c['raised']};}}
        QLineEdit#groupName {{background:transparent;border:0;font-size:18px;padding:3px 0;}}
        QPlainTextEdit {{background:{c['field']};border:0;border-radius:10px;padding:14px;selection-background-color:{c['selection']};}}
        QComboBox::drop-down {{border:0;width:22px;}}
        QComboBox::down-arrow {{image:none;}}
        QSpinBox::up-button,QSpinBox::down-button {{background:transparent;border:0;width:18px;}}
        QSpinBox::up-button:hover,QSpinBox::down-button:hover {{background:{c['raised']};}}
        QComboBox QAbstractItemView {{background:{c['raised']};color:{c['text']};selection-background-color:{c['selection']};padding:6px;border:1px solid {c['line']};}}
        QListWidget {{background:{c['field']};border:0;border-radius:10px;padding:5px;outline:0;}}
        QListWidget#navigation {{background:transparent;border:0;padding:0;}}
        QListWidget::item {{padding:8px;border-radius:7px;}}
        QListWidget::item:selected {{background:{c['selection']};color:{c['text']};}}
        QTabWidget::pane {{border:0;}}
        QTabBar::tab {{background:transparent;color:{c['muted']};padding:7px 10px;margin:0 4px 6px 0;border-radius:6px;}}
        QTabBar::tab:selected {{background:{c['selection']};color:{c['text']};}}
        QSlider::groove:horizontal {{height:4px;background:{c['line']};border-radius:2px;}}
        QSlider::sub-page:horizontal {{background:{c['accent']};border-radius:2px;}}
        QSlider::handle:horizontal {{width:13px;margin:-5px 0;background:{c['text']};border-radius:6px;}}
        QScrollArea {{border:0;background:transparent;}}
        QScrollBar:vertical {{width:5px;background:transparent;margin:0;}}
        QScrollBar::handle:vertical {{background:{c['line']};border-radius:2px;min-height:25px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {{background:transparent;}}
        QProgressBar {{background:{c['field']};border:0;border-radius:3px;min-height:6px;max-height:6px;}}
        QProgressBar::chunk {{background:{c['accent']};border-radius:3px;}}
    """
