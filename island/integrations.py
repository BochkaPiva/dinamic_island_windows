# SPDX-License-Identifier: GPL-3.0-only
"""Optional PowerToys adapter. Public CLI, read-only workspace discovery.

DSC replaces omitted settings with defaults: always GET and round-trip the full
object. Its 0.101 managed serializer also renames File Explorer, so retain the
native JSON snapshot and repair any unrelated serialization changes atomically,
only after the verified host has exited. Workspace files remain read-only.
"""
import json
import ctypes
import os
from pathlib import Path
import uuid
import time
from PySide6.QtCore import QObject, QProcess, QTimer, QCoreApplication, QThread, Signal

MODULES = ("CmdPal", "FancyZones", "Workspaces")


def close_powertoys_runner(root):
    """Request its normal Exit path; verify the HWND's executable first.

    PowerToys' own Settings UI uses PToyTrayIconWindow/WM_CLOSE. DSC writes
    configuration but does not reload a running host in supported 0.101 builds.
    No forced termination, Explorer restart, DLL injection or child killing.
    """
    user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    user.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
    user.FindWindowW.restype = ctypes.c_void_p
    hwnd = user.FindWindowW("PToyTrayIconWindow", None)
    if not hwnd:
        return None
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x101000, False, pid.value)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    if not handle:
        raise OSError("PowerToys process cannot be queried")
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel.QueryFullProcessImageNameW.argtypes = (ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_void_p)
    size = ctypes.c_ulong(32768)
    image = ctypes.create_unicode_buffer(size.value)
    if not kernel.QueryFullProcessImageNameW(ctypes.c_void_p(handle), 0, image, ctypes.byref(size)) or Path(image.value).resolve() != (root/"PowerToys.exe").resolve():
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise OSError("PowerToys window does not match the installation")
    user.PostMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    if not user.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0):
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise OSError("PowerToys did not accept a graceful close")
    return handle


def powertoys_root():
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if base:
            root = Path(base)/"PowerToys"
            if (root/"PowerToys.exe").is_file():
                return root
    return None


def load_workspaces(path=None):
    path = Path(path) if path else Path(os.environ.get("LOCALAPPDATA", ""))/"Microsoft/PowerToys/Workspaces/workspaces.json"
    try:
        if path.stat().st_size > 8_000_000:
            return []
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        result = []
        for item in payload.get("workspaces", payload.get("Workspaces", [])):
            identifier = "{"+str(uuid.UUID(item["id"].strip("{}"))).upper()+"}"
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                result.append((identifier, name[:160], len(item.get("applications", []))))
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


class PowerToysBridge(QObject):
    changed = Signal()
    message = Signal(str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.backup = self.directory/"powertoys-before-cloud-hub.json"
        self.root = powertoys_root()
        self.actual = {}
        self.desired = None
        self.status = "Не подключён"
        self.busy = False
        self._restore = False
        self._fresh = True
        self._restart = False
        self._runner_handle = None
        self._any_enabled = False
        self._closing_at = 0
        self.native_path = Path(os.environ.get("LOCALAPPDATA", ""))/"Microsoft/PowerToys/settings.json"
        self._native_before = None
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.process.kill)
        self.runner_poll = QTimer(self)
        self.runner_poll.setInterval(100)
        self.runner_poll.timeout.connect(self._runner_closed)

    def configure(self, desired, restore=False):
        self.root = powertoys_root()
        self.desired = {key: bool(desired[key]) for key in MODULES}
        self._restore = restore
        if not self.root:
            self.status = "PowerToys не установлен"
            self.changed.emit()
            return
        if not self.busy:
            self._get()

    def restore(self):
        try:
            saved = json.loads(self.backup.read_text(encoding="utf-8"))
            original = saved["managed_enabled"]
            if not all(type(original.get(key)) is bool for key in MODULES):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            self.message.emit("Нет сохранённого состояния PowerToys")
            return False
        self.configure(original, restore=True)
        return True

    def new_connection(self):
        try:
            if self.backup.exists():
                self.backup.replace(self.backup.with_suffix(".previous.json"))
            return True
        except OSError:
            self.message.emit("Не удалось сохранить предыдущую резервную копию PowerToys")
            return False

    def _get(self):
        self.busy = True
        self.status = "Применяю настройки…"
        self.changed.emit()
        self._stage = "get"
        try:
            self._native_before = json.loads(self.native_path.read_text(encoding="utf-8-sig")) if self.native_path.is_file() else None
            if self._native_before is not None and not all(type(self._native_before.get("enabled", {}).get(key)) is bool for key in MODULES):
                raise ValueError("Unknown native PowerToys settings format")
        except (OSError, ValueError, TypeError, AttributeError):
            self._fail("Не удалось сохранить исходные параметры PowerToys. Подключение не изменено.")
            return
        self._start(["get", "--resource", "settings", "--module", "App"])

    def _start(self, arguments):
        self.process.setProgram(str(self.root/"PowerToys.DSC.exe"))
        self.process.setArguments(arguments)
        self.process.start()
        self.timeout.start(15000)

    def _finished(self, code, exit_status):
        self.timeout.stop()
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8-sig", errors="replace")
        if code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            self._fail("PowerToys не применил настройки. Открой его параметры и попробуй снова.")
            return
        try:
            payload, _ = json.JSONDecoder().raw_decode(raw.lstrip())
            settings = payload["settings"]
            enabled = settings["enabled"]
            if not all(type(enabled.get(key)) is bool for key in MODULES):
                raise ValueError("Unsupported PowerToys settings format")
            self.actual = {key: enabled[key] for key in MODULES}
            native_enabled = self._native_before["enabled"] if self._native_before is not None else enabled
            self._any_enabled = any(value is True for value in native_enabled.values())
            if self._stage == "get":
                if not self._restore and not self.backup.exists():
                    temporary = self.backup.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"managed_enabled": self.actual,
                        "settings": settings, "native_settings": self._native_before}, ensure_ascii=False, indent=2), encoding="utf-8")
                    temporary.replace(self.backup)
                requested = dict(self.desired)
                reload = self._fresh or self.actual != requested
                self._fresh = False
                if reload:
                    self._runner_handle = close_powertoys_runner(self.root)
                    if self._runner_handle:
                        self._restart = True
                        self._pending_settings = settings
                        self._closing_at = time.monotonic()
                        self.status = "Перезапускаю модули PowerToys…"
                        self.changed.emit()
                        self.runner_poll.start()
                        return
                if self.actual == requested:
                    self._complete()
                    return
                self._send_settings(settings)
            else:
                if self.actual != self._sent:
                    raise ValueError("PowerToys did not accept the requested flags")
                self._retain_native_settings()
                if self.desired != self._sent:
                    self._get()  # A profile changed while the previous request was pending.
                else:
                    self._complete()
        except (ValueError, KeyError, TypeError, OSError):
            self._fail("Не удалось прочитать настройки PowerToys. Остальные модули работают.")

    def _complete(self):
        self.busy = False
        self._resume_runner()
        self.status = "Исходное состояние восстановлено" if self._restore else "Подключён"
        self.changed.emit()

    def _send_settings(self, settings):
        settings["enabled"].update(self.desired)
        self._any_enabled = any(value is True for value in settings["enabled"].values())
        self._sent = dict(self.desired)
        self._stage = "set"
        self._start(["set", "--resource", "settings", "--module", "App", "--input",
                     json.dumps({"settings": settings}, ensure_ascii=False)])

    def _retain_native_settings(self):
        if self._native_before is None:
            return
        expected = {**self._native_before, "enabled": {**self._native_before["enabled"], **self._sent}}
        current = json.loads(self.native_path.read_text(encoding="utf-8-sig"))
        if current != expected:
            temporary = self.native_path.with_suffix(".cloud-hub.tmp")
            temporary.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.native_path)
        self._any_enabled = any(value is True for value in expected["enabled"].values())

    def _runner_closed(self):
        kernel = ctypes.windll.kernel32
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        result = kernel.WaitForSingleObject(ctypes.c_void_p(self._runner_handle), 0)
        if result == 0:
            self.runner_poll.stop()
            kernel.CloseHandle(ctypes.c_void_p(self._runner_handle))
            self._runner_handle = None
            # Closing the runner can save its stale in-memory enable flags.
            # Reapply the complete pre-close snapshot, changing only our flags.
            self._send_settings(self._pending_settings)
        elif time.monotonic()-self._closing_at > 8:
            self.runner_poll.stop()
            kernel.CloseHandle(ctypes.c_void_p(self._runner_handle))
            self._runner_handle = None
            self._fail("PowerToys не завершился. Закрой его через трей и повтори подключение.")

    def _resume_runner(self):
        if self._any_enabled and self.root and (self.root/"PowerToys.exe").is_file():
            ok, _ = QProcess.startDetached(str(self.root/"PowerToys.exe"), ["--dont-elevate"])
            if not ok:
                self.message.emit("Настройки сохранены. Запусти PowerToys вручную.")
        self._restart = False

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.timeout.stop()
            self._fail("Не удалось запустить PowerToys DSC. Обнови PowerToys.")

    def _fail(self, text):
        self.busy = False
        if self._restart:
            self._resume_runner()
        self.status = text
        self.changed.emit()
        self.message.emit(text)

    def launch(self, name, arguments=()):
        self.root = powertoys_root()
        allowed = {"PowerToys.exe", "PowerToys.WorkspacesEditor.exe",
                   "PowerToys.WorkspacesLauncher.exe", "FancyZonesCLI.exe"}
        if not self.root or name not in allowed or not (self.root/name).is_file():
            self.message.emit("Установи PowerToys и подключи его в разделе «Модули».")
            return False
        ok, _ = QProcess.startDetached(str(self.root/name), list(arguments))
        if not ok:
            self.message.emit("Не удалось запустить PowerToys")
        return ok

    def launch_workspace(self, identifier):
        valid = {entry[0] for entry in load_workspaces()}
        if identifier not in valid:
            self.message.emit("Набор больше не существует. Обнови список.")
            return False
        return self.launch("PowerToys.WorkspacesLauncher.exe", [identifier])

    def close(self, restore=False):
        if restore and self.backup.exists():
            self.restore()
        deadline = time.monotonic()+12
        while self.busy and time.monotonic() < deadline:
            # A GET's finished handler can start a SET; drain both before exit.
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.waitForFinished(250)
            QCoreApplication.processEvents()
            QThread.msleep(10)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.runner_poll.stop()
        if self._runner_handle:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._runner_handle))
            self._runner_handle = None
