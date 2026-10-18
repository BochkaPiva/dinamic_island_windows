# SPDX-License-Identifier: GPL-3.0-only
"""On-demand local launcher and asynchronous Windows Search queries."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import time
from PySide6.QtCore import Qt, QObject, QTimer, QUrl, QEvent, Signal, QProcess, QFileInfo
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import QWidget, QListWidgetItem, QFileIconProvider
from .search_ui import SearchPresentation


@dataclass(frozen=True)
class Result:
    title: str
    detail: str
    target: str
    kind: str = "file"


def application_catalog():
    roots = [Path(os.environ.get("APPDATA", ""))/"Microsoft/Windows/Start Menu/Programs",
             Path(os.environ.get("PROGRAMDATA", ""))/"Microsoft/Windows/Start Menu/Programs",
             Path.home()/"Desktop", Path(os.environ.get("PUBLIC", "C:/Users/Public"))/"Desktop"]
    found = {}
    for index,root in enumerate(roots):
        try:
            if not root.is_dir():
                continue
            for path in (root.rglob("*") if index < 2 else root.iterdir()):
                if path.suffix.lower() in {".lnk", ".appref-ms", ".url"} and path.is_file():
                    found.setdefault(path.stem.casefold(), Result(path.stem, "Приложение · "+str(path.parent), str(path), "app"))
                if len(found) >= 4096:
                    break
        except OSError:
            continue
    # Store applications don't necessarily have .lnk files in the Start Menu.
    script = "$j=ConvertTo-Json -InputObject @(Get-StartApps | Select-Object Name,AppID) -Compress; [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($j)))"
    try:
        result = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-EncodedCommand",
            base64.b64encode(script.encode("utf-16le")).decode("ascii")],capture_output=True,timeout=5,creationflags=0x08000000)
        for item in json.loads(base64.b64decode(result.stdout.strip()).decode("utf-8")):
            if isinstance(item.get("Name"),str) and isinstance(item.get("AppID"),str):
                found.setdefault(item["Name"].casefold(),Result(item["Name"],"Приложение Windows",item["AppID"],"store"))
    except (OSError,ValueError,TypeError,subprocess.TimeoutExpired):
        pass
    return sorted(found.values(), key=lambda r: r.title.casefold())


def index_sql(query):
    # Only letters/digits reach SQL; raw input never reaches SQL or PowerShell.
    words = re.findall(r"[^\W_]+", query, flags=re.UNICODE)[:6]
    if not words:
        return ""
    clauses = " AND ".join("System.FileName LIKE '%"+word[:60]+"%'" for word in words)
    return ("SELECT TOP 35 System.ItemNameDisplay, System.ItemPathDisplay FROM SystemIndex "
            "WHERE SCOPE='file:' AND "+clauses+" ORDER BY System.DateModified DESC")


def indexed_files(query):
    sql = index_sql(query)
    if not sql:
        return [], "Введи имя файла"
    encoded_sql = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    script = r'''$ErrorActionPreference='Stop'
$c=New-Object -ComObject ADODB.Connection
try {
  $c.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
  $sql=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('SQL_BASE64'))
  $r=$c.Execute($sql); $items=@()
  while (!$r.EOF) {
    $items+=@{title=[string]$r.Fields.Item(0).Value;path=[string]$r.Fields.Item(1).Value}
    $r.MoveNext()
  }
  $r.Close()
  $json=ConvertTo-Json -InputObject $items -Compress
  [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
} finally { if ($c.State) {$c.Close()} }
'''.replace("SQL_BASE64", encoded_sql)
    command = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                                capture_output=True, timeout=5, creationflags=0x08000000)
        if result.returncode:
            return [], "Индекс Windows недоступен. Проверь «Параметры → Поиск Windows»."
        rows = json.loads(base64.b64decode(result.stdout.strip()).decode("utf-8"))
        if isinstance(rows, dict):
            rows = [rows]
        return [Result(r["title"], r["path"], r["path"]) for r in rows if r.get("path")], "Файлы из индекса Windows"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return [], "Индекс Windows не ответил. Приложения и команды доступны."


class Signals(QObject):
    completed = Signal(int, object, str)


class SearchPalette(SearchPresentation, QWidget):
    def __init__(self, owner):
        super().__init__(f=Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.owner, self.enabled = owner, True
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cloud-search")
        self.signals = Signals(self)
        self.signals.completed.connect(self._completed)
        self.generation = 0
        self.catalog, self.catalog_at = [], 0
        self.catalog_loading = False
        self.pending = None
        self.icon_provider = QFileIconProvider()
        self.icons = {}
        self.setWindowTitle("Cloud Hub — Поиск")
        self.build_presentation()
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._indexed)
        self.input.textChanged.connect(self._query)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.hide()

    def toggle(self):
        if self.isVisible():
            self.hide()
        elif self.enabled:
            screen = self.owner.screen().availableGeometry()
            self.resize(min(600,screen.width()-40),self.height())
            self.move(screen.center().x()-self.width()//2, screen.top()+max(60, screen.height()//6))
            self.show()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()
            self.input.selectAll()
            self._query(self.input.text())
            if time.monotonic()-self.catalog_at > 60 and not self.catalog_loading:
                self.catalog_loading = True
                self._submit(-1, application_catalog)
        else:
            self.owner.show_hub()
            self.owner.control_center._message("Поиск выключен или приостановлен текущим профилем.")

    def _submit(self, generation, function, *args):
        signal = self.signals
        future = self.executor.submit(function, *args)
        def done(job):
            try:
                value = job.result()
                rows, status = (value, "") if generation == -1 else value
                signal.completed.emit(generation, rows, status)
            except Exception:
                try:
                    signal.completed.emit(generation, [], "Не удалось завершить поиск")
                except RuntimeError:
                    pass
        future.add_done_callback(done)
        return future

    def _commands(self):
        return [Result("Открыть Cloud Hub", "Настройки модулей", "hub", "command"),
                Result("Открыть Dynamic Island", "Музыка и обзор", "island", "command"),
                Result("Файлы и заметки", "Твои сохранённые материалы", "library", "command"),
                Result("Таймер", "Своя длительность, пауза и продолжение", "timer", "command"),
                Result("Группы рабочего стола", "Добавить и настроить группу", "desktop", "command")]

    def _query(self, query):
        self.generation += 1
        self.debounce.stop()
        if self.pending is not None:
            self.pending.cancel()
        terms = query.casefold().split()
        rows = [r for r in self._commands() if all(t in r.title.casefold() for t in terms)] if terms else []
        if terms and self.owner.settings.get("search_apps"):
            rows += [r for r in self.catalog if all(t in r.title.casefold() for t in terms)][:40]
        direct = Path(os.path.expandvars(query.strip(' "'))) if query.strip() else None
        if direct and direct.is_absolute() and direct.exists():
            rows.insert(0, Result(direct.name, str(direct), str(direct)))
        self._set_rows(rows)
        self.status.setText("Приложения · файлы · команды" if not terms else
                            "Ищу в индексе Windows…" if self.owner.settings.get("search_files") and len(query.strip())>=2 else
                            "Ничего не найдено" if not rows else "Найдено: "+str(len(rows)))
        if len(query.strip()) >= 2 and self.owner.settings.get("search_files") and self.isVisible():
            self.debounce.start(350)

    def _set_rows(self, rows, append=False):
        if not append:
            self.results.clear()
        existing = {self.results.item(i).data(Qt.ItemDataRole.UserRole).target for i in range(self.results.count())}
        for result in rows:
            if result.target in existing:
                continue
            item = QListWidgetItem(result.title+"\n"+result.detail)
            item.setToolTip(result.detail)
            item.setData(Qt.ItemDataRole.UserRole, result)
            if result.kind in {"app","file"} and not result.target.startswith("\\\\"):
                if result.target not in self.icons:
                    if len(self.icons)>=128:
                        self.icons.clear()
                    self.icons[result.target]=self.icon_provider.icon(QFileInfo(result.target))
                item.setIcon(self.icons[result.target])
            self.results.addItem(item)
            existing.add(result.target)
        if self.results.currentRow() < 0 and self.results.count():
            self.results.setCurrentRow(0)
        self.update_presentation()

    def _indexed(self):
        self.pending = self._submit(self.generation, indexed_files, self.input.text())

    def _completed(self, generation, rows, status):
        if generation == -1:
            self.catalog_loading = False
            self.catalog, self.catalog_at = rows, time.monotonic()
            if self.isVisible():
                self._query(self.input.text())
        elif generation == self.generation and self.isVisible():
            self._set_rows(rows, append=True)
            self.status.setText(status if not self.results.count() else "Найдено: "+str(self.results.count())+" · "+status)

    def activate(self):
        item = self.results.currentItem()
        if not item:
            return
        result = item.data(Qt.ItemDataRole.UserRole)
        if result.kind == "command":
            self.hide()
            if result.target == "island":
                self.owner._show_panel()
            else:
                self.owner.show_hub()
                self.owner.control_center.navigate(result.target)
        elif result.kind == "store":
            ok,_ = QProcess.startDetached("explorer.exe",["shell:AppsFolder\\"+result.target])
            if ok:
                self.hide()
            else:
                self.status.setText("Windows не смогла открыть приложение")
        elif Path(result.target).exists() and QDesktopServices.openUrl(QUrl.fromLocalFile(result.target)):
            self.hide()
        else:
            self.status.setText("Файл недоступен или Windows не смогла его открыть")

    def eventFilter(self, obj, event):
        if isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self.results.setCurrentRow(max(0, min(self.results.count()-1,
                    self.results.currentRow()+(1 if event.key() == Qt.Key.Key_Down else -1))))
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.activate()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self.debounce.stop()
        self.height_animation.stop()
        if self.pending is not None:
            self.pending.cancel()
        self.generation += 1
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)

    def shutdown(self):
        self.hide()
        self.executor.shutdown(wait=False, cancel_futures=True)
