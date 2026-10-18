# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QCheckBox
from island.account_ui import AccountController, AccountPanel
from island.entitlements import FeatureAccess


class FakeController(QObject):
    changed = Signal()
    busy = False
    message = ''
    config = {'login_providers': ['yandex'], 'renewals_enabled': True}
    profile = {'email': 'Тестовый аккаунт', 'subscription': {'edition': 'free'}, 'devices': [], 'payments': [],
               'plans': [{'code': 'monthly', 'name': 'Месяц', 'amount_kopecks': 24900}]}
    def refresh(self): pass
    def sign_in(self): pass
    def sign_out(self): pass
    def cancel(self): pass
    def pay(self, plan, renew): self.choice = (plan, renew)


class AccountUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_payment_consent_is_unchecked_and_explicit(self):
        controller = FakeController()
        panel = AccountPanel(controller)
        consent = panel.findChild(QCheckBox)
        self.assertFalse(consent.isChecked())
        button = next(b for b in panel.findChildren(QPushButton) if b.text() == 'Перейти к оплате')
        button.click()
        self.assertEqual(controller.choice, ('monthly', False))
        consent.setChecked(True)
        button.click()
        self.assertEqual(controller.choice, ('monthly', True))
        panel.deleteLater()

    def test_worker_does_not_block_gui_and_transient_error_keeps_access(self):
        with tempfile.TemporaryDirectory() as folder:
            access = FeatureAccess(folder)
            controller = AccountController('https://accounts.example.test', folder, access)
            controller.timer.stop()
            ticks = []
            timer = QTimer()
            timer.setInterval(5)
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start()
            def operation():
                time.sleep(.07)
                return {'error': 'offline'}
            controller._run(operation)
            self.assertTrue(controller.busy)
            QTest.qWait(140)
            self.assertFalse(controller.busy)
            self.assertGreater(len(ticks), 2)
            self.assertEqual(access.grant.edition, 'preview')
            controller.stop()
            timer.stop()
            controller.deleteLater()

    def test_unconfigured_page_has_no_fake_checkout(self):
        panel = AccountPanel()
        self.assertFalse(panel.findChildren(QPushButton))
        panel.deleteLater()
