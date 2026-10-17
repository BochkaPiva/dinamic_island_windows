# SPDX-License-Identifier: GPL-3.0-only
"""Page factories: adding a page doesn't require changing the window shell."""
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QSpinBox, QSlider, QComboBox, QKeySequenceEdit, QLineEdit,
    QListWidget, QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox, QInputDialog)
from .modules import MODULES
from .policy import PROFILES
from .hub import FileShelf, fmt
from .notebook import Notebook
from .timer import TimerReadout


PAGES = (("hub","Обзор","overview_page"),
         ("island","Dynamic Island","island_page"),
         ("search","Поиск","search_page"),
         ("desktop","Рабочий стол","desktop_page"),
         ("library","Файлы и заметки","library_page"),
         ("timer","Фокус и таймер","timer_page"),
         ("shortcuts","Горячие клавиши","shortcuts_page"),
         ("workspaces","Окна и наборы","_workspaces_page"),
         ("integrations","Приложение","application_page"),
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
        layout = self._page()
        self.heading(layout,"Твоё рабочее пространство","Каждый модуль работает самостоятельно. Изменения настроек применяются сразу.")
        row = QHBoxLayout()
        self.profile_buttons = {}
        for key,title in PROFILES.items():
            btn = self.action(title,lambda _,k=key:self._setting("profile",k))
            btn.setCheckable(True)
            row.addWidget(btn)
            self.profile_buttons[key] = btn
        layout.addLayout(row)
        self.policy_label = text("",True)
        layout.addWidget(self.policy_label)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.module_status = {}
        for index,module in enumerate(MODULES):
            frame,inside = self.card(module.title,module.detail)
            status = text("",True)
            inside.addWidget(status)
            self.module_status[module.key] = status
            target = module.key if module.key not in {"layouts","workspaces"} else "workspaces"
            inside.addWidget(self.action("Настроить →",lambda _,k=target:self.navigate(k)))
            grid.addWidget(frame,index//2,index%2)
        layout.addLayout(grid)
        layout.addWidget(text("Авто: от сети — «Работа», без зарядки — «Батарея». От батареи спектр обновляется реже, но продолжает работать. «Игра» и пауза останавливают модули; запущенный таймер продолжает отсчёт.",True))
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
        from PyQt6.QtWidgets import QApplication
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
        from .control_center import text
        layout = self._page()
        self.heading(layout,"Группы рабочего стола","Наведи на заголовок — панель раскроется. Перетащи заголовок, чтобы переместить её. При работе в приложениях панели скрыты.")
        self._module(layout,"desktop_enabled","Сворачиваемые группы","Наш собственный модуль, без замены Проводника и изменения системных файлов")
        frame,inside = self.card("Мои группы","Добавляй файлы, папки и ярлыки кнопками или перетаскиванием на раскрытую группу. Двойной щелчок открывает элемент.")
        row = QHBoxLayout()
        self.group_picker = QComboBox()
        row.addWidget(self.group_picker,1)
        row.addWidget(self.action("＋ Группа",self.add_group))
        row.addWidget(self.action("Убрать группу",self.remove_group))
        inside.addLayout(row)
        name_row = QHBoxLayout()
        self.group_name = QLineEdit()
        self.group_name.setMaxLength(60)
        self.group_name.setPlaceholderText("Название группы")
        name_row.addWidget(self.group_name,1)
        name_row.addWidget(self.action("Переименовать",self.rename_group))
        inside.addLayout(name_row)
        self.group_items = QListWidget()
        self.group_items.setMinimumHeight(145)
        self.group_items.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.group_items.itemDoubleClicked.connect(self.open_group_item)
        inside.addWidget(self.group_items)
        actions = QHBoxLayout()
        for title,callback in (("＋ Файлы / ярлыки",self.group_add_files),("＋ Папка",self.group_add_folder),
                                ("Убрать ссылки",self.group_remove_items)):
            actions.addWidget(self.action(title,callback))
        inside.addLayout(actions)
        inside.addWidget(text("Файлы остаются на своём месте. Удаление группы или ссылки не удаляет оригиналы.",True))
        layout.addWidget(frame)
        frame,inside = self.card("Внешний вид и наведение")
        self.number(inside,"group_width","Ширина группы"," px",True)
        self.number(inside,"group_columns","Значков в строке")
        self.number(inside,"group_opacity","Непрозрачность фона"," %",True)
        self.number(inside,"group_hover_delay","Раскрытие при наведении"," мс")
        self.number(inside,"group_collapse_delay","Сворачивание после ухода"," мс")
        self._module(inside,"groups_locked","Закрепить расположение","Запретить случайное перемещение за заголовок")
        inside.addWidget(self.action("Выровнять группы на рабочем столе",self.owner.modules.desktop.arrange))
        layout.addWidget(frame)
        layout.addStretch()
        store = self.owner.modules.desktop.store
        store.changed.connect(self.refresh_groups)
        store.error.connect(self._message)
        self.group_picker.currentIndexChanged.connect(self.select_group)
        self.refresh_groups()

    def selected_group(self):
        return next((g for g in self.owner.modules.desktop.store.groups if g["id"] == self.group_picker.currentData()),None)

    def refresh_groups(self):
        current = self.group_picker.currentData()
        self.group_picker.blockSignals(True)
        self.group_picker.clear()
        for group in self.owner.modules.desktop.store.groups:
            self.group_picker.addItem(group["title"],group["id"])
        self.group_picker.setCurrentIndex(max(0,self.group_picker.findData(current)))
        self.group_picker.blockSignals(False)
        self.select_group()

    def select_group(self,*_):
        self.group_items.clear()
        group = self.selected_group()
        self.group_name.setText(group["title"] if group else "")
        if group:
            from PyQt6.QtWidgets import QListWidgetItem
            for path in group["items"]:
                item = QListWidgetItem(Path(path).name + (" · недоступен" if not Path(path).exists() else ""))
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole,path)
                self.group_items.addItem(item)

    def add_group(self):
        group = self.owner.modules.desktop.store.add()
        if group:
            self.group_picker.setCurrentIndex(self.group_picker.findData(group["id"]))
            self.group_name.setFocus()
            self.group_name.selectAll()
        else:
            self._message("Можно создать до 30 групп")

    def remove_group(self):
        group = self.selected_group()
        if group and QMessageBox.question(self,"Убрать группу?","Убрать «"+group["title"]+"»? Файлы на диске останутся.") == QMessageBox.StandardButton.Yes:
            self.owner.modules.desktop.store.remove(group["id"])

    def rename_group(self):
        group = self.selected_group()
        if group and self.group_name.text().strip():
            group["title"] = self.group_name.text().strip()
            self.owner.modules.desktop.store.save()

    def group_add_files(self):
        group = self.selected_group()
        if group:
            paths,_ = QFileDialog.getOpenFileNames(self,"Добавить ссылки на файлы и ярлыки")
            self.owner.modules.desktop.store.add_paths(group,paths)
            self.owner.modules.desktop.panels[group["id"]].shelf.reload()

    def group_add_folder(self):
        group = self.selected_group()
        if group:
            path = QFileDialog.getExistingDirectory(self,"Добавить ссылку на папку")
            if path:
                self.owner.modules.desktop.store.add_paths(group,[path])
                self.owner.modules.desktop.panels[group["id"]].shelf.reload()

    def group_remove_items(self):
        group = self.selected_group()
        if group:
            paths = {i.data(Qt.ItemDataRole.UserRole) for i in self.group_items.selectedItems()}
            group["items"] = [p for p in group["items"] if p not in paths]
            self.owner.modules.desktop.store.save()
            self.owner.modules.desktop.panels[group["id"]].shelf.reload()

    def open_group_item(self,item):
        self._url(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))

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
        if self.isVisible() and self.navigation.currentRow() == self.page_indices["timer"]:
            self.focus_tick.start()
            self.refresh_timer_display()
        else:
            self.focus_tick.stop()

    def refresh_timer_display(self):
        hub = self.owner.notch_hub
        self.timer_label.refresh()
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
        self.heading(layout,"Приложение","Профили сохраняют твои настройки модулей. Выключенный модуль не выполняет фоновую работу.")
        self._module(layout,"autostart","Запускать с Windows","При входе в систему — только трей и выбранные модули")
        self._module(layout,"updates","Проверять обновления","Проверка раз в день; установка запускается вручную")
        layout.addWidget(self.action("Проверить обновления",self.owner._check_update))
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
