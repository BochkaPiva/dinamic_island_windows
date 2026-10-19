# SPDX-License-Identifier: GPL-3.0-only
from PySide6.QtCore import Qt,QRectF,Signal
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel
from .window_layouts import zones,list_windows,place_window


from .settings_navigation import SettingsCombo as QComboBox

class ZonePicker(QWidget):
    selected=Signal(int)
    def __init__(self):
        super().__init__()
        self.preset='halves'
        self.hover=-1
        self.setFixedHeight(150)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Выбери зону для окна. Стрелки — выбор, Enter — разместить.')

    def rectangles(self):
        return [QRectF(*r) for r in zones((0,0,self.width(),self.height()),self.preset,6)]

    def mouseMoveEvent(self,event):
        self.hover=next((i for i,r in enumerate(self.rectangles()) if r.contains(event.position())),-1)
        self.update()

    def leaveEvent(self,event):
        self.hover=-1;self.update()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            for i,r in enumerate(self.rectangles()):
                if r.contains(event.position()): self.selected.emit(i);break

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self.hover=(self.hover+(1 if event.key()==Qt.Key.Key_Right else -1))%len(self.rectangles());self.update()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Space): self.selected.emit(max(0,self.hover))
        else: super().keyPressEvent(event)

    def paintEvent(self,event):
        c=self.window().colors
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i,r in enumerate(self.rectangles()):
            p.setBrush(QColor(c['selection'] if i==self.hover else c['raised']))
            p.setPen(QPen(QColor(c['accent'] if i==self.hover else c['line']),2 if i==self.hover else 1))
            p.drawRoundedRect(r,12,12)
            p.setPen(QColor(c['text']))
            p.drawText(r,Qt.AlignmentFlag.AlignCenter,str(i+1))
        p.end()


class WindowLayoutPanel(QWidget):
    def __init__(self):
        super().__init__()
        root=QVBoxLayout(self);root.setContentsMargins(0,14,0,14);root.setSpacing(14)
        row=QHBoxLayout();self.windows=QComboBox();self.windows.setMinimumWidth(0)
        self.windows.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.windows.setMinimumContentsLength(15)
        self.windows.setAccessibleName('Окно для размещения')
        row.addWidget(self.windows,1)
        refresh=QPushButton('Обновить');refresh.clicked.connect(self.reload);row.addWidget(refresh)
        root.addLayout(row)
        self.preset=QComboBox()
        for title,key in (('Две половины','halves'),('Три колонки','thirds'),('Широкая и узкая · 60/40','wide')): self.preset.addItem(title,key)
        self.preset.setAccessibleName('Раскладка окна')
        root.addWidget(self.preset)
        self.picker=ZonePicker();root.addWidget(self.picker)
        self.status=QLabel('')
        self.status.setObjectName('secondary');self.status.setWordWrap(True);root.addWidget(self.status)
        self.preset.currentIndexChanged.connect(self.change_preset)
        self.picker.selected.connect(self.place)
        self.loaded=False

    def showEvent(self,event):
        super().showEvent(event)
        if not self.loaded: self.reload()

    def reload(self):
        old=self.windows.currentData()
        self.windows.clear()
        for window in list_windows(): self.windows.addItem(window.title,window)
        if old:
            for i in range(self.windows.count()):
                if self.windows.itemData(i).hwnd==old.hwnd: self.windows.setCurrentIndex(i);break
        self.loaded=True
        if not self.windows.count(): self.status.setText('Нет доступных окон. Открой приложение и обнови список.')

    def change_preset(self):
        self.picker.preset=self.preset.currentData();self.picker.hover=-1;self.picker.update()

    def place(self,index):
        window=self.windows.currentData()
        if not window: self.status.setText('Сначала выбери окно.');return
        try: ok,message=place_window(window,self.preset.currentData(),index)
        except OSError: ok,message=False,'Не удалось обратиться к окну. Обнови список и попробуй ещё раз.'
        self.status.setText(message)
