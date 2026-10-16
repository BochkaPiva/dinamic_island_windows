# SPDX-License-Identifier: GPL-3.0-only
"""Desktop-only roll-up groups. Links stay in place; Explorer is never patched."""
import ctypes
import json
import math
import time
from contextlib import contextmanager
from pathlib import Path
import uuid
from PyQt6.QtCore import Qt, QObject, QTimer, QEvent, QSize, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QFileDialog, QMenu)
from .hub import FileShelf
from .platform_win import desktop_is_foreground, restore_desktop_panel, exclude_from_peek
from .motion import DampedValue, smoothstep


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

    def add(self, title="Новая группа", x=None):
        if len(self.groups) >= 30:
            return None
        group = {"id": str(uuid.uuid4()), "title": title[:60] or "Новая группа", "items": [],
                 "x": x if x is not None else .03+(len(self.groups)%3)*.32,
                 "y": .12+min(.7, len(self.groups)//3*.27), "screen": ""}
        self.groups.append(group)
        self.save()
        return group

    def remove(self, identifier):
        self.groups = [g for g in self.groups if g["id"] != identifier]
        self.save()

    def add_paths(self, group, paths):
        for value in paths:
            path = Path(value)
            if path.exists() and str(path) not in group["items"] and len(group["items"]) < 100:
                group["items"].append(str(path))
        self.save()


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
        self.setSpacing(2)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.reload()

    def reload(self):
        self.clear()
        self.add_paths(self.panel.group["items"], save=False, keep_missing=True)
        self.filter(self.panel.search.text())
        if hasattr(self.panel,"animation") and self.panel.expanded:
            self.panel.animate(True, refresh=True)

    def persist(self):
        self.panel.group["items"] = self.paths()
        self.panel.manager.store.save()
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
        self.setWindowTitle("Cloud Hub — группа «"+group["title"]+"»")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setStyleSheet("""QWidget {color:#eef0f5;font:12px 'Segoe UI';background:transparent;}
            QPushButton {border:0;padding:5px;background:transparent;border-radius:7px;}
            QPushButton:hover {background:rgba(255,255,255,22);} QLabel {font-weight:600;font-size:13px;}
            QLineEdit {background:rgba(0,0,0,35);border:0;padding:7px;border-radius:8px;selection-background-color:#53647a;}
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
        self.name = QLabel(group["title"])
        self.name.installEventFilter(self)
        self.name.setToolTip("Наведи для раскрытия. Перетащи заголовок, чтобы переместить группу.")
        header.addWidget(self.name, 1)
        self.chevron = QPushButton("⌄")
        self.chevron.setFixedSize(25, 30)
        self.chevron.clicked.connect(lambda: self.animate(not self.expanded))
        header.addWidget(self.chevron)
        menu = QPushButton("⋯")
        self.menu_button = menu
        menu.setFixedSize(25, 30)
        menu.clicked.connect(self.menu)
        header.addWidget(menu)
        self.body = QWidget(self)
        body = QVBoxLayout(self.body)
        body.setContentsMargins(10, 4, 10, 10)
        body.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти в группе…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(30)
        body.addWidget(self.search)
        self.shelf = GroupShelf(self)
        self.shelf.setMinimumHeight(0)
        self.search.textChanged.connect(self.shelf.filter)
        body.addWidget(self.shelf, 1)
        self.empty = QPushButton("＋  Добавить файлы или программы")
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

    def configure(self):
        s = self.manager.owner.settings
        old_width, old_grid = self.width(), self.shelf.gridSize()
        self.setFixedWidth(s.get("group_width"))
        self.shelf.setGridSize(QSize((self.width()-30)//s.get("group_columns"), 88))
        self.header.setGeometry(0, 0, self.width(), 44)
        self.name.setText(self.group["title"])
        self.setWindowTitle("Cloud Hub — группа «"+self.group["title"]+"»")
        changed = old_width != self.width() or old_grid != self.shelf.gridSize()
        if self.expanded or self.animation.isActive():
            self.animate(self.expanded,refresh=changed)
        self.update()

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == self.group["screen"]), QApplication.primaryScreen())
        r = screen.availableGeometry()
        self.move(r.left()+round(self.group["x"]*max(0,r.width()-self.width())),
                  r.top()+round(self.group["y"]*max(0,r.height()-44)))

    def animate(self, expanded, refresh=False):
        rows = math.ceil(self.shelf.count()/self.manager.owner.settings.get("group_columns"))
        available = self.screen().availableGeometry().bottom()-self.y()+1
        full = max(44, min(44 + (min(4, rows)*92 + 90 if rows else 68), available))
        height = full if expanded else 44
        if expanded == self.expanded and height == self.target_height and not refresh:
            return
        was_moving = self.animation.isActive()
        if not was_moving or self.texture.isNull() or refresh:
            self.search.setVisible(bool(rows))
            self.shelf.setVisible(bool(rows))
            self.body.setGeometry(0, 44, self.width(), max(1, full-44))
            self.body.ensurePolished()
            self.body.layout().activate()
            self.texture = self.body.grab()
        self.expanded = expanded
        self.chevron.setText("⌃" if expanded else "⌄")
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
        self.setFixedHeight(max(44, round(height)))
        if abs(height-self.target_height) < .04 and abs(self.extent.velocity) < .8:
            self.animation.stop()
            self.extent.value, self.extent.velocity = float(self.target_height), 0.
            self.setFixedHeight(self.target_height)
            self.body.setVisible(self.expanded)
            self.texture = QPixmap()
        self.update()

    def enterEvent(self, event):
        self.collapse.stop()
        if not self.expanded:
            self.hover.start(self.manager.owner.settings.get("group_hover_delay"))

    def leaveEvent(self, event):
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
                self.group.update(x=max(0.,min(1.,(self.x()-r.left())/max(1,r.width()-self.width()))),
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

    def menu(self):
        self.collapse.stop()
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        menu.addAction("Добавить файлы / ярлыки…",self.add_files)
        menu.addAction("Добавить папку…",self.add_folder)
        menu.addAction("Настроить группы…",self.manager.open_settings)
        menu.addSeparator()
        menu.addAction("Выровнять группы", self.manager.arrange)
        with self.interacting():
            menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
        menu.deleteLater()
        self.collapse.start(800)

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
        color = QColor("#242832")
        color.setAlpha(round(255*self.manager.owner.settings.get("group_opacity")/100))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),14,14)
        p.fillPath(path,color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255,255,255,22),1))
        p.drawPath(path)
        if self.animation.isActive() and not self.texture.isNull():
            p.setClipPath(path)
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

    def hideEvent(self,event):
        self.hover.stop()
        self.collapse.stop()
        self.animation.stop()
        self.expanded = False
        self.body.hide()
        self.setFixedHeight(44)
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
        self.timer.setInterval(300)
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
            self.panels.pop(identifier).deleteLater()
        for group in self.store.groups:
            if group["id"] not in self.panels:
                self.panels[group["id"]] = GroupPanel(self,group)
            else:
                panel = self.panels[group["id"]]
                if panel.shelf.paths() != group["items"]:
                    panel.shelf.reload()
                panel.configure()
        self.repair_overlaps()

    def repair_overlaps(self, force=False):
        """Move colliding headers only; keep identities, references and a backup."""
        occupied = {}
        moved = False
        for panel in self.panels.values():
            panel.place()
            screen = panel.screen()
            bounds = screen.availableGeometry()
            used = occupied.setdefault(screen.name(), [])
            rect = QRect(panel.x(), panel.y(), panel.width(), 44)
            if force or any(rect.adjusted(-6,-6,6,6).intersects(old) for old in used):
                step = panel.width()+20
                candidates = [QRect(bounds.x()+20+x, bounds.y()+70+y, panel.width(),44)
                    for y in range(0,max(1,bounds.height()-114),280)
                    for x in range(0,max(1,bounds.width()-panel.width()-20),step)]
                # Dense fallback for many groups/small screens, still no coincident headers.
                candidates += [QRect(bounds.x()+12+x,bounds.y()+12+y,panel.width(),44)
                    for y in range(0,max(1,bounds.height()-56),60)
                    for x in range(0,max(1,bounds.width()-panel.width()-12),step)]
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
                    panel.group.update(x=(rect.x()-bounds.x())/max(1,bounds.width()-panel.width()),
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
        ctypes.windll.user32.GetForegroundWindow.restype = ctypes.c_void_p
        foreground = ctypes.windll.user32.GetForegroundWindow()
        own_group = any(int(p.winId()) == foreground for p in self.panels.values())
        popup = QApplication.activePopupWidget() or QApplication.activeModalWidget()
        related = popup
        while related is not None and related not in self.panels.values():
            related = related.parentWidget()
        group_popup = related is not None or any(p.interactions for p in self.panels.values())
        desktop = desktop_is_foreground()
        visible = self.enabled and (desktop or own_group or group_popup or
            (not foreground and getattr(self,"_visible",False)))
        self._visible = visible
        for panel in self.panels.values():
            if visible and not panel.isVisible():
                panel.show()
            elif not visible and panel.isVisible():
                panel.hide()
            if visible and desktop and not popup and not group_popup:
                restore_desktop_panel(panel)

    def open_settings(self):
        self.owner.show_hub()
        self.owner.control_center.navigate("desktop")

    def shutdown(self):
        self.enabled = False
        self.timer.stop()
        for panel in self.panels.values():
            panel.close()
