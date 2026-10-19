# SPDX-License-Identifier: GPL-3.0-or-later
"""Direct Telegram device pairing. No account provider or OAuth dependency."""
import base64
import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError
from .protected_storage import protect, unprotect
from .community_access import PermitStore


class CommunityError(Exception):
    def __init__(self, code, status=0):
        self.code, self.status = code, status
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def proof(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode()


def validate_origin(origin, allow_local=False):
    parsed = urlsplit(origin)
    if (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or
            not parsed.hostname or parsed.scheme != 'https' and
            not (allow_local and parsed.scheme == 'http' and parsed.hostname == '127.0.0.1')):
        raise ValueError('Community service requires an HTTPS origin')
    return origin


class CommunityClient:
    def __init__(self, origin, directory, installation_id, keys, channel_id, *, allow_local=False, clock=None):
        self.origin = validate_origin(origin, allow_local)
        self.directory = Path(directory)
        self.installation_id = str(uuid.UUID(installation_id))
        self.clock = clock or time.time
        self.store = PermitStore(directory, keys, self.installation_id, channel_id, clock=self.clock)
        self.http = build_opener(ProxyHandler({}), NoRedirect())
        self.lock = threading.RLock()
        self.session = None
        self.pairing = None
        try:
            value = json.loads(unprotect((self.directory / 'community-device.bin').read_bytes()))
            if value.get('origin') == self.origin and value.get('installation_id') == self.installation_id:
                if isinstance(value.get('credential'), str) and re.fullmatch(r'[a-f0-9]{64}', value['credential']):
                    self.session = value
        except (OSError, ValueError, TypeError):
            pass
        try:
            value=json.loads(unprotect((self.directory/'community-pairing.bin').read_bytes()))
            if (value.get('origin')==self.origin and value.get('installation_id')==self.installation_id and
                    type(value.get('expires_at')) is int and self.clock()<value['expires_at']<=self.clock()+660 and
                    isinstance(value.get('verifier'),str) and re.fullmatch(r'[A-Za-z0-9_-]{64}',value['verifier'])):
                value['id']=str(uuid.UUID(value['id']))
                self.pairing=value
        except (OSError,ValueError,TypeError,KeyError):
            pass

    def request(self, route, data=None, *, authenticated=False):
        if not re.fullmatch(r'[a-z0-9/-]+', route):
            raise ValueError('Invalid API route')
        headers = {'Accept': 'application/json'}
        if authenticated:
            if not self.session:
                raise CommunityError('device_not_connected', 401)
            headers['Authorization'] = 'Bearer ' + self.session['credential']
        raw = None if data is None else json.dumps(data).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(self.origin + '/api/v2/community/' + route, data=raw, headers=headers)
        try:
            with self.http.open(request, timeout=15) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError()
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError()
                return value
        except HTTPError as exc:
            try:
                code = json.loads(exc.read(16384)).get('error', 'request_failed')
            except (ValueError, AttributeError):
                code = 'request_failed'
            raise CommunityError(code if isinstance(code, str) else 'request_failed', exc.code) from None
        except (URLError, OSError, TimeoutError):
            raise CommunityError('connection_failed') from None
        except (ValueError, TypeError):
            raise CommunityError('invalid_response') from None

    def start_pairing(self):
        with self.lock:
            verifier = secrets.token_urlsafe(48)
            value = self.request('pairings', {'product': 'cloud-hub', 'installation_id': self.installation_id,
                                               'code_challenge': proof(verifier)})
            identifier = str(uuid.UUID(value['id']))
            parsed = urlsplit(value['bot_url'])
            params = parse_qs(parsed.query)
            if (parsed.scheme != 'https' or parsed.netloc != 't.me' or parsed.fragment or
                    not re.fullmatch(r'/[A-Za-z][A-Za-z0-9_]{4,31}', parsed.path) or
                    set(params) != {'start'} or len(params['start']) != 1 or
                    not re.fullmatch(r'[A-Za-z0-9_-]{32}', params['start'][0]) or
                    type(value.get('expires_at')) is not int or
                    not self.clock() < value['expires_at'] <= self.clock() + 660):
                raise ValueError('Invalid pairing response')
            self.pairing = {**value, 'id': identifier, 'verifier': verifier}
            self.directory.mkdir(parents=True,exist_ok=True)
            pending={**self.pairing,'origin':self.origin,'installation_id':self.installation_id}
            temporary=self.directory/'community-pairing.tmp'
            temporary.write_bytes(protect(json.dumps(pending).encode()))
            temporary.replace(self.directory/'community-pairing.bin')
            return value

    def pairing_status(self):
        with self.lock:
            if not self.pairing or self.clock() >= self.pairing['expires_at']:
                self.pairing = None
                raise CommunityError('pairing_expired')
            return self.request('pairings/' + self.pairing['id'] + '/status',
                                {'verifier': self.pairing['verifier']})

    def confirm_pairing(self, telegram_id):
        with self.lock:
            if not self.pairing:
                raise CommunityError('pairing_expired')
            value = self.request('pairings/' + self.pairing['id'] + '/confirm',
                {'verifier': self.pairing['verifier'], 'telegram_id': telegram_id})
            if (value.get('installation_id') != self.installation_id or
                    not isinstance(value.get('credential'), str) or
                    not re.fullmatch(r'[a-f0-9]{64}', value['credential']) or
                    type(value.get('credential_expires_at')) is not int or
                    value['credential_expires_at'] <= self.clock()):
                raise ValueError('Invalid device credential')
            session = {**value, 'origin': self.origin}
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.directory / 'community-device.tmp'
            temporary.write_bytes(protect(json.dumps(session).encode()))
            temporary.replace(self.directory / 'community-device.bin')
            self.session = session
            self.pairing = None
            (self.directory/'community-pairing.bin').unlink(missing_ok=True)
        return self.refresh()

    def refresh(self):
        with self.lock:
            value = self.request('permit', {}, authenticated=True)
            return self.store.install(value['permit'])

    def disconnect(self):
        with self.lock:
            if self.session:
                result = self.request('disconnect', {}, authenticated=True)
                if result.get('disconnected') is not True:
                    raise ValueError('Disconnect was not acknowledged')
            self.forget_local()

    def forget_local(self):
        """Explicit local disconnect also works offline. No remote-revocation claim."""
        with self.lock:
            (self.directory / 'community-device.bin').unlink(missing_ok=True)
            (self.directory / 'community-pairing.bin').unlink(missing_ok=True)
            self.store.clear()
            self.session = self.pairing = None
