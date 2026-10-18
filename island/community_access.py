# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in membership client foundation. No desktop modules are blocked by this file.

Network methods must run on a worker. First-party account authentication is a
separate prerequisite; Telegram is only a community-membership factor.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit, parse_qs
from .signed_payload import verify_envelope
from . import build_config


OFFLINE_SECONDS = 72 * 3600
LEAVE_GRACE_SECONDS = 24 * 3600
PURPOSE = 'cloud-hub/community/v1'


@dataclass(frozen=True)
class MembershipPermit:
    state: str
    revision: int
    issued_at: int
    refresh_after: int
    expires_at: int
    access_until: int

    def allows(self, now):
        return now < min(self.expires_at, self.access_until) and self.state in ('active', 'grace')

    def needs_refresh(self, now):
        return now >= self.refresh_after

    def reason(self, now):
        if self.state == 'suspended' or now >= self.access_until and self.state == 'grace':
            return 'membership_required'
        if now >= self.expires_at:
            return 'verification_expired'
        return 'membership_grace' if self.state == 'grace' else 'verified'


def verify_permit(envelope, keys, installation_id, channel_id, now=None, *, allow_expired=False):
    now = time.time() if now is None else now
    value = verify_envelope(envelope, keys, PURPOSE)
    if (type(value.get('schema')) is not int or value['schema'] != 1 or
            value.get('product') != build_config.PRODUCT_ID or
            value.get('policy') != 'telegram-membership-v1' or
            type(channel_id) is not int or channel_id >= 0 or
            type(value.get('channel_id')) is not int or value['channel_id'] != channel_id or
            value.get('installation_id') != installation_id):
        raise ValueError('Permit belongs to another product, channel or installation')
    fields = ('revision', 'issued_at', 'refresh_after', 'expires_at', 'access_until')
    if any(type(value.get(field)) is not int or value[field] < 0 for field in fields):
        raise ValueError('Invalid permit bounds')
    state = value.get('state')
    revision, issued, refresh, expires, until = [value[field] for field in fields]
    if (state not in ('active', 'grace', 'suspended') or revision < 1 or
            not issued <= refresh <= expires or not issued < expires <= issued + OFFLINE_SECONDS or
            until > expires or issued > now + 300 or not allow_expired and now >= expires):
        raise ValueError('Invalid or expired membership permit')
    if (state == 'active' and until != expires or
            state == 'grace' and not issued < until <= issued + LEAVE_GRACE_SECONDS or
            state == 'suspended' and until > issued):
        raise ValueError('Inconsistent membership state')
    return MembershipPermit(state, revision, issued, refresh, expires, until)


class PermitStore:
    """Only signed decisions replace the cache. HTTP errors must never call clear()."""
    def __init__(self, directory, keys, installation_id, channel_id, *, clock=None):
        self.path = Path(directory) / 'community-permit.json'
        self.keys, self.installation_id, self.channel_id = keys, installation_id, channel_id
        self.clock = clock or time.time
        self.lock = threading.RLock()

    def _verify(self, envelope, allow_expired=False):
        return verify_permit(envelope, self.keys, self.installation_id, self.channel_id,
                             self.clock(), allow_expired=allow_expired)

    def load(self):
        try:
            return self._verify(self.path.read_bytes())
        except (OSError, ValueError):
            return None

    def install(self, envelope):
        with self.lock:
            permit = self._verify(envelope)
            try:
                previous = self._verify(self.path.read_bytes(), allow_expired=True)
            except (OSError, ValueError):
                previous = None
            if previous and (permit.revision < previous.revision or permit.issued_at < previous.issued_at):
                raise ValueError('Stale membership decision')
            # A signed refusal is persisted too, so an old positive cache cannot resurrect access.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(envelope, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
            return permit

    def clear(self):
        """Explicit disconnect only. No user documents, shortcuts or settings are touched."""
        with self.lock:
            self.path.unlink(missing_ok=True)


class CommunitySession:
    def __init__(self, account_session, store):
        if account_session.installation_id != store.installation_id:
            raise ValueError('Account and community installation differ')
        self.account = account_session
        self.store = store

    def start_pairing(self):
        value = self.account.api('community/pairings', {})
        parsed = urlsplit(value.get('bot_url', ''))
        params = parse_qs(parsed.query)
        if (parsed.scheme != 'https' or parsed.netloc != 't.me' or parsed.fragment or
                not parsed.path.strip('/') or set(params) != {'start'} or
                len(params['start']) != 1 or len(params['start'][0]) != 32):
            raise ValueError('Invalid Telegram pairing URL')
        return value

    def pairing_status(self, pairing_id):
        import uuid
        return self.account.api('community/pairings/' + str(uuid.UUID(pairing_id)))

    def confirm_pairing(self, pairing_id, telegram_id):
        import uuid
        return self.account.api('community/pairings/' + str(uuid.UUID(pairing_id)) + '/confirm',
                                       {'telegram_id': telegram_id})

    def refresh(self):
        value = self.account.api('community/permit', {})
        return self.store.install(value['permit'])

    def disconnect(self):
        value = self.account.api('community/disconnect', {})
        if value.get('disconnected') is not True:
            raise ValueError('Disconnect was not acknowledged')
        self.store.clear()
