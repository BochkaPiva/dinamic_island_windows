# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""First-party desktop OAuth client. Call blocking methods from a worker thread."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from .protected_storage import protect, unprotect


class AccountError(Exception):
    def __init__(self, code, status=0):
        self.code, self.status = code, status
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_origin(origin, allow_local=False):
    value = urlsplit(origin)
    if value.username or value.password or value.path or value.query or value.fragment or not value.hostname:
        raise ValueError('Invalid account service origin')
    if value.scheme != 'https' and not (allow_local and value.scheme == 'http' and value.hostname == '127.0.0.1'):
        raise ValueError('Account service requires HTTPS')
    return origin


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')


def authorization_code(origin, opener=webbrowser.open, timeout=120):
    """Bind loopback before opening system browser. Codes never enter logs or clipboard."""
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            valid = (len(self.path) < 8192 and parsed.path == '/callback' and
                     self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}' and
                     len(query.get('state', [])) == 1 and query['state'][0].isascii() and
                     hmac.compare_digest(query['state'][0], state))
            if query.get('iss') and query['iss'] != [origin]:
                valid = False
            if valid and len(query.get('code', [])) == 1 and len(query['code'][0]) <= 2048:
                result['code'] = query['code'][0]
            elif valid and query.get('error'):
                result['error'] = 'login_canceled'
            else:
                self.send_error(400)
                return
            raw = '<!doctype html><meta charset="utf-8"><title>Cloud Hub</title><p>Вернитесь в Cloud Hub. Это окно можно закрыть.</p>'.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Content-Security-Policy', "default-src 'none'")
            self.end_headers()
            self.wfile.write(raw)

    class LoopbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(2)
            return connection, address

    with LoopbackServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = .25
        redirect = f'http://127.0.0.1:{server.server_port}/callback'
        params = {'response_type': 'code', 'client_id': 'cloud-hub-desktop', 'redirect_uri': redirect,
                  'scope': 'account license', 'state': state, 'code_challenge': challenge(verifier),
                  'code_challenge_method': 'S256'}
        if opener(origin + '/o/authorize/?' + urlencode(params)) is False:
            raise AccountError('browser_not_opened')
        deadline = time.monotonic() + timeout
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if 'code' not in result:
            raise AccountError(result.get('error', 'login_timeout'))
        return {'grant_type': 'authorization_code', 'client_id': 'cloud-hub-desktop',
                'code': result['code'], 'redirect_uri': redirect, 'code_verifier': verifier}


class AccountSession:
    def __init__(self, origin, directory, installation_id, *, allow_local=False):
        self.origin = validate_origin(origin, allow_local)
        self.directory = Path(directory)
        self.installation_id = installation_id
        self.lock = threading.RLock()
        self.tokens = None
        self.http = build_opener(ProxyHandler({}), NoRedirect())
        try:
            value = json.loads(unprotect((self.directory / 'account-session.bin').read_bytes()))
            tokens = value.get('tokens')
            if (value.get('origin') == origin and isinstance(tokens, dict) and
                    isinstance(tokens.get('access_token'), str) and isinstance(tokens.get('refresh_token'), str) and
                    type(tokens.get('expires_at')) in (int, float)):
                self.tokens = tokens
        except (OSError, ValueError, TypeError):
            pass

    def _request(self, path, data=None, token=None, form=False):
        raw = None if data is None else (urlencode(data).encode() if form else json.dumps(data).encode())
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.origin + path, data=raw, headers=headers)
        try:
            with self.http.open(request, timeout=20) as response:
                content = response.read(262145)
                if len(content) > 262144:
                    raise AccountError('invalid_response')
                return json.loads(content)
        except HTTPError as exc:
            try:
                code = json.loads(exc.read(16384)).get('error', 'request_failed')
            except (ValueError, AttributeError):
                code = 'request_failed'
            raise AccountError(code if isinstance(code, str) else 'request_failed', exc.code) from None
        except (URLError, TimeoutError, OSError):
            raise AccountError('connection_failed') from None
        except ValueError:
            raise AccountError('invalid_response') from None

    def _save_tokens(self, tokens):
        if (not isinstance(tokens.get('access_token'), str) or not isinstance(tokens.get('refresh_token'), str) or
                tokens.get('token_type', '').lower() != 'bearer' or type(tokens.get('expires_in')) is not int or
                not 0 < tokens['expires_in'] <= 3600):
            raise AccountError('invalid_token_response')
        value = {**tokens, 'expires_at': time.time() + tokens['expires_in']}
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / 'account-session.tmp'
        temporary.write_bytes(protect(json.dumps({'origin': self.origin, 'tokens': value}).encode()))
        temporary.replace(self.directory / 'account-session.bin')
        self.tokens = value

    def _access(self):
        if not self.tokens:
            raise AccountError('authentication_required', 401)
        if self.tokens['expires_at'] < time.time() + 30:
            result = self._request('/o/token/', {'grant_type': 'refresh_token', 'client_id': 'cloud-hub-desktop',
                'refresh_token': self.tokens['refresh_token']}, form=True)
            self._save_tokens(result)
        return self.tokens['access_token']

    def api(self, path, data=None):
        # A single rotating refresh token must never be used by parallel requests.
        with self.lock:
            try:
                return self._request('/api/v1/' + path, data, self._access())
            except AccountError as exc:
                if exc.status != 401 or not self.tokens:
                    raise
                # Server time/revocation is authoritative, including after resume or a local clock change.
                result = self._request('/o/token/', {'grant_type': 'refresh_token', 'client_id': 'cloud-hub-desktop',
                    'refresh_token': self.tokens['refresh_token']}, form=True)
                self._save_tokens(result)
                return self._request('/api/v1/' + path, data, self.tokens['access_token'])

    def sign_in(self, name, opener=webbrowser.open):
        form = authorization_code(self.origin, opener)
        with self.lock:
            self._save_tokens(self._request('/o/token/', form, form=True))
            self.api('devices', {'installation_id': self.installation_id, 'name': name[:80]})
            return self.api('account')

    def configuration(self):
        return self._request('/api/v1/config')

    def sign_out(self):
        with self.lock:
            self.api('logout', {})  # Offline failure remains visible; do not pretend remote sessions were revoked.
            (self.directory / 'account-session.bin').unlink(missing_ok=True)
            (self.directory / 'license.json').unlink(missing_ok=True)
            (self.directory / 'community-permit.json').unlink(missing_ok=True)
            self.tokens = None
