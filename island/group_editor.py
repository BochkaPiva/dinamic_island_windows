# SPDX-License-Identifier: GPL-3.0-only
"""Visible group collection and one ID-bound editor shared with desktop actions."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,
    QPushButton,QListWidget,QListWidgetItem,QFrame,QFileDialog,QMenu)
from .hub import FileShelf
from .group_icons import group_icons
from .hub_ui import ElidedLabel, CollectionDelegate, icon
from .settings_navigation import SettingsSurface


class GroupFiles(FileShelf):
    def __init__(self,editor):
        self.editor=editor
        super().__init__(None)
        self.setMinimumHeight(80)
        self.setAccessibleName("Файлы выбранной группы")
        self.empty=QLabel("Перетащи файлы сюда",self.viewport())
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.itemSelectionChanged.connect(editor.update_actions)
        group_icons().changed.connect(self.refresh_icon)

    def paintEvent(self,event):
        # The group-specific empty label replaces FileShelf's generic message.
        from PySide6.QtWidgets import QListWidget
        QListWidget.paintEvent(self,event)

    def icon_for(self,path):
        return group_icons().icon(path)

    def extra_context_actions(self,menu,item):
        path=item.data(Qt.ItemDataRole.UserRole)
        store=self.editor.manager.store
        if store.library.owns(path):
            menu.addAction("Скопировать ярлык на рабочий стол",lambda:store.restore_shortcut(path))

    def refresh_icon(self,path):
        for index in range(self.count()):
            item=self.item(index)
            if item.data(Qt.ItemDataRole.UserRole)==path:
                item.setIcon(self.icon_for(path))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,"empty"):
            self.empty.setGeometry(self.viewport().rect().adjusted(8,8,-8,-8))

    def load(self,group):
        self.clear()
        if group:
            self.add_paths(group["items"],save=False,keep_missing=True)
        self.empty.setText("Перетащи файлы сюда" if group else
                           "Выбери группу в списке слева\nили создай новую")
        self.empty.setVisible(not self.count())
        self.empty.setGeometry(self.viewport().rect().adjusted(8,8,-8,-8))

    def persist(self):
        if not self.editor.manager.store.set_paths(self.editor.selected_id,self.paths()):
            self.load(self.editor.selected_group())

    def add_paths(self,paths,save=True,keep_missing=False):
        if save:
            self.add_to_group(self.editor.selected_id,paths)
        else:
            super().add_paths(paths,save=False,keep_missing=keep_missing)

    def add_files(self):
        identifier=self.editor.selected_id
        paths,_=QFileDialog.getOpenFileNames(self,"Добавить ссылки на файлы и программы")
        self.add_to_group(identifier,paths)

    def add_folder(self):
        identifier=self.editor.selected_id
        path=QFileDialog.getExistingDirectory(self,"Добавить ссылку на папку")
        self.add_to_group(identifier,[path] if path else [])

    def add_to_group(self,identifier,paths):
        # A modal dialog runs a nested event loop: never retarget its result
        # if another surface changed the editor selection in the meantime.
        group=self.editor.manager.store.find(identifier)
        if group and paths:
            self.editor.manager.store.add_paths(group,paths)


class GroupEditor(QWidget):
    def __init__(self,manager,notify,parent=None):
        super().__init__(parent)
        self.manager,self.notify=manager,notify
        self.selected_id=None
        self.dirty=False
        self.loading=False
        self.setMinimumHeight(280)
        root=QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(12)
        left,left_layout=self.pane()
        left.setMinimumWidth(180)
        left.setMaximumWidth(240)
        self.count=QLabel();self.count.setObjectName('paneTitle')
        collection_header=QHBoxLayout();collection_header.addWidget(self.count,1)
        self.create=self.button('+',self.create_group);self.create.setFixedSize(30,30)
        self.create.setAccessibleName('Создать группу');self.create.setToolTip('Создать группу')
        collection_header.addWidget(self.create);left_layout.addLayout(collection_header)
        self.groups=QListWidget()
        self.groups.setStyleSheet("QListWidget {background:transparent;border:0;}")
        self.groups.setItemDelegate(CollectionDelegate(self.groups))
        self.groups.setMouseTracking(True)
        self.groups.setAccessibleName("Все созданные группы рабочего стола")
        self.groups.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.groups.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.groups.currentItemChanged.connect(self.selection_changed)
        left_layout.addWidget(self.groups,1)
        self.list_empty=QLabel("Групп пока нет")
        self.list_empty.setObjectName("hint")
        left_layout.addWidget(self.list_empty)
        root.addWidget(left,1)
        right,right_layout=self.pane()
        self.title=ElidedLabel('Выбери группу',self);self.title.hide()
        self.fields=QWidget();fields=QVBoxLayout(self.fields);fields.setContentsMargins(0,0,0,0);fields.setSpacing(4)
        row=QHBoxLayout()
        self.name=QLineEdit();self.name.setObjectName('groupName');self.name.setMaxLength(60)
        self.name.setPlaceholderText('Название группы');self.name.setAccessibleName('Название выбранной группы')
        self.name.textEdited.connect(self.name_edited);self.name.editingFinished.connect(self.rename_current)
        row.addWidget(self.name,1)
        self.more=self.button('…',lambda:None);self.more.setObjectName('iconButton');self.more.setFixedSize(30,30)
        self.more.setAccessibleName('Действия с группой')
        self.menu=QMenu(self.more)
        self.menu.addAction('Переименовать',self.focus_name)
        self.active_action=self.menu.addAction('На рабочий стол',lambda:self.manager.store.make_active(self.selected_id))
        self.menu.addSeparator();self.delete_action=self.menu.addAction('Удалить группу…',self.delete_group)
        self.more.setMenu(self.menu);row.addWidget(self.more);fields.addLayout(row)
        self.detail=QLabel();self.detail.setObjectName('secondary');fields.addWidget(self.detail)
        right_layout.addWidget(self.fields)
        # Existing command controls stay available to the shared management API.
        self.remove=self.button('Удалить группу…',self.delete_group);self.remove.setParent(self);self.remove.hide()
        self.rename=self.button('Сохранить',self.rename_current);self.rename.setParent(self);self.rename.hide()
        self.activate=self.button('На рабочий стол',lambda:self.manager.store.make_active(self.selected_id));self.activate.setParent(self);self.activate.hide()
        self.files=GroupFiles(self)
        self.files.setStyleSheet("QListWidget {background:transparent;border:0;}")
        right_layout.addWidget(self.files,1)
        actions=QHBoxLayout()
        self.add_files=self.button("Файлы…",self.files.add_files)
        self.add_folder=self.button("Папку…",self.files.add_folder)
        self.remove_links=self.button("Убрать ссылки",self.files.remove_selected)
        actions.addWidget(self.add_files);actions.addWidget(self.add_folder);actions.addStretch();actions.addWidget(self.remove_links)
        self.remove_links.setObjectName('quiet')
        right_layout.addLayout(actions)
        root.addWidget(right,3)
        manager.store.changed.connect(self.refresh)
        if manager.store.access:
            manager.store.access.changed.connect(self.refresh)
        manager.store.error.connect(notify)
        manager.store.notice.connect(notify)
        self.refresh()
        if manager.store.last_warning:
            notify(manager.store.last_warning)

    def focus_name(self):
        self.name.setFocus();self.name.selectAll()

    def pane(self):
        frame=SettingsSurface()
        frame.setObjectName("groupPane")
        layout=QVBoxLayout(frame)
        layout.setContentsMargins(12,12,12,12)
        layout.setSpacing(9)
        return frame,layout

    def button(self,title,callback):
        button=QPushButton(title)
        button.clicked.connect(callback)
        return button

    def selected_group(self):
        return self.manager.store.find(self.selected_id)

    def refresh(self):
        if self.loading:
            return
        old=self.selected_id
        old_row=max(0,self.groups.currentRow())
        self.loading=True
        self.groups.blockSignals(True)
        self.groups.clear()
        records=self.manager.store.groups
        active=self.manager.store.access.active_ids(records) if self.manager.store.access else {g['id'] for g in records}
        for number,group in enumerate(records,1):
            count=len(group["items"])
            detail = f"Элементов: {count}" if count else "Пустая группа"
            if group['id'] not in active:
                detail = 'Сохранена · панель не активна'
            item=QListWidgetItem(f"{group['title']}\n"+detail)
            item.setData(Qt.ItemDataRole.UserRole,group["id"])
            item.setToolTip(group["title"])
            item.setIcon(icon("folder"))
            item.setSizeHint(QSize(1,58))
            self.groups.addItem(item)
        index=next((i for i,g in enumerate(records) if g["id"]==old),min(old_row,len(records)-1))
        self.groups.setCurrentRow(index)
        self.selected_id=records[index]["id"] if index>=0 else None
        self.groups.blockSignals(False)
        self.loading=False
        self.count.setText(f"Группы · {len(records)}")
        self.list_empty.setVisible(not records)
        self.create.setEnabled(len(records)<30)
        self.load_details(preserve_draft=self.selected_id==old)

    def select_id(self,identifier):
        for index in range(self.groups.count()):
            if self.groups.item(index).data(Qt.ItemDataRole.UserRole)==identifier:
                self.groups.setCurrentRow(index)
                self.groups.scrollToItem(self.groups.item(index))
                return self.selected_id==identifier
        return False

    def selection_changed(self,current,previous):
        if self.loading:
            return
        identifier=current.data(Qt.ItemDataRole.UserRole) if current else None
        if not self.rename_current():
            self.align_selection(self.selected_id)
            return
        self.selected_id=identifier
        self.align_selection(identifier)
        self.dirty=False
        self.load_details()

    def align_selection(self,identifier):
        self.groups.blockSignals(True)
        for index in range(self.groups.count()):
            if self.groups.item(index).data(Qt.ItemDataRole.UserRole)==identifier:
                self.groups.setCurrentRow(index)
                break
        self.groups.blockSignals(False)

    def load_details(self,preserve_draft=False):
        group=self.selected_group()
        self.title.setText(group["title"] if group else "Выбери группу")
        self.detail.setText(f"Элементов: {len(group['items'])}" if group else "")
        if not (preserve_draft and self.dirty):
            self.name.setText(group["title"] if group else "")
            self.dirty=False
        self.files.load(group)
        self.update_actions()

    def update_actions(self):
        selected=self.selected_group() is not None
        self.fields.setEnabled(selected)
        self.more.setEnabled(selected)
        self.delete_action.setEnabled(selected)
        self.active_action.setEnabled(selected)
        self.files.setEnabled(selected)
        for button in (self.remove,self.add_files,self.add_folder):
            button.setEnabled(selected)
        self.rename.setEnabled(selected and self.dirty)
        self.remove_links.setEnabled(selected and bool(self.files.selectedItems()))

    def name_edited(self,value):
        self.dirty=True
        self.update_actions()

    def rename_current(self):
        if not self.dirty or self.loading:
            return True
        if not self.name.text().strip():
            self.notify("Название не может быть пустым")
            return False
        identifier,title=self.selected_id,self.name.text()
        self.dirty=False
        if self.manager.store.rename(identifier,title):
            self.name.setText(self.selected_group()["title"])
            self.update_actions()
            self.notify("Название сохранено")
            return True
        self.dirty=True
        self.update_actions()
        return False

    def create_group(self):
        if not self.rename_current():
            return
        group=self.manager.request_create(parent=self)
        if group:
            self.select_id(group["id"])
            self.notify("Группа создана")

    def delete_group(self):
        identifier=self.selected_id
        if identifier and self.manager.request_delete(identifier,self):
            self.notify("Группа удалена · файлы сохранены")
