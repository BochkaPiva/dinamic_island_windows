# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json
from pathlib import Path
import sys
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import User, Device, Payment
from accounts import tests as account_test_helpers
from .models import Membership, TelegramLink, Pairing
from .provider import member_status, TelegramUnavailable
from .service import start_pairing, offer_pairing, confirm_pairing, reconcile, observe_event, permit_for


@override_settings(COMMUNITY_CHANNEL_ID=-100123456, TELEGRAM_BOT_USERNAME='fixture_bot',
                   COMMUNITY_CHANNEL_URL='https://t.me/fixture_channel')
class MembershipTests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.user = User.objects.create(username='member')
        self.link = TelegramLink.objects.create(user=self.user, telegram_id=123456)
        self.device = Device.objects.create(user=self.user, installation_id=uuid.uuid4(),
            name='Test', token_family=uuid.uuid4())
        self.provider = Mock()
        self.provider.membership.return_value = True
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key = Ed25519PrivateKey.generate()
        path = Path(self.folder.name) / 'test.pem'
        path.write_bytes(self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        self.settings_override = override_settings(COMMUNITY_SIGNING_KEY_PATH=str(path),
                                                   COMMUNITY_SIGNING_KEY_ID='fixture')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def payload(self, now=None):
        envelope = permit_for(self.device, now or self.now, self.provider)
        raw = base64.b64decode(envelope['payload'])
        self.key.public_key().verify(base64.b64decode(envelope['signature']), b'cloud-hub/community/v1\0' + raw)
        return json.loads(raw)

    def event(self, present, when=None, telegram_id=123456, channel=-100123456):
        return {'chat': {'id': channel}, 'date': int((when or self.now).timestamp()),
                'new_chat_member': {'status': 'member' if present else 'left', 'user': {'id': telegram_id}}}

    def test_membership_statuses_are_explicit(self):
        for status in ('creator', 'administrator', 'member'):
            self.assertTrue(member_status({'status': status}))
        self.assertFalse(member_status({'status': 'kicked'}))
        self.assertFalse(member_status({'status': 'left'}))
        self.assertTrue(member_status({'status': 'restricted', 'is_member': True}))
        self.assertFalse(member_status({'status': 'restricted', 'is_member': False}))
        for value in ({'status': 'future'}, {'status': 'restricted'}, None):
            with self.assertRaises(TelegramUnavailable):
                member_status(value)

    def test_bot_failure_does_not_record_a_leave(self):
        reconcile(self.link, self.provider, self.now)
        before = Membership.objects.get().verified_at
        self.provider.membership.side_effect = TelegramUnavailable()
        with self.assertRaises(TelegramUnavailable):
            reconcile(self.link, self.provider, self.now + timedelta(hours=7))
        row = Membership.objects.get()
        self.assertEqual(row.state, 'member')
        self.assertEqual(row.verified_at, before)
        self.assertIsNone(row.missing_since)

    def test_cache_never_slides_offline_deadline(self):
        first = self.payload()
        again = self.payload(self.now + timedelta(hours=1))
        self.assertEqual(first['expires_at'], again['expires_at'])
        self.assertEqual(first['revision'], again['revision'])
        self.assertEqual(first['expires_at'], int((self.now + timedelta(hours=72)).timestamp()))
        self.provider.membership.assert_called_once_with(123456)
        self.assertFalse(Payment.objects.exists())

    def test_periodic_recheck_detects_missed_leave(self):
        self.payload()
        self.provider.membership.return_value = False
        later = self.now + timedelta(hours=6)
        payload = self.payload(later)
        self.assertEqual(payload['state'], 'grace')
        self.assertEqual(payload['access_until'], int((later + timedelta(hours=24)).timestamp()))

    def test_duplicate_leave_does_not_extend_grace_and_then_suspends(self):
        reconcile(self.link, self.provider, self.now - timedelta(hours=1))
        observe_event(self.event(False), 10, self.now)
        self.provider.membership.return_value = False
        first = self.payload()
        self.assertFalse(observe_event(self.event(False), 10, self.now))
        observe_event(self.event(False, self.now + timedelta(hours=1)), 11, self.now + timedelta(hours=1))
        again = self.payload(self.now + timedelta(hours=1))
        self.assertEqual(first['access_until'], again['access_until'])
        self.assertEqual(self.payload(self.now + timedelta(hours=24))['state'], 'suspended')

    def test_join_event_cannot_grant_without_canonical_check(self):
        observe_event(self.event(True), 10, self.now)
        row = Membership.objects.get()
        self.assertEqual(row.state, 'unknown')
        self.assertIsNone(row.verified_at)
        self.provider.membership.return_value = False
        self.assertEqual(self.payload()['state'], 'suspended')

    def test_resubscription_restores_all_features_without_payment(self):
        self.provider.membership.return_value = False
        self.payload()
        later = self.now + timedelta(hours=25)
        observe_event(self.event(True, later), 12, later)
        self.provider.membership.return_value = True
        self.assertEqual(self.payload(later)['state'], 'active')
        self.assertIsNone(Membership.objects.get().missing_since)

    def test_out_of_order_and_foreign_events_cannot_replace_new_observation(self):
        reconcile(self.link, self.provider, self.now)
        observe_event(self.event(False, self.now - timedelta(hours=1)), 9, self.now)
        row = Membership.objects.get()
        self.assertEqual(row.state, 'member')
        self.assertIsNone(row.missing_since)
        self.assertFalse(observe_event(self.event(False, channel=-999), 10, self.now))
        self.assertFalse(observe_event(self.event(False, telegram_id=999), 10, self.now))
        with self.assertRaises(ValueError):
            observe_event(self.event(False, self.now + timedelta(hours=1)), 11, self.now)

    def test_slower_lookup_does_not_overwrite_newer_event(self):
        def delayed(_):
            observe_event(self.event(False, self.now + timedelta(seconds=1)), 20,
                          self.now + timedelta(seconds=1))
            return True
        self.provider.membership.side_effect = delayed
        row = reconcile(self.link, self.provider, self.now)
        self.assertEqual(row.state, 'left')
        self.assertIsNone(row.verified_at)

    def test_inactive_device_never_gets_a_permit(self):
        self.device.active = False
        with self.assertRaises(ValueError):
            self.payload()
        self.provider.membership.assert_not_called()

    def test_pairing_needs_bot_then_desktop_confirmation_and_is_single_use(self):
        other = User.objects.create(username='pairing')
        pairing, token = start_pairing(other, self.now)
        self.assertNotEqual(pairing.token_hash, token)
        with self.assertRaises(ValueError):
            confirm_pairing(other, pairing.pk, 789, self.now)
        offer_pairing(token, 789, self.now)
        self.assertFalse(TelegramLink.objects.filter(user=other).exists())
        with self.assertRaises(ValueError):
            confirm_pairing(other, pairing.pk, 999, self.now)
        self.assertEqual(confirm_pairing(other, pairing.pk, 789, self.now).telegram_id, 789)
        with self.assertRaises(ValueError):
            confirm_pairing(other, pairing.pk, 789, self.now)

    def test_pairing_cannot_be_taken_by_other_account_or_other_telegram_user(self):
        other = User.objects.create(username='pairing')
        pairing, token = start_pairing(other, self.now)
        offer_pairing(token, 789, self.now)
        with self.assertRaises(ValueError):
            offer_pairing(token, 999, self.now)
        with self.assertRaises(ValueError):
            confirm_pairing(self.user, pairing.pk, 789, self.now)
        with self.assertRaises(ValueError):
            offer_pairing(token, 789, self.now + timedelta(minutes=11))

    def test_one_telegram_account_cannot_bind_two_accounts(self):
        other = User.objects.create(username='pairing')
        pairing, token = start_pairing(other, self.now)
        offer_pairing(token, self.link.telegram_id, self.now)
        with self.assertRaisesRegex(ValueError, 'telegram_already_linked'):
            confirm_pairing(other, pairing.pk, self.link.telegram_id, self.now)
        self.assertIsNone(Pairing.objects.get(pk=pairing.pk).consumed_at)

    def test_pairing_limits_and_expiry(self):
        for _ in range(5):
            start_pairing(self.user, self.now)
        with self.assertRaisesRegex(ValueError, 'too_many_pairings'):
            start_pairing(self.user, self.now)
        start_pairing(self.user, self.now + timedelta(minutes=11))

    def test_never_subscribed_account_does_not_get_a_free_grace_day(self):
        self.provider.membership.return_value = False
        self.assertEqual(self.payload()['state'], 'suspended')

    def test_signed_server_contract_is_accepted_by_actual_desktop(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from island.community_access import verify_permit
        envelope = permit_for(self.device, self.now, self.provider)
        keys = {'fixture': base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        permit = verify_permit(envelope, keys, str(self.device.installation_id), -100123456, self.now.timestamp())
        self.assertTrue(permit.allows(self.now.timestamp()))
        self.provider.membership.return_value = False
        later = self.now + timedelta(hours=73)
        envelope = permit_for(self.device, later, self.provider)
        permit = verify_permit(envelope, keys, str(self.device.installation_id), -100123456, later.timestamp())
        self.assertEqual(permit.state, 'grace')


@override_settings(ROOT_URLCONF='cloud_accounts.legacy_urls', COMMUNITY_EXPERIMENT_ENABLED=True, TELEGRAM_WEBHOOK_SECRET='fixture-webhook',
                   COMMUNITY_CHANNEL_ID=-100123456, TELEGRAM_BOT_USERNAME='fixture_bot',
                   COMMUNITY_CHANNEL_URL='https://t.me/fixture_channel')
class CommunityApiTests(TestCase):
    # Reuse the real public-client PKCE exchange helpers without inheriting its tests.
    authorize = account_test_helpers.OAuthTests.authorize
    tokens = account_test_helpers.OAuthTests.tokens

    def setUp(self):
        account_test_helpers.OAuthTests.setUp(self)

    def post(self, path, data, **headers):
        return self.client.post(path, data, content_type='application/json', **headers)

    @override_settings(COMMUNITY_EXPERIMENT_ENABLED=False)
    def test_default_disabled_never_calls_telegram_or_creates_pairings(self):
        with patch('community.api.Telegram') as bot:
            self.assertFalse(self.client.get('/api/v1/community/config').json()['enabled'])
            self.assertEqual(self.post('/api/v1/community/pairings', {}).status_code, 503)
            self.assertEqual(self.post('/hooks/telegram', {}).status_code, 503)
            bot.assert_not_called()
        self.assertFalse(Pairing.objects.exists())

    def test_cookies_or_telegram_id_cannot_replace_first_party_auth(self):
        self.assertEqual(self.post('/api/v1/community/pairings', {'telegram_id': 123}).status_code, 401)

    def test_authenticated_pairing_from_api_through_bot_to_explicit_confirmation(self):
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + self.tokens()['access_token']}
        response = self.post('/api/v1/community/pairings', {}, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        pairing_id = response.json()['id']
        token = response.json()['bot_url'].split('start=')[1]
        event = {'update_id': 1, 'callback_query': {'id': 'fixture-callback', 'data': 'pair:' + token,
            'from': {'id': 123456, 'is_bot': False}, 'message': {'chat': {'type': 'private', 'id': 123456}}}}
        with patch('community.api.Telegram') as provider:
            provider.return_value.membership.return_value = True
            response = self.post('/hooks/telegram', event,
                                 HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='fixture-webhook')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(TelegramLink.objects.exists())
        response = self.client.get('/api/v1/community/pairings/' + pairing_id, **headers)
        self.assertEqual(response.json(), {'state': 'confirm', 'telegram_id': 123456})
        response = self.post('/api/v1/community/pairings/' + pairing_id + '/confirm', {'telegram_id': 123456}, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(TelegramLink.objects.get().user_id, self.user.pk)

    def test_forged_webhook_and_malformed_body_never_reach_provider(self):
        with patch('community.api.Telegram') as bot:
            self.assertEqual(self.post('/hooks/telegram', {'update_id': 1}).status_code, 403)
            self.assertEqual(self.post('/hooks/telegram', {'update_id': True},
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='fixture-webhook').status_code, 400)
            bot.assert_not_called()

    def test_provider_outage_is_503_and_does_not_link(self):
        token = start_pairing(self.user)[1]
        event = {'update_id': 1, 'callback_query': {'id': 'cb', 'data': 'pair:' + token,
            'from': {'id': 123456, 'is_bot': False}, 'message': {'chat': {'type': 'private', 'id': 123456}}}}
        with patch('community.api.Telegram') as bot:
            bot.return_value.membership.side_effect = TelegramUnavailable()
            response = self.post('/hooks/telegram', event, HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='fixture-webhook')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(TelegramLink.objects.exists())

    def test_explicit_disconnect_deletes_only_community_identity(self):
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + self.tokens()['access_token']}
        link = TelegramLink.objects.create(user=self.user, telegram_id=123456)
        Membership.objects.create(link=link, channel_id=-100123456)
        start_pairing(self.user)
        response = self.post('/api/v1/community/disconnect', {}, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TelegramLink.objects.exists())
        self.assertFalse(Membership.objects.exists())
        self.assertFalse(Pairing.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_authenticated_api_to_desktop_leave_expiry_and_rejoin(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from island.community_access import PermitStore, CommunitySession
        from island.account_client import AccountError
        headers = {'HTTP_AUTHORIZATION': 'Bearer ' + self.tokens()['access_token']}
        installation = str(uuid.uuid4())
        registered = self.post('/api/v1/devices', {'installation_id': installation, 'name': 'Fixture PC'}, **headers)
        self.assertEqual(registered.status_code, 200)
        TelegramLink.objects.create(user=self.user, telegram_id=123456)
        now = timezone.now().replace(microsecond=0)
        clock = [now]
        key = Ed25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.pem'
            path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            keys = {'fixture': base64.b64encode(key.public_key().public_bytes_raw()).decode()}
            store = PermitStore(folder, keys, installation, -100123456, clock=lambda: clock[0].timestamp())
            client = self

            class FirstPartyApi:
                installation_id = installation

                def api(self, route, data=None):
                    response = client.post('/api/v1/' + route, data or {}, **headers)
                    if response.status_code != 200:
                        raise AccountError(response.json()['error'], response.status_code)
                    return response.json()

            community = CommunitySession(FirstPartyApi(), store)
            with override_settings(COMMUNITY_SIGNING_KEY_PATH=str(path), COMMUNITY_SIGNING_KEY_ID='fixture'), \
                    patch('community.api.permit_for', side_effect=lambda device: permit_for(device, clock[0])), \
                    patch('community.api.observe_event', side_effect=lambda event, identifier: observe_event(event, identifier, clock[0])), \
                    patch('community.service.Telegram') as bot:
                bot.return_value.membership.return_value = True
                self.assertTrue(community.refresh().allows(clock[0].timestamp()))
                bot.return_value.membership.side_effect = TelegramUnavailable()
                clock[0] = now + timedelta(hours=7)
                with self.assertRaises(AccountError):
                    community.refresh()
                self.assertTrue(store.load().allows(clock[0].timestamp()))
                bot.return_value.membership.side_effect = None
                bot.return_value.membership.return_value = False
                event = {'update_id': 77, 'chat_member': {'chat': {'id': -100123456},
                    'date': int(clock[0].timestamp()),
                    'new_chat_member': {'status': 'left', 'user': {'id': 123456}}}}
                with patch('community.api.Telegram'):
                    response = self.post('/hooks/telegram', event,
                        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='fixture-webhook')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(community.refresh().state, 'grace')
                clock[0] += timedelta(hours=24)
                self.assertEqual(community.refresh().state, 'suspended')
                self.assertFalse(store.load().allows(clock[0].timestamp()))
                clock[0] += timedelta(seconds=1)
                event['update_id'] = 78
                event['chat_member']['date'] = int(clock[0].timestamp())
                event['chat_member']['new_chat_member']['status'] = 'member'
                with patch('community.api.Telegram'):
                    self.assertEqual(self.post('/hooks/telegram', event,
                        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='fixture-webhook').status_code, 200)
                bot.return_value.membership.return_value = True
                self.assertTrue(community.refresh().allows(clock[0].timestamp()))
                self.assertFalse(Payment.objects.exists())
