# SPDX-License-Identifier: GPL-3.0-only
"""Desktop-only roll-up groups. Links stay in place; Explorer is never patched."""
import json
import math
import time
from contextlib import contextmanager
from pathlib import Path
import uuid
from PyQt6.QtCore import Qt, QObject, QTimer, QEvent, QSize, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QFileDialog, QMenu, QStyledItemDelegate, QStyle,
    QInputDialog, QMessageBox, QDialog, QDialogButtonBox)
from .hub import FileShelf
from .platform_win import anchor_desktop_panel, disable_window_transitions, exclude_from_peek
from .motion import DampedValue, smoothstep
from .style import font
from .ui_tokens import LineIcon, IconButton, TEXT, SURFACE


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


def ask_group_title(parent,caption,value,verb):
    dialog=QInputDialog(parent)
    dialog.setStyleSheet(DIALOG_STYLE)
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
    changed = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, directory):
        super().__init__()
        self.path = Path(directory)/"desktop-groups.json"
        self.groups = []
        loaded = False
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            loaded = isinstance(document.get("groups"),list)
            for record in document.get("groups", [])[:30]:
                if not isinstance(record, dict) or not isinstance(record.get("title"), str):
                    continue
                self.groups.append({"id": str(uuid.UUID(record["id"])), "title": record["title"][:60],
                    "items": list(dict.fromkeys(p for p in record.get("items", []) if isinstance(p, str)))[:100],
                    "x": max(0., min(1., float(record.get("x", .03)))),
                    "y": max(0., min(1., float(record.get("y", .12)))),
                    "screen": str(record.get("screen", ""))})
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            # Preserve an unreadable file for recovery instead of silently overwriting it.
            if self.path.exists():
                import shutil
                shutil.copy2(self.path, self.path.with_suffix(".recovery.json"))
        if not self.groups and not loaded:
            self.add("Работа", .03)
            self.add("Личное", .31)

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps({"version": 1, "groups": self.groups}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
            self.changed.emit()
            return True
        except OSError:
            self.error.emit("Не удалось сохранить группы на диск")
            return False

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
        values=group["items"][:]
        for value in paths:
            path = Path(value)
            if path.exists() and str(path) not in values and len(values) < 100:
                values.append(str(path))
        return self.set_paths(group["id"],values)


class GroupItemDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        grid=self.parent().gridSize()
        return QSize(max(1,grid.width()-4),max(1,grid.height()-4))

    def paint(self,painter,option,index):
        p=painter
        p.save()
        p.setClipRect(option.rect)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
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
        p.setPen(QColor(TEXT))
        label=index.data(Qt.ItemDataRole.DisplayRole) or ""
        width=max(10,round(rect.width()-6))
        label=p.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,width*2-8)
        p.drawText(QRectF(rect.x()+3,rect.y()+54,width,30),Qt.AlignmentFlag.AlignHCenter|Qt.TextFlag.TextWordWrap,label)
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
        self.reload()

    def reload(self):
        self.clear()
        self.add_paths(self.panel.group["items"], save=False, keep_missing=True)
        for index in range(self.count()):
            item=self.item(index)
            path=Path(item.data(Qt.ItemDataRole.UserRole))
            item.setText(path.stem if path.suffix.casefold()==".lnk" else path.name)
        self.filter(self.panel.search.text())
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
        super().__init__(flags=Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
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
        self.setWindowTitle("Cloud Hub — группа «"+group["title"]+"»")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setStyleSheet("""QWidget {color:#f4f4f6;font:12px 'Golos Text';background:transparent;}
            QPushButton {border:0;padding:5px;background:transparent;border-radius:7px;}
            QPushButton:hover {background:rgba(255,255,255,18);}
            QLabel#groupName {font-weight:500;font-size:15px;}
            QLabel#groupCount {color:#b2b6bf;font-size:11px;}
            QLineEdit {background:rgba(255,255,255,7);border:0;padding:7px;border-radius:7px;selection-background-color:#53647a;}
            QListWidget {border:0;background:transparent;outline:0;padding:2px;}
            QListWidget::item {padding:3px;border-radius:7px;}
            QListWidget::item:selected {background:rgba(255,255,255,24);}
            QScrollBar:vertical {width:4px;background:transparent;}
            QScrollBar::handle:vertical {background:#657080;border-radius:2px;min-height:24px;}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
            QMenu {background:#20242c;border:1px solid #414550;border-radius:10px;padding:6px;}
            QMenu::item {padding:9px 15px;border-radius:5px;}
            QMenu::item:selected {background:#3c4350;}""")
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
        s = self.manager.owner.settings
        old_width, old_grid = getattr(self,"full_width",0), self.shelf.gridSize()
        self.full_width = s.get("group_width")
        self.closed_width = min(self.full_width,max(216,min(264,self.name.fontMetrics().horizontalAdvance(self.group["title"])+88)))
        if not self.animation.isActive():
            self.setFixedWidth(self.full_width if self.expanded else self.closed_width)
        self.shelf.setGridSize(QSize((self.full_width-30)//s.get("group_columns"), 96))
        self.header.setGeometry(0, 0, self.width(), 44)
        self.name.setText(self.group["title"])
        self.setWindowTitle("Cloud Hub — группа «"+self.group["title"]+"»")
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
        color = QColor(SURFACE)
        color.setAlpha(round((150+90*progress)*self.manager.owner.settings.get("group_opacity")/100))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        path = QPainterPath()
        radius=10+4*progress
        path.addRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),radius,radius)
        p.fillPath(path,color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255,255,255,22),1))
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
        self.store = GroupStore(owner.settings.directory)
        self.panels = {}
        self.store.changed.connect(self.reconcile)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)  # Shell recovery only; foreground changes never hide/show tiles.
        self.timer.timeout.connect(self.tick)
        QApplication.instance().screenAdded.connect(self.screen_added)
        QApplication.instance().screenRemoved.connect(lambda _:self.reposition())
        for screen in QApplication.screens():
            screen.availableGeometryChanged.connect(lambda _:self.reposition())
        self.reconcile()

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
        if not self.enabled:
            return
        for panel in self.panels.values():
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
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setWindowTitle("Удалить группу?")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("Удалить группу «"+group["title"]+"»?\n\nИсчезнут только группа и её ссылки.\nФайлы и папки на диске останутся.")
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
