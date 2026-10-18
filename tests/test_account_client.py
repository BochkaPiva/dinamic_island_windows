# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
from island.account_client import AccountSession, AccountError, authorization_code, challenge, validate_origin


class AccountClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.session = AccountSession('https://accounts.example.test', self.temp.name, 'test-installation')

    def tearDown(self):
        self.temp.cleanup()

    def test_only_trusted_https_origins(self):
        for value in ['http://evil.test', 'https://user:secret@site.test', 'https://site.test/path', 'https://site.test?foo=1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_origin(value)
        self.assertEqual(validate_origin('http://127.0.0.1:8000', True), 'http://127.0.0.1:8000')

    def test_dpapi_credentials_are_not_plaintext_and_are_origin_bound(self):
        self.session._save_tokens({'access_token': 'access-secret-test', 'refresh_token': 'refresh-secret-test', 'token_type': 'Bearer', 'expires_in': 600})
        content = (Path(self.temp.name)/'account-session.bin').read_bytes()
        self.assertNotIn(b'access-secret-test', content)
        self.assertNotIn(b'refresh-secret-test', content)
        restored = AccountSession(self.session.origin, self.temp.name, 'test-installation')
        self.assertEqual(restored.tokens['refresh_token'], 'refresh-secret-test')
        alien = AccountSession('https://other.example.test', self.temp.name, 'test-installation')
        self.assertIsNone(alien.tokens)

    def test_single_refresh_for_parallel_calls(self):
        self.session._save_tokens({'access_token': 'old', 'refresh_token': 'refresh', 'token_type': 'Bearer', 'expires_in': 600})
        self.session.tokens['expires_at'] = 0
        requests = []
        def request(path, data=None, token=None, form=False):
            requests.append(path)
            if path == '/o/token/':
                time.sleep(.02)
                return {'access_token': 'new', 'refresh_token': 'rotated', 'token_type': 'Bearer', 'expires_in': 600}
            self.assertEqual(token, 'new')
            return {'ok': True}
        with patch.object(self.session, '_request', side_effect=request):
            threads = [threading.Thread(target=lambda: self.session.api('account')) for _ in range(3)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
        self.assertEqual(requests.count('/o/token/'), 1)

    def test_401_retries_once_with_fresh_server_token(self):
        self.session._save_tokens({'access_token': 'old', 'refresh_token': 'refresh', 'token_type': 'Bearer', 'expires_in': 600})
        with patch.object(self.session, '_request', side_effect=[AccountError('invalid_token', 401),
                {'access_token': 'new', 'refresh_token': 'rotated', 'token_type': 'Bearer', 'expires_in': 600}, {'id': 'account'}]) as request:
            self.assertEqual(self.session.api('account'), {'id': 'account'})
            self.assertEqual(request.call_count, 3)

    def test_not_signed_in_does_not_attempt_refresh(self):
        with patch.object(self.session, '_request') as request, self.assertRaises(AccountError):
            self.session.api('account')
        request.assert_not_called()

    def test_loopback_checks_state_before_accepting_code(self):
        errors, browser_threads = [], []
        def browser(url):
            values = parse_qs(urlsplit(url).query)
            def callback():
                try:
                    wrong = values['redirect_uri'][0] + '?' + urlencode({'state': 'wrong', 'code': 'attacker-code'})
                    try:
                        urlopen(wrong, timeout=3)
                        errors.append('wrong state accepted')
                    except HTTPError as exc:
                        if exc.code != 400: errors.append(str(exc))
                        exc.close()
                    valid = values['redirect_uri'][0] + '?' + urlencode({'state': values['state'][0], 'code': 'real-code'})
                    with urlopen(valid, timeout=3) as response:
                        if response.status != 200: errors.append('callback failed')
                except Exception as exc:
                    errors.append(str(exc))
            thread = threading.Thread(target=callback)
            browser_threads.append(thread)
            thread.start()
            self.assertEqual(values['code_challenge_method'], ['S256'])
            self.browser_challenge = values['code_challenge'][0]
            return True
        form = authorization_code(self.session.origin, browser, timeout=4)
        for thread in browser_threads: thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(form['code'], 'real-code')
        self.assertEqual(challenge(form['code_verifier']), self.browser_challenge)

    def test_browser_failure_has_no_lingering_listener(self):
        with self.assertRaises(AccountError):
            authorization_code(self.session.origin, lambda _: False)

    def test_failed_refresh_preserves_local_license(self):
        path = Path(self.temp.name)/'license.json'
        path.write_text('existing-signed-license', encoding='utf-8')
        self.session.tokens = {'expires_at': 0, 'access_token': 'old', 'refresh_token': 'old'}
        with patch.object(self.session, '_request', side_effect=AccountError('connection_failed')), self.assertRaises(AccountError):
            self.session.api('account')
        self.assertEqual(path.read_text(), 'existing-signed-license')


if __name__ == '__main__':
    unittest.main()
