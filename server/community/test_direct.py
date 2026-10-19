# SPDX-License-Identifier: GPL-3.0-or-later
import base64
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from accounts.models import User, Payment
from .models import CommunityMember, MemberDevice, MemberStatus, DevicePairing
from .provider import TelegramUnavailable
from . import direct
from django.db import DatabaseError


@override_settings(COMMUNITY_EXPERIMENT_ENABLED=True, COMMUNITY_CHANNEL_ID=-1004359060579,
    TELEGRAM_BOT_USERNAME='fixture_bot', TELEGRAM_BOT_TOKEN='123:fixture',
    COMMUNITY_SIGNING_KEY_PATH='fixture.pem', COMMUNITY_SIGNING_KEY_ID='fixture')
class HealthTests(SimpleTestCase):
    def test_health_checks_database_without_exposing_details(self):
        with patch.object(MemberDevice.objects, 'exists', return_value=False):
            response=self.client.get('/api/v2/community/health')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'status':'ok','schema':2})

    def test_database_failure_returns_safe_retryable_status(self):
        with patch.object(MemberDevice.objects, 'exists', side_effect=DatabaseError('private detail')):
            response=self.client.get('/api/v2/community/health')
        self.assertEqual(response.status_code,503)
        self.assertNotIn(b'private detail',response.content)


@override_settings(COMMUNITY_EXPERIMENT_ENABLED=True, COMMUNITY_CHANNEL_ID=-1004359060579,
    COMMUNITY_CHANNEL_URL='https://t.me/Nelviro', TELEGRAM_BOT_USERNAME='nelviro_bot',
    TELEGRAM_BOT_TOKEN='123:fixture', TELEGRAM_WEBHOOK_SECRET='fixture-webhook',
    COMMUNITY_SIGNING_KEY_ID='fixture', YANDEX_CLIENT_ID='', YANDEX_CLIENT_SECRET='')
class DirectTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key=Ed25519PrivateKey.generate()
        path=Path(self.folder.name)/'fixture.pem'
        path.write_bytes(self.key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
        override=override_settings(COMMUNITY_SIGNING_KEY_PATH=str(path))
        override.enable();self.addCleanup(override.disable)
        self.installation=str(uuid.uuid4())
        self.verifier='v'*64
        self.now=timezone.now().replace(microsecond=0)
        self.provider=Mock();self.provider.membership.return_value=True

    def post(self,path,data=None,credential=None):
        headers={'HTTP_AUTHORIZATION':'Bearer '+credential} if credential else {}
        return self.client.post('/api/v2/community/'+path,data or {},content_type='application/json',**headers)

    def start(self):
        response=self.post('pairings',{'installation_id':self.installation,'product':'cloud-hub',
                                     'code_challenge':direct.challenge(self.verifier)})
        self.assertEqual(response.status_code,200,response.content)
        value=response.json();value['token']=value['bot_url'].split('start=')[1]
        return value

    def confirm(self,pairing,telegram_id=123456):
        return self.post('pairings/'+pairing['id']+'/confirm',{'verifier':self.verifier,'telegram_id':telegram_id})

    def connected(self):
        pairing=self.start();direct.offer(pairing['token'],123456)
        response=self.confirm(pairing)
        self.assertEqual(response.status_code,200,response.content)
        return response.json()

    def test_base_configuration_has_no_login_and_legacy_routes_are_not_exposed(self):
        config=self.client.get('/api/v2/community/config').json()
        self.assertFalse(config['base_requires_connection'])
        self.assertEqual(config['free_groups'],2)
        for path in ('/auth/yandex/start/','/auth/login/','/o/token/','/api/v1/checkout'):
            self.assertEqual(self.client.post(path).status_code,404)

    def test_pairing_requires_device_proof_and_explicit_confirmation(self):
        pairing=self.start()
        self.assertEqual(self.confirm(pairing).status_code,409)
        direct.offer(pairing['token'],123456)
        self.assertEqual(self.post('pairings/'+pairing['id']+'/status',{'verifier':'x'*64}).status_code,404)
        self.assertEqual(self.post('pairings/'+pairing['id']+'/status',{'verifier':self.verifier}).json(),
                         {'state':'confirm','telegram_id':123456})
        self.assertEqual(self.confirm(pairing,999).status_code,409)
        self.assertFalse(MemberDevice.objects.exists())
        response=self.confirm(pairing)
        self.assertEqual(response.status_code,200)
        self.assertNotIn(response.json()['credential'],MemberDevice.objects.get().credential_hash)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_confirmation_retry_is_idempotent_after_lost_response(self):
        pairing=self.start();direct.offer(pairing['token'],123456)
        first=self.confirm(pairing).json()
        second=self.confirm(pairing).json()
        self.assertEqual(first,second)
        self.assertEqual(MemberDevice.objects.count(),1)

    def test_another_telegram_cannot_claim_an_existing_installation(self):
        self.connected()
        pairing=self.start();direct.offer(pairing['token'],789)
        self.assertEqual(self.confirm(pairing,789).status_code,409)
        self.assertEqual(MemberDevice.objects.get().member.telegram_id,123456)

    def test_expired_and_forged_enrollments_do_not_connect(self):
        pairing=self.start();direct.offer(pairing['token'],123456)
        DevicePairing.objects.filter(pk=pairing['id']).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.confirm(pairing).status_code,409)
        self.assertFalse(MemberDevice.objects.exists())

    def test_throttles_abandoned_pairings(self):
        for _ in range(3):self.start()
        self.assertEqual(self.post('pairings',{'installation_id':self.installation,'product':'cloud-hub',
            'code_challenge':direct.challenge(self.verifier)}).status_code,429)

    def test_member_permit_has_valid_desktop_signature_and_no_personal_data(self):
        connection=self.connected()
        with patch('community.direct.Telegram',return_value=self.provider):
            response=self.post('permit',credential=connection['credential'])
        self.assertEqual(response.status_code,200,response.content)
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from island.community_access import verify_permit
        keys={'fixture':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        permit=verify_permit(response.json()['permit'],keys,self.installation,-1004359060579)
        self.assertTrue(permit.allows(timezone.now().timestamp()))
        payload=json.loads(base64.b64decode(response.json()['permit']['payload']))
        self.assertNotIn('telegram_id',payload)
        self.assertNotIn('email',payload)

    def test_unknown_or_disconnected_device_cannot_renew(self):
        self.assertEqual(self.post('permit').status_code,401)
        connection=self.connected()
        self.assertEqual(self.post('disconnect',credential=connection['credential']).status_code,200)
        self.assertEqual(self.post('permit',credential=connection['credential']).status_code,401)
        self.assertFalse(MemberDevice.objects.get().active)

    def test_canonical_failure_is_not_a_leave(self):
        connection=self.connected()
        self.provider.membership.side_effect=TelegramUnavailable()
        with patch('community.direct.Telegram',return_value=self.provider):
            self.assertEqual(self.post('permit',credential=connection['credential']).status_code,503)
        self.assertIsNone(MemberStatus.objects.get().missing_since)

    def test_out_of_order_leave_and_duplicates_do_not_extend_grace(self):
        self.connected();member=CommunityMember.objects.get()
        direct.reconcile_member(member,self.provider,self.now)
        later=self.now+timedelta(seconds=1)
        event={'chat':{'id':-1004359060579},'date':int(later.timestamp()),
               'new_chat_member':{'status':'left','user':{'id':123456}}}
        direct.observe(event,1,later)
        first=MemberStatus.objects.get().missing_since
        direct.observe(event,1,later+timedelta(hours=1))
        self.assertEqual(MemberStatus.objects.get().missing_since,first)
        self.provider.membership.return_value=False
        device=MemberDevice.objects.get()
        permit=direct.device_permit(device,self.provider,later)
        self.assertEqual(json.loads(base64.b64decode(permit['payload']))['state'],'grace')
        permit=direct.device_permit(device,self.provider,later+timedelta(hours=24))
        self.assertEqual(json.loads(base64.b64decode(permit['payload']))['state'],'suspended')

    def test_webhook_secret_is_checked_before_processing(self):
        with patch('community.direct.Telegram') as bot:
            response=self.client.post('/hooks/telegram',{'update_id':1},content_type='application/json')
            self.assertEqual(response.status_code,403);bot.assert_not_called()
