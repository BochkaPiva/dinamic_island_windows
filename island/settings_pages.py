# SPDX-License-Identifier: GPL-3.0-only
"""Page factories: adding a page doesn't require changing the window shell."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QSpinBox, QSlider, QComboBox, QKeySequenceEdit, QLineEdit,
    QListWidget, QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox, QInputDialog)
from .modules import MODULES
from .policy import PROFILES
from .hub import FileShelf, fmt
from .notebook import Notebook
from .timer import TimerReadout


PAGES = (("hub","Модули","overview_page"),
         ("island","Dynamic Island","island_page"),
         ("search","Поиск","search_page"),
         ("desktop","Рабочий стол","desktop_page"),
         ("library","Заметки и файлы","library_page"),
         ("timer","Фокус","timer_page"),
         ("shortcuts","Горячие клавиши","shortcuts_page"),
         ("workspaces","Окна и наборы","_workspaces_page"),
         ("integrations","Приложение","application_page"),
         ("updates","Обновления","updates_page"),
         ("account","Аккаунт","account_page"),
         ("windows","Windows и HONOR","_windows_page"))


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
        from .account_ui import AccountPanel
        layout = self._page()
        self.heading(layout, 'Аккаунт', 'Подписка и устройства')
        self.account_panel = AccountPanel(getattr(self.owner, 'account', None))
        layout.addWidget(self.account_panel)

    def heading(self, layout, title, detail=""):
        from .control_center import section
        section(layout,title,detail)

    def action(self, title, callback):
        btn = QPushButton(title)
        btn.clicked.connect(callback)
        return btn

    def card(self,title,detail=""):
        from .control_center import text
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18,14,18,16)
        layout.setSpacing(9)
        label = text(title)
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        if detail:
            layout.addWidget(text(detail,True))
        return frame,layout

    def number(self,layout,key,label,suffix="",slider=False):
        row = QHBoxLayout()
        title = QLabel(label)
        title.setMinimumWidth(205)
        row.addWidget(title,1)
        if slider:
            scale = QSlider(Qt.Orientation.Horizontal)
            scale.setRange(*self.owner.settings.RANGES[key])
            scale.setValue(self.owner.settings.get(key))
            scale.setMaximumWidth(170)
            self.sliders[key] = scale
            row.addWidget(scale,1)
        value = QSpinBox()
        value.setRange(*self.owner.settings.RANGES[key])
        value.setSuffix(suffix)
        value.setValue(self.owner.settings.get(key))
        value.setMinimumWidth(100)
        value.setKeyboardTracking(False)
        value.valueChanged.connect(lambda v:self._setting(key,v))
        self.values[key] = value
        if slider:
            scale.valueChanged.connect(value.setValue)
            value.valueChanged.connect(scale.setValue)
        row.addWidget(value)
        layout.addLayout(row)
        return value

    def overview_page(self):
        from .control_center import text
        from .hub_ui import IslandPreview,ModuleCard,ToggleSwitch,icon
        layout = self._page()
        self.heading(layout,"Твоё пространство")
        hero=QFrame()
        hero.setObjectName('hero')
        hero_layout=QHBoxLayout(hero)
        hero_layout.setContentsMargins(22,12,14,12)
        words=QVBoxLayout()
        eyebrow=text('CLOUD HUB  /  ДЛЯ ТВОЕГО РИТМА')
        eyebrow.setObjectName('eyebrow')
        words.addWidget(eyebrow)
        hero_title=text('Всё под рукой.')
        hero_title.setObjectName('heroTitle')
        words.addWidget(hero_title)
        words.addWidget(text('Музыка, фокус и рабочие инструменты\nв твоём ритме.',True))
        hero_layout.addLayout(words,1)
        self.hero_preview=IslandPreview(self.owner)
        hero_layout.addWidget(self.hero_preview,1)
        layout.addWidget(hero)
        row = QHBoxLayout()
        self.policy_label=text('',True)
        row.addWidget(self.policy_label)
        segmented=QFrame()
        segmented.setObjectName('segments')
        segment_row=QHBoxLayout(segmented)
        segment_row.setContentsMargins(3,3,3,3)
        segment_row.setSpacing(2)
        self.profile_buttons = {}
        for key,title in PROFILES.items():
            btn = self.action('Авто' if key=='auto' else title,lambda _,k=key:self._setting("profile",k))
            btn.setObjectName('segment')
            btn.setCheckable(True)
            segment_row.addWidget(btn)
            self.profile_buttons[key] = btn
        row.addStretch()
        row.addWidget(segmented)
        layout.addLayout(row)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.module_status = {}
        self.module_switches={}
        specs=(('island','Dynamic Island','Музыка и звук у верхней рамки','island_enabled','island'),
            ('desktop','Рабочий стол','Группы с твоими приложениями','desktop_enabled','folder'),
            ('search','Быстрый поиск','Найти и открыть одной строкой','search_enabled','search'),
            ('timer','Фокус','Время для важного',None,'timer'),
            ('library','Заметки и файлы','Мысли и материалы под рукой',None,'note'),
            ('workspaces','Окна и наборы','Рабочие раскладки PowerToys',None,'windows'))
        for index,(key,title,detail,setting,glyph_name) in enumerate(specs):
            frame=ModuleCard(lambda k=key:self.navigate(k))
            inside=QVBoxLayout(frame)
            inside.setContentsMargins(16,14,16,14)
            inside.setSpacing(8)
            top=QHBoxLayout()
            emblem=QLabel()
            emblem.setProperty('glyph',glyph_name)
            emblem.setPixmap(icon(glyph_name,self.colors['accent'],24).pixmap(24,24))
            top.addWidget(emblem)
            top.addStretch()
            if setting:
                toggle=ToggleSwitch(title)
                toggle.toggled.connect(lambda value,k=setting:self._setting(k,value))
                top.addWidget(toggle)
                self.module_switches[setting]=toggle
            else:
                arrow=self.action('↗',lambda _,k=key:self.navigate(k))
                arrow.setObjectName('quiet')
                arrow.setFixedSize(26,26)
                arrow.setAccessibleName('Открыть '+title)
                top.addWidget(arrow)
            inside.addLayout(top)
            label=text(title)
            label.setObjectName('cardTitle')
            inside.addWidget(label)
            inside.addWidget(text(detail,True))
            if setting:
                status=text('',True)
                inside.addWidget(status)
                self.module_status[key]=status
            elif key=='timer':
                self.overview_timer=TimerReadout(self.owner.notch_hub,26)
                inside.addWidget(self.overview_timer)
            elif key=='workspaces':
                for external in ('layouts','workspaces'):
                    status=text('',True)
                    status.setStyleSheet('font-size:10px')
                    inside.addWidget(status)
                    self.module_status[external]=status
            else:
                inside.addWidget(text('Открыть заметки →',True))
            grid.addWidget(frame,index//3,index%3)
        layout.addLayout(grid)
        layout.addStretch()

    def island_page(self):
        layout = self._page()
        self.heading(layout,"Dynamic Island","Мини-плеер слева, неделя по центру, фокус справа. Календарь листается жестами и перетаскиванием, без полос прокрутки.")
        self._module(layout,"island_enabled","Показывать чёлку","Всегда по центру выбранного экрана, у верхней рамки")
        row = QHBoxLayout()
        row.addWidget(self.action("Посмотреть чёлку",self.owner._show_panel))
        row.addWidget(self.action("Сбросить её оформление",self.reset_island))
        layout.addLayout(row)
        frame,inside = self.card("Размер и прозрачность","Размеры в логических пикселях: системный масштаб Windows учитывается автоматически.")
        for key,label in (("compact_width","Ширина свёрнутой"),("compact_height","Высота свёрнутой"),
                          ("expanded_width","Ширина раскрытой"),("expanded_height","Высота раскрытой")):
            self.number(inside,key,label," px",True)
        self.number(inside,"island_opacity","Непрозрачность"," %",True)
        layout.addWidget(frame)
        frame,inside = self.card("Поведение")
        self._module(inside,"overview_calendar","Неделя в обзоре","Сегодня по центру; нажми месяц, чтобы вернуться к текущей дате. События аккаунтов не подключаются")
        self._module(inside,"overview_focus","Фокус в обзоре","Небольшой таймер справа; подробные настройки на вкладке «Фокус»")
        self.number(inside,"hover_delay","Раскрытие при наведении"," мс")
        self.number(inside,"collapse_delay","Сворачивание после ухода"," мс")
        self._module(inside,"cursor_retreat","Уворачиваться от курсора","Освобождает вкладки браузера; верхний край экрана раскрывает чёлку")
        self._module(inside,"spectrum","Реальный спектр звука","Анализ воспроизводимого звука; микрофон не используется")
        self._module(inside,"spectrum_battery_save","Отключать спектр в свёрнутой чёлке от батареи","Дополнительная экономия. По умолчанию выключена: спектр реагирует на звук и без зарядки")
        self._module(inside,"hide_fullscreen","Скрывать в полноэкранных приложениях","В обычных и развёрнутых окнах чёлка остаётся доступна")
        self._module(inside,"volume_scroll_reverse","Обратить прокрутку громкости","Для нестандартного направления драйвера тачпада")
        self._module(inside,"island_files","Дополнительная вкладка «Полка»","Промежуточные ссылки: перетаскивание из Проводника в полку и дальше в другое приложение")
        screen_row = QHBoxLayout()
        screen_row.addWidget(QLabel("Экран"))
        self.screen_picker = QComboBox()
        self.screen_picker.addItem("Основной экран","")
        from PySide6.QtWidgets import QApplication
        for screen in QApplication.screens():
            self.screen_picker.addItem(screen.name(),screen.name())
        self.screen_picker.setCurrentIndex(max(0,self.screen_picker.findData(self.owner.settings.get("monitor"))))
        self.screen_picker.currentIndexChanged.connect(lambda _:self._setting("monitor",self.screen_picker.currentData()))
        screen_row.addWidget(self.screen_picker,1)
        inside.addLayout(screen_row)
        layout.addWidget(frame)
        layout.addStretch()

    def reset_island(self):
        for key in ("compact_width","compact_height","expanded_width","expanded_height","island_opacity","hover_delay","collapse_delay"):
            self._setting(key,self.owner.settings.DEFAULTS[key])

    def search_page(self):
        layout = self._page()
        self.heading(layout,"Быстрый поиск","Одна строка для приложений, файлов и команд Cloud Hub. Управление: ↑ ↓, Enter и Esc.")
        self._module(layout,"search_enabled","Включить поиск Cloud Hub","Собственный модуль; PowerToys Command Palette для него не нужен")
        self._module(layout,"search_glass","Полупрозрачная поверхность","Спокойное тонирование без дополнительных рамок; выключи для полностью непрозрачного фона")
        self._module(layout,"search_apps","Приложения и ярлыки","Меню «Пуск» и рабочий стол; каталог обновляется по запросу")
        self._module(layout,"search_files","Файлы из индекса Windows","По имени файла. Только индексированные Windows папки, без своего фонового обхода диска")
        layout.addWidget(self.action("Открыть поиск",self.owner.show_search))
        layout.addWidget(self.action("Изменить горячую клавишу →",lambda:self.navigate("shortcuts")))
        layout.addWidget(self.action("Настроить индексируемые папки Windows ↗",lambda:self._url(QUrl("ms-settings:search"))))
        frame,inside = self.card("Что можно вводить","Название приложения или файла, полный путь к файлу или папке, «таймер», «заметки», «группы». Поиск ничего не запускает до Enter или двойного щелчка.")
        layout.addWidget(frame)
        layout.addStretch()

    def desktop_page(self):
        from PySide6.QtWidgets import QScrollArea
        from .group_editor import GroupEditor
        layout=self._page()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(10)
        self.heading(layout,"Группы рабочего стола")
        self._module(layout,"desktop_enabled","Показывать группы","Они остаются на рабочем столе под окнами приложений")
        self.group_tabs=QTabWidget()
        self.group_editor=GroupEditor(self.owner.modules.desktop,self._message)
        self.group_tabs.addTab(self.group_editor,"Мои группы")
        appearance=QWidget()
        inside=QVBoxLayout(appearance)
        inside.setContentsMargins(16,16,16,16)
        inside.setSpacing(12)
        self.number(inside,"group_width","Ширина раскрытой группы"," px",True)
        self.number(inside,"group_columns","Значков в строке")
        self.number(inside,"group_opacity","Непрозрачность фона"," %",True)
        self.number(inside,"group_hover_delay","Раскрытие при наведении"," мс")
        self.number(inside,"group_collapse_delay","Сворачивание после ухода"," мс")
        self._module(inside,"groups_locked","Закрепить расположение","Запретить случайное перемещение за заголовок")
        self._module(inside,"group_collect_shortcuts","Убирать добавленные ярлыки с рабочего стола","Cloud Hub сначала сохраняет собственную копию .lnk или .url. Документы и папки остаются на своём месте.")
        inside.addWidget(self.action("Открыть библиотеку ярлыков ↗",lambda:self._url(QUrl.fromLocalFile(str(self.owner.modules.desktop.store.library.root)))))
        inside.addWidget(self.action("Выровнять группы на рабочем столе",self.owner.modules.desktop.arrange))
        inside.addStretch()
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(appearance)
        self.group_tabs.addTab(scroll,"Оформление и поведение")
        layout.addWidget(self.group_tabs,1)

    def library_page(self):
        layout = self._page()
        self.heading(layout,"Файлы и заметки","Полка хранит ссылки для быстрого доступа и перетаскивания. Заметки сохраняются на этом компьютере, без регистрации.")
        tabs = QTabWidget()
        files = QWidget()
        file_layout = QVBoxLayout(files)
        self.file_shelf = FileShelf(self.owner.settings.directory/"notch-files.json")
        self.file_shelf.setMinimumHeight(280)
        row = QHBoxLayout()
        for title,callback in (("＋ Файлы",self.file_shelf.add_files),("＋ Папка",self.file_shelf.add_folder),
                                ("Убрать ссылки",self.file_shelf.remove_selected)):
            row.addWidget(self.action(title,callback))
        file_layout.addLayout(row)
        file_layout.addWidget(self.file_shelf,1)
        from .control_center import text
        file_layout.addWidget(text("Двойной щелчок — открыть. Правый щелчок — расположение и действия. Можно перетянуть ссылку в Проводник, мессенджер или окно прикрепления файла. Оригиналы не перемещаются.",True))
        self.owner.notch_hub.shelf.changed.connect(self.file_shelf.reload)
        self.file_shelf.changed.connect(self.owner.notch_hub.shelf.reload)
        tabs.addTab(files,"Полка файлов")
        self.notebook = Notebook(self.owner.notch_hub)
        self.notebook.setMinimumHeight(340)
        tabs.addTab(self.notebook,"Заметки")
        layout.addWidget(tabs,1)

    def timer_page(self):
        from .control_center import text
        layout = self._page()
        self.heading(layout,"Фокус и таймер","От 1 минуты до 24 часов. Пауза сохраняет оставшееся время; изменение длительности начинает новый отсчёт.")
        frame,inside = self.card("Твой интервал")
        self.timer_label = TimerReadout(self.owner.notch_hub,48)
        inside.addWidget(self.timer_label)
        self.number(inside,"timer_minutes","Длительность"," мин")
        row = QHBoxLayout()
        self.focus_start = self.action("Начать",self.owner.notch_hub.toggle_timer)
        row.addWidget(self.focus_start)
        row.addWidget(self.action("Сбросить",self.owner.notch_hub.reset_timer))
        row.addWidget(self.action("Показать в чёлке",self.open_focus))
        inside.addLayout(row)
        quick = QHBoxLayout()
        for minutes in (5,15,25,45,60):
            quick.addWidget(self.action(str(minutes)+" мин",lambda _,n=minutes:self._setting("timer_minutes",n)))
        inside.addLayout(quick)
        layout.addWidget(frame)
        frame,inside = self.card("Завершение таймера","Звуковой сигнал, раскрытие вкладки «Фокус» и уведомление. Кнопка «Остановить» прекращает сигнал; новый отсчёт или сброс тоже убирает его.")
        self._module(inside,"timer_sound","Звуковой сигнал","Повторяется ограниченное время; громкость определяется обычной громкостью Windows")
        self.number(inside,"timer_alarm_seconds","Длительность сигнала"," сек")
        inside.addWidget(self.action("Прослушать сигнал",self.preview_timer_sound))
        layout.addWidget(frame)
        layout.addWidget(text("Меняй минуты колесом прямо на цифрах или щёлкни по ним и введи число. Enter применяет, Esc отменяет. Отсчёт продолжается при скрытом окне; полный выход останавливает таймер. В профиле «Игра» сигнал звучит без раскрытия чёлки поверх игры.",True))
        layout.addStretch()
        self.focus_tick = QTimer(self)
        self.focus_tick.setInterval(1000)
        self.focus_tick.timeout.connect(self.refresh_timer_display)
        self.pages.currentChanged.connect(lambda _:self.sync_focus_timer())

    def open_focus(self):
        self.owner._show_panel()
        self.owner.notch_hub.select_tab(1)

    def sync_focus_timer(self):
        if self.isVisible() and self.navigation.currentRow() in {self.page_indices["timer"],self.page_indices['hub']}:
            self.focus_tick.start()
            self.refresh_timer_display()
        else:
            self.focus_tick.stop()

    def refresh_timer_display(self):
        hub = self.owner.notch_hub
        self.timer_label.refresh()
        if hasattr(self,'overview_timer'): self.overview_timer.refresh()
        self.focus_start.setText("Остановить сигнал" if hub.alarm.active else "Пауза" if hub._timer_end else "Продолжить" if 0 < hub.timer_seconds() < self.owner.settings.get("timer_minutes")*60 else "Начать")

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
        self.heading(layout,"Горячие клавиши","Нажми поле, введи сочетание и нажми «Применить». «Отключить» освобождает клавишу. Занятые сочетания не заменяют рабочую настройку.")
        self.key_editors, self.key_status = {},{}
        for key,title in (("hotkey_search","Быстрый поиск"),("hotkey_island","Открыть чёлку"),("hotkey_hub","Открыть Cloud Hub")):
            frame,inside = self.card(title)
            row = QHBoxLayout()
            editor = ShortcutRecorder(self.owner,self.owner.settings.get(key))
            editor.setMaximumSequenceLength(1)
            self.key_editors[key] = editor
            row.addWidget(editor,1)
            row.addWidget(self.action("Применить",lambda _,k=key:self.apply_shortcut(k)))
            row.addWidget(self.action("Вручную…",lambda _,k=key:self.manual_shortcut(k)))
            row.addWidget(self.action("Отключить",lambda _,k=key:self._setting(k,"")))
            inside.addLayout(row)
            status = text("",True)
            inside.addWidget(status)
            self.key_status[key] = status
            layout.addWidget(frame)
        layout.addWidget(text("Используй Ctrl, Alt или Win с буквой, цифрой, Space или F1–F24. Системные зарезервированные сочетания могут быть недоступны. Трей остаётся доступен при отключённых клавишах.",True))
        layout.addStretch()

    def apply_shortcut(self,key):
        self._setting(key,self.key_editors[key].keySequence().toString(QKeySequence.SequenceFormat.PortableText))

    def manual_shortcut(self,key):
        value,ok = QInputDialog.getText(self,"Горячая клавиша","Например Alt+Space или Ctrl+Alt+Space",text=self.owner.settings.get(key))
        if ok:
            self._setting(key,value.strip())
            self.key_editors[key].setKeySequence(QKeySequence(self.owner.settings.get(key)))

    def application_page(self):
        layout = self._page()
        self.heading(layout,"Приложение","Оформление, запуск и подключение дополнительных инструментов.")
        frame,inside=self.card('Твой Cloud Hub')
        row=QHBoxLayout()
        row.addWidget(QLabel('Оформление'),1)
        self.theme_picker=QComboBox()
        for label,value in (('Тёмное','dark'),('Светлое','light'),('Как в Windows','system')): self.theme_picker.addItem(label,value)
        self.theme_picker.setCurrentIndex(max(0,self.theme_picker.findData(self.owner.settings.get('hub_theme'))))
        self.theme_picker.currentIndexChanged.connect(lambda _:self._setting('hub_theme',self.theme_picker.currentData()))
        row.addWidget(self.theme_picker)
        inside.addLayout(row)
        self._module(inside,'hub_animations','Плавные переходы','Короткие анимации навигации, переключателей и карточек')
        layout.addWidget(frame)
        self._module(layout,"autostart","Запускать с Windows","При входе в систему — только трей и выбранные модули")
        layout.addWidget(self.action('Версия и обновления →',lambda:self.navigate('updates')))
        layout.addWidget(self.action("Открыть папку данных",lambda:self._url(QUrl.fromLocalFile(str(self.owner.settings.directory)))))
        frame,inside = self.card("PowerToys · необязательное подключение","Для FancyZones и Workspaces. Поиск и группы Cloud Hub работают самостоятельно. При применении параметров PowerToys перезапускается. При выходе исходное подключение восстанавливается.")
        self.integration_status = QLabel()
        self.integration_status.setWordWrap(True)
        inside.addWidget(self.integration_status)
        self._module(inside,"layouts_enabled","Раскладки окон","Shift при перетаскивании — разместить окно в зоне")
        self._module(inside,"workspaces_enabled","Рабочие наборы","Сохранённые наборы приложений и расположения окон")
        self.connect_button = self.action("Подключить PowerToys",self._connect)
        self.restore_button = self.action("Восстановить исходное подключение",self._restore)
        inside.addWidget(self.connect_button)
        inside.addWidget(self.restore_button)
        inside.addWidget(self.action("Параметры PowerToys",lambda:self.owner.powertoys.launch("PowerToys.exe",["--open-settings"])))
        layout.addWidget(frame)
        layout.addStretch()

    def updates_page(self):
        from .update_ui import UpdatePanel
        layout=self._page()
        self.heading(layout,'Обновления','Новые возможности приходят сюда. Без ручной загрузки с GitHub.')
        self.update_panel=UpdatePanel(self.owner)
        layout.addWidget(self.update_panel)
        self._module(layout,'updates','Проверять автоматически','Раз в день и после запуска. Загрузка и перезапуск — когда ты решишь.')
        layout.addStretch()
