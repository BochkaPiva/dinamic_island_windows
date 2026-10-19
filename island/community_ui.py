# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal native community surface and bounded background subscription checks."""
import threading
import time
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton
from .community_client import CommunityClient, CommunityError
from . import build_config


MESSAGES = {
    'connection_failed': 'Нет связи с сервисом. Базовые функции доступны, последнее подтверждение сохранено.',
    'device_not_connected': 'Подключите Telegram ещё раз. Базовые функции работают без входа.',
    'community_temporarily_unavailable': 'Проверка временно недоступна. Последнее подтверждение сохранено.',
    'pairing_expired': 'Время подключения истекло. Начните ещё раз.',
    'pairing_unavailable': 'Запрос больше не действует. Начните подключение ещё раз.',
    'installation_already_linked': 'Эта установка связана с другим Telegram. Сначала отключите прежнее подключение.',
    'too_many_pairings': 'Подождите несколько минут перед новым подключением.',
}


class CommunityController(QObject):
    changed = Signal()
    completed = Signal(object)

    def __init__(self, directory, access, parent=None, *, origin=None, keys=None, channel_id=None,
                 allow_local=False, auto_start=True, clock=None):
        super().__init__(parent)
        self.access = access
        self.clock = clock or time.time
        self.busy = self.stopped = False
        self.message = ''
        self.candidate = None
        self.retry_at = 0
        self.last_attempt = 0
        self.client = None
        self._permit = None
        origin = build_config.COMMUNITY_API_ORIGIN if origin is None else origin
        if origin:
            self.client = CommunityClient(origin, directory, access.installation_id,
                build_config.COMMUNITY_PUBLIC_KEYS if keys is None else keys,
                build_config.COMMUNITY_CHANNEL_ID if channel_id is None else channel_id,
                allow_local=allow_local, clock=self.clock)
            self._permit = self.client.store.load()
        self.completed.connect(self._complete)
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        if self.client and self.client.pairing:
            self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        if auto_start:
            self.timer.start()
            QTimer.singleShot(800, self.tick)

    @property
    def connected(self):
        return bool(self.client and self.client.session)

    @property
    def permit(self):
        return self._permit

    def _run(self, operation):
        if self.busy or self.stopped or not self.client:
            return
        self.busy = True
        self.message = ''
        self.last_attempt = self.clock()
        self.changed.emit()

        def worker():
            try:
                result = operation()
            except CommunityError as exc:
                result = {'error': MESSAGES.get(exc.code, 'Не удалось выполнить проверку. Попробуйте ещё раз.')}
            except Exception:
                # No exception strings here: they can contain URLs, tokens or response bodies.
                result = {'error': 'Не удалось безопасно проверить подключение. Базовые функции доступны.'}
            try:
                self.completed.emit(result)
            except RuntimeError:
                pass
        threading.Thread(target=worker, daemon=True, name='nelviro-community').start()

    def connect_telegram(self):
        self.candidate = None
        self._run(lambda: {'pairing': self.client.start_pairing()})

    def confirm(self):
        if self.candidate is None:
            return
        identifier = self.candidate
        def operation():
            self.client.confirm_pairing(identifier)
            return {'refresh': True, 'confirmed': True}
        self._run(operation)

    def refresh(self):
        if not self.connected:
            return
        def operation():
            self.client.refresh()
            return {'refresh': True}
        self._run(operation)

    def disconnect(self):
        def operation():
            try:
                self.client.disconnect()
                return {'disconnected': True}
            except CommunityError:
                self.client.forget_local()
                return {'disconnected': True, 'message': 'Подключение удалено с этого компьютера. Отзыв на сервере пока не подтверждён.'}
        self._run(operation)

    def tick(self):
        if self.stopped:
            return
        now = self.clock()
        self.access._expire()
        if not self.client or self.busy or now < self.retry_at:
            return
        if self.client.pairing and self.candidate is None and now - self.last_attempt >= 3:
            self._run(lambda: {'candidate': self.client.pairing_status()})
            return
        if self.client.pairing and self.candidate is not None and now-self.last_attempt>=60:
            self.confirm()
            return
        permit = self.permit
        if self.connected and (not permit or permit.needs_refresh(now)) and now - self.last_attempt >= 300:
            self.refresh()

    def _complete(self, result):
        if self.stopped:
            return
        self.busy = False
        self.message = result.get('error', result.get('message', ''))
        if result.get('error'):
            self.retry_at = self.clock() + 60
        else:
            self.retry_at = 0
        if self.client and self.client.session and not self.client.pairing:
            self.candidate = None
            self.timer.setInterval(60000)
        candidate = result.get('candidate')
        if candidate and candidate.get('state') == 'confirm' and type(candidate.get('telegram_id')) is int:
            self.candidate = candidate['telegram_id']
            QTimer.singleShot(0,self.confirm)
        if result.get('confirmed') or result.get('disconnected'):
            self.candidate = None
            self.timer.setInterval(60000)
        if result.get('refresh') or result.get('disconnected'):
            self._permit = self.client.store.load()
            self.access.reload()
        if result.get('pairing'):
            self.timer.setInterval(1000)
            QDesktopServices.openUrl(QUrl(result['pairing']['bot_url']))
            self.message = 'Подпишитесь и нажмите «Проверить подписку» в боте. Затем вернитесь сюда.'
        self.changed.emit()

    def stop(self):
        self.stopped = True
        self.timer.stop()


def text(value, secondary=False):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if secondary:
        label.setObjectName('secondary')
    return label


class CommunityPanel(QWidget):
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(16)
        if controller:
            controller.changed.connect(self.render)
            controller.access.changed.connect(self.render)
        self.render()

    def card(self, title, detail):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        heading = text(title)
        heading.setObjectName('cardTitle')
        layout.addWidget(heading)
        layout.addWidget(text(detail, True))
        self.layout_.addWidget(frame)
        return layout

    def button(self, title, callback, *, active=True):
        button = QPushButton(title)
        button.setMinimumHeight(40)
        button.setEnabled(active and not (self.controller and self.controller.busy))
        button.clicked.connect(callback)
        return button

    def render(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        controller = self.controller
        base = self.card('Работает без входа',
            'Dynamic Island, поиск, две группы рабочего стола, таймер и локальные заметки. Без оплаты и регистрации.')
        base.addWidget(text('Ваши файлы и настройки остаются на компьютере.', True))
        permit = controller.permit if controller else None
        active = bool(permit and permit.allows(controller.clock()))
        title = 'Расширенные возможности подключены' if active else 'Больше пространства'
        extended = self.card(title,
            'Дополнительные группы рабочего стола — за подписку на канал Nelviro. Новые функции и варианты оформления будем добавлять постепенно.')
        if permit and permit.state == 'grace':
            extended.addWidget(text('Подписка не подтверждена. Подпишитесь снова, чтобы сохранить расширенный доступ.', True))
        if controller and controller.message:
            extended.addWidget(text(controller.message, True))
        actions = QHBoxLayout()
        if not controller or not controller.client:
            extended.addWidget(text('Сервис проверки ещё не подключён. Базовые инструменты уже доступны.', True))
            actions.addWidget(self.button('Открыть канал', lambda: QDesktopServices.openUrl(QUrl(build_config.COMMUNITY_CHANNEL_URL))))
        elif controller.candidate is not None:
            extended.addWidget(text('Подписка подтверждена. Подключаем расширенные возможности…', True))
            actions.addWidget(self.button('Начать заново',controller.connect_telegram))
        elif controller.connected:
            actions.addWidget(self.button('Проверить подписку', controller.refresh))
            actions.addWidget(self.button('Отключить на этом ПК', controller.disconnect))
        else:
            actions.addWidget(self.button('Подключить Telegram', controller.connect_telegram))
            if controller.client.pairing:
                actions.addWidget(self.button('Открыть бота', lambda: QDesktopServices.openUrl(QUrl(controller.client.pairing['bot_url']))))
        actions.addStretch()
        extended.addLayout(actions)
        extended.addWidget(text('При завершении доступа группы сохраняются в настройках. На рабочем столе остаются две активные.', True))
        self.layout_.addStretch()
