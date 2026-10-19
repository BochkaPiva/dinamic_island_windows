# SPDX-License-Identifier: GPL-3.0-only
import base64
import hashlib
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from oauth2_provider.models import AccessToken, RefreshToken
from .auth import identity_user, safe_next
from .billing import checkout, apply_payment, send_payment, active_until, add_months, cancel_renewal, queue_renewals, apply_refund, reconcile_refunds
from .licensing import license_for
from .models import User, Device, Plan, Payment, GrantPeriod, Subscription, ReceiptTask
from .provider import ProviderUnavailable


@override_settings(ROOT_URLCONF='cloud_accounts.legacy_urls', YOOKASSA_SHOP_ID='fixture-shop', YOOKASSA_SECRET_KEY='fixture-only',
    YOOKASSA_TEST=True, SALES_ENABLED=True, RENEWALS_ENABLED=True, CONSENT_VERSION='fixture-v1')
class BillingTests(TestCase):
    def setUp(self):
        self.user = identity_user('subject-a', 'contact@example.test')
        self.plan = Plan.objects.create(code='monthly', name='Месяц', amount_kopecks=24900, months=1, enabled=True)

    def remote(self, payment, status='succeeded', **changes):
        value = {'id': 'fixture-' + str(payment.id), 'status': status, 'paid': status == 'succeeded',
            'recipient': {'account_id': 'fixture-shop'}, 'test': True,
            'metadata': {'cloud_payment_id': str(payment.id)},
            'amount': {'value': f'{payment.amount_kopecks / 100:.2f}', 'currency': 'RUB'},
            'payment_method': {'id': 'fixture-method', 'saved': True}}
        value.update(changes)
        return value

    def paid(self, consent=False):
        payment = checkout(self.user, self.plan.pk, consent, 'fixture-v1')
        return apply_payment(payment.id, self.remote(payment))

    def test_checkout_reuses_open_payment(self):
        self.assertEqual(checkout(self.user, self.plan.pk).pk, checkout(self.user, self.plan.pk).pk)
        self.assertEqual(Payment.objects.count(), 1)

    def test_duplicate_success_grants_exactly_once(self):
        payment = self.paid()
        until = active_until(self.user)
        apply_payment(payment.pk, self.remote(payment))
        self.assertEqual(GrantPeriod.objects.count(), 1)
        self.assertEqual(ReceiptTask.objects.count(), 1)
        self.assertEqual(active_until(self.user), until)

    def test_redirect_never_grants(self):
        payment = checkout(self.user, self.plan.pk)
        self.client.get('/auth/done/?payment_id=' + str(payment.pk))
        self.assertIsNone(active_until(self.user))

    def test_wrong_canonical_data_rejected(self):
        payment = checkout(self.user, self.plan.pk)
        for changes in [{'test': False}, {'paid': False}, {'amount': {'value': '1.00', 'currency': 'RUB'}},
                        {'recipient': {'account_id': 'other-shop'}}, {'metadata': {}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                apply_payment(payment.pk, self.remote(payment, **changes))
        self.assertFalse(GrantPeriod.objects.exists())

    def test_stale_pending_cannot_downgrade_success(self):
        payment = self.paid()
        apply_payment(payment.pk, self.remote(payment, status='pending'))
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, 'succeeded')

    def test_timeout_uses_same_key_and_payload(self):
        payment = checkout(self.user, self.plan.pk)
        with patch('accounts.billing.YooKassa') as provider:
            provider.return_value.create.side_effect = ProviderUnavailable('timeout')
            with self.assertRaises(ProviderUnavailable):
                send_payment(payment.id)
            self.assertEqual(Payment.objects.get(pk=payment.pk).status, 'unknown')
            provider.return_value.create.side_effect = None
            provider.return_value.create.return_value = self.remote(payment, 'pending')
            send_payment(payment.id)
            calls = provider.return_value.create.call_args_list
            self.assertEqual(calls[0].args[0].id, calls[1].args[0].id)
            self.assertEqual(calls[0].args[0].request_payload, calls[1].args[0].request_payload)

    def test_old_ambiguous_payment_not_recharged(self):
        payment = checkout(self.user, self.plan.pk)
        Payment.objects.filter(pk=payment.pk).update(first_sent_at=timezone.now()-timedelta(hours=25), status='unknown')
        with patch('accounts.billing.YooKassa') as provider:
            self.assertEqual(send_payment(payment.id).status, 'manual_review')
            provider.return_value.create.assert_not_called()

    def test_no_autorenew_without_explicit_consent(self):
        self.paid()
        self.assertFalse(Subscription.objects.get(user=self.user).auto_renew)

    def test_one_off_purchase_does_not_change_recurring_terms_silently(self):
        self.paid(True)
        self.paid(False)
        self.assertFalse(Subscription.objects.get(user=self.user).auto_renew)

    def test_cancel_preserves_paid_access_and_cannot_resurrect(self):
        payment = checkout(self.user, self.plan.pk, True, 'fixture-v1')
        cancel_renewal(self.user)
        apply_payment(payment.pk, self.remote(payment))
        self.assertIsNotNone(active_until(self.user))
        self.assertFalse(Subscription.objects.get(user=self.user).auto_renew)

    def test_renewal_queued_once_and_canceled_before_send(self):
        self.paid(True)
        sub = Subscription.objects.get(user=self.user)
        now = sub.next_due + timedelta(seconds=1)
        self.assertEqual(queue_renewals(now), 1)
        self.assertEqual(queue_renewals(now), 0)
        renewal = Payment.objects.get(renewal_due__isnull=False)
        cancel_renewal(self.user)
        with patch('accounts.billing.YooKassa') as provider:
            self.assertEqual(send_payment(renewal.id).status, 'canceled')
            provider.return_value.create.assert_not_called()

    def test_plan_price_change_does_not_raise_existing_renewal(self):
        self.paid(True)
        sub = Subscription.objects.get(user=self.user)
        self.plan.amount_kopecks = 99900
        self.plan.save()
        queue_renewals(sub.next_due)
        self.assertEqual(Payment.objects.get(renewal_due__isnull=False).amount_kopecks, 24900)

    def test_month_end_anchor(self):
        start = datetime(2027, 1, 31, 12, tzinfo=tz.utc)
        feb = add_months(start, 1, 31)
        self.assertEqual(feb.day, 28)
        self.assertEqual(add_months(feb, 1, 31).day, 31)

    def test_partial_full_refund_replay_and_gap(self):
        first = self.paid()
        second = self.paid()
        refund = {'id': 'refund-one', 'payment_id': first.provider_id, 'status': 'succeeded',
                  'amount': {'value': '49.00', 'currency': 'RUB'}}
        apply_refund(refund)
        self.assertIsNotNone(active_until(self.user))
        apply_refund(refund)
        refund.update(id='refund-two', amount={'value': '200.00', 'currency': 'RUB'})
        apply_refund(refund)
        self.assertIsNone(active_until(self.user))  # Second period must not bridge a refunded first period.
        self.assertEqual(ReceiptTask.objects.count(), 4)
        self.assertIsNotNone(active_until(self.user, GrantPeriod.objects.get(payment=second).start))

    def test_webhook_fetches_authoritative_payment(self):
        payment = checkout(self.user, self.plan.pk)
        obj = self.remote(payment)
        with patch('accounts.api.YooKassa') as provider:
            provider.return_value.payment.return_value = self.remote(payment, 'pending')
            result = self.client.post('/hooks/yookassa', {'event': 'payment.succeeded', 'object': obj}, content_type='application/json')
            self.assertEqual(result.status_code, 200)
            provider.return_value.payment.assert_called_once_with(obj['id'])
        self.assertIsNone(active_until(self.user))

    def test_webhook_provider_timeout_is_retryable(self):
        payment = checkout(self.user, self.plan.pk)
        with patch('accounts.api.YooKassa') as provider:
            provider.return_value.payment.side_effect = ProviderUnavailable('timeout')
            result = self.client.post('/hooks/yookassa', {'event': 'payment.succeeded', 'object': self.remote(payment)}, content_type='application/json')
            self.assertEqual(result.status_code, 503)

    def test_lost_refund_webhook_recovered_from_provider_list(self):
        payment = self.paid()
        refund = {'id': 'missed-refund', 'payment_id': payment.provider_id, 'status': 'succeeded',
                  'amount': {'value': '249.00', 'currency': 'RUB'}}
        with patch('accounts.billing.YooKassa') as provider:
            provider.return_value.refunds.side_effect = [{'items': [], 'next_cursor': 'page-two'}, {'items': [refund]}]
            self.assertEqual(reconcile_refunds(), 1)
        self.assertIsNone(active_until(self.user))

    def test_truncated_refund_scan_is_reported(self):
        with patch('accounts.billing.YooKassa') as provider:
            provider.return_value.refunds.return_value = {'items': [], 'next_cursor': 'page-two'}
            with self.assertRaisesMessage(ValueError, 'refund_scan_incomplete'):
                reconcile_refunds(max_pages=1)

    def test_signed_license_is_device_bound_and_bounded(self):
        self.paid()
        device = Device.objects.create(user=self.user, installation_id=uuid.uuid4(), name='Laptop', token_family=uuid.uuid4())
        key = Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'key.pem'
            path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            with override_settings(SIGNING_KEY_PATH=str(path), SIGNING_KEY_ID='test-key'):
                envelope = license_for(device)
        raw = base64.b64decode(envelope['payload'])
        key.public_key().verify(base64.b64decode(envelope['signature']), b'cloud-hub/license/v1\0' + raw)
        payload = json.loads(raw)
        self.assertEqual(payload['installation_id'], str(device.installation_id))
        self.assertLessEqual(payload['offline_until'] - payload['issued_at'], 7*86400)
        self.assertLessEqual(payload['offline_until'], payload['paid_until'])

    @override_settings(SALES_ENABLED=False)
    def test_unconfigured_service_cannot_take_payment(self):
        with self.assertRaises(ValueError):
            checkout(self.user, self.plan.pk)


@override_settings(ROOT_URLCONF='cloud_accounts.legacy_urls')
class OAuthTests(TestCase):
    def setUp(self):
        call_command('bootstrap_desktop', verbosity=0)
        self.user = identity_user('yandex-user', 'same@example.test')
        self.client.force_login(self.user)

    def authorize(self, method='S256', verifier='v'*64):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        query = {'response_type': 'code', 'client_id': 'cloud-hub-desktop',
            'redirect_uri': 'http://127.0.0.1:57423/callback', 'scope': 'account license',
            'state': 'state-example', 'code_challenge': challenge, 'code_challenge_method': method}
        return self.client.get('/o/authorize/?' + urlencode(query))

    def tokens(self):
        redirect = self.authorize()
        self.assertEqual(redirect.status_code, 302, redirect.content)
        query = parse_qs(urlsplit(redirect['Location']).query)
        self.assertEqual(query['state'], ['state-example'])
        response = self.client.post('/o/token/', {'grant_type': 'authorization_code', 'client_id': 'cloud-hub-desktop',
            'code': query['code'][0], 'redirect_uri': 'http://127.0.0.1:57423/callback', 'code_verifier': 'v'*64})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def refresh(self, token):
        return self.client.post('/o/token/', {'grant_type': 'refresh_token', 'client_id': 'cloud-hub-desktop', 'refresh_token': token})

    def test_real_pkce_exchange_rotation_reuse_protection(self):
        tokens = self.tokens()
        self.assertEqual(AccessToken.objects.get().token, '')
        self.assertEqual(RefreshToken.objects.get().token, '')
        self.assertEqual(self.client.get('/api/v1/account', HTTP_AUTHORIZATION='Bearer '+tokens['access_token']).status_code, 200)
        refreshed = self.refresh(tokens['refresh_token'])
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        self.assertNotEqual(tokens['refresh_token'], refreshed.json()['refresh_token'])
        self.assertEqual(self.refresh(tokens['refresh_token']).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/account', HTTP_AUTHORIZATION='Bearer '+refreshed.json()['access_token']).status_code, 401)

    def test_plain_pkce_is_rejected(self):
        response = self.authorize('plain')
        self.assertNotIn('code=', response.get('Location', ''))

    def test_bad_verifier_cannot_exchange(self):
        response = self.authorize()
        code = parse_qs(urlsplit(response['Location']).query)['code'][0]
        result = self.client.post('/o/token/', {'grant_type': 'authorization_code', 'client_id': 'cloud-hub-desktop',
            'code': code, 'redirect_uri': 'http://127.0.0.1:57423/callback', 'code_verifier': 'wrong'*12})
        self.assertEqual(result.status_code, 400)

    def test_email_does_not_merge_accounts(self):
        other = identity_user('different-yandex-id', 'same@example.test')
        self.assertNotEqual(self.user.id, other.id)
        self.assertEqual(identity_user('yandex-user', 'changed@example.test').id, self.user.id)

    def test_only_bearer_tokens_not_cookies_or_query(self):
        tokens = self.tokens()
        self.assertEqual(self.client.get('/api/v1/account').status_code, 401)
        self.assertEqual(self.client.get('/api/v1/account?access_token='+tokens['access_token']).status_code, 401)

    def test_devices_are_account_scoped_and_revocation_revokes_tokens(self):
        tokens = self.tokens()
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + tokens['access_token']}
        result = self.client.post('/api/v1/devices', {'installation_id': str(uuid.uuid4()), 'name': 'My PC'}, content_type='application/json', **headers)
        self.assertEqual(result.status_code, 200, result.content)
        other = identity_user('other-user')
        alien = Device.objects.create(user=other, installation_id=uuid.uuid4(), name='Other PC', token_family=uuid.uuid4())
        self.assertEqual(self.client.post(f'/api/v1/devices/{alien.id}/revoke', **headers).status_code, 404)
        self.assertEqual(self.client.post(f'/api/v1/devices/{result.json()["id"]}/revoke', **headers).status_code, 200)
        self.assertEqual(self.refresh(tokens['refresh_token']).status_code, 400)

    @override_settings(MAX_DEVICES=1)
    def test_device_limit(self):
        tokens = self.tokens()
        Device.objects.create(user=self.user, installation_id=uuid.uuid4(), name='Existing', token_family=uuid.uuid4())
        result = self.client.post('/api/v1/devices', {'installation_id': str(uuid.uuid4()), 'name': 'New'}, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + tokens['access_token'])
        self.assertEqual(result.status_code, 409)

    def test_redirect_allowlist_and_csrf(self):
        self.assertEqual(safe_next('https://evil.test/o/authorize/'), '/auth/done/')
        self.assertEqual(safe_next('//evil.test/o/authorize/'), '/auth/done/')
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/auth/yandex/start/').status_code, 403)

    def test_no_provider_secrets_no_fake_login(self):
        self.assertEqual(self.client.get('/auth/login/').status_code, 503)
        self.assertEqual(self.client.get('/api/v1/config').json()['login_providers'], [])

    @override_settings(SALES_ENABLED=True, CONSENT_VERSION='fixture', YOOKASSA_SHOP_ID='fixture-shop',
                       YOOKASSA_SECRET_KEY='fixture-secret', YOOKASSA_TEST=True)
    def test_authenticated_checkout_then_device_bound_license_with_desktop_verifier(self):
        tokens = self.tokens()
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + tokens['access_token']}
        installation = str(uuid.uuid4())
        register = self.client.post('/api/v1/devices', {'installation_id': installation, 'name': 'Test Windows'},
                                    content_type='application/json', **headers)
        self.assertEqual(register.status_code, 200)
        Plan.objects.create(code='month', name='Месяц', months=1, amount_kopecks=24900, enabled=True)
        data = {'plan': 'month', 'expected_amount_kopecks': 1, 'expected_months': 1, 'auto_renew': False}
        result = self.client.post('/api/v1/checkout', data, content_type='application/json', **headers)
        self.assertEqual(result.status_code, 409)
        self.assertFalse(Payment.objects.exists())
        data['expected_amount_kopecks'] = 24900
        def provider_response(payment):
            return {'id': 'fixture-paid', 'status': 'succeeded', 'paid': True, 'test': True,
                    'amount': {'value': '249.00', 'currency': 'RUB'},
                    'recipient': {'account_id': 'fixture-shop'},
                    'metadata': {'cloud_payment_id': str(payment.id)}}
        with patch('accounts.billing.YooKassa.create', side_effect=provider_response):
            result = self.client.post('/api/v1/checkout', data, content_type='application/json', **headers)
        self.assertEqual(result.status_code, 200, result.content)
        key = Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'fixture.pem'
            path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            with override_settings(SIGNING_KEY_PATH=str(path), SIGNING_KEY_ID='fixture-key'):
                response = self.client.post('/api/v1/license', {}, content_type='application/json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        # Import the actual desktop signature verifier without adding Qt to the server runtime.
        import importlib.util
        spec = importlib.util.spec_from_file_location('desktop_signed_payload', Path(__file__).resolve().parents[2]/'island'/'signed_payload.py')
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
        payload = verifier.verify_envelope(response.json()['license'], {'fixture-key': public}, 'cloud-hub/license/v1')
        self.assertEqual(payload['installation_id'], installation)
        self.assertEqual(payload['edition'], 'pro')
        account = self.client.get('/api/v1/account', **headers).json()
        self.assertEqual(account['subscription']['edition'], 'pro')
        self.assertEqual(account['payments'][0]['status'], 'succeeded')

    @override_settings(YANDEX_CLIENT_ID='fixture-client', YANDEX_CLIENT_SECRET='fixture-secret')
    def test_yandex_uses_state_and_s256_and_rejects_unsolicited_callback(self):
        response = self.client.post('/auth/yandex/start/')
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response['Location']).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertGreater(len(query['state'][0]), 20)
        self.assertNotIn('fixture-secret', response['Location'])
        with patch('accounts.auth.requests.get') as info:
            rejected = self.client.get('/auth/yandex/callback/?code=untrusted&state=wrong')
            self.assertEqual(rejected.status_code, 400)
            info.assert_not_called()
