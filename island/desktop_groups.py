# SPDX-License-Identifier: GPL-3.0-only
"""Desktop-only roll-up groups. Links stay in place; Explorer is never patched."""
import ctypes
import json
import math
from pathlib import Path
import uuid
from PyQt6.QtCore import (Qt, QObject, QTimer, QEvent, QPoint, QSize, QFileInfo,
                          QVariantAnimation, QEasingCurve, pyqtSignal)
from PyQt6.QtGui import QCursor, QColor, QPainter
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QFileIconProvider, QFileDialog, QMenu)
from .hub import FileShelf
from .platform_win import desktop_is_foreground, keep_desktop_visible


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

    def add(self, title="Новая группа", x=.03):
        if len(self.groups) >= 30:
            return None
        group = {"id": str(uuid.uuid4()), "title": title[:60] or "Новая группа", "items": [],
                 "x": x, "y": .12+min(.5, len(self.groups)//3*.12), "screen": ""}
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
        self.reload()

    def reload(self):
        self.clear()
        self.add_paths(self.panel.group["items"], save=False, keep_missing=True)
        self.filter(self.panel.search.text())

    def persist(self):
        self.panel.group["items"] = self.paths()
        self.panel.manager.store.save()
        self.panel.animate(True)

    def filter(self, query):
        for i in range(self.count()):
            self.item(i).setHidden(query.casefold() not in self.item(i).text().casefold())


class GroupPanel(QWidget):
    def __init__(self, manager, group):
        super().__init__(flags=Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.manager, self.group = manager, group
        self.expanded = False
        self.drag_origin = None
        self.setWindowTitle("Cloud Hub — группа «"+group["title"]+"»")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setStyleSheet("""QWidget {color:#f3f6fc;font:12px 'Segoe UI';background:transparent;}
            QPushButton {border:0;padding:3px;background:transparent;border-radius:6px;}
            QPushButton:hover {background:#46526a;} QLabel {font-weight:600;font-size:14px;}
            QLineEdit {background:#202a3b;border:0;padding:6px;border-radius:7px;}
            QListWidget {border:0;background:transparent;outline:0;padding:2px;}
            QListWidget::item {padding:3px;border-radius:7px;}
            QListWidget::item:selected {background:#50698d;}
            QScrollBar:vertical {width:7px;background:transparent;}""")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 0, 8, 0)
        root.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(3)
        self.name = QLabel(group["title"])
        self.name.setMinimumHeight(43)
        self.name.installEventFilter(self)
        self.name.setToolTip("Наведи для раскрытия. Перетащи заголовок, чтобы переместить группу.")
        header.addWidget(self.name, 1)
        self.chevron = QPushButton("⌄")
        self.chevron.setFixedSize(25, 30)
        self.chevron.clicked.connect(lambda: self.animate(not self.expanded))
        header.addWidget(self.chevron)
        menu = QPushButton("⋯")
        menu.setFixedSize(25, 30)
        menu.clicked.connect(self.menu)
        header.addWidget(menu)
        root.addLayout(header)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 9)
        body.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти в группе…")
        self.search.setClearButtonEnabled(True)
        body.addWidget(self.search)
        self.shelf = GroupShelf(self)
        self.shelf.setMinimumHeight(80)
        self.search.textChanged.connect(self.shelf.filter)
        body.addWidget(self.shelf, 1)
        self.empty = QPushButton("＋ Добавить файлы или программы")
        self.empty.clicked.connect(self.add_files)
        body.addWidget(self.empty)
        root.addWidget(self.body, 1)
        self.body.hide()
        self.hover = QTimer(self)
        self.hover.setSingleShot(True)
        self.hover.timeout.connect(lambda: self.animate(True))
        self.collapse = QTimer(self)
        self.collapse.setSingleShot(True)
        self.collapse.timeout.connect(self._collapse)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(320)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda value: self.setFixedHeight(round(value)))
        self.animation.finished.connect(lambda: self.body.setVisible(self.expanded))
        self.configure()
        self.setFixedHeight(44)
        self.place()

    def configure(self):
        s = self.manager.owner.settings
        self.setFixedWidth(s.get("group_width"))
        self.shelf.setGridSize(QSize((self.width()-30)//s.get("group_columns"), 88))
        self.name.setText(self.group["title"])
        self.setWindowTitle("Cloud Hub — группа «"+self.group["title"]+"»")
        self.update()

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == self.group["screen"]), QApplication.primaryScreen())
        r = screen.availableGeometry()
        self.move(r.left()+round(self.group["x"]*max(0,r.width()-self.width())),
                  r.top()+round(self.group["y"]*max(0,r.height()-44)))

    def animate(self, expanded):
        self.expanded = expanded
        self.chevron.setText("⌃" if expanded else "⌄")
        self.animation.stop()
        self.body.show()
        rows = max(1, math.ceil(self.shelf.count()/self.manager.owner.settings.get("group_columns")))
        available = self.screen().availableGeometry().bottom()-self.y()+1
        height = max(44, min(44+48+min(4,rows)*92+40, available)) if expanded else 44
        self.animation.setStartValue(float(self.height()))
        self.animation.setEndValue(float(height))
        self.animation.start()

    def enterEvent(self, event):
        self.collapse.stop()
        if not self.expanded:
            self.hover.start(self.manager.owner.settings.get("group_hover_delay"))

    def leaveEvent(self, event):
        self.hover.stop()
        self.collapse.start(self.manager.owner.settings.get("group_collapse_delay"))

    def _collapse(self):
        if self.underMouse() or QApplication.activePopupWidget() or self.search.hasFocus():
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
        paths, _ = QFileDialog.getOpenFileNames(self,"Добавить ссылки на файлы и программы")
        self.manager.store.add_paths(self.group, paths)
        self.shelf.reload()
        self.animate(True)

    def menu(self):
        self.collapse.stop()
        menu = QMenu(self)
        menu.addAction("Добавить файлы / ярлыки…",self.add_files)
        menu.addAction("Добавить папку…",self.add_folder)
        menu.addAction("Настроить группы…",self.manager.open_settings)
        menu.exec(QCursor.pos())
        self.collapse.start(800)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self,"Добавить ссылку на папку")
        if path:
            self.manager.store.add_paths(self.group,[path])
            self.shelf.reload()

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
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self,event):
        self.collapse.start(self.manager.owner.settings.get("group_collapse_delay"))
        event.accept()

    def paintEvent(self,event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#283244")
        color.setAlpha(round(255*self.manager.owner.settings.get("group_opacity")/100))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(self.rect(),12,12)

    def hideEvent(self,event):
        self.hover.stop()
        self.collapse.stop()
        self.animation.stop()
        self.expanded = False
        self.body.hide()
        self.setFixedHeight(44)
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
                self.panels[group["id"]].configure()

    def reposition(self):
        for panel in self.panels.values():
            panel.place()

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
        group_popup = popup and any(p.isAncestorOf(popup) for p in self.panels.values())
        visible = self.enabled and (desktop_is_foreground() or own_group or group_popup)
        for panel in self.panels.values():
            if visible and not panel.isVisible():
                panel.show()
            elif not visible and panel.isVisible():
                panel.hide()
            if visible:
                keep_desktop_visible(panel)

    def open_settings(self):
        self.owner.show_hub()
        self.owner.control_center.navigate("desktop")

    def shutdown(self):
        self.enabled = False
        self.timer.stop()
        for panel in self.panels.values():
            panel.close()
