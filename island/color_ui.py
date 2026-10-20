# SPDX-License-Identifier: GPL-3.0-only
"""Keyboard/mouse HSV wheel with exact RGB/HEX entry and transactional preview."""
import math
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QTimer
from PySide6.QtGui import QColor,QPainter,QPen,QConicalGradient,QRadialGradient,QPainterPath,QRegion
from PySide6.QtWidgets import QWidget,QPushButton,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QSpinBox,QLineEdit,QSlider
from .island_material import Appearance,valid_color,smoke_color
from .style import font


class ColorWheel(QWidget):
    colorChanged=Signal(QColor)
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(240,240)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus);self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName('Цветовой круг. Влево и вправо — тон, вверх и вниз — насыщенность.')
        self.hue=0.;self.saturation=0.;self.value=0.
    def set_color(self,color):
        hue,saturation,value,_=QColor(color).getHsvF()
        if hue>=0:self.hue=hue
        self.saturation=saturation;self.value=value;self.update()
    def disk(self):return QRectF(self.rect()).adjusted(9,9,-9,-9)
    def select(self,point):
        box=self.disk();dx=point.x()-box.center().x();dy=box.center().y()-point.y()
        self.hue=math.atan2(dy,dx)/(2*math.pi)%1
        self.saturation=min(1.,math.hypot(dx,dy)/(box.width()/2))
        if self.value<.001:self.value=1.
        self.colorChanged.emit(QColor.fromHsvF(self.hue,self.saturation,self.value));self.update()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.setFocus();self.select(event.position());event.accept()
    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.MouseButton.LeftButton:self.select(event.position());event.accept()
    def keyPressEvent(self,event):
        step=.03 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else .01
        if event.key()==Qt.Key.Key_Left:self.hue=(self.hue-step)%1
        elif event.key()==Qt.Key.Key_Right:self.hue=(self.hue+step)%1
        elif event.key()==Qt.Key.Key_Up:self.saturation=min(1.,self.saturation+step)
        elif event.key()==Qt.Key.Key_Down:self.saturation=max(0.,self.saturation-step)
        else:super().keyPressEvent(event);return
        if self.value<.001:self.value=1.
        self.colorChanged.emit(QColor.fromHsvF(self.hue,self.saturation,self.value));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);box=self.disk()
        hue=QConicalGradient(box.center(),0)
        for i in range(7):hue.setColorAt(i/6,QColor.fromHsvF((i/6)%1,1.,1.))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(hue);p.drawEllipse(box)
        saturation=QRadialGradient(box.center(),box.width()/2)
        saturation.setColorAt(0,QColor('white'));saturation.setColorAt(1,QColor(255,255,255,0))
        p.setBrush(saturation);p.drawEllipse(box)
        angle=self.hue*2*math.pi;r=box.width()/2*self.saturation
        point=box.center()+QPointF(math.cos(angle)*r,-math.sin(angle)*r)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#111111'),5));p.drawEllipse(point,6,6)
        p.setPen(QPen(QColor('white'),2));p.drawEllipse(point,6,6)
        if self.hasFocus():
            p.setPen(QPen(QColor(self.window().colors['muted']),1,Qt.PenStyle.DashLine));p.drawEllipse(box.adjusted(-5,-5,5,5))


class ColorButton(QPushButton):
    def __init__(self,callback):
        super().__init__();self.color='#000000';self.locked=False;self.setFixedSize(188,38)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setAccessibleName('Цвет стекла');self.clicked.connect(callback)
    def set_color(self,color,locked=False):
        self.color=color;self.locked=locked;self.setAccessibleDescription('Подписчикам' if locked else color);self.update()
    def paintEvent(self,event):
        c=self.window().colors;p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(c['muted'] if self.hasFocus() else c['line']),1));p.setBrush(QColor(c['raised']))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1,1,-1,-1),9,9)
        p.setPen(QPen(QColor(c['muted']),.7));p.setBrush(QColor(self.color));p.drawEllipse(QRectF(12,10,18,18))
        p.setFont(font(12));p.setPen(QColor(c['muted'] if self.locked else c['text']))
        p.drawText(QRectF(40,0,self.width()-50,self.height()),Qt.AlignmentFlag.AlignVCenter,'Подписчикам' if self.locked else self.color)


class IslandColorDialog(QDialog):
    def __init__(self,center):
        super().__init__(center,Qt.WindowType.Dialog|Qt.WindowType.FramelessWindowHint)
        self.center=center;self.owner=center.owner;self.colors=center.colors;self.material=False
        self.color=QColor(self.owner.settings.get('island_color'));self._syncing=False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.setWindowTitle('Цвет стекла');self.setFixedWidth(600)
        from .hub_ui import stylesheet
        self.setStyleSheet(stylesheet(self.colors)+'QDialog {background:transparent;}')
        root=QVBoxLayout(self);root.setContentsMargins(24,18,24,18);root.setSpacing(14)
        title=QLabel('Цвет стекла');title.setObjectName('paneTitle');root.addWidget(title)
        columns=QHBoxLayout();columns.setSpacing(22);root.addLayout(columns)
        self.wheel=ColorWheel();columns.addWidget(self.wheel)
        controls=QVBoxLayout();controls.setSpacing(10);columns.addLayout(controls,1)
        from .module_preview import FormPreview
        self.preview=FormPreview(self.owner,'floating' if self.owner.floating_mode() else 'notch');self.preview.setFixedHeight(82);controls.addWidget(self.preview)
        controls.addWidget(QLabel('Яркость оттенка'))
        self.brightness=QSlider(Qt.Orientation.Horizontal);self.brightness.setRange(0,1000);self.brightness.setAccessibleName('Яркость оттенка');controls.addWidget(self.brightness)
        rgb=QHBoxLayout();rgb.setSpacing(6);self.rgb=[]
        for channel in 'RGB':
            column=QVBoxLayout();label=QLabel(channel);label.setAlignment(Qt.AlignmentFlag.AlignCenter);column.addWidget(label)
            value=QSpinBox();value.setRange(0,255);value.setKeyboardTracking(False);value.setAccessibleName(channel);column.addWidget(value);rgb.addLayout(column);self.rgb.append(value)
            value.valueChanged.connect(self.rgb_changed)
        controls.addLayout(rgb)
        self.hex=QLineEdit();self.hex.setMaxLength(7);self.hex.setPlaceholderText('#RRGGBB');self.hex.setAccessibleName('HEX RGB');controls.addWidget(self.hex)
        self.hex.textEdited.connect(self.hex_changed);controls.addStretch()
        self.error=QLabel();self.error.setObjectName('secondary');self.error.setWordWrap(True);root.addWidget(self.error);self.error.hide()
        footer=QHBoxLayout();root.addLayout(footer)
        reset=QPushButton('Без оттенка');reset.clicked.connect(lambda:self.choose(QColor('#000000')));footer.addWidget(reset);footer.addStretch()
        cancel=QPushButton('Отмена');cancel.clicked.connect(self.reject);footer.addWidget(cancel)
        self.save_button=QPushButton('Применить');self.save_button.setObjectName('primary');self.save_button.clicked.connect(self.apply);footer.addWidget(self.save_button)
        self.wheel.colorChanged.connect(self.choose);self.brightness.valueChanged.connect(self.brightness_changed)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(34);self.preview_timer.timeout.connect(self.live_preview)
        self.choose(self.color)
        self.owner_ref=self.owner
        self.destroyed.connect(lambda:self.owner_ref.preview_island_color(None) if not self.owner_ref._closed else None)
    def choose(self,color):
        self.color=QColor(color);self._syncing=True;self.wheel.set_color(self.color)
        for value,number in zip(self.rgb,(self.color.red(),self.color.green(),self.color.blue())):value.setValue(number)
        self.brightness.setValue(round(self.color.valueF()*1000));self.hex.setText(self.color.name().upper());self._syncing=False
        self.save_button.setEnabled(True);self.error.hide()
        self.preview.appearance_override=Appearance(True,self.color.name());self.preview.update()
        if not self.preview_timer.isActive():self.preview_timer.start()
    def rgb_changed(self):
        if not self._syncing:self.choose(QColor(*(value.value() for value in self.rgb)))
    def brightness_changed(self,value):
        if not self._syncing:self.choose(QColor.fromHsvF(self.wheel.hue,self.wheel.saturation,value/1000))
    def hex_changed(self,value):
        if valid_color(value):self.choose(QColor(value))
        else:self.save_button.setEnabled(False)
    def live_preview(self):
        if not self.owner._closed:self.owner.preview_island_color(self.color.name().upper())
    def apply(self):
        if not valid_color(self.hex.text()):return
        if self.owner._toggle_setting('island_color',self.color.name().upper()):self.accept()
        else:self.error.setText('Цвет не сохранён. Проверь подключение к сообществу и доступность папки настроек.');self.error.show()
    def done(self,result):
        self.preview_timer.stop()
        if not self.owner._closed:self.owner.preview_island_color(None)
        super().done(result)
    def showEvent(self,event):
        super().showEvent(event)
        from .native_material import apply_acrylic
        self.material=apply_acrylic(self,light=QColor(self.colors['bg']).lightness()>128)
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()),18,18)
        if self.material:self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        self.wheel.setFocus()
    def paintEvent(self,event):
        from .optics import paint_surface
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);paint_surface(p,self,self.colors)
