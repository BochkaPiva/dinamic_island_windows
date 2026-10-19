# SPDX-License-Identifier: GPL-3.0-only
"""Small native account surface; network and browser authorization run off the GUI thread."""
import platform
import threading
from datetime import datetime
from urllib.parse import urlsplit
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QComboBox, QFrame
from .account_client import AccountSession, AccountError


MESSAGES = {
    'authentication_required': 'Войдите в аккаунт.', 'invalid_grant': 'Сеанс завершён. Войдите ещё раз.',
    'invalid_token': 'Войдите ещё раз.', 'connection_failed': 'Нет связи с сервером. Действующий доступ сохранён.',
    'login_timeout': 'Время ожидания входа истекло. Попробуйте ещё раз.', 'login_canceled': 'Вход отменён.',
    'device_limit': 'Достигнут лимит устройств. Отключите ненужное устройство и войдите снова.',
    'payment_pending_reconciliation': 'Проверяем состояние платежа. Не оплачивайте повторно.',
    'checkout_not_available': 'Сейчас начать оплату не удалось. Обновите состояние аккаунта.',
}


class AccountController(QObject):
    changed = Signal()
    completed = Signal(object)

    def __init__(self, origin, directory, access, parent=None):
        super().__init__(parent)
        self.session = AccountSession(origin, directory, access.installation_id)
        self.access = access
        self.profile = None
        self.config = {}
        self.busy = False
        self.message = ''
        self.stopped = False
        self.completed.connect(self._complete)
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 3600 * 1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(500, self.refresh)

    def _run(self, operation):
        if self.busy or self.stopped:
            return
        self.busy, self.message = True, ''
        self.changed.emit()
        def work():
            try:
                result = operation()
            except AccountError as exc:
                result = {'error': MESSAGES.get(exc.code, 'Действие не выполнено. Попробуйте ещё раз.'),
                          'reauth': exc.status == 401 or exc.code == 'invalid_grant'}
            except (OSError, ValueError, KeyError, TypeError):
                result = {'error': 'Не удалось безопасно сохранить или проверить данные аккаунта.'}
            except Exception:
                result = {'error': 'Действие не выполнено. Обновите состояние аккаунта.'}
            try:
                self.completed.emit(result)
            except RuntimeError:
                pass  # Application was closed during a network request.
        threading.Thread(target=work, daemon=True, name='cloud-account').start()

    def _snapshot(self):
        config = self.session.configuration()
        if not self.session.tokens:
            return {'config': config, 'profile': None}
        profile = self.session.api('account')
        registered = any(d['current'] and d['active'] for d in profile.get('devices', []))
        return {'config': config, 'profile': profile,
                'license': self.session.api('license', {}).get('license') if registered else None}

    def refresh(self):
        self._run(self._snapshot)

    def sign_in(self):
        def operation():
            self.session.sign_in(platform.node() or 'Мой компьютер')
            return self._snapshot()
        self._run(operation)

    def sign_out(self):
        def operation():
            self.session.sign_out()
            return {'profile': None, 'signed_out': True}
        self._run(operation)

    def cancel(self):
        def operation():
            self.session.api('subscription/cancel', {})
            return self._snapshot()
        self._run(operation)

    def revoke(self, identifier):
        def operation():
            self.session.api('devices/' + identifier + '/revoke', {})
            return self._snapshot()
        self._run(operation)

    def pay(self, plan, auto_renew):
        selected = next(p for p in self.profile['plans'] if p['code'] == plan)
        expected_amount, expected_months = selected['amount_kopecks'], selected['months']
        def operation():
            return {'checkout': self.session.api('checkout', {'plan': plan, 'auto_renew': auto_renew,
                                    'expected_amount_kopecks': expected_amount, 'expected_months': expected_months,
                                    'consent_version': self.config.get('consent_version', '')})}
        self._run(operation)

    def _complete(self, result):
        if self.stopped:
            return
        self.busy = False
        self.message = result.get('error', '')
        self.config = result.get('config', self.config)
        if 'profile' in result:
            self.profile = result['profile']
        if result.get('reauth'):
            self.profile = None
        if result.get('license'):
            try:
                self.access.install_license(result['license'])
            except (OSError, ValueError):
                self.message = 'Не удалось проверить разрешение сервера. Текущий доступ сохранён.'
        elif ('license' in result and result.get('profile') and
                result['profile']['subscription']['edition'] == 'free'):
            try:
                (self.session.directory / 'license.json').unlink(missing_ok=True)
                self.access.reload()
            except OSError:
                self.message = 'Не удалось обновить локальное разрешение.'
        if result.get('signed_out'):
            self.access.reload()
        payment = result.get('checkout')
        if payment:
            value = payment.get('confirmation_url') or ''
            parsed = urlsplit(value)
            host = parsed.hostname or ''
            if (parsed.scheme == 'https' and not parsed.username and not parsed.password and
                    parsed.port in (None, 443) and any(host == d or host.endswith('.'+d) for d in ('yookassa.ru','yoomoney.ru'))):
                QDesktopServices.openUrl(QUrl(value))
                self.message = 'Оплата открыта в браузере. После оплаты нажмите «Обновить».'
            else:
                self.message = 'Платёж обрабатывается. Обновите состояние аккаунта.'
        self.changed.emit()

    def stop(self):
        self.stopped = True
        self.timer.stop()


def label(value, muted=False):
    widget = QLabel(value)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if muted:
        widget.setObjectName('muted')
    return widget


class AccountPanel(QWidget):
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        if controller:
            controller.changed.connect(self.render)
        self.render()

    def _card(self, title):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title_label = label(title)
        title_label.setObjectName('cardTitle')
        layout.addWidget(title_label)
        self.layout_.addWidget(frame)
        return layout

    def _button(self, text, callback):
        button = QPushButton(text)
        button.setEnabled(not self.controller.busy)
        button.clicked.connect(callback)
        return button

    def render(self):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        controller = self.controller
        if not controller:
            card = self._card('Аккаунт')
            card.addWidget(label('Вход и оплата появятся после подключения сервера.', True))
            card.addWidget(label('Ваши группы, заметки и настройки остаются на этом компьютере.', True))
            self.layout_.addStretch()
            return
        profile = controller.profile
        card = self._card(profile.get('email') or 'Ваш аккаунт' if profile else 'Ваше пространство')
        if controller.message:
            card.addWidget(label(controller.message, True))
        if controller.busy:
            card.addWidget(label('Подключаемся…', True))
        actions = QHBoxLayout()
        if not profile:
            if 'yandex' in controller.config.get('login_providers', []):
                actions.addWidget(self._button('Продолжить с Яндекс ID', controller.sign_in))
        else:
            actions.addWidget(self._button('Выйти', controller.sign_out))
            if not any(d['current'] and d['active'] for d in profile.get('devices', [])):
                actions.addWidget(self._button('Подключить этот компьютер', controller.sign_in))
        actions.addWidget(self._button('Обновить', controller.refresh))
        actions.addStretch()
        card.addLayout(actions)
        if profile:
            sub = profile['subscription']
            card = self._card('Подписка' if sub['edition'] == 'pro' else 'Бесплатный доступ')
            if sub.get('paid_until'):
                date = datetime.fromisoformat(sub['paid_until']).astimezone().strftime('%d.%m.%Y')
                card.addWidget(label('Доступ до ' + date, True))
            if sub.get('auto_renew'):
                card.addWidget(label('Автопродление включено', True))
                card.addWidget(self._button('Отключить продление', controller.cancel))
            plans = profile.get('plans', [])
            if plans:
                selector = QComboBox()
                for plan in plans:
                    selector.addItem(f"{plan['name']} · {plan['amount_kopecks']/100:g} ₽", plan['code'])
                card.addWidget(selector)
                consent = QCheckBox('Автоматически продлевать по выбранной цене. Можно отключить в любой момент.')
                consent.setVisible(controller.config.get('renewals_enabled', False))
                card.addWidget(consent)
                selector.currentIndexChanged.connect(lambda _: consent.setChecked(False))
                # Snapshot choices before controller.changed rebuilds this panel.
                def pay():
                    choice, renew = selector.currentData(), consent.isChecked()
                    controller.pay(choice, renew)
                card.addWidget(self._button('Перейти к оплате', pay))
            devices = self._card('Устройства')
            for device in profile.get('devices', []):
                if not device['active']:
                    continue
                row = QHBoxLayout()
                row.addWidget(label(device['name'] + (' · этот компьютер' if device['current'] else '')), 1)
                if not device['current']:
                    row.addWidget(self._button('Отключить', lambda checked=False, key=device['id']: controller.revoke(key)))
                devices.addLayout(row)
            payments = profile.get('payments', [])
            if payments:
                history = self._card('Последние платежи')
                statuses = {'succeeded': 'Оплачен', 'canceled': 'Отменён', 'pending': 'Ожидает оплаты',
                            'manual_review': 'На сверке', 'unknown': 'Проверяется'}
                for payment in payments[:5]:
                    date = datetime.fromisoformat(payment['created_at']).astimezone().strftime('%d.%m.%Y')
                    status = statuses.get(payment['status'], 'Обрабатывается')
                    refunded = payment.get('refunded_kopecks', 0)
                    if refunded:
                        status = 'Возвращён' if refunded >= payment['amount_kopecks'] else 'Частичный возврат'
                    history.addWidget(label(f"{date} · {payment['amount_kopecks']/100:g} ₽ · {status}", True))
        self.layout_.addStretch()
