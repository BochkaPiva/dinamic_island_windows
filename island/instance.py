# SPDX-License-Identifier: GPL-3.0-only
"""Same-user local IPC for activation and graceful installer shutdown."""
import hashlib
import json
import os
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from .storage import data_dir


def server_name():
    identity = str(data_dir().resolve()).casefold().encode("utf-8")
    return "BochkaPiva.CloudIsland." + hashlib.sha256(identity).hexdigest()[:24]


def notify_existing(command):
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(500):
        return False
    socket.write(command.encode("ascii")+b"\n")
    socket.waitForBytesWritten(1000)
    if not socket.bytesAvailable():
        socket.waitForReadyRead(15000)
    reply = bytes(socket.readAll()).strip()
    socket.disconnectFromServer()
    return reply == b"ok"


def query_status():
    socket=QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(500):
        return {"running":False}
    socket.write(b"status\n")
    socket.waitForBytesWritten(1000)
    if not socket.bytesAvailable():
        socket.waitForReadyRead(2000)
    try:
        return json.loads(bytes(socket.readAll()))
    except ValueError:
        return {"running":False}
    finally:
        socket.disconnectFromServer()


class InstanceServer(QObject):
    def __init__(self, window, application):
        super().__init__(window)
        self.window, self.application = window, application
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self.connections = set()

    def listen(self):
        return self.server.listen(server_name())

    def _accept(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            self.connections.add(connection)
            connection.disconnected.connect(lambda c=connection: self._discard(c))
            connection.readyRead.connect(lambda c=connection: self._read(c))
            if connection.bytesAvailable():
                self._read(connection)

    def _discard(self, connection):
        self.connections.discard(connection)
        connection.deleteLater()

    def _read(self, connection):
        if not connection.canReadLine():
            if connection.bytesAvailable() > 64:
                connection.disconnectFromServer()
            return
        command = bytes(connection.readLine(64)).strip()
        if command == b"status":
            w=self.window
            from . import __version__
            report={"running":True,"version":__version__,"pid":os.getpid(),"profile":w._policy.profile,
                    "spectrum_policy":w._policy.spectrum,"audio_enabled":w.audio.enabled.is_set(),
                    "audio_capture":w.audio.capture_active.is_set(),"spectrum_levels":list(w.status_mark.levels),
                    "island_visible":w.isVisible(),"island_expanded":w._island_expanded,
                    "spectrum_battery_save":w.settings.get("spectrum_battery_save"),
                    "audio_economy":w.audio.economy.is_set(),"timer_alarm":w.notch_hub.alarm.active,
                    "timer_sounding":w.notch_hub.alarm.sounding,
                    "timer_remaining":w.notch_hub.timer_seconds(),"timer_running":bool(w.notch_hub._timer_end),
                    "search_glass_requested":w.modules.search.backdrop_applied,
                    "desktop_enabled":w.modules.desktop.enabled,
                    "desktop_groups":len(w.modules.desktop.panels),
                    "desktop_visible":sum(p.isVisible() for p in w.modules.desktop.panels.values()),
                    "desktop_animating":sum(p.animation.isActive() for p in w.modules.desktop.panels.values()),
                    "island_animating":w._geometry.timer.isActive(),
                    "hub_visible":bool(w.control_center and w.control_center.isVisible()),
                    "hub_page":w.control_center.pages.currentIndex() if w.control_center else None}
            connection.write(json.dumps(report).encode("utf-8"))
            connection.flush()
            connection.disconnectFromServer()
            return
        if command == b"quit":
            self.window.cleanup()
        elif command == b"show":
            self.window._show_panel()
        elif command == b"hub":
            self.window.show_hub()
        elif command == b"ping":
            pass  # An overlapping background/login launch must not open settings.
        else:
            connection.disconnectFromServer()
            return
        connection.write(b"ok\n")
        connection.flush()
        connection.disconnectFromServer()
        if command == b"quit":
            QTimer.singleShot(0, self.application.quit)
