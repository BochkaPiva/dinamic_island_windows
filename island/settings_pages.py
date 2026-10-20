# SPDX-License-Identifier: GPL-3.0-only
"""Page factories: adding a page doesn't require changing the window shell."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QMenu,
    QLabel, QPushButton, QSpinBox, QSlider, QComboBox, QKeySequenceEdit, QLineEdit,
    QListWidget, QSizePolicy, QStackedWidget, QButtonGroup, QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox, QInputDialog)
from .modules import MODULES
from .policy import PROFILES
from .hub import FileShelf, fmt
from .notebook import Notebook
from .timer import TimerReadout
from .settings_navigation import SettingsSurface, SettingsCombo as QComboBox


PAGES = (("hub","Главная","overview_page"),
         ("island","Остров","island_page"),
         ("search","Поиск","search_page"),
         ("desktop","Рабочий стол","desktop_page"),
         ("library","Заметки и файлы","library_page"),
         ("timer","Фокус","timer_page"),
         ("workspaces","Окна","_workspaces_page"),
         ("shortcuts","Горячие клавиши","shortcuts_page"),
         ("integrations","Приложение","application_page"),
         ("updates","Обновления","updates_page"),
         ("account","Сообщество","account_page"))


class ShortcutRecorder(QKeySequenceEdit):
    def __init__(self,owner,value):
        super().__init__(QKeySequence(value))
        self.owner = owner

    def focusInEvent(self,event):
        for binding in self.owner.hotkeys.values():
            binding.suspend()
        super().focusInEvent(event)

    def focusOutEvent(self,event):
        super().focusOutEvent(event)
        if not self.owner._closed:
            for key,binding in self.owner.hotkeys.items():
                binding.rebind(self.owner.settings.get(key))


class SettingsPages:
    def account_page(self):
        from .community_ui import CommunityPanel
        layout = self._page()
        self.heading(layout, 'Сообщество', 'Nelviro развивается вместе с тобой')
        self.account_panel = CommunityPanel(getattr(self.owner, 'community', None))
        layout.addWidget(self.account_panel)

    def visual_header(self, layout, title, detail, kind, callback=None):
        from .control_center import text
        from .module_preview import ModulePreview,FocusPreview
        # Useful live previews only; ordinary settings do not need illustrations.
        if kind not in {'island','desktop','search','timer'}:
            self.heading(layout,title,detail)
            return None
        row=QHBoxLayout()
        row.setSpacing(20)
        row.addWidget(text(detail,True),1)
        preview=FocusPreview(self.owner.notch_hub) if kind=='timer' else ModulePreview(self.owner,kind,callback)
        preview.setFixedWidth(280)
        row.addWidget(preview)
        layout.addLayout(row)
        return preview

    def heading(self,layout,title,detail=""):
        # The section header provides the name; help is available on demand.
        pass


    def action(self, title, callback):
        btn = QPushButton(title)
        btn.clicked.connect(callback)
        return btn

    def card(self,title,detail=""):
        wrapper=QFrame();wrapper.setObjectName('sectionWrapper')
        outer=QVBoxLayout(wrapper);outer.setContentsMargins(0,0,0,0);outer.setSpacing(10)
        if title:
            label=QLabel(title);label.setObjectName('paneTitle');outer.addWidget(label)
        frame=SettingsSurface();frame.setObjectName('card');outer.addWidget(frame)
        layout=QVBoxLayout(frame);layout.setContentsMargins(18,0,18,0);layout.setSpacing(0)
        if detail:frame.setToolTip(detail)
        return wrapper,layout


    def fold(self,title,opened=False):
        from .settings_navigation import SettingsSubpage
        section=SettingsSubpage(self,title)
        return section,section.content

    def choice(self,layout,label,control):
        frame=QFrame();frame.setObjectName('settingRow');frame.setMinimumHeight(52)
        row=QHBoxLayout(frame);row.setContentsMargins(0,8,0,8)
        row.addWidget(QLabel(label),1);row.addWidget(control)
        layout.addWidget(frame)
        self.index_setting(label,layout,control)
        return control

    def link(self,layout,title,callback,summary=''):
        from .settings_navigation import SettingsLink
        link=SettingsLink(title,callback,summary);layout.addWidget(link)
        return link

    def shortcut_row(self,layout,key,title='Сочетание клавиш'):
        from .shortcut_ui import ShortcutButton
        control=ShortcutButton(self.owner.settings.get(key));control.setFixedWidth(190)
        control.clicked.connect(lambda:self.open_shortcut(key,title,control))
        self.extra_key_editors.append((key,control))
        self.choice(layout,title,control)
        return control


    def number(self,layout,key,label,suffix="",slider=False):
        frame=QFrame();frame.setObjectName('settingRow');frame.setMinimumHeight(52)
        row=QHBoxLayout(frame);row.setContentsMargins(0,8,0,8);row.setSpacing(14)
        title=QLabel(label);title.setWordWrap(True);row.addWidget(title,1)
        value=QSpinBox();value.setRange(*self.owner.settings.RANGES[key]);value.setSuffix(suffix)
        value.setValue(self.owner.settings.get(key));value.setFixedWidth(100);value.setKeyboardTracking(False)
        value.setAccessibleName(label);value.valueChanged.connect(lambda v:self._setting(key,v));self.values[key]=value
        if slider:
            scale=QSlider(Qt.Orientation.Horizontal);scale.setRange(*self.owner.settings.RANGES[key])
            scale.setValue(self.owner.settings.get(key));scale.setFixedWidth(110)
            scale.setAccessibleName(label);self.sliders[key]=scale
            scale.valueChanged.connect(value.setValue);value.valueChanged.connect(scale.setValue);row.addWidget(scale)
        row.addWidget(value);layout.addWidget(frame)
        self.index_setting(label,layout,value)
        return value


    def overview_page(self):
        from .control_center import text
        from .hub_ui import ToggleSwitch,icon
        from .dashboard import DashboardDeck
        from .module_preview import ModulePreview,FocusPreview
        from .settings_navigation import SettingsSurface
        layout=self._page();layout.setSpacing(16)
        self.module_status={};self.module_switches={};self.catalog_buttons={}
        self.catalog_stack=DashboardDeck(self.select_catalog)
        for index,(key,title,setting,glyph) in enumerate((('island','Остров','island_enabled','island'),('desktop','Группы','desktop_enabled','folder'),('search','Поиск','search_enabled','search'),('timer','Фокус',None,'timer'),('library','Материалы',None,'note'),('workspaces','Окна',None,'windows'))):
            panel=SettingsSurface();panel.setObjectName('card');panel.setMinimumHeight(176)
            inside=QVBoxLayout(panel);inside.setContentsMargins(16,10,16,10);inside.setSpacing(6)
            header=QHBoxLayout()
            select=self.action(title,lambda _,i=index:self.select_catalog(i));select.setObjectName('tileTitle');select.setIcon(icon(glyph,self.colors['text'],20))
            select.setFixedHeight(30);select.setAccessibleName('Предпросмотр: '+title);header.addWidget(select,1);self.catalog_buttons[key]=select
            if setting:
                toggle=ToggleSwitch(title);toggle.toggled.connect(lambda v,k=setting:self._setting(k,v));header.addWidget(toggle);self.module_switches[setting]=toggle
            inside.addLayout(header)
            if key in ('island','desktop','search'):
                callback=self.owner._show_panel if key=='island' else self.owner.show_search if key=='search' else lambda:self.navigate('desktop')
                preview=ModulePreview(self.owner,key,callback);preview.setMinimumWidth(180);preview.setFixedHeight(84);inside.addWidget(preview)
                if key=='island':self.hero_preview=preview
            elif key=='timer':
                self.focus_preview=FocusPreview(self.owner.notch_hub,readout_size=18);self.focus_preview.setFixedHeight(84)
                self.overview_timer=self.focus_preview.readout;inside.addWidget(self.focus_preview)
            elif key=='library':
                sample=QLabel();sample.setTextFormat(Qt.TextFormat.PlainText);sample.setObjectName('noteSample');sample.setWordWrap(True);sample.setFixedHeight(84)
                def refresh_note(label=sample):label.setText(self.owner.notch_hub.notes.toPlainText()[:140] or 'Записать мысль…')
                refresh_note();self.owner.notch_hub.notes.textChanged.connect(refresh_note);inside.addWidget(sample)
            else:
                from .window_layout_ui import ZonePicker
                picker=ZonePicker();picker.setFixedHeight(84);picker.selected.connect(lambda _:self.navigate('workspaces'));inside.addWidget(picker)
            footer=QHBoxLayout()
            if key=='timer':
                self.overview_start=self.action('Начать',lambda:self.start_dashboard_focus());self.overview_start.setObjectName('quiet');self.overview_start.setFixedHeight(30);footer.addWidget(self.overview_start)
            for status_key in ([key] if setting else ['layouts','workspaces'] if key=='workspaces' else []):
                status=text('',True);status.setFixedHeight(30);footer.addWidget(status);self.module_status[status_key]=status
                if key=='workspaces':status.hide()
            footer.addStretch();open_button=self.action('Открыть',lambda _,k=key:self.navigate(k));open_button.setObjectName('quiet');open_button.setFixedHeight(30);footer.addWidget(open_button)
            inside.addLayout(footer);self.catalog_stack.addWidget(panel)
        layout.addWidget(self.catalog_stack)
        self.policy_label=text('',True);self.policy_label.hide()
        profile_row=QHBoxLayout();profile_row.addWidget(text('Режим',True));profile_row.addStretch();self.profile_buttons={}
        for key,title in PROFILES.items():
            control=self.action('Авто' if key=='auto' else title,lambda _,k=key:self._setting('profile',k));control.setObjectName('segment');control.setCheckable(True);profile_row.addWidget(control);self.profile_buttons[key]=control
        layout.addLayout(profile_row);layout.addStretch();self.select_catalog(0)

    def select_catalog(self,index):
        self.catalog_stack.setCurrentIndex(index)
        if hasattr(self,'focus_tick'):self.sync_focus_timer()

    def start_dashboard_focus(self):
        self.select_catalog(3);self.owner.notch_hub.toggle_timer()

    def island_page(self):
        from .module_preview import FormPreview
        from PySide6.QtWidgets import QApplication
        layout=self._page()
        self._module(layout,'island_enabled','Остров','Показывать остров на экране')
        self.form_buttons={}
        hero=SettingsSurface();hero.setObjectName('card');hero_layout=QVBoxLayout(hero)
        hero_layout.setContentsMargins(16,12,16,0);hero_layout.setSpacing(8);layout.addWidget(hero)
        self.island_preview=FormPreview(self.owner,'notch',self.owner._show_panel)
        self.island_preview.setFixedHeight(100);hero_layout.addWidget(self.island_preview)
        forms=QHBoxLayout();forms.setSpacing(6)
        for title,key in (('Чёлка','notch'),('Остров','floating')):
            control=self.action(title,lambda _,style=key:self._setting('island_style',style))
            control.setObjectName('segment');control.setCheckable(True);forms.addWidget(control,1);self.form_buttons[key]=control
            if key=='floating':control.setToolTip('Плавающий остров — для подписчиков канала')
        hero_layout.addLayout(forms)
        self.index_setting('Форма острова',hero_layout,self.form_buttons['floating'])
        self.material_buttons={}
        materials=QHBoxLayout();materials.setSpacing(6)
        for title,key in (('Обычный','black'),('Стекло','glass')):
            control=self.action(title,lambda _,value=key:self._setting('island_material',value))
            control.setObjectName('segment');control.setCheckable(True);materials.addWidget(control,1);self.material_buttons[key]=control
        hero_layout.addLayout(materials)
        self.material_buttons['glass'].setToolTip('Стеклянная поверхность — для подписчиков канала')
        self.index_setting('Материал стекло',hero_layout,self.material_buttons['glass'])
        from .color_ui import ColorButton
        self.island_color_button=ColorButton(self.open_island_color)
        self.island_color_button.setToolTip('Цвет применяется к обоим материалам. Контраст текста подстраивается автоматически.')
        self.choice(hero_layout,'Цвет острова',self.island_color_button)
        self.screen_picker=QComboBox();self.screen_picker.addItem('Основной','')
        for screen in QApplication.screens():self.screen_picker.addItem(screen.name(),screen.name())
        self.screen_picker.currentIndexChanged.connect(lambda _:self._setting('monitor',self.screen_picker.currentData()))
        self.choice(hero_layout,'Экран',self.screen_picker)
        frame,links=self.card('Настройки');layout.addWidget(frame)
        section,inside=self.fold('Размер и прозрачность');links.addWidget(section)
        for title,keys in (('Свёрнутый',(('compact_width','Ширина'),('compact_height','Высота'))),('Раскрытый',(('expanded_width','Ширина'),('expanded_height','Высота')))):
            card,group=self.card(title);inside.addWidget(card)
            for key,label in keys:self.number(group,key,label,' px',True)
        card,group=self.card('Поверхность');inside.addWidget(card)
        self.number(group,'island_opacity','Непрозрачность',' %',True)
        self.number(group,'island_gap','Отступ острова',' px',True)
        self.link(inside,'Сбросить оформление',self.reset_island);inside.addStretch()
        section,inside=self.fold('Поведение');links.addWidget(section)
        card,group=self.card('Видимость');inside.addWidget(card)
        self._module(group,'cursor_retreat','Уклоняться от курсора','При приближении к вкладкам остаётся тонкий язычок. Наведи на него, чтобы открыть остров.')
        self._module(group,'hide_fullscreen','Скрывать в полном экране','В обычных окнах остров остаётся доступен')
        card,group=self.card('Наведение');inside.addWidget(card)
        self.number(group,'hover_delay','Раскрытие',' мс');self.number(group,'collapse_delay','Сворачивание',' мс')
        self._module(group,'volume_scroll_reverse','Обратная прокрутка громкости','Изменить направление регулировки колесом');inside.addStretch()
        section,inside=self.fold('Звук');links.addWidget(section)
        card,group=self.card('Эквалайзер');inside.addWidget(card)
        self._module(group,'spectrum','Реагировать на звук','Анализ звука компьютера, без микрофона')
        self._module(group,'spectrum_battery_save','Экономить заряд','Отключать спектр свёрнутого острова при работе от батареи');inside.addStretch()
        section,inside=self.fold('Содержимое');links.addWidget(section)
        card,group=self.card('В обзоре');inside.addWidget(card)
        self._module(group,'overview_calendar','Календарь','Показывать текущую неделю')
        self._module(group,'overview_focus','Таймер','Показывать таймер фокуса')
        self._module(group,'island_files','Полка файлов','Дополнительная вкладка для переноса файлов');inside.addStretch()
        frame,links=self.card('Инструменты');layout.addWidget(frame)
        section,inside=self.fold('Видео и камера');section.summary='Подписчикам';links.addWidget(section)
        card,group=self.card('Видео');inside.addWidget(card)
        self.link(group,'Открыть файл',self.owner.media_stage.choose_file)
        self.link(group,'Продолжить просмотр',self.owner.media_stage.resume)
        card,group=self.card('Камера');inside.addWidget(card)
        self.link(group,'Открыть зеркало',self.owner.media_stage.choose_camera)
        self.link(inside,'Закрепить текущую карточку',self.owner.activities.toggle_pin);inside.addStretch()
        layout.addStretch()


    def open_island_color(self):
        if not self.owner.access.feature('island.color').allowed:
            self.navigate('account');self._message('Цвет острова открывается после подписки на канал');return
        from .color_ui import IslandColorDialog
        dialog=IslandColorDialog(self);dialog.exec();dialog.deleteLater();self.refresh()

    def reset_island(self):
        for key in ("compact_width","compact_height","expanded_width","expanded_height","island_opacity","island_gap","island_style","island_material","hover_delay","collapse_delay"):
            self._setting(key,self.owner.settings.DEFAULTS[key])

    def search_page(self):
        from .module_preview import ModulePreview
        layout=self._page()
        self._module(layout,'search_enabled','Поиск','Открывать приложения, файлы и команды')
        from .dashboard import SearchDemo
        layout.addWidget(SearchDemo(self))
        frame,group=self.card('Искать');layout.addWidget(frame)
        self._module(group,'search_apps','Приложения','Меню «Пуск» и ярлыки')
        self._module(group,'search_files','Файлы','Используется индекс Windows')
        frame,group=self.card('Управление');layout.addWidget(frame)
        self.shortcut_row(group,'hotkey_search')
        self._module(group,'search_glass','Прозрачный фон','Акрил Windows; можно выключить')
        self.link(group,'Индекс Windows',lambda:self._url(QUrl('ms-settings:search')))
        layout.addStretch()


    def desktop_page(self):
        from .group_editor import GroupEditor
        layout=self._page();layout.setSpacing(12)
        self._module(layout,'desktop_enabled','Группы','Показывать группы на рабочем столе')
        self.group_settings,inside=self.fold('Оформление групп')
        self.group_settings.setMaximumHeight(40);layout.addWidget(self.group_settings)
        self.group_editor=GroupEditor(self.owner.modules.desktop,self._message)
        self.group_editor.setMinimumHeight(280);layout.addWidget(self.group_editor,1)
        frame,group=self.card('Вид');inside.addWidget(frame)
        self.number(group,'group_width','Ширина',' px',True);self.number(group,'group_columns','Столбцы')
        self.number(group,'group_opacity','Непрозрачность',' %',True)
        frame,group=self.card('Поведение');inside.addWidget(frame)
        self.number(group,'group_hover_delay','Раскрытие',' мс');self.number(group,'group_collapse_delay','Сворачивание',' мс')
        self._module(group,'groups_locked','Закрепить расположение','Запретить перемещение групп за заголовок')
        self._module(group,'group_collect_shortcuts','Переносить ярлыки в группы','Сначала создаётся собственная копия .lnk или .url, затем убирается ярлык с рабочего стола. Документы и папки не перемещаются.')
        self.link(inside,'Выровнять группы',self.owner.modules.desktop.arrange)
        self.link(inside,'Библиотека ярлыков',lambda:self._url(QUrl.fromLocalFile(str(self.owner.modules.desktop.store.library.root))))
        inside.addStretch()


    def library_page(self):
        layout=self._page();tabs=QTabWidget();self.library_tabs=tabs
        files=QWidget();inside=QVBoxLayout(files);inside.setContentsMargins(0,10,0,0);inside.setSpacing(10)
        self.file_shelf=FileShelf(self.owner.settings.directory/'notch-files.json');self.file_shelf.setMinimumHeight(250)
        toolbar=QHBoxLayout()
        add=self.action('Добавить',self.file_shelf.add_files);menu=QMenu(add)
        menu.addAction('Файлы…',self.file_shelf.add_files);menu.addAction('Папку…',self.file_shelf.add_folder);add.setMenu(menu)
        toolbar.addWidget(add);toolbar.addStretch()
        remove=self.action('Убрать',self.file_shelf.remove_selected);remove.setObjectName('quiet');toolbar.addWidget(remove)
        inside.addLayout(toolbar);inside.addWidget(self.file_shelf,1)
        self.owner.notch_hub.shelf.changed.connect(self.file_shelf.reload);self.file_shelf.changed.connect(self.owner.notch_hub.shelf.reload)
        tabs.addTab(files,'Файлы')
        self.notebook=Notebook(self.owner.notch_hub);self.notebook.setMinimumHeight(320);tabs.addTab(self.notebook,'Заметки')
        shell=SettingsSurface();shell.setObjectName('card');frame=QVBoxLayout(shell);frame.setContentsMargins(14,10,14,14);frame.addWidget(tabs);layout.addWidget(shell,1)


    def timer_page(self):
        from .module_preview import FocusPreview
        layout=self._page()
        frame,body=self.card('');layout.addWidget(frame)
        main=QHBoxLayout();main.setContentsMargins(0,20,0,20);main.setSpacing(24)
        self.timer_header=FocusPreview(self.owner.notch_hub);self.timer_header.setFixedSize(190,190)
        self.timer_label=self.timer_header.readout;main.addWidget(self.timer_header)
        controls=QVBoxLayout();controls.setSpacing(14)
        quick=QGridLayout();quick.setSpacing(6)
        for i,minutes in enumerate((5,15,25,45,60)):
            control=self.action(str(minutes)+' мин',lambda _,n=minutes:self._setting('timer_minutes',n));control.setObjectName('segment');quick.addWidget(control,i//3,i%3)
        controls.addLayout(quick)
        row=QHBoxLayout();self.focus_start=self.action('Начать',self.owner.notch_hub.toggle_timer);self.focus_start.setObjectName('primary');row.addWidget(self.focus_start)
        reset=self.action('Сбросить',self.owner.notch_hub.reset_timer);reset.setObjectName('quiet');row.addWidget(reset);controls.addLayout(row)
        main.addLayout(controls,1);body.addLayout(main)
        self.number(body,'timer_minutes','Минуты',' мин')
        frame,group=self.card('Завершение');layout.addWidget(frame)
        self._module(group,'timer_sound','Звук','Громкость определяется Windows')
        self.number(group,'timer_alarm_seconds','Длительность сигнала',' сек')
        self.link(group,'Прослушать',self.preview_timer_sound)
        layout.addStretch()
        self.focus_tick=QTimer(self);self.focus_tick.setInterval(1000);self.focus_tick.timeout.connect(self.refresh_timer_display)
        self.pages.currentChanged.connect(lambda _:self.sync_focus_timer())

    def open_focus(self):
        self.owner._show_panel()
        self.owner.notch_hub.select_tab(1)

    def sync_focus_timer(self):
        if self.isVisible() and (self.navigation.currentRow()==self.page_indices['timer'] or
                self.navigation.currentRow()==self.page_indices['hub']):
            self.focus_tick.start()
            self.refresh_timer_display()
        else:
            self.focus_tick.stop()

    def refresh_timer_display(self):
        hub = self.owner.notch_hub
        self.timer_label.refresh()
        if hasattr(self,'overview_timer') and self.overview_timer.isVisible(): self.overview_timer.refresh()
        if hasattr(self,'focus_preview'): self.focus_preview.update()
        if hasattr(self,'timer_header'): self.timer_header.readout.refresh(); self.timer_header.update()
        self.focus_start.setText("Остановить сигнал" if hub.alarm.active else "Пауза" if hub._timer_end else "Продолжить" if 0 < hub.timer_seconds() < self.owner.settings.get("timer_minutes")*60 else "Начать")
        if hasattr(self,'overview_start'): self.overview_start.setText(self.focus_start.text())

    def preview_timer_sound(self):
        import winsound
        if self.owner.notch_hub.alarm.active:
            self.owner.notch_hub.alarm.dismiss()
        try:
            winsound.PlaySound(str(Path(__file__).parent/"assets/timer-chime.wav"),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
        except (RuntimeError,OSError):
            self._message("Звук недоступен — проверь устройство вывода и громкость Windows")

    def shortcuts_page(self):
        from .control_center import text
        layout = self._page()

        self.key_editors, self.key_status = {},{}
        frame,inside=self.card('Глобальные')
        from .shortcut_ui import ShortcutButton
        from .hub_ui import icon
        for key,title in (("hotkey_search","Быстрый поиск"),("hotkey_island","Открыть чёлку"),("hotkey_hub","Открыть Nelviro")):
            row=QHBoxLayout();row.setSpacing(8)
            emblem=QLabel();emblem.setPixmap(icon('search' if key=='hotkey_search' else 'island' if key=='hotkey_island' else 'hub',self.colors['text'],22).pixmap(22,22))
            emblem.setFixedSize(34,38);row.addWidget(emblem)
            words=QVBoxLayout();words.setSpacing(2)
            words.addWidget(text(title))
            status=text('',True);words.addWidget(status);self.key_status[key]=status
            row.addLayout(words,1)
            editor=ShortcutButton(self.owner.settings.get(key))
            editor.setFixedWidth(230)
            editor.setAccessibleName('Изменить сочетание: '+title)
            editor.clicked.connect(lambda _,k=key,t=title:self.open_shortcut(k,t))
            self.key_editors[key]=editor
            row.addWidget(editor)
            more=QPushButton('…');more.setObjectName('iconButton');more.setFixedWidth(30)
            more.setAccessibleName('Другие действия: '+title)
            menu=QMenu(more)
            menu.addAction('Ввести вручную…',lambda _,k=key:self.manual_shortcut(k))
            menu.addAction('Отключить',lambda _,k=key:self._setting(k,''))
            more.setMenu(menu);row.addWidget(more)
            inside.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()

    def open_shortcut(self,key,title,anchor=None):
        from .shortcut_ui import ShortcutDialog
        dialog=ShortcutDialog(self,key,title,anchor=anchor)
        dialog.exec()
        dialog.deleteLater()
        self.refresh()

    def apply_shortcut(self,key):
        self._setting(key,self.key_editors[key].keySequence().toString(QKeySequence.SequenceFormat.PortableText))

    def manual_shortcut(self,key):
        value,ok = QInputDialog.getText(self,"Горячая клавиша","Например Alt+Space или Ctrl+Alt+Space",text=self.owner.settings.get(key))
        if ok:
            self._setting(key,value.strip())
            self.key_editors[key].setKeySequence(QKeySequence(self.owner.settings.get(key).replace('Win+','Meta+')))

    def application_page(self):
        layout=self._page()
        frame,group=self.card('Основные');layout.addWidget(frame)
        self.theme_picker=QComboBox()
        for label,value in (('Тёмное','dark'),('Светлое','light'),('Как в Windows','system')):self.theme_picker.addItem(label,value)
        self.theme_picker.setCurrentIndex(max(0,self.theme_picker.findData(self.owner.settings.get('hub_theme'))))
        self.theme_picker.currentIndexChanged.connect(lambda _:self._setting('hub_theme',self.theme_picker.currentData()))
        self.choice(group,'Тема',self.theme_picker)
        self._module(group,'hub_animations','Анимации','Учитывается и на вложенных экранах')
        self._module(group,'autostart','Запускать с Windows','При входе — трей и выбранные модули')
        frame,group=self.card('Приложение');layout.addWidget(frame)
        self.link(group,'Горячие клавиши',lambda:self.navigate('shortcuts'))
        self.link(group,'Обновления',lambda:self.navigate('updates'))
        self.link(group,'Папка данных',lambda:self._url(QUrl.fromLocalFile(str(self.owner.settings.directory))))
        frame,group=self.card('Интеграции');layout.addWidget(frame)
        section,inside=self.fold('PowerToys');group.addWidget(section)
        self.integration_status=QLabel();self.integration_status.setObjectName('secondary');self.integration_status.setWordWrap(True);inside.addWidget(self.integration_status)
        frame,group=self.card('Модули');inside.addWidget(frame)
        self._module(group,'layouts_enabled','Зоны окон','Shift при перетаскивании включает FancyZones')
        self._module(group,'workspaces_enabled','Рабочие наборы','Приложения и их расположение')
        self.connect_button=self.action('Подключить PowerToys',self._connect);inside.addWidget(self.connect_button,0,Qt.AlignmentFlag.AlignLeft)
        self.restore_button=self.action('Восстановить подключение',self._restore);self.restore_button.setObjectName('quiet');inside.addWidget(self.restore_button,0,Qt.AlignmentFlag.AlignLeft)
        self.link(inside,'Настройки PowerToys',lambda:self.owner.powertoys.launch('PowerToys.exe',['--open-settings']));inside.addStretch();layout.addStretch()


    def updates_page(self):
        from .update_ui import UpdatePanel
        layout=self._page();self.update_panel=UpdatePanel(self.owner);layout.addWidget(self.update_panel)
        frame,group=self.card('');layout.addWidget(frame)
        self._module(group,'updates','Проверять автоматически','Раз в день и после запуска')
        layout.addStretch()
