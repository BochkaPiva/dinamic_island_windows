# SPDX-License-Identifier: GPL-3.0-only
"""Named local notes, with the existing quick note kept intact and shared."""
import json
from pathlib import Path
import uuid
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QPlainTextEdit, QLineEdit, QPushButton, QLabel, QFileDialog)
from PySide6.QtWidgets import QApplication, QPlainTextDocumentLayout
from PySide6.QtGui import QTextDocument


class Notebook(QWidget):
    def __init__(self,hub):
        super().__init__()
        self.hub = hub
        self.path = hub.store/"notes.json"
        self.records = []
        self._owned_document = None
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            self.records = [r for r in document.get("notes",[]) if isinstance(r,dict) and
                all(isinstance(r.get(k),str) for k in ("id","title","text"))][:1000]
        except (OSError,ValueError,TypeError,AttributeError):
            if self.path.exists():
                import shutil
                shutil.copy2(self.path,self.path.with_suffix(".recovery.json"))
        self.current = None
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        left = QVBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Найти заметку…")
        self.filter.textChanged.connect(self.refilter)
        left.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setMaximumWidth(230)
        self.list.currentRowChanged.connect(self.select)
        left.addWidget(self.list,1)
        add = QPushButton("＋ Новая заметка")
        add.clicked.connect(self.add)
        left.addWidget(add)
        root.addLayout(left,1)
        right = QVBoxLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText("Название заметки")
        self.title.setMaxLength(100)
        self.title.textEdited.connect(self.edited)
        right.addWidget(self.title)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Текст…")
        self.editor.textChanged.connect(self.edited)
        right.addWidget(self.editor,1)
        bar = QHBoxLayout()
        self.status = QLabel("Автосохранение · локально")
        bar.addWidget(self.status,1)
        for title,callback in (("Копировать",lambda: QApplication.clipboard().setText(self.editor.toPlainText())),
                               ("Экспорт…",self.export)):
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            bar.addWidget(btn)
        right.addLayout(bar)
        root.addLayout(right,3)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self.rebuild()
        hub._note_save.timeout.connect(lambda:self.status.setText(hub.note_status.text()) if self.current is None else None)

    def rebuild(self,selected=0):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItem("Быстрая заметка · остров")
        self.list.addItems([r["title"] or "Без названия" for r in self.records])
        self.list.blockSignals(False)
        self.list.setCurrentRow(selected)

    def add(self):
        if len(self.records) >= 1000:
            self.status.setText("Достигнут предел: 1000 заметок")
            return
        record = {"id":str(uuid.uuid4()),"title":"Новая заметка","text":""}
        self.records.append(record)
        self.save()
        self.filter.clear()
        self.rebuild(len(self.records))
        self.title.setFocus()
        self.title.selectAll()

    def select(self,row):
        if row < 0:
            return
        self._loading = True
        self.current = self.records[row-1] if row else None
        self.title.setReadOnly(not row)
        self.title.setText(self.current["title"] if row else "Быстрая заметка — общая с островом")
        previous = self._owned_document
        self._owned_document = None
        if row == 0:
            self.editor.setDocument(self.hub.notes.document())
        else:
            document = QTextDocument(self.editor)
            document.setDocumentLayout(QPlainTextDocumentLayout(document))
            document.setPlainText(self.current["text"])
            self.editor.setDocument(document)
            self._owned_document = document
        if previous is not None:
            previous.deleteLater()
        self._loading = False

    def edited(self):
        if self._loading:
            return
        if self.current is not None:
            self.current["title"] = self.title.text()
            self.current["text"] = self.editor.toPlainText()
            self.list.currentItem().setText(self.title.text() or "Без названия")
            self.save_timer.start(500)
        else:
            self.hub._note_save.start(500)
        self.status.setText("Сохраняю…")

    def save(self):
        try:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps({"version":1,"notes":self.records},ensure_ascii=False,indent=2),encoding="utf-8")
            temp.replace(self.path)
            self.status.setText("Сохранено на компьютере")
        except OSError:
            self.status.setText("Ошибка сохранения — экспортируй текст")

    def refilter(self,query):
        for row in range(self.list.count()):
            content = self.hub.notes.toPlainText() if row == 0 else self.records[row-1]["text"]
            item = self.list.item(row)
            item.setHidden(query.casefold() not in (item.text()+" "+content).casefold())

    def export(self):
        target,_ = QFileDialog.getSaveFileName(self,"Экспорт заметки",(self.title.text()[:60] or "Заметка")+".txt","Текст (*.txt)")
        if target:
            try:
                Path(target).write_text(self.editor.toPlainText(),encoding="utf-8")
                self.status.setText("Экспортировано")
            except OSError:
                self.status.setText("Не удалось экспортировать")

    def flush(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save()
