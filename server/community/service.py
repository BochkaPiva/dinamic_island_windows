# SPDX-License-Identifier: GPL-3.0-or-later
"""Membership is separate from identity and donations. All features remain equal."""
import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone as utc
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from .models import Membership, Pairing, TelegramLink
from .provider import Telegram, TelegramUnavailable, member_status


CHECK_INTERVAL = timedelta(hours=6)
OFFLINE_WINDOW = timedelta(hours=72)
LEAVE_GRACE = timedelta(hours=24)
PAIRING_WINDOW = timedelta(minutes=10)


def start_pairing(user, now=None):
    now = now or timezone.now()
    # Serialize issuance per account and bound abandoned challenges.
    with transaction.atomic():
        type(user).objects.select_for_update().get(pk=user.pk)
        if Pairing.objects.filter(user=user, consumed_at=None, expires_at__gt=now).count() >= 5:
            raise ValueError('too_many_pairings')
        token = secrets.token_urlsafe(24)
        pairing = Pairing.objects.create(user=user, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                         expires_at=now + PAIRING_WINDOW)
    return pairing, token


def offer_pairing(token, telegram_id, now=None):
    """Trusted bot event identifies a candidate. Desktop must explicitly confirm it."""
    now = now or timezone.now()
    if type(telegram_id) is not int or not 0 < telegram_id < 2**52:
        raise ValueError('invalid_telegram_id')
    if not isinstance(token, str) or len(token) != 32:
        raise ValueError('invalid_pairing')
    with transaction.atomic():
        pairing = Pairing.objects.select_for_update().filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), consumed_at=None, expires_at__gt=now).first()
        if not pairing or pairing.telegram_id not in (None, telegram_id):
            raise ValueError('pairing_unavailable')
        pairing.telegram_id = telegram_id
        pairing.save(update_fields=['telegram_id'])
    return pairing


def confirm_pairing(user, pairing_id, expected_id, now=None):
    now = now or timezone.now()
    if type(expected_id) is not int:
        raise ValueError('invalid_telegram_id')
    try:
        with transaction.atomic():
            type(user).objects.select_for_update().get(pk=user.pk)
            pairing = Pairing.objects.select_for_update().filter(
                pk=pairing_id, user=user, consumed_at=None, expires_at__gt=now).first()
            if not pairing or pairing.telegram_id != expected_id:
                raise ValueError('pairing_not_confirmed')
            link = TelegramLink.objects.filter(user=user).first()
            if link and link.telegram_id != expected_id:
                # Account recovery/relinking requires its own reviewed flow.
                raise ValueError('already_linked')
            if not link:
                link = TelegramLink.objects.create(user=user, telegram_id=expected_id)
            pairing.consumed_at = now
            pairing.save(update_fields=['consumed_at'])
            Pairing.objects.filter(user=user, consumed_at=None).update(consumed_at=now)
        return link
    except IntegrityError:
        raise ValueError('telegram_already_linked') from None


def _observe(row, present, when):
    if row.observed_at and when < row.observed_at:
        return False
    row.state = 'member' if present else 'left'
    row.observed_at = when
    row.verified_at = when
    row.missing_since = None if present else (row.missing_since or when)
    if present:
        row.last_member_at = when
    row.revision += 1
    return True


def reconcile(link, provider=None, now=None, force=False):
    now = now or timezone.now()
    row, _ = Membership.objects.get_or_create(link=link, channel_id=settings.COMMUNITY_CHANNEL_ID)
    if not force and row.verified_at and now - row.verified_at < CHECK_INTERVAL:
        return row
    present = (provider or Telegram()).membership(link.telegram_id)
    with transaction.atomic():
        row = Membership.objects.select_for_update().get(pk=row.pk)
        # A request started before a newer webhook must not overwrite its observation.
        if _observe(row, present, now):
            row.save()
    return row


def observe_event(event, update_id, now=None):
    """Events invalidate positive cache; only a canonical lookup can restore access."""
    now = now or timezone.now()
    if not isinstance(event, dict) or type(update_id) is not int or update_id < 0:
        raise ValueError('invalid_event')
    if event.get('chat', {}).get('id') != settings.COMMUNITY_CHANNEL_ID:
        return False
    raw_date = event.get('date')
    if type(raw_date) is not int or not 0 <= raw_date <= int(now.timestamp()) + 300:
        raise ValueError('invalid_event_date')
    when = datetime.fromtimestamp(raw_date, utc.utc)
    member = event.get('new_chat_member')
    present = member_status(member)
    telegram_id = member.get('user', {}).get('id')
    if type(telegram_id) is not int:
        raise ValueError('invalid_event_member')
    link = TelegramLink.objects.filter(telegram_id=telegram_id).first()
    if not link:
        return False
    with transaction.atomic():
        row, _ = Membership.objects.get_or_create(link=link, channel_id=settings.COMMUNITY_CHANNEL_ID)
        row = Membership.objects.select_for_update().get(pk=row.pk)
        if row.last_event_at and (when, update_id) <= (row.last_event_at, row.last_event_id):
            return False
        row.last_event_at, row.last_event_id = when, update_id
        if not row.observed_at or when >= row.observed_at:
            row.observed_at = when
            row.verified_at = None  # Force canonical reconciliation, including after a leave event.
            if present:
                row.state = 'unknown'
            else:
                row.state = 'left'
                row.missing_since = row.missing_since or when
            row.revision += 1
        row.save()
    return True


def permit_for(device, now=None, provider=None):
    now = now or timezone.now()
    if not device.active:
        raise ValueError('inactive_device')
    link = TelegramLink.objects.filter(user=device.user).first()
    if not link:
        raise ValueError('telegram_not_linked')
    row = reconcile(link, provider, now)
    return sign_membership(row, device.installation_id, now)


def sign_membership(row, installation_id, now):
    """Shared signed decision format; account and direct transports are independent."""
    if not row.verified_at or row.state not in ('member', 'left'):
        raise TelegramUnavailable('membership_not_verified')
    if row.state == 'member':
        until = row.verified_at + OFFLINE_WINDOW
        state = 'active'
    else:
        until = row.missing_since + (LEAVE_GRACE if row.last_member_at else timedelta())
        state = 'grace' if now < until else 'suspended'
    expires = now + OFFLINE_WINDOW
    if state == 'active':
        expires = until  # Cached checks must never slide the offline deadline forward.
    payload = {'schema': 1, 'product': 'cloud-hub', 'policy': 'telegram-membership-v1',
               'revision': row.revision,
               'channel_id': settings.COMMUNITY_CHANNEL_ID,
               'installation_id': str(installation_id), 'state': state,
               'issued_at': int(now.timestamp()), 'expires_at': int(expires.timestamp()),
               'access_until': int(until.timestamp()),
               'refresh_after': int(min(now + CHECK_INTERVAL, expires).timestamp())}
    key_data = settings.COMMUNITY_SIGNING_KEY_PEM.encode() if settings.COMMUNITY_SIGNING_KEY_PEM else Path(settings.COMMUNITY_SIGNING_KEY_PATH).read_bytes()
    key = load_pem_private_key(key_data, None)
    if not isinstance(key, Ed25519PrivateKey) or not settings.COMMUNITY_SIGNING_KEY_ID:
        raise ValueError('community_signing_not_configured')
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return {'key_id': settings.COMMUNITY_SIGNING_KEY_ID,
            'payload': base64.b64encode(raw).decode(),
            'signature': base64.b64encode(key.sign(b'cloud-hub/community/v1\0' + raw)).decode()}
