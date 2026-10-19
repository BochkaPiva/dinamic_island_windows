# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import Mock,patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtTest import QTest
from PySide6.QtCore import QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication,QPushButton,QLabel
from island.community_client import CommunityClient,CommunityError,proof,validate_origin
from island.community_ui import CommunityController,CommunityPanel
from island.entitlements import FeatureAccess
from island.desktop_groups import GroupStore


class DirectCommunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.key=Ed25519PrivateKey.generate()
        self.keys={'fixture':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.clock=[1000]
        self.access=FeatureAccess(self.temp.name,distribution='community',clock=lambda:self.clock[0])
        self.client=CommunityClient('https://community.example.test',self.temp.name,
            self.access.installation_id,self.keys,-1004359060579,clock=lambda:self.clock[0])

    def permit(self,state='active',revision=1):
        payload={'schema':1,'product':'cloud-hub','policy':'telegram-membership-v1',
            'installation_id':self.access.installation_id,'channel_id':-1004359060579,'state':state,
            'revision':revision,'issued_at':1000,'refresh_after':2000,'expires_at':10000,
            'access_until':10000 if state=='active' else 1000}
        raw=json.dumps(payload).encode()
        return {'key_id':'fixture','payload':base64.b64encode(raw).decode(),
            'signature':base64.b64encode(self.key.sign(b'cloud-hub/community/v1\0'+raw)).decode()}

    def start(self):
        response={'id':str(uuid.uuid4()),'bot_url':'https://t.me/nelviro_bot?start='+'a'*32,'expires_at':1600}
        with patch.object(self.client,'request',return_value=response) as request:
            self.client.start_pairing()
        sent=request.call_args.args[1]
        self.assertEqual(sent['code_challenge'],proof(self.client.pairing['verifier']))
        self.assertNotIn(self.client.pairing['verifier'],response['bot_url'])

    def test_pairing_proof_stays_on_device_and_credentials_are_dpapi_protected(self):
        self.start()
        credential='a'*64
        def response(route,data=None,**kwargs):
            if route.endswith('/confirm'):
                self.assertEqual(data['verifier'],self.client.pairing['verifier'])
                return {'installation_id':self.access.installation_id,'device_id':str(uuid.uuid4()),
                    'credential':credential,'credential_expires_at':100000}
            return {'permit':self.permit()}
        with patch.object(self.client,'request',side_effect=response):
            self.assertTrue(self.client.confirm_pairing(123).allows(1000))
        content=(Path(self.temp.name)/'community-device.bin').read_bytes()
        self.assertNotIn(credential.encode(),content)
        restored=CommunityClient(self.client.origin,self.temp.name,self.access.installation_id,self.keys,
                                 -1004359060579,clock=lambda:1000)
        self.assertEqual(restored.session['credential'],credential)
        alien=CommunityClient('https://alien.example.test',self.temp.name,self.access.installation_id,self.keys,
                              -1004359060579,clock=lambda:1000)
        self.assertIsNone(alien.session)

    def test_expired_pairing_and_wrong_origins_are_rejected(self):
        self.start();self.clock[0]=1600
        with self.assertRaises(CommunityError):self.client.pairing_status()
        for origin in ('http://evil.test','https://user@host.test','https://host.test/path'):
            with self.assertRaises(ValueError):validate_origin(origin)
        self.assertEqual(validate_origin('http://127.0.0.1:8768',True),'http://127.0.0.1:8768')

    def test_pending_pairing_survives_a_short_restart_but_not_expiry(self):
        self.start()
        original=self.client.pairing['verifier']
        raw=(Path(self.temp.name)/'community-pairing.bin').read_bytes()
        self.assertNotIn(original.encode(),raw)
        restored=CommunityClient(self.client.origin,self.temp.name,self.access.installation_id,
            self.keys,-1004359060579,clock=lambda:1100)
        self.assertEqual(restored.pairing['verifier'],original)
        expired=CommunityClient(self.client.origin,self.temp.name,self.access.installation_id,
            self.keys,-1004359060579,clock=lambda:1700)
        self.assertIsNone(expired.pairing)

    def test_bot_approval_completes_without_a_second_desktop_button(self):
        controller=CommunityController(self.temp.name,self.access,origin=self.client.origin,keys=self.keys,
            channel_id=-1004359060579,auto_start=False,clock=lambda:1000)
        controller.client=Mock(session=None,pairing={'id':'fixture'})
        controller.client.store.load.return_value=None
        controller._complete({'candidate':{'state':'confirm','telegram_id':123}})
        QTest.qWait(70)
        controller.client.confirm_pairing.assert_called_once_with(123)
        controller.stop();controller.deleteLater()

    def test_failed_refresh_keeps_signed_access_and_explicit_local_disconnect_clears_it(self):
        self.client.store.install(self.permit())
        with patch.object(self.client,'request',side_effect=CommunityError('connection_failed')):
            with self.assertRaises(CommunityError):self.client.refresh()
        self.assertTrue(self.client.store.load().allows(1000))
        self.client.forget_local()
        self.assertIsNone(self.client.store.load())

    def test_access_changes_limit_without_deleting_groups_or_old_island_tools(self):
        with patch('island.build_config.COMMUNITY_PUBLIC_KEYS',self.keys):
            store=GroupStore(self.temp.name,collect_desktop=False,access=self.access)
            self.assertEqual(len(store.groups),2)
            self.assertIsNone(store.add('Third'))
            self.client.store.install(self.permit());self.access.reload()
            self.assertIsNotNone(store.add('Third'))
            self.assertEqual(len(self.access.active_ids(store.groups)),3)
            original=store.path.read_bytes()
            self.client.store.install(self.permit('suspended',2));self.access.reload()
            self.assertEqual(len(self.access.active_ids(store.groups)),2)
            self.assertEqual(store.path.read_bytes(),original)
            self.assertTrue(self.access.feature('island.focus').allowed)
            self.assertTrue(self.access.feature('island.notes').allowed)
            self.assertTrue(self.access.feature('search.basic').allowed)
            third=store.groups[-1]['id']
            self.assertTrue(store.make_active(third))
            self.assertIn(third,self.access.active_ids(store.groups))
            self.assertEqual(len(store.groups),3)

    def test_optional_panel_has_no_yandex_password_or_payment_controls(self):
        panel=CommunityPanel()
        titles=[w.text() for w in panel.findChildren(QLabel)]+[b.text() for b in panel.findChildren(QPushButton)]
        self.assertFalse(any('Яндекс' in title or 'оплатить' in title.lower() for title in titles))
        self.assertTrue(any('без входа' in title for title in titles))
        self.assertTrue(any(b.text()=='Открыть канал' for b in panel.findChildren(QPushButton)))
        panel.close();panel.deleteLater()

    def test_worker_keeps_gui_responsive_and_offline_does_not_remove_access(self):
        controller=CommunityController(self.temp.name,self.access,origin=self.client.origin,keys=self.keys,
            channel_id=-1004359060579,auto_start=False,clock=lambda:1000)
        ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
        def slow():time.sleep(.07);raise CommunityError('connection_failed')
        controller._run(slow)
        QTest.qWait(140)
        self.assertFalse(controller.busy);self.assertGreater(len(ticks),2)
        self.assertEqual(self.access.grant.edition,'free')
        controller.stop();timer.stop();controller.deleteLater()

    def test_panel_survives_repeated_refresh_and_access_notifications(self):
        controller=CommunityController(self.temp.name,self.access,origin=self.client.origin,keys=self.keys,
            channel_id=-1004359060579,auto_start=False,clock=lambda:self.clock[0])
        panel=CommunityPanel(controller);panel.resize(680,850);panel.show()
        self.addCleanup(controller.stop)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(controller.deleteLater)
        QTest.qWait(20)
        original=tuple(panel.findChildren(QLabel)+panel.findChildren(QPushButton))
        for _ in range(12):
            controller.busy=True;controller.changed.emit()
            self.assertFalse(panel.primary.isEnabled())
            controller._complete({'refresh':True})  # access.changed then changed, synchronously
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            QTest.qWait(1)
            self.assertEqual(tuple(panel.findChildren(QLabel)+panel.findChildren(QPushButton)),original)
            self.assertTrue(panel.primary.isVisible())
            self.assertTrue(panel.benefits.isVisible())
            self.assertGreater(panel.benefits.height(),100)
        self.assertEqual(panel.primary.text(),'Подключить Telegram')
        panel.close()

    def test_visible_membership_cycle_preserves_groups_and_recovers_after_rejoin(self):
        controller=CommunityController(self.temp.name,self.access,origin=self.client.origin,keys=self.keys,
            channel_id=-1004359060579,auto_start=False,clock=lambda:self.clock[0])
        controller.client.session={'credential':'fixture'}
        panel=CommunityPanel(controller);panel.show()
        self.addCleanup(controller.stop);self.addCleanup(controller.deleteLater);self.addCleanup(panel.deleteLater)
        with patch('island.build_config.COMMUNITY_PUBLIC_KEYS',self.keys):
            groups=GroupStore(self.temp.name,collect_desktop=False,access=self.access)
            for state,revision in [('active',1),('grace',2),('suspended',3),('active',4)]:
                signed=self.permit(state,revision)
                if state=='grace':
                    payload=json.loads(base64.b64decode(signed['payload']))
                    payload['access_until']=3000
                    raw=json.dumps(payload).encode()
                    signed={'key_id':'fixture','payload':base64.b64encode(raw).decode(),
                        'signature':base64.b64encode(self.key.sign(b'cloud-hub/community/v1\0'+raw)).decode()}
                controller.client.store.install(signed)
                controller._complete({'refresh':True});QTest.qWait(1)
                self.assertEqual(self.access.feature('island.floating').allowed,state!='suspended')
                if state=='active' and revision==1:
                    self.assertIsNotNone(groups.add('Third'))
                    original=groups.path.read_bytes()
                self.assertEqual(groups.path.read_bytes(),original)
                self.assertEqual(len(self.access.active_ids(groups.groups)),2 if state=='suspended' else 3)
                self.assertTrue(panel.primary.isVisible())
                self.assertEqual(panel.status.text(),{'active':'Подписка подтверждена',
                    'grace':'Нужно подтвердить подписку','suspended':'Telegram подключён'}[state])
            controller._complete({'error':'Нет связи с сервисом'})
            self.assertTrue(panel.message.isVisible())
            self.assertTrue(self.access.feature('island.floating').allowed)
            self.clock[0]=10000;self.access._expire();QTest.qWait(1)
            self.assertFalse(self.access.feature('island.floating').allowed)
            self.assertEqual(panel.title.text(),'Подтверди подписку на канал')
            controller.client.forget_local();controller._complete({'disconnected':True})
            self.assertEqual(panel.primary.text(),'Подключить Telegram')
            self.assertFalse(panel.disconnect_button.isVisible())
            self.assertEqual(groups.path.read_bytes(),original)
        panel.close()
