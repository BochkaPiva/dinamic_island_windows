# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from island.community_access import verify_permit, PermitStore, CommunitySession
from island.account_client import AccountError


class CommunityAccessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.keys = {'fixture': base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.store = PermitStore(self.folder.name, self.keys, 'installation', -100123456, clock=lambda: 1000)

    def envelope(self, changes=None, purpose='cloud-hub/community/v1'):
        payload = {'schema': 1, 'product': 'cloud-hub', 'policy': 'telegram-membership-v1',
            'revision': 1, 'installation_id': 'installation', 'channel_id': -100123456,
            'state': 'active', 'issued_at': 900, 'refresh_after': 2000, 'expires_at': 10000, 'access_until': 10000}
        payload.update(changes or {})
        raw = json.dumps(payload).encode()
        return {'key_id': 'fixture', 'payload': base64.b64encode(raw).decode(),
                'signature': base64.b64encode(self.key.sign(purpose.encode() + b'\0' + raw)).decode()}

    def test_valid_offline_permit_and_refresh_deadline(self):
        permit = self.store.install(self.envelope())
        self.assertTrue(permit.allows(1000))
        self.assertFalse(permit.needs_refresh(1000))
        self.assertTrue(permit.needs_refresh(2000))
        self.assertFalse(permit.allows(10000))
        self.assertEqual(permit.reason(10000), 'verification_expired')

    def test_reject_wrong_product_channel_device_key_purpose_or_bounds(self):
        cases = [{'schema': True}, {'product': 'other'}, {'channel_id': -999},
            {'installation_id': 'other'}, {'state': 'pro'}, {'issued_at': True},
            {'revision': 0}, {'revision': True}, {'refresh_after': 20000},
            {'expires_at': 9999999, 'access_until': 9999999}, {'access_until': 11000},
            {'state': 'suspended'}, {'state': 'grace', 'access_until': 900},
            {'issued_at': 1400}, {'expires_at': 999, 'access_until': 999, 'refresh_after': 950}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.install(self.envelope(changes))
        with self.assertRaises(ValueError):
            self.store.install(self.envelope(purpose='cloud-hub/license/v1'))
        with self.assertRaises(ValueError):
            verify_permit(self.envelope(), {}, 'installation', -100123456, 1000)

    def test_signed_denial_replaces_positive_and_old_allow_cannot_restore_it(self):
        self.store.install(self.envelope())
        denied = self.envelope({'state': 'suspended', 'revision': 2, 'issued_at': 1000,
                                'access_until': 950})
        permit = self.store.install(denied)
        self.assertFalse(permit.allows(1000))
        self.assertEqual(permit.reason(1000), 'membership_required')
        with self.assertRaises(ValueError):
            self.store.install(self.envelope())
        self.assertEqual(self.store.load().state, 'suspended')

    def test_grace_expires_at_fixed_deadline(self):
        permit = self.store.install(self.envelope({'state': 'grace', 'access_until': 2000}))
        self.assertTrue(permit.allows(1999))
        self.assertFalse(permit.allows(2000))
        self.assertEqual(permit.reason(1999), 'membership_grace')
        self.assertEqual(permit.reason(2000), 'membership_required')

    def test_network_failure_does_not_erase_last_signed_grant_or_user_files(self):
        before = self.envelope()
        self.store.install(before)
        notes = Path(self.folder.name) / 'notes.txt'
        notes.write_text('keep me')
        session = Mock(installation_id='installation')
        session.api.side_effect = AccountError('connection_failed')
        with self.assertRaises(AccountError):
            CommunitySession(session, self.store).refresh()
        self.assertTrue(self.store.load().allows(1000))
        self.assertEqual(notes.read_text(), 'keep me')

    def test_forgery_does_not_replace_cache(self):
        self.store.install(self.envelope())
        forged = self.envelope()
        forged['payload'] = base64.b64encode(b'{}').decode()
        with self.assertRaises(ValueError):
            self.store.install(forged)
        self.assertTrue(self.store.load().allows(1000))

    def test_expired_or_corrupt_cache_is_unverified(self):
        self.store.install(self.envelope())
        self.store.clock = lambda: 10000
        self.assertIsNone(self.store.load())
        self.store.path.write_text('{}')
        self.assertIsNone(self.store.load())

    def test_session_uses_existing_serialized_account_client(self):
        session = Mock(installation_id='installation')
        session.api.return_value = {'permit': self.envelope()}
        permit = CommunitySession(session, self.store).refresh()
        self.assertTrue(permit.allows(1000))
        session.api.assert_called_once_with('community/permit', {})

    def test_pairing_url_is_telegram_only(self):
        session = Mock(installation_id='installation')
        community = CommunitySession(session, self.store)
        for url in ('https://evil.test/bot?start=' + 'x'*32, 'https://t.me@evil.test/bot?start=' + 'x'*32):
            session.api.return_value = {'bot_url': url}
            with self.assertRaises(ValueError):
                community.start_pairing()
        session.api.return_value = {'bot_url': 'https://t.me/fixture_bot?start=' + 'x'*32}
        self.assertIn('bot_url', community.start_pairing())

    def test_disconnect_removes_only_permit_after_server_acknowledgement(self):
        self.store.install(self.envelope())
        notes = Path(self.folder.name) / 'notes.txt'
        notes.write_text('preserve')
        session = Mock(installation_id='installation')
        community = CommunitySession(session, self.store)
        session.api.side_effect = AccountError('connection_failed')
        with self.assertRaises(AccountError):
            community.disconnect()
        self.assertIsNotNone(self.store.load())
        session.api.side_effect = None
        session.api.return_value = {'disconnected': True}
        community.disconnect()
        self.assertIsNone(self.store.load())
        self.assertEqual(notes.read_text(), 'preserve')

    def test_community_distribution_has_no_paid_function_or_group_limits(self):
        from island.entitlements import FeatureAccess, PRO_FEATURES
        access = FeatureAccess(self.folder.name, distribution='community')
        for feature in PRO_FEATURES:
            self.assertTrue(access.feature(feature).allowed)
        self.assertTrue(access.capacity('desktop.groups.active', 100).allowed)
        self.assertEqual(access.grant.edition, 'community')
