# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""These checks must actually run against PostgreSQL before the sales gate is approved."""
import threading
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase, override_settings
from .auth import identity_user
from .billing import checkout, apply_payment
from .models import Plan, Payment, GrantPeriod


@skipUnless(connection.vendor == 'postgresql', 'requires PostgreSQL row locks; SQLite cannot verify this')
@override_settings(SALES_ENABLED=True, CONSENT_VERSION='fixture', YOOKASSA_SHOP_ID='fixture-shop',
                   YOOKASSA_SECRET_KEY='fixture-key', YOOKASSA_TEST=True)
class ConcurrentLedgerTests(TransactionTestCase):
    def setUp(self):
        self.user = identity_user('concurrent-user')
        self.plan = Plan.objects.create(code='month', name='Месяц', amount_kopecks=24900, months=1, enabled=True)

    def parallel(self, operation):
        barrier = threading.Barrier(2)
        failures = []
        results = []
        def work():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                results.append(operation())
            except BaseException as exc:
                failures.append(exc)
            finally:
                close_old_connections()
        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(15)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        return results

    def test_simultaneous_checkout_has_one_payment(self):
        results = self.parallel(lambda: checkout(self.user, self.plan.pk).pk)
        self.assertEqual(results[0], results[1])
        self.assertEqual(Payment.objects.count(), 1)

    def test_simultaneous_success_has_one_grant(self):
        payment = checkout(self.user, self.plan.pk)
        remote = {'id': 'fixture-payment', 'status': 'succeeded', 'paid': True,
                  'recipient': {'account_id': 'fixture-shop'}, 'test': True,
                  'metadata': {'cloud_payment_id': str(payment.id)},
                  'amount': {'value': '249.00', 'currency': 'RUB'}}
        self.parallel(lambda: apply_payment(payment.pk, remote).pk)
        self.assertEqual(GrantPeriod.objects.count(), 1)
