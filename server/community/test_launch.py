# SPDX-License-Identifier: GPL-3.0-or-later
"""Import actual production settings in a fresh process, without connecting to a DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption


class LaunchTests(TestCase):
    def check_settings(self, directory, approvals):
        path = Path(directory) / 'approvals.json'
        path.write_text(json.dumps(approvals))
        key_path = Path(directory) / 'fixture.pem'
        key = Ed25519PrivateKey.generate()
        key_path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        env = {k: v for k, v in os.environ.items() if k not in ('SALES_ENABLED', 'RENEWALS_ENABLED')}
        env.update({'CLOUD_ENV': 'production', 'DJANGO_SECRET_KEY': 'fixture-production-secret-' * 3,
            'PGHOST': '127.0.0.1', 'PUBLIC_ORIGIN': 'https://fixture.example',
            'ALLOWED_HOSTS': 'fixture.example', 'COMMUNITY_EXPERIMENT_ENABLED': '1',
            'COMMUNITY_APPROVALS_PATH': str(path), 'YANDEX_CLIENT_ID': 'fixture-client',
            'YANDEX_CLIENT_SECRET': 'fixture-secret', 'COMMUNITY_CHANNEL_ID': '-100123456',
            'COMMUNITY_CHANNEL_URL': 'https://t.me/fixture_channel',
            'TELEGRAM_BOT_USERNAME': 'fixture_bot', 'TELEGRAM_BOT_TOKEN': '12345:fixture_token',
            'TELEGRAM_WEBHOOK_SECRET': 'fixture-webhook-secret-' * 3,
            'COMMUNITY_SIGNING_KEY_PATH': str(key_path), 'COMMUNITY_SIGNING_KEY_ID': 'fixture'})
        return subprocess.run([sys.executable, '-c', 'import cloud_accounts.settings'],
            cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, timeout=15).returncode

    def test_production_rejects_unreviewed_membership_experiment(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertNotEqual(self.check_settings(folder, {}), 0)

    def test_production_requires_each_review_and_a_complete_config(self):
        fields = ('authentication_review', 'personal_data_review', 'code_rights', 'operational_checks')
        with tempfile.TemporaryDirectory() as folder:
            for missing in fields:
                with self.subTest(missing=missing):
                    self.assertNotEqual(self.check_settings(folder, {k: k != missing for k in fields}), 0)
            # Fixture acknowledgements verify the import guard; they are NOT legal approvals.
            self.assertEqual(self.check_settings(folder, {k: True for k in fields}), 0)
