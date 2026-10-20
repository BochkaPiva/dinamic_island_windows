# SPDX-License-Identifier: GPL-3.0-only
"""Nelviro: native, local module settings and optional PowerToys integration."""
import ctypes
import os
from pathlib import Path
import time
import winreg
from PySide6.QtCore import Qt, QTimer, QUrl, QRectF,QEvent
from PySide6.QtGui import QDesktopServices,QPainter,QPainterPath,QRegion,QColor,QPen,QShortcut,QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QListWidget, QStackedWidget, QFrame, QScrollArea, QComboBox,QLineEdit,QMenu)
from . import __version__, REPO_URL
from .integrations import load_workspaces, powertoys_root
from .policy import PROFILES
from .style import app_icon
from .settings_pages import SettingsPages, PAGES
from .modules import MODULES
from .hub_ui import Navigation,ContentTransition,ToggleSwitch,WindowHeader,ActionFooter,palette,stylesheet,icon
from .style import font


def text(value, secondary=False):
    label = QLabel(value)
    label.setWordWrap(True)
    if secondary:
        label.setObjectName("secondary")
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def button(title, callback):
    widget = QPushButton(title)
    widget.clicked.connect(callback)
    return widget


def section(layout, title, detail=""):
    heading = text(title)
    heading.setObjectName("heading")
    layout.addWidget(heading)
    if detail:
        layout.addWidget(text(detail, True))


class ProcessUsage:
    def __init__(self):
        self.last = None

    def sample(self):
        class Times(ctypes.Structure):
            _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]
            @property
            def number(self):
                return self.low+(self.high << 32)
        class Memory(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("peak", "working", "quota_peak_paged",
                "quota_paged", "quota_peak_nonpaged", "quota_nonpaged", "pagefile", "peak_pagefile")]
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        handle = ctypes.c_void_p(kernel.GetCurrentProcess())
        creation, end, system, user = Times(), Times(), Times(), Times()
        memory = Memory()
        memory.size = ctypes.sizeof(memory)
        if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(end),
                                      ctypes.byref(system), ctypes.byref(user)):
            return "Нагрузка временно недоступна"
        getter = ctypes.windll.psapi.GetProcessMemoryInfo
        getter.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        if not getter(handle, ctypes.byref(memory), memory.size):
            return "Память временно недоступна"
        now, cpu = time.monotonic(), (system.number+user.number)/10_000_000
        percent = None if self.last is None else 100*(cpu-self.last[1])/max(.01, now-self.last[0])/(os.cpu_count() or 1)
        self.last = now, cpu
        return f"{memory.working/1024**2:.0f} МБ RAM · " + (f"{percent:.2f}% CPU" if percent is not None else "измеряю CPU…")


class ControlCenter(QWidget, SettingsPages):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowTitle("Nelviro")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600)
        self.resize(1120, 760)
        self.usage = ProcessUsage()
        self._workspace_ids = []
        self.subpages=[]
        self.setting_search_entries=[]
        self.active_detail=None
        self.extra_key_editors=[]
        self.header_switches={}
        self._apply_theme()
        self.outer=QVBoxLayout(self)
        layout=self.outer
        layout.setContentsMargins(6,6,6,6)
        layout.setSpacing(0)
        titlebar=WindowHeader(self)
        titlebar.setFixedHeight(38)
        header = QHBoxLayout()
        titlebar.setLayout(header)
        header.setContentsMargins(12,0,6,0)
        brand_icon=QLabel()
        brand_icon.setPixmap(app_icon().pixmap(24,24))
        header.addWidget(brand_icon)
        title = text("Nelviro")
        title.setObjectName("brand")
        header.addWidget(title)
        subtitle = text("", True)
        subtitle.setObjectName('eyebrow')
        subtitle.setWordWrap(False)
        header.addSpacing(16)
        header.addWidget(subtitle)
        header.addStretch()
        for label,tip,callback,name in (('−','Свернуть',self.showMinimized,'windowButton'),
            ('□','Развернуть',self.toggle_maximized,'windowButton'),('×','Скрыть в трей',self.close,'closeButton')):
            control=button(label,callback)
            control.setObjectName(name)
            control.setFixedSize(34,30)
            control.setAccessibleName(tip)
            control.setToolTip(tip)
            header.addWidget(control)
        layout.addWidget(titlebar)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar=QFrame()
        self.sidebar=sidebar
        self.sidebar_collapsed=False
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(218)
        side=QVBoxLayout(sidebar)
        side.setContentsMargins(10,14,10,10)
        side.setSpacing(10)
        self.collapse_navigation=button('',self.toggle_sidebar)
        self.collapse_navigation.setIcon(icon('windows',self.colors['muted'],16))
        self.collapse_navigation.setFixedSize(28,28)
        self.collapse_navigation.setObjectName('quiet')
        self.collapse_navigation.setAccessibleName('Свернуть боковую панель')
        header.insertWidget(0,self.collapse_navigation)
        self.settings_search=QLineEdit()
        self.settings_search.setPlaceholderText('Найти настройку…')
        self.settings_search.setAccessibleName('Поиск раздела настроек')
        self.search_action=self.settings_search.addAction(icon('search'),QLineEdit.ActionPosition.LeadingPosition)
        self.settings_search.setClearButtonEnabled(True)
        side.addWidget(self.settings_search)
        self.navigation = Navigation()
        for key,label,_ in PAGES:
            self.navigation.addItem(label)
            self.navigation.item(self.navigation.count()-1).setData(Qt.ItemDataRole.UserRole,key)
            self.navigation.item(self.navigation.count()-1).setToolTip(label)
            self.navigation.item(self.navigation.count()-1).setHidden(key in {'shortcuts','updates'})
        self.navigation.setObjectName("navigation")
        self.pages = QStackedWidget()
        self.transition=ContentTransition(self.pages)
        side.addWidget(self.navigation,1)
        self.search_empty=text('Ничего не найдено',True)
        self.search_empty.hide()
        side.addWidget(self.search_empty)
        self.pause_button=button('Приостановить',self._pause)
        side.addWidget(self.pause_button)
        version=button(f'Nelviro  {__version__}',lambda:self.navigate('updates'))
        self.version_button=version
        version.setObjectName('quiet')
        side.addWidget(version)
        body.addWidget(sidebar)
        content=QVBoxLayout()
        content.setContentsMargins(30,16,24,0)
        content.setSpacing(12)
        self.section_title=text('Главная')
        self.section_title.setObjectName('heading')
        page_header=QHBoxLayout()
        self.back_button=button('‹',lambda:self.travel(-1))
        self.forward_button=button('›',lambda:self.travel(1))
        for control,label in ((self.back_button,'Назад · Alt+←'),(self.forward_button,'Вперёд · Alt+→')):
            control.setObjectName('windowButton');control.setFixedSize(26,28)
            control.setAccessibleName(label);control.setToolTip(label);page_header.addWidget(control)
        page_header.addSpacing(6)
        page_header.addWidget(self.section_title,1)
        self.page_action=button('Открыть',self.run_page_action)
        self.page_action.setObjectName('quiet')
        self.page_action.setFixedWidth(28)
        self.help_button=button('',self.show_page_help)
        self.help_button.setIcon(icon('info',self.colors['muted'],18))
        self.help_button.setObjectName('windowButton');self.help_button.setFixedSize(28,30)
        self.help_button.setAccessibleName('О разделе');page_header.addWidget(self.help_button)
        page_header.addWidget(self.page_action)
        self.master_slot=QHBoxLayout();self.master_slot.setContentsMargins(8,0,0,0)
        page_header.addLayout(self.master_slot)
        content.addLayout(page_header)
        self.page_deck=QStackedWidget()
        self.page_deck.addWidget(self.pages)
        self.transition.setParent(self.page_deck)
        from .scrolling import SmoothScrollArea
        self.detail_scroll=SmoothScrollArea();self.detail_scroll.setWidgetResizable(True)
        self.detail_host=QWidget();self.detail_layout=QVBoxLayout(self.detail_host)
        self.detail_layout.setContentsMargins(0,0,0,0)
        self.detail_scroll.setWidget(self.detail_host)
        self.page_deck.addWidget(self.detail_scroll)
        content.addWidget(self.page_deck,1)
        body.addLayout(content,1)
        layout.addLayout(body, 1)
        self.checks = {}
        self.values = {}
        self.sliders = {}
        self.page_indices = {key:i for i,(key,_,_) in enumerate(PAGES)}
        self.feedback = QLabel(self)
        self.feedback.setObjectName('toast')
        self.feedback.setWordWrap(True)
        self.feedback.setMaximumWidth(440)
        self.feedback.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.feedback.hide()
        self.toast_timer=QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.feedback.hide)
        for _,_,factory in PAGES:
            getattr(self,factory)()
        self.navigation.currentRowChanged.connect(self.select_page)
        self.navigation.itemClicked.connect(lambda _:self.navigate(PAGES[self.navigation.currentRow()][0]) if self.active_detail else None)
        self.navigation.setCurrentRow(0)
        self.settings_search.textChanged.connect(self.filter_pages)
        self.settings_search.returnPressed.connect(self.open_first_match)
        QShortcut(QKeySequence('Ctrl+F'),self,activated=self.focus_settings_search)
        self.action_footer=ActionFooter()
        self.resource_label=self.action_footer.context
        self.resource_label.setText('')
        self.shortcut_label=QLabel('')
        self.shortcut_label.hide()
        self.action_footer.add_action('Найти',('Ctrl','F'),self.focus_settings_search)
        self.action_footer.add_action('Действия',('Ctrl','K'),self.show_page_actions)
        layout.addWidget(self.action_footer)
        QShortcut(QKeySequence('Ctrl+K'),self,activated=self.show_page_actions)
        QShortcut(QKeySequence('Alt+Left'),self,activated=lambda:self.travel(-1))
        QShortcut(QKeySequence('Alt+Right'),self,activated=lambda:self.travel(1))
        self._history=[(self.navigation.currentRow(),None)];self._history_index=0
        self._travelling=False
        self.update_page_action()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(3000)
        self.refresh_timer.timeout.connect(self.refresh)
        owner.powertoys.changed.connect(self.refresh)
        owner.powertoys.message.connect(self._message)
        owner.updates.changed.connect(lambda _:self.navigation.viewport().update())
        self._apply_theme()

    def page_action_spec(self):
        key=PAGES[max(0,self.navigation.currentRow())][0]
        return {
            'hub':('Открыть остров',self.owner._show_panel),
            'island':('Открыть остров',self.owner._show_panel),
            'search':('Открыть поиск',self.owner.show_search),
            'desktop':('Выровнять группы',self.owner.modules.desktop.arrange),
            'library':('Добавить файлы',self.file_shelf.add_files),
            'timer':('Открыть фокус',self.open_focus),
            'shortcuts':('Открыть поиск',self.owner.show_search),
            'workspaces':('Обновить окна',self.window_layout.reload),
            'integrations':('Папка данных',lambda:self._url(QUrl.fromLocalFile(str(self.owner.settings.directory)))),
            'updates':('Открыть GitHub',lambda:self._url(QUrl(REPO_URL))),
            'account':('Открыть канал',lambda:self._url(QUrl('https://t.me/Nelviro'))),
        }.get(key,('Открыть остров',self.owner._show_panel))

    def show_page_help(self):
        from PySide6.QtWidgets import QMessageBox
        key=PAGES[max(0,self.navigation.currentRow())][0]
        help_text={
            'hub':'Выбери модуль для предпросмотра. Двойной щелчок открывает его настройки. Переключатели включают модули, профиль управляет их работой.',
            'island':'Форма меняется сразу. Плавающий остров доступен подписчикам. В остальных разделах можно отдельно настроить размеры, звук и содержимое.',
            'search':'Вводи имя приложения, файла или путь. Enter открывает выбранное, Ctrl+K показывает действия. Для файлов используется индекс Windows.',
            'desktop':'Выбери группу слева. Название редактируется сверху; Enter сохраняет. Добавляй файлы кнопкой или перетаскиванием. Удаление группы не удаляет оригиналы. Ярлыки Nelviro сохраняет в своей библиотеке.',
            'library':'Файлы хранятся как ссылки на оригиналы. Заметки сохраняются автоматически на этом компьютере. Быстрая заметка общая с островом.',
            'timer':'Введи минуты прямо в цифры или используй колесо. Enter применяет, Esc отменяет. Отсчёт продолжается при скрытом окне.',
            'workspaces':'Выбери окно и нажми зону. Окно изменит положение и размер. Рабочие наборы и зоны при перетаскивании подключаются через PowerToys.',
            'shortcuts':'Нажми сочетание и введи новое. Используй Ctrl, Alt или Win с клавишей. Конфликтующие сочетания не заменят действующие.',
            'integrations':'Настройки применяются сразу. Данные находятся на этом компьютере; автозапуск открывает трей и включённые модули.',
            'updates':'Проверка ищет новую версию. После загрузки проверяется контрольная сумма; установка создаёт резервную копию и перезапускает приложение.',
            'account':'Подписка на канал открывает плавающий остров, дополнительные группы, видеофайлы, камеру и закрепление. Проверка раз в 6 часов; последнее подтверждение действует до 72 часов без интернета.'}
        QMessageBox.information(self,self.section_title.text(),help_text.get(key,''))

    def update_page_action(self):
        if hasattr(self,'action_footer'):
            title,_=self.page_action_spec();self.page_action.setText('↗')
            self.page_action.setAccessibleName(title);self.page_action.setToolTip(title)
            self.back_button.setEnabled(self._history_index>0 or self.active_detail is not None)
            self.forward_button.setEnabled(self._history_index<len(self._history)-1)
            self.action_footer.context.setText('')
            current=PAGES[max(0,self.navigation.currentRow())][0]+'_enabled'
            for key,control in self.header_switches.items():control.setVisible(key==current and self.active_detail is None)

    def record_route(self):
        if not hasattr(self,'_history') or self._travelling:return
        route=(self.navigation.currentRow(),self.active_detail)
        if self._history[self._history_index]==route:return
        self._history=self._history[:self._history_index+1]+[route]
        self._history_index=len(self._history)-1

    def close_detail(self):
        if self.active_detail:
            self.active_detail.body.hide();self.active_detail.body.setParent(self)
            self.active_detail=None
        self.page_deck.setCurrentIndex(0)
        self.section_title.setText(PAGES[max(0,self.navigation.currentRow())][1])

    def open_detail(self,section):
        old=self.page_deck.grab() if self.isVisible() else None
        self.transition.animation.stop();self.transition.done()
        self.close_detail()
        self.active_detail=section
        self.detail_layout.addWidget(section.body)
        section.body.show()
        self.page_deck.setCurrentIndex(1)
        self.section_title.setText(section.title)
        self.detail_scroll.verticalScrollBar().setValue(0)
        self.record_route();self.update_page_action()
        section.body.setFocusPolicy(Qt.FocusPolicy.StrongFocus);section.body.setFocus()
        if old is not None and self.owner.settings.get('hub_animations'):
            self.transition.start(old,self.page_deck.grab())

    def run_page_action(self):
        self.page_action_spec()[1]()

    def show_page_actions(self):
        menu=QMenu(self)
        title,callback=self.page_action_spec();menu.addAction(title,callback)
        menu.addSeparator()
        menu.addAction('Найти настройку',self.focus_settings_search).setShortcut(QKeySequence('Ctrl+F'))
        menu.addAction('Горячие клавиши',lambda:self.navigate('shortcuts'))
        menu.addAction('Приостановить / продолжить',self._pause)
        menu.exec(self.page_action.mapToGlobal(self.page_action.rect().bottomLeft()))

    def travel(self,step):
        index=self._history_index+step
        if 0<=index<len(self._history):
            self._history_index=index;self._travelling=True
            row,detail=self._history[index]
            self.close_detail();self.settings_search.clear()
            self.navigation.setCurrentRow(row)
            if detail:self.open_detail(detail)
            self._travelling=False;self.update_page_action()
        elif step<0 and self.active_detail:
            self.close_detail();self.record_route();self.update_page_action()

    def focus_settings_search(self):
        if self.sidebar_collapsed: self.toggle_sidebar()
        self.settings_search.setFocus()

    def toggle_sidebar(self):
        self.sidebar_collapsed=not self.sidebar_collapsed
        self.sidebar.setFixedWidth(54 if self.sidebar_collapsed else 218)
        self.navigation.setProperty('collapsed',self.sidebar_collapsed)
        self.navigation.viewport().update()
        self.settings_search.setVisible(not self.sidebar_collapsed)
        self.pause_button.setVisible(not self.sidebar_collapsed)
        self.version_button.setVisible(not self.sidebar_collapsed)
        self.collapse_navigation.setToolTip('Развернуть меню' if self.sidebar_collapsed else 'Свернуть меню')
        self.collapse_navigation.setAccessibleName('Развернуть боковую панель' if self.sidebar_collapsed else 'Свернуть боковую панель')

    def navigate(self,key):
        if self.settings_search.text(): self.settings_search.clear()
        self.close_detail()
        index=self.page_indices.get(key,0)
        self.navigation.setCurrentRow(index)
        self.record_route();self.update_page_action()

    def select_page(self,index):
        if index<0 or index==self.pages.currentIndex(): return
        old=self.page_deck.grab() if self.isVisible() else None
        self.transition.animation.stop()
        self.transition.hide()
        self.section_title.setText(PAGES[index][1])
        self.close_detail()
        self.record_route()
        self.update_page_action()
        self.pages.setCurrentIndex(index)
        self.pages.currentWidget().ensurePolished()
        if self.pages.currentWidget().layout(): self.pages.currentWidget().layout().activate()
        if old is not None and self.owner.settings.get('hub_animations'):
            self.transition.start(old,self.page_deck.grab())

    def index_setting(self,title,layout,control,detail=''):
        parent=layout.parentWidget()
        detail_page=next((section for section in self.subpages if section.body==parent or section.body.isAncestorOf(parent)),None) if parent else None
        self.setting_search_entries.append((title+' '+detail,self.pages.count()-1,detail_page,control))

    def filter_pages(self,value):
        synonyms={'island':'чёлка челка музыка прозрачность эквалайзер', 'desktop':'группы папки ярлыки прозрачность',
            'integrations':'автозапуск тема оформление анимации powertoys', 'updates':'обновление установить скачать версия',
            'timer':'таймер минуты фокус звук','library':'заметки файлы текст','shortcuts':'клавиши сочетания хоткей'}
        count=0
        for i,(key,label,_) in enumerate(PAGES):
            visible=value.casefold().strip() in (label+' '+synonyms.get(key,'')+' '+' '.join(entry[0] for entry in self.setting_search_entries if entry[1]==i)+' '+' '.join(section.title for section in self.subpages if section.parent_index==i)).casefold()
            if not value.strip() and key in {'shortcuts','updates'}:visible=False
            self.navigation.item(i).setHidden(not visible)
            count+=visible
        self.search_empty.setVisible(not count)

    def open_first_match(self):
        query=self.settings_search.text().strip().casefold()
        exact=next((key for key,label,_ in PAGES if query==label.casefold()),None)
        exact=exact or {'таймер':'timer','чёлка':'island','челка':'island','заметки':'library','группы':'desktop','обновление':'updates'}.get(query)
        if exact:self.navigate(exact);return
        matches=[entry for entry in self.setting_search_entries if query and query in entry[0].casefold()]
        if matches:
            _,row,section,control=matches[0]
            self.navigate(PAGES[row][0])
            if section:self.open_detail(section)
            scroll=self.detail_scroll if section else self.pages.currentWidget()
            scroll.ensureWidgetVisible(control);control.setFocus()
            return
        section=next((section for section in self.subpages if query and query in section.title.casefold()),None)
        if section:
            self.navigate(PAGES[section.parent_index][0]);self.open_detail(section);return
        for i in range(self.navigation.count()):
            if not self.navigation.item(i).isHidden():
                self.navigate(PAGES[i][0]);self.pages.setFocus();return

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()) if self.isMaximized() else QRectF(self.rect()).adjusted(5,5,-5,-5)
        radius=0 if self.isMaximized() else 12
        outline=QPainterPath();outline.addRoundedRect(rect,radius,radius)
        p.setClipPath(outline)
        base=QColor(self.colors['bg'])
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        base.setAlpha(94 if getattr(self,'material',False) else 255)
        p.fillPath(outline,base)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if getattr(self,'material',False):
            from .optics import light_field
            dpr=self.devicePixelRatioF()
            p.setOpacity(.18)
            p.drawImage(0,0,light_field(round(self.width()*dpr),round(self.height()*dpr),dpr,QColor(self.colors['bg']).lightness()>128))
            p.setOpacity(1)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(self.colors['line']),1))
        p.drawRoundedRect(rect,radius,radius)
        p.drawLine(6,44,self.width()-6,44)
        if hasattr(self,'sidebar'):
            x=self.sidebar.geometry().right()
            p.drawLine(x,44,x,self.height()-6)

    def refresh_material(self):
        from .native_material import apply_acrylic
        self.material=apply_acrylic(self,light=self.owner.settings.get('hub_theme')=='light' or self.colors['bg'].upper()=='#F5F5F5',tint_alpha=140)
        self.setStyleSheet(stylesheet(self.colors,glass=self.material))
        self.clip_material()
        self.update()

    def clip_material(self):
        if getattr(self,'material',False) and not self.isMaximized():
            path=QPainterPath();path.addRoundedRect(QRectF(self.rect()).adjusted(5,5,-5,-5),12,12)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        else:self.clearMask()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.clip_material()
        if hasattr(self,'transition'): self.transition.animation.stop(); self.transition.done()
        if hasattr(self,'feedback') and self.feedback.isVisible(): self.place_toast()

    def mouseMoveEvent(self,event):
        point=event.position()
        horizontal=point.x()<8 or point.x()>self.width()-8
        vertical=point.y()<8 or point.y()>self.height()-8
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if horizontal and vertical else Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor if vertical else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.isMaximized(): return
        point=event.position()
        edges=Qt.Edge(0)
        if point.x()<8: edges|=Qt.Edge.LeftEdge
        if point.x()>self.width()-8: edges|=Qt.Edge.RightEdge
        if point.y()<8: edges|=Qt.Edge.TopEdge
        if point.y()>self.height()-8: edges|=Qt.Edge.BottomEdge
        if edges and self.windowHandle(): self.windowHandle().startSystemResize(edges)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:
            if self.active_detail:self.travel(-1)
            elif self.settings_search.text():self.settings_search.clear()
            else:self.close()
        else: super().keyPressEvent(event)


    def _page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 12, 4)
        layout.setSpacing(12)
        from .scrolling import SmoothScrollArea
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)
        return layout

    def _module(self, layout, key, name, detail):
        checkbox=ToggleSwitch(name);checkbox.setObjectName(key)
        checkbox.setToolTip(detail or name)
        checkbox.toggled.connect(lambda value,k=key:self._setting(k,value))
        self.checks[key]=checkbox
        self.index_setting(name,layout,checkbox,detail)
        if key in {'island_enabled','search_enabled','desktop_enabled'}:
            self.header_switches[key]=checkbox;self.master_slot.addWidget(checkbox);checkbox.hide()
            return
        frame=QFrame();frame.setObjectName('settingRow');frame.setMinimumHeight(52)
        row=QHBoxLayout(frame);row.setContentsMargins(0,7,0,7)
        label=text(name);label.setToolTip(detail);row.addWidget(label,1);row.addWidget(checkbox)
        layout.addWidget(frame)

    def _workspaces_page(self):
        from .window_layout_ui import WindowLayoutPanel
        layout=self._page();frame,inside=self.card('Расположение');layout.addWidget(frame)
        self.window_layout=WindowLayoutPanel();inside.addWidget(self.window_layout)
        frame,links=self.card('');layout.addWidget(frame)
        section,inside=self.fold('Рабочие наборы');links.addWidget(section)
        row=QHBoxLayout();row.addWidget(button('Создать',self._workspace_editor));row.addStretch();row.addWidget(button('Обновить',self._refresh_workspaces));inside.addLayout(row)
        self.workspaces=QListWidget();self.workspaces.setMinimumHeight(140);self.workspaces.itemDoubleClicked.connect(lambda _:self._launch_workspace());inside.addWidget(self.workspaces)
        self.launch_button=button('Запустить',self._launch_workspace);inside.addWidget(self.launch_button,0,Qt.AlignmentFlag.AlignLeft)
        self.workspace_empty=text('',True);inside.addWidget(self.workspace_empty);inside.addStretch()
        section,inside=self.fold('Зоны при перетаскивании');links.addWidget(section)
        frame,group=self.card('PowerToys');inside.addWidget(frame)
        self.link(group,'Открыть редактор зон',self._zones_editor)
        self.link(group,'Подключение',lambda:self.navigate('integrations'));inside.addStretch();layout.addStretch()

    def _setting(self, key, value):
        self.owner._toggle_setting(key,value)
        if key=='hub_theme': self._apply_theme()
        if key=='hub_animations' and not value: self.transition.animation.stop(); self.transition.done()
        self.refresh()

    def _pause(self):
        self._setting("paused", not self.owner.settings.get("paused"))

    def _connect(self):
        if not self.owner.powertoys.root:
            self._url(QUrl("https://learn.microsoft.com/windows/powertoys/install"))
            return
        if not self.owner.settings.get("manage_powertoys") and not self.owner.powertoys.new_connection():
            return
        self.owner.powertoys.launch("PowerToys.exe")
        self._setting("manage_powertoys", True)

    def _restore(self):
        if self.owner.powertoys.restore():
            self.owner.settings.set("manage_powertoys", False)
            self.refresh()

    def _workspace_editor(self):
        if self._require("workspaces_enabled"):
            self.owner.powertoys.launch("PowerToys.WorkspacesEditor.exe")

    def _zones_editor(self):
        if self._require("layouts_enabled"):
            self.owner.powertoys.launch("FancyZonesCLI.exe", ["open-editor"])

    def _require(self, key):
        policy = self.owner._policy
        active = policy.workspaces if key == "workspaces_enabled" else policy.layouts
        if not self.owner.settings.get("manage_powertoys") or not active:
            self._message("Подключи PowerToys и включи нужный модуль в рабочем профиле.")
            return False
        if self.owner.powertoys.busy:
            self._message("Дождись применения настроек PowerToys.")
            return False
        return True

    def _refresh_workspaces(self):
        items = load_workspaces()
        if items == getattr(self, "_workspace_items", None):
            return
        self._workspace_items = items
        self._workspace_ids = [item[0] for item in items]
        self.workspaces.clear()
        self.workspaces.addItems([f"{name} · приложений: {count}" for _, name, count in items])
        if items:
            self.workspaces.setCurrentRow(0)
        self.launch_button.setEnabled(bool(items))
        self.workspace_empty.setText("" if items else "Сохранённых наборов пока нет. Создай первый в редакторе Workspaces.")

    def _launch_workspace(self):
        row = self.workspaces.currentRow()
        if self._require("workspaces_enabled") and 0 <= row < len(self._workspace_ids):
            self.owner.powertoys.launch_workspace(self._workspace_ids[row])

    def _url(self, url):
        if not QDesktopServices.openUrl(url):
            self._message("Не удалось открыть настройки или ссылку")

    def _message(self, message):
        self.feedback.setText(message)
        if message:
            self.feedback.adjustSize()
            self.place_toast()
            self.feedback.show()
            self.feedback.raise_()
            self.toast_timer.start(3500)
        else: self.feedback.hide()

    def place_toast(self):
        self.feedback.move(max(230,self.width()-self.feedback.width()-25),max(20,self.height()-self.feedback.height()-44))

    def refresh(self):
        w = self.owner
        for key, checkbox in self.checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(w.settings.get(key))
            checkbox.blockSignals(False)
            checkbox.setEnabled(key not in {"layouts_enabled", "workspaces_enabled"} or w.settings.get("manage_powertoys"))
        for key,widget in self.values.items():
            if widget.hasFocus(): continue
            widget.blockSignals(True)
            widget.setValue(w.settings.get(key))
            widget.blockSignals(False)
        for key,widget in self.sliders.items():
            if widget.isSliderDown(): continue
            widget.blockSignals(True)
            widget.setValue(w.settings.get(key))
            widget.blockSignals(False)
        self.screen_picker.blockSignals(True)
        self.screen_picker.setCurrentIndex(max(0,self.screen_picker.findData(w.settings.get("monitor"))))
        self.screen_picker.blockSignals(False)
        for key, widget in self.profile_buttons.items():
            widget.setChecked(w.settings.get("profile") == key)
        self.pause_button.setText("Возобновить" if w.settings.get("paused") else "Приостановить")
        self.policy_label.setText('Модули на паузе' if w.settings.get('paused') else 'Сейчас: '+PROFILES[w._policy.profile])
        self.policy_label.setToolTip('Авто: от сети — «Работа», без зарядки — «Батарея». «Игра» и пауза останавливают модули, но не отсчёт таймера.')
        effective_style='floating' if w.floating_mode() else 'notch'
        for style,control in self.form_buttons.items():control.setChecked(style==effective_style)
        self.island_preview.display_style=effective_style
        self.island_preview.update()
        bridge = w.powertoys
        bridge.root = powertoys_root()
        self.integration_status.setText(bridge.status if w.settings.get("manage_powertoys") or bridge.busy else "Не подключён · изменения PowerToys не применяются")
        self.connect_button.setText("Обновить подключение" if w.settings.get("manage_powertoys") else "Подключить PowerToys" if bridge.root else "Установить PowerToys ↗")
        self.connect_button.setEnabled(not bridge.busy)
        self.restore_button.setEnabled(w.settings.get("manage_powertoys") and not bridge.busy and bridge.backup.exists())
        active = not w.settings.get("paused") and w._policy.profile != "game"
        for module in MODULES:
            enabled = w.settings.get(module.setting)
            external = module.key in {"layouts","workspaces"}
            status="Выключен" if not enabled else "На паузе" if not active else "Не подключён" if external and not w.settings.get("manage_powertoys") else "Включён"
            prefix=('FancyZones: ' if module.key=='layouts' else 'Workspaces: ') if external else ''
            self.module_status[module.key].setText(prefix+status)
        for key,widget in getattr(self,'module_switches',{}).items():
            widget.blockSignals(True); widget.setChecked(w.settings.get(key)); widget.blockSignals(False); widget.update()
        if hasattr(self,'hero_preview'): self.hero_preview.update()
        for key,editor in self.extra_key_editors:
            editor.setKeySequence(QKeySequence(w.settings.get(key).replace('Win+','Meta+')))
        for key,status in self.key_status.items():
            binding = w.hotkeys.get(key)
            value = w.settings.get(key)
            status.setText("Не назначено" if not value else (binding.error if binding else ""))
            status.setVisible(bool(status.text()))
            if hasattr(self,'key_editors'):
                self.key_editors[key].setKeySequence(QKeySequence(value.replace('Win+','Meta+')))
        self.refresh_timer_display()
        if self.isVisible():
            self.resource_label.setToolTip(self.usage.sample())
            hotkey = getattr(w, "_hub_hotkey", None)
            self.shortcut_label.setText(w.settings.get("hotkey_hub") if hotkey and hotkey.registered else "Открытие через трей")
        self._refresh_workspaces()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_material()
        self.refresh()
        self.refresh_timer.start()
        self.sync_focus_timer()

    def hideEvent(self, event):
        self.refresh_timer.stop()
        self.transition.animation.stop()
        self.transition.done()
        if hasattr(self,"focus_tick"):
            self.focus_tick.stop()
        if hasattr(self,"notebook"):
            self.notebook.flush()
        super().hideEvent(event)

    def _apply_theme(self):
        from .brand import resolved_palette
        self.colors=resolved_palette(self.owner.settings)
        self.setStyleSheet(stylesheet(self.colors))
        self.setFont(font(15))
        if hasattr(self,'help_button'):self.help_button.setIcon(icon('info',self.colors['muted'],18))
        if hasattr(self,'search_action'): self.search_action.setIcon(icon('search',self.colors['muted']))
        if hasattr(self,'collapse_navigation'): self.collapse_navigation.setIcon(icon('windows',self.colors['muted'],16))
        from .hub_ui import NAV_ICONS
        for key,select in getattr(self,'catalog_buttons',{}).items():
            select.setIcon(icon(NAV_ICONS[key],self.colors['muted'],20))
        from .timer import TimerReadout
        for readout in self.findChildren(TimerReadout):
            base=getattr(readout,'_hub_original_style',readout.styleSheet())
            readout._hub_original_style=base
            readout.setStyleSheet(base.replace('#f1f2f6',self.colors['text']).replace('#648ac9',self.colors['accent']))
        for emblem in self.findChildren(QLabel):
            if emblem.property('glyph'):
                emblem.setPixmap(icon(emblem.property('glyph'),self.colors['accent'],24).pixmap(24,24))
        if self.isVisible(): self.refresh_material()
        self.update()
