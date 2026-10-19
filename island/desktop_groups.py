# SPDX-License-Identifier: GPL-3.0-only
"""Desktop groups with owned shortcuts; documents remain references."""
import json
import math
import time
from contextlib import contextmanager
from pathlib import Path
import uuid
import os
import tempfile
from PySide6.QtCore import Qt, QObject, QTimer, QEvent, QSize, QRect, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QTextLayout, QTextOption
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QFileDialog, QMenu, QStyledItemDelegate, QStyle,
    QInputDialog, QMessageBox, QDialog, QDialogButtonBox)
from .hub import FileShelf
from .platform_win import anchor_desktop_panel, disable_window_transitions, exclude_from_peek
from .motion import DampedValue, smoothstep
from .style import font
from .brand import resolved_palette
from .ui_tokens import LineIcon, IconButton, TEXT, SURFACE
from .shortcut_library import ShortcutLibrary
from .scrolling import SmoothScroll
from .group_icons import group_icons


DIALOG_STYLE="""
    QDialog,QMessageBox {background:#202227;color:#f4f4f6;}
    QLabel {background:transparent;color:#f4f4f6;font:13px 'Golos Text';}
    QLineEdit {background:#292c33;color:#f4f4f6;border:1px solid #41454e;
        border-radius:7px;padding:9px;min-width:240px;selection-background-color:#4b637a;selection-color:white;}
    QPushButton {background:#2b2e36;color:#f4f4f6;border:1px solid #41454e;
        border-radius:7px;padding:8px 15px;min-width:70px;}
    QPushButton:hover {background:#3a414e;}
    QPushButton:disabled {color:#747985;}
"""


def group_dialog_style(parent):
    window=parent.window() if parent is not None else None
    if window is not None and hasattr(window,'colors'):
        from .hub_ui import stylesheet
        return stylesheet(window.colors)
    return DIALOG_STYLE


def ask_group_title(parent,caption,value,verb):
    dialog=QInputDialog(parent)
    dialog.setStyleSheet(group_dialog_style(parent))
    dialog.setWindowTitle(caption)
    dialog.setLabelText("Название группы:")
    dialog.setTextValue(value)
    dialog.setOkButtonText(verb)
    dialog.setCancelButtonText("Отмена")
    field=dialog.findChild(QLineEdit)
    field.setMaxLength(60)
    accept=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
    field.textChanged.connect(lambda text:accept.setEnabled(bool(text.strip())))
    accept.setEnabled(bool(value.strip()))
    accepted=dialog.exec()==QDialog.DialogCode.Accepted
    title=dialog.textValue()
    dialog.deleteLater()
    return title,accepted


class GroupStore(QObject):
    changed = Signal()
    error = Signal(str)
    notice = Signal(str)

    def __init__(self, directory, collect_desktop=True, desktop_roots=None, migrate=True, access=None):
        super().__init__()
        self.path = Path(directory)/"desktop-groups.json"
        self.library=ShortcutLibrary(directory,desktop_roots)
        self.collect_desktop=collect_desktop
        self.last_warning=""
        self.groups = []
        self.access = access
        self._read_failed = False
        loaded = False
        missing = False
        try:
            for attempt in range(3):
                try:
                    raw = self.path.read_text(encoding="utf-8-sig")
                    break
                except FileNotFoundError:
                    raise
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(.025)
            document = json.loads(raw)
            if not isinstance(document, dict) or not isinstance(document.get("groups"), list):
                raise ValueError("Invalid group document")
            loaded = True
            for record in document.get("groups", [])[:30]:
                if not isinstance(record, dict) or not isinstance(record.get("title"), str):
                    continue
                self.groups.append({"id": str(uuid.UUID(record["id"])), "title": record["title"][:60],
                    "items": list(dict.fromkeys(p for p in record.get("items", []) if isinstance(p, str)))[:100],
                    "x": max(0., min(1., float(record.get("x", .03)))),
                    "y": max(0., min(1., float(record.get("y", .12)))),
                    "screen": str(record.get("screen", ""))})
        except FileNotFoundError:
            missing = True
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            # Never turn a read failure into a fresh install or overwrite the evidence.
            self._read_failed = True
            self.last_warning = "Не удалось прочитать группы. Данные сохранены; повторим загрузку автоматически."
        if not self.groups and missing:
            self.add("Работа", .03)
            self.add("Личное", .31)
        elif loaded and migrate and not self._read_failed:
            self.migrate_shortcuts()

    def warn(self,message):
        self.last_warning=message
        self.error.emit(message)

    def collect(self,paths):
        enabled=self.collect_desktop() if callable(self.collect_desktop) else self.collect_desktop
        if enabled:
            for path in dict.fromkeys(paths):
                try:
                    self.library.collect(path)
                except OSError:
                    self.warn("Ярлык сохранён в Nelviro, но убрать его с рабочего стола не удалось: "+Path(path).name)

    def restore_shortcut(self,path):
        try:
            result=self.library.restore(path)
            self.notice.emit("Ярлык скопирован на рабочий стол: "+result.name)
            return result
        except OSError as exc:
            self.warn(str(exc))
            return None

    def migrate_shortcuts(self):
        import shutil
        replacements={}
        try:
            candidates=[p for group in self.groups for p in group['items']
                if Path(p).suffix.casefold() in {'.lnk','.url'} and Path(p).is_file() and not self.library.owns(p)]
            if not candidates:
                return
            backup=self.path.with_suffix('.before-shortcuts.json')
            if not backup.exists():
                shutil.copy2(self.path,backup)
            for path in dict.fromkeys(candidates):
                replacements[path]=self.library.capture(path)
        except OSError:
            self.warn("Не удалось перенести ярлыки в библиотеку. Исходные ярлыки оставлены на месте.")
            return
        previous=[g['items'] for g in self.groups]
        for group in self.groups:
            group['items']=list(dict.fromkeys(replacements.get(p,p) for p in group['items']))
        if self.save():
            self.collect(replacements.values())
        else:
            for group,items in zip(self.groups,previous): group['items']=items

    def save(self):
        if self._read_failed:
            self.warn("Сохранение групп приостановлено: сначала нужно восстановить чтение существующих данных.")
            return False
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Validate the previous document before retaining it as a recovery generation.
            if self.path.exists():
                previous = self.path.read_bytes()
                parsed = json.loads(previous.decode('utf-8-sig'))
                if not isinstance(parsed, dict) or not isinstance(parsed.get('groups'), list):
                    raise ValueError('Invalid previous groups')
                backup = self.path.with_suffix('.last-good.json')
                with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(previous)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(backup)
                temporary = None
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps({"version": 1, "groups": self.groups}, ensure_ascii=False, indent=2).encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
            temporary = None
            self.changed.emit()
            return True
        except (OSError, ValueError):
            self.error.emit("Не удалось сохранить группы на диск")
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def retry_load(self):
        if not self._read_failed:
            return
        try:
            document = json.loads(self.path.read_text(encoding='utf-8-sig'))
            if not isinstance(document, dict) or not isinstance(document.get('groups'), list):
                return
        except (OSError, ValueError):
            return
        retry = GroupStore(self.path.parent, collect_desktop=False, desktop_roots=[], migrate=False)
        if retry._read_failed:
            return
        self.groups = retry.groups
        self._read_failed = False
        self.last_warning = ""
        self.changed.emit()
        self.notice.emit("Группы загружены повторно. Ваши данные на месте.")

    def find(self,identifier):
        return next((g for g in self.groups if g["id"]==identifier),None)

    def next_title(self):
        titles={g["title"].casefold() for g in self.groups}
        title,index="Новая группа",1
        while title.casefold() in titles:
            index+=1
            title="Новая группа "+str(index)
        return title

    def add(self, title=None, x=None):
        if self.access is not None:
            decision=self.access.capacity('desktop.groups.active',len(self.groups))
            if not decision.allowed:
                self.error.emit(decision.reason)
                return None
        if len(self.groups) >= 30:
            return None
        title=self.next_title() if title is None else title.strip()[:60]
        if not title:
            self.error.emit("Введите название группы")
            return None
        group = {"id": str(uuid.uuid4()), "title": title[:60] or "Новая группа", "items": [],
                 "x": x if x is not None else .03+(len(self.groups)%3)*.32,
                 "y": .12+min(.7, len(self.groups)//3*.27), "screen": ""}
        self.groups.append(group)
        if self.save():
            return group
        self.groups.remove(group)
        return None

    def rename(self,identifier,title):
        group=self.find(identifier)
        title=title.strip()[:60]
        if not group or not title:
            self.error.emit("Введите название группы" if group else "Группа уже удалена")
            return False
        previous=group["title"]
        if previous==title:
            return True
        group["title"]=title
        if self.save():
            return True
        group["title"]=previous
        return False

    def make_active(self,identifier):
        group=self.find(identifier)
        if not group:
            return False
        previous=list(self.groups)
        self.groups=[group]+[item for item in self.groups if item['id']!=identifier]
        if self.save():
            return True
        self.groups=previous
        return False

    def remove(self, identifier):
        previous=self.groups
        self.groups = [g for g in self.groups if g["id"] != identifier]
        if len(previous)==len(self.groups):
            return False
        if self.save():
            return True
        self.groups=previous
        return False

    def set_paths(self,identifier,paths):
        group=self.find(identifier)
        if not group:
            return False
        previous=group["items"]
        group["items"]=list(dict.fromkeys(p for p in paths if isinstance(p,str)))[:100]
        if self.save():
            return True
        group["items"]=previous
        return False

    def add_paths(self, group, paths):
        if self.find(group['id']) is None:
            return False
        values=group["items"][:]
        captured=[]
        try:
            for value in paths:
                path=Path(value)
                if not path.exists() or len(values)>=100:
                    continue
                stored=self.library.capture(path)
                if stored not in values:
                    values.append(stored)
                captured.append(stored)
        except OSError:
            self.warn("Не удалось сохранить ярлык. Исходный файл оставлен на месте.")
            return False
        if self.set_paths(group["id"],values):
            self.collect(captured)
            return True
        return False


class GroupItemDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        grid=self.parent().gridSize()
        return QSize(max(1,grid.width()-4),max(1,grid.height()-4))

    def paint(self,painter,option,index):
        p=painter
        p.save()
        p.setClipRect(option.rect)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect=QRectF(option.rect).adjusted(3,2,-3,-2)
        selected=bool(option.state & QStyle.StateFlag.State_Selected)
        hovered=bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255,255,255,24 if selected else 12 if hovered else 0))
        p.drawRoundedRect(rect,9,9)
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            icon.paint(p,QRect(round(rect.center().x()-20),round(rect.y()+7),40,40))
        p.setFont(font(11,400))
        p.setPen(QColor(self.parent().panel._brand_colors['text']))
        label=index.data(Qt.ItemDataRole.DisplayRole) or ""
        width=max(10,round(rect.width()-6))
        text_layout=QTextLayout(label,p.font())
        text_option=QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        text_layout.setTextOption(text_option)
        text_layout.beginLayout()
        first=text_layout.createLine()
        if first.isValid(): first.setLineWidth(width)
        length=first.textLength() if first.isValid() else len(label)
        text_layout.endLayout()
        lines=[p.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,width)] if ' ' not in label else [label[:length].strip()]
        if ' ' in label and length<len(label):
            lines.append(p.fontMetrics().elidedText(label[length:].strip(),Qt.TextElideMode.ElideRight,width))
        for number,line in enumerate(lines):
            p.drawText(QRectF(rect.x()+3,rect.y()+53+number*15,width,15),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignVCenter,line)
        p.restore()


class GroupShelf(FileShelf):
    def __init__(self, panel):
        self.panel = panel
        # No separate on-disk shelf; the group's store is the single source of truth.
        super().__init__(None)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWordWrap(True)
        self.setIconSize(QSize(38, 38))
        self.setItemDelegate(GroupItemDelegate(self))
        self.setMouseTracking(True)
        self.setSpacing(2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.smooth_scroll=SmoothScroll(self)
        group_icons().changed.connect(self.refresh_icon)
        self.reload()

    def icon_for(self,path):
        return group_icons().icon(path)

    def extra_context_actions(self,menu,item):
        path=item.data(Qt.ItemDataRole.UserRole)
        store=self.panel.manager.store
        if store.library.owns(path):
            menu.addAction("Скопировать ярлык на рабочий стол",lambda:store.restore_shortcut(path))

    def refresh_icon(self,path):
        for index in range(self.count()):
            item=self.item(index)
            if item.data(Qt.ItemDataRole.UserRole)==path:
                item.setIcon(self.icon_for(path))

    def wheelEvent(self,event):
        self.smooth_scroll.wheel(event)

    def hideEvent(self,event):
        self.smooth_scroll.stop()
        super().hideEvent(event)

    def add_paths(self,paths,save=True,keep_missing=False):
        if save:
            self.panel.manager.store.add_paths(self.panel.group,paths)
        else:
            super().add_paths(paths,save=False,keep_missing=keep_missing)

    def reload(self):
        position=self.verticalScrollBar().value()
        selected=set(i.data(Qt.ItemDataRole.UserRole) for i in self.selectedItems())
        self.clear()
        self.add_paths(self.panel.group["items"], save=False, keep_missing=True)
        for index in range(self.count()):
            item=self.item(index)
            path=Path(item.data(Qt.ItemDataRole.UserRole))
            item.setText(path.stem if path.suffix.casefold() in {".lnk",".url"} else path.name)
            item.setSelected(str(path) in selected)
        self.filter(self.panel.search.text())
        self.doItemsLayout()
        self.verticalScrollBar().setValue(position)
        if hasattr(self.panel,"animation") and self.panel.expanded:
            self.panel.animate(True, refresh=True)

    def persist(self):
        if not self.panel.manager.store.set_paths(self.panel.group["id"],self.paths()):
            self.reload()
        self.panel.animate(True)

    def filter(self, query):
        for i in range(self.count()):
            self.item(i).setHidden(query.casefold() not in self.item(i).text().casefold())


class GroupPanel(QWidget):
    def __init__(self, manager, group):
        super().__init__(f=Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.manager, self.group = manager, group
        self.expanded = False
        self.drag_origin = None
        self.interactions = 0
        self.extent = DampedValue()
        self.extent.value = 44
        self.target_height = 44
        self.texture = QPixmap()
        self.full_height = 112
        self.closed_width = 216
        self.setWindowTitle("Nelviro — группа «"+group["title"]+"»")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.header = QWidget(self)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(14, 0, 8, 0)
        header.setSpacing(3)
        header.addWidget(LineIcon("folder",20))
        header.addSpacing(8)
        self.name = QLabel(group["title"])
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setObjectName("groupName")
        self.name.setFont(font(15,500))
        self.name.setMinimumWidth(0)
        self.name.installEventFilter(self)
        self.name.setToolTip("Наведи для раскрытия. Перетащи заголовок, чтобы переместить группу.")
        header.addWidget(self.name, 1)
        self.chevron = IconButton("chevron","Свернуть группу")
        self.chevron.clicked.connect(lambda: self.animate(not self.expanded))
        header.addWidget(self.chevron)
        slot=QWidget()
        slot.setFixedSize(28,28)
        self.count_label=QLabel(slot)
        self.count_label.setObjectName("groupCount")
        self.count_label.setGeometry(slot.rect())
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        menu = IconButton("dots","Меню группы",slot)
        self.menu_button = menu
        menu.clicked.connect(self.menu)
        header.addWidget(slot)
        self.body = QWidget(self)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(10, 4, 10, 10)
        body.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Фильтр…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(30)
        body.addWidget(self.search)
        self.shelf = GroupShelf(self)
        self.shelf.setMinimumHeight(0)
        self.search.textChanged.connect(self.shelf.filter)
        body.addWidget(self.shelf, 1)
        self.empty = QPushButton("＋  Добавить")
        self.empty.setFixedHeight(30)
        self.empty.clicked.connect(self.add_files)
        body.addWidget(self.empty)
        self.body.hide()
        self.hover = QTimer(self)
        self.hover.setSingleShot(True)
        self.hover.timeout.connect(lambda: self.animate(True))
        self.collapse = QTimer(self)
        self.collapse.setSingleShot(True)
        self.collapse.timeout.connect(self._collapse)
        self.animation = QTimer(self)
        self.animation.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation.timeout.connect(self._frame)
        self.configure()
        self.setFixedHeight(44)
        self.place()
        self._header_state(False)

    def configure(self):
        colors=resolved_palette(self.manager.owner.settings)
        if getattr(self,'_brand_colors',None)!=colors:
            from .hub_ui import stylesheet
            self._brand_colors=colors
            self.setStyleSheet(stylesheet(colors)+f"""
                QWidget {{font-size:12px;}}
                QLabel#groupName {{font-size:15px;font-weight:500;}}
                QPushButton {{background:transparent;border:0;padding:5px;}}
                QPushButton:hover {{background:{colors['raised']};}}
                QLineEdit {{border:0;padding:7px;}}
                QListWidget {{border:0;background:transparent;padding:2px;}}
            """)
            self.texture=QPixmap()

        s = self.manager.owner.settings
        old_width, old_grid = getattr(self,"full_width",0), self.shelf.gridSize()
        self.full_width = s.get("group_width")
        self.closed_width = min(self.full_width,max(216,min(264,self.name.fontMetrics().horizontalAdvance(self.group["title"])+88)))
        if not self.animation.isActive():
            self.setFixedWidth(self.full_width if self.expanded else self.closed_width)
        self.shelf.setGridSize(QSize((self.full_width-30)//s.get("group_columns"), 96))
        self.header.setGeometry(0, 0, self.width(), 44)
        self.name.setText(self.group["title"])
        self.setWindowTitle("Nelviro — группа «"+self.group["title"]+"»")
        self.count_label.setText(str(self.shelf.count()))
        changed = old_width != self.full_width or old_grid != self.shelf.gridSize()
        if self.expanded or self.animation.isActive():
            self.animate(self.expanded,refresh=changed)
        self.update()

    def _header_state(self,hovered=None):
        hovered=self.underMouse() if hovered is None else hovered
        controls=hovered or self.expanded or self.interactions>0
        self.menu_button.setVisible(controls)
        self.count_label.setVisible(not controls)
        self.chevron.setVisible(self.expanded)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"header"):
            self.header.setGeometry(0,0,self.width(),44)

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == self.group["screen"]), QApplication.primaryScreen())
        r = screen.availableGeometry()
        self.move(r.left()+round(self.group["x"]*max(0,r.width()-self.full_width)),
                  r.top()+round(self.group["y"]*max(0,r.height()-44)))

    def animate(self, expanded, refresh=False):
        rows = math.ceil(self.shelf.count()/self.manager.owner.settings.get("group_columns"))
        available = self.screen().availableGeometry().bottom()-self.y()+1
        full = max(44, min(44 + (min(4, rows)*100 + 90 if rows else 68), available))
        height = full if expanded else 44
        if expanded == self.expanded and height == self.target_height and not refresh:
            return
        was_moving = self.animation.isActive()
        if not was_moving or self.texture.isNull() or refresh:
            self.search.setVisible(bool(rows))
            self.shelf.setVisible(bool(rows))
            self.full_height=full
            self.body.setGeometry(0, 44, self.full_width, max(1, full-44))
            self.body.ensurePolished()
            self.body.layout().activate()
            self.texture = self.body.grab()
        self.expanded = expanded
        self._header_state()
        self.target_height = height
        self.body.hide()
        if not was_moving:
            self.extent.value, self.extent.velocity = float(self.height()), 0.
        self.last_frame = time.monotonic()
        self.animation.start(8 if self.screen().refreshRate() >= 90 else 16)

    def _frame(self):
        now = time.monotonic()
        height = self.extent.step(self.target_height, now-self.last_frame, 23)
        self.last_frame = now
        progress=max(0.,min(1.,(height-44)/max(1,self.full_height-44)))
        self.setFixedSize(round(self.closed_width+(self.full_width-self.closed_width)*progress),max(44,round(height)))
        if abs(height-self.target_height) < .04 and abs(self.extent.velocity) < .8:
            self.animation.stop()
            self.extent.value, self.extent.velocity = float(self.target_height), 0.
            self.setFixedHeight(self.target_height)
            self.setFixedWidth(self.full_width if self.expanded else self.closed_width)
            self.body.setVisible(self.expanded)
            self.texture = QPixmap()
        self.update()

    def enterEvent(self, event):
        self._header_state(True)
        self.collapse.stop()
        if not self.expanded:
            self.hover.start(self.manager.owner.settings.get("group_hover_delay"))

    def leaveEvent(self, event):
        self._header_state(False)
        self.hover.stop()
        self.collapse.start(self.manager.owner.settings.get("group_collapse_delay"))

    def _collapse(self):
        if self.underMouse() or QApplication.activePopupWidget() or self.interactions or self.search.hasFocus():
            self.collapse.start(500)
        else:
            self.animate(False)

    def eventFilter(self, obj, event):
        if obj is self.name:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if not self.manager.owner.settings.get("groups_locked"):
                    self.drag_origin = event.globalPosition().toPoint()-self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self.drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint()-self.drag_origin)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self.drag_origin is not None:
                self.drag_origin = None
                r = self.screen().availableGeometry()
                self.group.update(x=max(0.,min(1.,(self.x()-r.left())/max(1,r.width()-self.full_width))),
                    y=max(0.,min(1.,(self.y()-r.top())/max(1,r.height()-44))), screen=self.screen().name())
                self.manager.store.save()
                self.place()
                return True
        return super().eventFilter(obj,event)

    def add_files(self):
        with self.interacting():
            paths, _ = QFileDialog.getOpenFileNames(self,"Добавить ссылки на файлы и программы")
        self.manager.store.add_paths(self.group, paths)
        self.shelf.reload()
        self.animate(True)

    def build_menu(self):
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        for key,title in (("rename","Переименовать…"),("settings","Настроить эту группу…"),
                          ("files","Добавить файлы / ярлыки…"),("folder","Добавить папку…")):
            menu.addAction(title).setData(key)
        menu.addSeparator()
        menu.addAction("Создать новую группу…").setData("create")
        menu.addAction("Выровнять группы").setData("arrange")
        menu.addSeparator()
        menu.addAction("Удалить эту группу…").setData("delete")
        return menu

    def perform_action(self,key):
        # Dispatch after QMenu.exec has returned: deleting its owning panel
        # inside the menu's nested event loop can otherwise invalidate widgets.
        identifier=self.group["id"]
        if key=="settings":
            self.manager.open_settings(identifier)
        elif key in {"rename","delete","create"}:
            with self.interacting():
                getattr(self.manager,"request_"+key)(identifier,self)
        elif key=="files":
            self.add_files()
        elif key=="folder":
            self.add_folder()
        elif key=="arrange":
            self.manager.arrange()

    def menu(self):
        self.collapse.stop()
        menu=self.build_menu()
        with self.interacting():
            selected=menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
            key=selected.data() if selected else None
        menu.deleteLater()
        self.collapse.start(800)
        if key:
            self.perform_action(key)

    @contextmanager
    def interacting(self):
        self.interactions += 1
        self.hover.stop()
        self.collapse.stop()
        try:
            yield
        finally:
            self.interactions -= 1
            self.collapse.start(self.manager.owner.settings.get("group_collapse_delay"))

    def add_folder(self):
        with self.interacting():
            path = QFileDialog.getExistingDirectory(self,"Добавить ссылку на папку")
        if path:
            self.manager.store.add_paths(self.group,[path])
            self.shelf.reload()
            self.animate(True)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():
            self.hover.stop()
            self.collapse.stop()
            self.animate(True)
            event.acceptProposedAction()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key.Key_Escape:
            self.search.clearFocus()
            self.animate(False)
            event.accept()
        else:
            super().keyPressEvent(event)

    def dropEvent(self,event):
        self.manager.store.add_paths(self.group,[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        self.shelf.reload()
        self.animate(True)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self,event):
        self.collapse.start(self.manager.owner.settings.get("group_collapse_delay"))
        event.accept()

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        progress=max(0.,min(1.,(self.height()-44)/max(1,self.full_height-44)))
        colors=self._brand_colors
        color = QColor(colors['surface'])
        color.setAlpha(round((150+90*progress)*self.manager.owner.settings.get("group_opacity")/100))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        path = QPainterPath()
        radius=16+4*progress
        path.addRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),radius,radius)
        p.fillPath(path,color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(colors['line']),1))
        p.drawPath(path)
        if self.animation.isActive() and not self.texture.isNull():
            p.setClipPath(path)
            p.setClipRect(QRect(0,44,self.width(),max(0,self.height()-44)),Qt.ClipOperation.IntersectClip)
            full = self.texture.height()/self.texture.devicePixelRatioF()
            progress = min(1., max(0., (self.height()-44)/max(1,full)))
            p.setOpacity(smoothstep(progress/.7))
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(self.width()*.02*(1-progress), 44-10*(1-progress))
            p.scale(.96+.04*progress,.96+.04*progress)
            p.drawPixmap(0,0,self.texture)

    def showEvent(self,event):
        super().showEvent(event)
        exclude_from_peek(self)
        disable_window_transitions(self)

    def hideEvent(self,event):
        self.hover.stop()
        self.collapse.stop()
        self.animation.stop()
        self.expanded = False
        self.body.hide()
        self.setFixedHeight(44)
        self.setFixedWidth(self.closed_width)
        self.target_height = 44
        self.extent.value, self.extent.velocity = 44., 0.
        self.texture = QPixmap()
        super().hideEvent(event)


class DesktopGroups(QObject):
    def __init__(self,owner):
        super().__init__(owner)
        self.owner, self.enabled = owner, False
        self.store = GroupStore(owner.settings.directory,collect_desktop=lambda:owner.settings.get('group_collect_shortcuts'),
                                access=getattr(owner,'access',None))
        self.store.notice.connect(self.notify)
        self.store.error.connect(self.notify)
        self.panels = {}
        self.store.changed.connect(self.reconcile)
        if self.store.access:
            self.store.access.changed.connect(self.reconcile)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)  # Shell recovery only; foreground changes never hide/show tiles.
        self.timer.timeout.connect(self.tick)
        QApplication.instance().screenAdded.connect(self.screen_added)
        QApplication.instance().screenRemoved.connect(lambda _:self.reposition())
        for screen in QApplication.screens():
            screen.availableGeometryChanged.connect(lambda _:self.reposition())
        self.reconcile()

    def notify(self,message):
        if self.owner._services and getattr(self.owner,'tray',None) and not (self.owner.control_center and self.owner.control_center.isVisible()):
            self.owner.tray.showMessage('Nelviro',message)

    def screen_added(self,screen):
        screen.availableGeometryChanged.connect(lambda _:self.reposition())
        self.reposition()

    def reconcile(self):
        ids = {g["id"] for g in self.store.groups}
        for identifier in set(self.panels)-ids:
            panel=self.panels.pop(identifier)
            panel.hide()
            panel.deleteLater()
        for group in self.store.groups:
            if group["id"] not in self.panels:
                self.panels[group["id"]] = GroupPanel(self,group)
            else:
                panel = self.panels[group["id"]]
                if panel.shelf.paths() != group["items"]:
                    panel.shelf.reload()
                panel.configure()
        self.repair_overlaps()
        if self.enabled:
            self.tick()

    def repair_overlaps(self, force=False):
        """Move colliding headers only; keep identities, references and a backup."""
        occupied = {}
        moved = False
        for panel in self.panels.values():
            panel.place()
            screen = panel.screen()
            bounds = screen.availableGeometry()
            used = occupied.setdefault(screen.name(), [])
            rect = QRect(panel.x(), panel.y(), panel.full_width, 44)
            if force or any(rect.adjusted(-6,-6,6,6).intersects(old) for old in used):
                step = panel.full_width+20
                candidates = [QRect(bounds.x()+20+x, bounds.y()+70+y, panel.full_width,44)
                    for y in range(0,max(1,bounds.height()-114),280)
                    for x in range(0,max(1,bounds.width()-panel.full_width-20),step)]
                # Dense fallback for many groups/small screens, still no coincident headers.
                candidates += [QRect(bounds.x()+12+x,bounds.y()+12+y,panel.full_width,44)
                    for y in range(0,max(1,bounds.height()-56),60)
                    for x in range(0,max(1,bounds.width()-panel.full_width-12),step)]
                rect = next((r for r in candidates if not any(r.adjusted(-6,-6,6,6).intersects(old) for old in used)),rect)
                if rect.topLeft() != panel.pos():
                    if not moved and self.store.path.exists():
                        import shutil
                        backup = self.store.path.with_suffix(".before-arrange.json")
                        if not backup.exists():
                            try:
                                shutil.copy2(self.store.path,backup)
                            except OSError:
                                self.store.error.emit("Не удалось сохранить резервную копию расположения групп")
                                return
                    panel.group.update(x=(rect.x()-bounds.x())/max(1,bounds.width()-panel.full_width),
                        y=(rect.y()-bounds.y())/max(1,bounds.height()-44), screen=screen.name())
                    panel.place()
                    moved = True
            used.append(rect)
        if moved:
            # Avoid a recursive changed/reconcile pass while migrating positions.
            self.store.blockSignals(True)
            try:
                self.store.save()
            finally:
                self.store.blockSignals(False)

    def arrange(self):
        self.repair_overlaps(force=True)

    def reposition(self):
        for panel in self.panels.values():
            panel.place()
        self.repair_overlaps()

    def set_enabled(self,enabled):
        enabled = enabled and self.owner._services
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.timer.start()
            self.tick()
        else:
            self.timer.stop()
            for panel in self.panels.values():
                panel.hide()

    def tick(self):
        self.store.retry_load()
        if not self.enabled:
            return
        active = self.store.access.active_ids(self.store.groups) if self.store.access else set(self.panels)
        for identifier,panel in self.panels.items():
            if identifier not in active:
                panel.hide()
                continue
            shown = not panel.isVisible()
            if shown:
                if not anchor_desktop_panel(panel):
                    continue  # Explorer is not ready yet during login.
                panel.show()
            panel.desktop_anchored = anchor_desktop_panel(panel,reset=shown)

    def request_create(self,identifier=None,parent=None):
        if len(self.store.groups)>=30:
            QMessageBox.information(parent,"Группы","Можно создать до 30 групп")
            return None
        title,ok=ask_group_title(parent,"Создать группу",self.store.next_title(),"Создать")
        return self.store.add(title) if ok else None

    def request_rename(self,identifier,parent=None):
        group=self.store.find(identifier)
        if not group:
            return False
        title,ok=ask_group_title(parent,"Переименовать группу",group["title"],"Сохранить")
        return self.store.rename(identifier,title) if ok else False

    def request_delete(self,identifier,parent=None):
        group=self.store.find(identifier)
        if not group:
            return False
        dialog=QMessageBox(parent)
        dialog.setStyleSheet(group_dialog_style(parent))
        dialog.setWindowTitle("Удалить группу?")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("Удалить группу «"+group["title"]+"»?\n\nФайлы и папки на диске останутся.\nСохранённые ярлыки останутся в библиотеке Nelviro.")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText("Удалить группу")
        dialog.button(QMessageBox.StandardButton.No).setText("Отмена")
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setEscapeButton(QMessageBox.StandardButton.No)
        answer=dialog.exec()
        dialog.deleteLater()
        return self.store.remove(identifier) if answer==QMessageBox.StandardButton.Yes else False

    def open_settings(self,identifier=None):
        self.owner.show_hub()
        center=self.owner.control_center
        center.navigate("desktop")
        center.group_tabs.setCurrentIndex(0)
        if identifier:
            center.group_editor.select_id(identifier)

    def shutdown(self):
        self.enabled = False
        self.timer.stop()
        for panel in self.panels.values():
            panel.close()
