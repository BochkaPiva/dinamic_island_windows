# SPDX-License-Identifier: GPL-3.0-only
"""Interactive workspace tiles. Shared models, no background media service."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QWidget,QGridLayout,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit
from .settings_navigation import SettingsSurface

class DashboardDeck(QWidget):
    def __init__(self,activate):
        super().__init__();self.panels=[];self.selected=0;self.activate=activate
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(14)
    def addWidget(self,panel):
        i=len(self.panels);self.panels.append(panel);self.grid.addWidget(panel,i//2,i%2)
        panel.installEventFilter(self)
    def currentIndex(self):return self.selected
    def count(self):return len(self.panels)
    def widget(self,index):return self.panels[index]
    def setCurrentIndex(self,index):
        self.selected=index
        for i,panel in enumerate(self.panels):panel.setProperty('active',i==index);panel.update()
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Enter and obj in self.panels:self.activate(self.panels.index(obj))
        return super().eventFilter(obj,event)

class SearchDemo(SettingsSurface):
    def __init__(self,center):
        super().__init__();self.setObjectName('card')
        root=QVBoxLayout(self);root.setContentsMargins(18,14,18,14);root.setSpacing(4)
        self.input=QLineEdit();self.input.setPlaceholderText('Попробуй: остров, заметки, таймер')
        self.input.setAccessibleName('Предпросмотр команд поиска');root.addWidget(self.input)
        self.commands=[]
        from .hub_ui import icon
        for title,key,glyph in (('Остров','island','island'),('Заметки','library','note'),('Таймер','timer','timer')):
            control=QPushButton(title);control.setIcon(icon(glyph));control.setObjectName('demoResult')
            control.clicked.connect(lambda _,k=key:center.navigate(k));root.addWidget(control)
            self.commands.append((title.casefold(),control))
        self.empty=QLabel('Нет такой команды');self.empty.setObjectName('secondary');self.empty.hide();root.addWidget(self.empty)
        self.input.textChanged.connect(self.filter)
        self.input.returnPressed.connect(self.open_first)
    def filter(self,value):
        value=value.casefold().strip();count=0
        for title,control in self.commands:
            visible=value in title;control.setVisible(visible);count+=visible
        self.empty.setVisible(not count)
    def open_first(self):
        for _,control in self.commands:
            if not control.isHidden():control.click();return
