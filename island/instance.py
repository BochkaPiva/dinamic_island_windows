# SPDX-License-Identifier: GPL-3.0-only
"""Same-user local IPC for activation and graceful installer shutdown."""
import hashlib
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
        if command == b"quit":
            self.window.cleanup()
        elif command == b"show":
            self.window._show_panel()
        else:
            connection.disconnectFromServer()
            return
        connection.write(b"ok\n")
        connection.flush()
        connection.disconnectFromServer()
        if command == b"quit":
            QTimer.singleShot(0, self.application.quit)
