# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal native community surface and bounded background subscription checks."""
import threading
import time
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel, QPushButton
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


class CommunityBenefits(QWidget):
    """One selectable preview plus a literal comparison of existing features."""
    def __init__(self,owner=None,parent=None):
        super().__init__(parent)
        self.owner=owner
        from .module_preview import FormPreview
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(12)
        grid=QGridLayout();grid.setHorizontalSpacing(20);grid.setVerticalSpacing(12)
        for column,title in enumerate(('Возможности','Без входа','С подпиской')):
            label=text(title);label.setObjectName('paneTitle');grid.addWidget(label,0,column)
        for row,values in enumerate((('Форма','Чёлка','Чёлка и остров'),
            ('Группы на рабочем столе','2 активные','Все группы'),
            ('Поиск, заметки, таймер','Доступны','Доступны'),
            ('Видеофайлы, камера, закрепление','—','Доступны')),1):
            for column,value in enumerate(values):
                grid.addWidget(text(value,column>0),row,column)
        grid.setColumnStretch(0,1)
        root.addLayout(grid)
        if owner:
            controls=QHBoxLayout()
            self.preview=FormPreview(owner,'floating')
            self.preview.setFixedHeight(100)
            self.preview_buttons=[]
            for style,title in (('notch','Чёлка'),('floating','Остров')):
                button=QPushButton(title);button.setObjectName('segment');button.setCheckable(True)
                button.setChecked(style=='floating')
                button.clicked.connect(lambda _,s=style:self.select_preview(s))
                controls.addWidget(button);self.preview_buttons.append((style,button))
            controls.addStretch()
            root.addLayout(controls);root.addWidget(self.preview)
        self.setAccessibleName('Без входа: чёлка и две группы. С подпиской: плавающий остров и дополнительные группы.')

    def select_preview(self,style):
        self.preview.display_style=style
        self.preview.update()
        for key,button in self.preview_buttons: button.setChecked(style==key)


class CommunityPanel(QWidget):
    """Keep the widget tree alive across worker and entitlement notifications.

    Reparenting a widget owned only by a layout can destroy its Python wrapper
    immediately. Rebuilding here also discarded focus and every live preview.
    Build once; notifications only update text, visibility and enabled states.
    """
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(14)
        owner = controller.parent() if controller else None
        if not owner or not hasattr(owner, 'snapshot'):
            owner = None
        self.owner = owner
        hero = QFrame(self)
        hero.setObjectName('hero')
        inside = QVBoxLayout(hero)
        inside.setContentsMargins(16, 14, 16, 14)
        inside.setSpacing(12)
        self.status = text('')
        self.status.setObjectName('secondary')
        self.status.setAccessibleName('Состояние подключения Telegram')
        self.title = text('')
        self.title.setObjectName('paneTitle')
        self.detail = text('', True)
        self.message = text('', True)
        for label in (self.status, self.title, self.detail, self.message):
            inside.addWidget(label)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.primary = self.button('', self._primary_action)
        self.primary.setObjectName('primary')
        self.channel = self.button('Открыть канал', self._open_channel)
        self.channel.setObjectName('')
        actions.addWidget(self.primary)
        actions.addWidget(self.channel)
        actions.addStretch()
        inside.addLayout(actions)
        self.disconnect_button = self.button('Отключить на этом ПК', self._disconnect)
        inside.addWidget(self.disconnect_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.restart_button = self.button('Начать подключение заново', self._restart)
        inside.addWidget(self.restart_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout_.addWidget(hero)
        self.benefits = CommunityBenefits(owner, self)
        self.layout_.addWidget(self.benefits)
        from .hub_ui import SettingsSection
        help_section = SettingsSection('Как работает подключение')
        self.layout_.addWidget(help_section)
        help_card = help_section.content
        help_card.addWidget(text(
            'Один раз подключи Telegram через бота. Дальше Nelviro проверяет подписку автоматически.', True))
        help_card.addWidget(text(
            'Проверка — раз в 6 часов. Без интернета последнее подтверждение действует до 72 часов. '
            'После отписки — 24 часа, чтобы вернуться в канал.', True))
        help_card.addWidget(text(
            'Базовые инструменты работают без входа. Если расширенный доступ закончится, '
            'дополнительные группы сохранятся вместе с содержимым. Оплата и банковская карта не нужны.', True))
        self.layout_.addStretch()
        if controller:
            controller.changed.connect(self.render)
            controller.access.changed.connect(self.render)
        self.render()

    def card(self, title, detail):
        frame = QFrame(self)
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
        button.setMinimumHeight(32)
        if title in {'Подключить Telegram','Настроить остров','Открыть канал'}: button.setObjectName('primary')
        button.setEnabled(active and not (self.controller and self.controller.busy))
        button.clicked.connect(callback)
        return button

    def _open_channel(self):
        QDesktopServices.openUrl(QUrl(build_config.COMMUNITY_CHANNEL_URL))

    def _primary_action(self):
        controller = self.controller
        if not controller or not controller.client:
            self._open_channel()
        elif controller.busy:
            return
        elif controller.connected:
            controller.refresh()
        elif controller.client.pairing:
            QDesktopServices.openUrl(QUrl(controller.client.pairing['bot_url']))
        else:
            controller.connect_telegram()

    def _disconnect(self):
        if self.controller and not self.controller.busy:
            self.controller.disconnect()

    def _restart(self):
        if self.controller and not self.controller.busy:
            self.controller.connect_telegram()

    def render(self):
        controller = self.controller
        permit = controller.permit if controller else None
        active = bool(permit and permit.allows(controller.clock()))
        connected = bool(controller and controller.connected)
        configured = bool(controller and controller.client)
        pairing = bool(configured and controller.client.pairing)
        busy = bool(controller and controller.busy)
        if active and permit.state == 'grace':
            status, title = 'Нужно подтвердить подписку', 'Вернись в сообщество'
            detail = 'Подпишись на канал и нажми «Проверить подписку». Расширенные инструменты пока доступны.'
        elif active:
            status, title = 'Подписка подтверждена', 'Всё подключено'
            detail = 'Плавающий остров, видеоплеер для файлов, зеркало камеры и дополнительные группы доступны на этом компьютере.'
        elif connected:
            status, title = 'Telegram подключён', 'Подтверди подписку на канал'
            detail = 'Открой канал, подпишись и вернись сюда для проверки. Базовые инструменты уже работают.'
        elif pairing:
            status, title = 'Ожидаем подтверждение', 'Продолжи в Telegram'
            detail = 'В боте нажми «Проверить подписку». После подтверждения возможности откроются автоматически.'
        else:
            status, title = 'Без оплаты · без пароля', 'Расширенные возможности'
            detail = 'Подпишись на Nelviro в Telegram, чтобы открыть дополнительные инструменты. Подключение займёт пару шагов.'
        if controller and controller.candidate is not None:
            status = 'Подключаем расширенные возможности…'
        if not configured:
            detail = 'Сервис проверки ещё не подключён. Базовые инструменты уже доступны без входа.'
        self.status.setText('Проверяем подключение…' if busy else status)
        self.title.setText(title)
        self.detail.setText(detail)
        self.message.setText(controller.message if controller else '')
        self.message.setVisible(bool(self.message.text()))
        self.primary.setText('Проверяем…' if busy else 'Открыть канал' if not configured else
            'Проверить подписку' if connected else 'Открыть бота' if pairing else 'Подключить Telegram')
        self.primary.setEnabled(not busy)
        self.channel.setVisible(configured)
        self.disconnect_button.setVisible(connected)
        self.disconnect_button.setEnabled(not busy)
        self.restart_button.setVisible(pairing and not connected)
        self.restart_button.setEnabled(not busy)
