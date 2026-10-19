# SPDX-License-Identifier: GPL-3.0-only
"""A single update surface shared by manual checks and background notifications."""
from pathlib import Path
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,QPlainTextEdit
from . import __version__
from .style import app_icon


class UpdatePanel(QFrame):
    def __init__(self,owner,parent=None):
        super().__init__(parent)
        self.owner=owner
        self.manager=owner.updates
        self.setObjectName('card')
        root=QVBoxLayout(self)
        root.setContentsMargins(20,20,20,20)
        root.setSpacing(16)
        header=QHBoxLayout()
        emblem=QLabel()
        emblem.setPixmap(app_icon().pixmap(40,40))
        header.addWidget(emblem)
        header.addSpacing(10)
        words=QVBoxLayout()
        self.title=QLabel('Nelviro')
        self.title.setObjectName('heading')
        words.addWidget(self.title)
        self.version=QLabel(f'Версия {__version__}')
        self.version.setObjectName('secondary')
        words.addWidget(self.version)
        header.addLayout(words,1)
        root.addLayout(header)
        self.status=QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Состояние обновления')
        root.addWidget(self.status)
        self.progress=QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName('Загрузка обновления')
        root.addWidget(self.progress)
        self.detail=QLabel()
        self.detail.setObjectName('secondary')
        root.addWidget(self.detail)
        actions=QHBoxLayout()
        self.primary=QPushButton('Проверить обновления')
        self.primary.setObjectName('primary')
        self.primary.setMinimumHeight(38)
        self.primary.clicked.connect(self.act)
        self.secondary=QPushButton('Отменить')
        self.secondary.clicked.connect(self.secondary_action)
        actions.addWidget(self.primary)
        actions.addWidget(self.secondary)
        actions.addStretch()
        root.addLayout(actions)
        self.notes_title=QLabel('Что нового')
        self.notes_title.setObjectName('cardTitle')
        root.addWidget(self.notes_title)
        self.notes=QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setMinimumHeight(130)
        self.notes.setMaximumHeight(230)
        self.notes.setAccessibleName('Изменения в новой версии')
        root.addWidget(self.notes)
        self.backup=QPushButton('Открыть резервную копию')
        self.backup.setObjectName('quiet')
        self.backup.clicked.connect(self.open_backup)
        root.addWidget(self.backup,alignment=Qt.AlignmentFlag.AlignLeft)
        self.manager.changed.connect(self.render)
        self.render(self.manager.snapshot())

    def render(self,value):
        state=value['state']
        info=value.get('info') or {}
        self.title.setText('Nelviro '+info['version'] if state in {'available','downloading','verifying','ready','installing'} and info else 'Nelviro')
        self.status.setText(value['message'])
        busy=state in {'checking','downloading','verifying','installing'}
        self.primary.setEnabled(not busy)
        self.primary.setText({'checking':'Проверяем…','downloading':'Скачиваем…','verifying':'Проверяем файл…',
            'installing':'Устанавливаем…','available':'Скачать обновление','ready':'Установить и перезапустить',
            'error':'Попробовать снова'}.get(state,'Проверить обновления'))
        self.progress.setVisible(state in {'checking','downloading','verifying','ready','installing'})
        self.progress.setRange(0,0 if state in {'checking','verifying','installing'} else 100)
        if state in {'downloading','ready'}: self.progress.setValue(value['progress'])
        self.secondary.setVisible(state in {'downloading','verifying','ready','current'})
        self.secondary.setEnabled(state!='verifying' or not self.manager.cancel_event.is_set())
        self.secondary.setText('Позже' if state=='ready' else 'Восстановить установку' if state=='current' else 'Отменить')
        self.secondary.setToolTip('Заново установить текущую версию, сохранив данные' if state=='current' else '')
        if state=='current' and not(info.get('version')==__version__ and info.get('installer') and info.get('checksums')): self.secondary.hide()
        self.detail.setVisible(state in {'downloading','ready','verifying'})
        self.detail.setText('Файл проверен · готов к установке' if state=='ready' else
            f"{value['received']/1024**2:.1f} из {value['total']/1024**2:.1f} МБ · {value['progress']}%")
        notes=info.get('notes','')
        self.notes_title.setVisible(bool(notes))
        self.notes.setVisible(bool(notes))
        if self.notes.toPlainText()!=notes: self.notes.setPlainText(notes)
        result=value.get('last_result') or {}
        backup=Path(result.get('backup') or '.')
        self.backup.setVisible(bool(result.get('backup')) and backup.is_dir() and backup.resolve().is_relative_to((self.owner.settings.directory/'backups').resolve()))

    def act(self):
        if self.manager.state=='available': self.manager.download()
        elif self.manager.state=='ready': self.owner._install_update()
        else: self.owner._check_update()

    def secondary_action(self):
        if self.manager.state=='ready': self.window().navigate('hub')
        elif self.manager.state=='current': self.manager.download()
        else: self.manager.cancel()

    def open_backup(self):
        result=self.manager.last_result or {}
        path=Path(result.get('backup') or '.')
        if result.get('backup') and path.resolve().is_relative_to((self.owner.settings.directory/'backups').resolve()):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
