# SPDX-License-Identifier: GPL-3.0-or-later
"""Telegram-only pairing for optional extended features. Base tools need no service."""
import base64
from datetime import timedelta, datetime, timezone as utc
import hashlib
import hmac
import re
import secrets
import uuid
import functools
import json
from django.conf import settings
from django.db import transaction, IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from .models import CommunityMember, MemberStatus, MemberDevice, DevicePairing
from .provider import Telegram, TelegramUnavailable, member_status
from .service import _observe, CHECK_INTERVAL, PAIRING_WINDOW, sign_membership


def error(code, status=400):
    return JsonResponse({'error': code}, status=status)


def body(request):
    if request.content_type != 'application/json' or len(request.body) > 16384:
        raise ValueError('invalid_body')
    value = json.loads(request.body)
    if not isinstance(value, dict):
        raise ValueError('invalid_body')
    return value


def experiment(view):
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not configured():
            return error('community_not_configured', 503)
        return view(request, *args, **kwargs)
    return wrapped


def digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode()


def configured():
    return bool(settings.COMMUNITY_EXPERIMENT_ENABLED and settings.COMMUNITY_CHANNEL_ID < 0 and
                settings.TELEGRAM_BOT_USERNAME and settings.TELEGRAM_BOT_TOKEN and
                (settings.COMMUNITY_SIGNING_KEY_PATH or settings.COMMUNITY_SIGNING_KEY_PEM) and
                settings.COMMUNITY_SIGNING_KEY_ID)


@require_GET
def configuration(request):
    return JsonResponse({'schema': 2, 'enabled': configured(), 'base_requires_connection': False,
        'channel_url': settings.COMMUNITY_CHANNEL_URL,
        'bot_username': settings.TELEGRAM_BOT_USERNAME,
        'channel_id': settings.COMMUNITY_CHANNEL_ID,
        'free_groups': 2, 'extended_groups': None,
        'check_interval_seconds': 21600, 'offline_seconds': 259200, 'leave_grace_seconds': 86400})


@require_GET
@experiment
def health(request):
    from django.db import DatabaseError
    try:
        MemberDevice.objects.exists()
    except DatabaseError:
        return error('database_unavailable', 503)
    return JsonResponse({'status': 'ok', 'schema': 2})


def pairing_from(request, identifier):
    value = body(request)
    verifier = value.get('verifier')
    if not isinstance(verifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', verifier):
        raise ValueError('invalid_proof')
    pairing = DevicePairing.objects.filter(pk=identifier, expires_at__gt=timezone.now()).first()
    if not pairing or not hmac.compare_digest(pairing.code_challenge, challenge(verifier)):
        raise ValueError('pairing_unavailable')
    return pairing, verifier, value


@csrf_exempt
@require_POST
@experiment
def pairing_start(request):
    if not configured():
        return error('community_not_configured', 503)
    try:
        value = body(request)
        installation = uuid.UUID(value['installation_id'])
        proof = value.get('code_challenge')
        if value.get('product') != 'cloud-hub' or not isinstance(proof, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', proof):
            raise ValueError()
        now = timezone.now()
        if DevicePairing.objects.filter(installation_id=installation, expires_at__gt=now).count() >= 3:
            return error('too_many_pairings', 429)
        token = secrets.token_urlsafe(24)
        pairing = DevicePairing.objects.create(installation_id=installation, code_challenge=proof,
            bot_token_hash=digest(token), expires_at=now + PAIRING_WINDOW)
        return JsonResponse({'id': str(pairing.pk), 'expires_at': int(pairing.expires_at.timestamp()),
            'bot_url': f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}'})
    except (ValueError, KeyError, TypeError, AttributeError):
        return error('invalid_pairing')


@csrf_exempt
@require_POST
@experiment
def pairing_status(request, pairing_id):
    try:
        pairing, _, _ = pairing_from(request, pairing_id)
        return JsonResponse({'state': 'confirm' if pairing.telegram_id else 'waiting',
                             'telegram_id': pairing.telegram_id})
    except (ValueError, TypeError, KeyError):
        return error('pairing_unavailable', 404)


def complete_pairing(pairing, verifier, expected_id):
    now = timezone.now()
    if type(expected_id) is not int or expected_id != pairing.telegram_id:
        raise ValueError('pairing_not_confirmed')
    # Repeatable only with the original device proof during the 10-minute exchange.
    credential = hmac.new(settings.SECRET_KEY.encode(),
        ('community-device/v2\0' + str(pairing.pk) + '\0' + verifier).encode(), hashlib.sha256).hexdigest()
    with transaction.atomic():
        pairing = DevicePairing.objects.select_for_update().get(pk=pairing.pk)
        if pairing.expires_at <= now:
            raise ValueError('pairing_expired')
        if pairing.consumed_at:
            device = MemberDevice.objects.get(pk=pairing.device_id, active=True)
            if not hmac.compare_digest(device.credential_hash, digest(credential)):
                raise ValueError('pairing_consumed')
            return device, credential
        member, _ = CommunityMember.objects.get_or_create(telegram_id=expected_id)
        CommunityMember.objects.select_for_update().get(pk=member.pk)
        device = MemberDevice.objects.select_for_update().filter(installation_id=pairing.installation_id).first()
        if device and device.member_id != member.pk:
            raise ValueError('installation_already_linked')
        if device:
            device.credential_hash = digest(credential)
            device.credential_expires_at = now + timedelta(days=90)
            device.active = True
            device.save()
        else:
            device = MemberDevice.objects.create(member=member, installation_id=pairing.installation_id,
                credential_hash=digest(credential), credential_expires_at=now + timedelta(days=90))
        pairing.device = device
        pairing.consumed_at = now
        pairing.save(update_fields=['device', 'consumed_at'])
    return device, credential


def reconcile_member(member, provider=None, now=None, force=False):
    now = now or timezone.now()
    row, _ = MemberStatus.objects.get_or_create(member=member, channel_id=settings.COMMUNITY_CHANNEL_ID)
    if not force and row.verified_at and now - row.verified_at < CHECK_INTERVAL:
        return row
    present = (provider or Telegram()).membership(member.telegram_id)
    with transaction.atomic():
        row = MemberStatus.objects.select_for_update().get(pk=row.pk)
        if _observe(row, present, now):
            row.save()
    return row


def device_permit(device, provider=None, now=None):
    now = now or timezone.now()
    if not device.active or device.credential_expires_at <= now:
        raise ValueError('device_expired')
    return sign_membership(reconcile_member(device.member, provider, now), device.installation_id, now)


@csrf_exempt
@require_POST
@experiment
def pairing_confirm(request, pairing_id):
    try:
        pairing, verifier, value = pairing_from(request, pairing_id)
        device, credential = complete_pairing(pairing, verifier, value.get('telegram_id'))
        return JsonResponse({'device_id': str(device.pk), 'installation_id': str(device.installation_id),
            'credential': credential, 'credential_expires_at': int(device.credential_expires_at.timestamp())})
    except (ValueError, TypeError, KeyError, MemberDevice.DoesNotExist, IntegrityError) as exc:
        return error(str(exc) if isinstance(exc, ValueError) else 'pairing_unavailable', 409)


def authenticated_device(request):
    header = request.headers.get('Authorization', '')
    if not re.fullmatch(r'Bearer [a-f0-9]{64}', header):
        raise ValueError('device_not_connected')
    device = MemberDevice.objects.select_related('member').filter(
        credential_hash=digest(header[7:]), active=True, credential_expires_at__gt=timezone.now()).first()
    if not device:
        raise ValueError('device_not_connected')
    return device


@csrf_exempt
@require_POST
@experiment
def membership_permit(request):
    try:
        device = authenticated_device(request)
    except ValueError:
        return error('device_not_connected', 401)
    try:
        permit = device_permit(device)
        MemberDevice.objects.filter(pk=device.pk).update(last_seen=timezone.now())
        return JsonResponse({'permit': permit})
    except (TelegramUnavailable, OSError, ValueError, MemberStatus.DoesNotExist):
        return error('community_temporarily_unavailable', 503)


@csrf_exempt
@require_POST
@experiment
def disconnect(request):
    try:
        device = authenticated_device(request)
    except ValueError:
        return error('device_not_connected', 401)
    # Revoke only this installation. Other computers are independent.
    with transaction.atomic():
        MemberDevice.objects.filter(pk=device.pk).update(active=False)
        DevicePairing.objects.filter(installation_id=device.installation_id).delete()
    return JsonResponse({'disconnected': True})


def offer(token, telegram_id):
    if type(telegram_id) is not int or not 0 < telegram_id < 2**52:
        raise ValueError('invalid_telegram_id')
    with transaction.atomic():
        pairing = DevicePairing.objects.select_for_update().filter(bot_token_hash=digest(token),
            expires_at__gt=timezone.now(), consumed_at=None).first()
        if not pairing or pairing.telegram_id not in (None, telegram_id):
            raise ValueError('pairing_unavailable')
        pairing.telegram_id = telegram_id
        pairing.save(update_fields=['telegram_id'])


def observe(event, update_id, now=None):
    now = now or timezone.now()
    if event.get('chat', {}).get('id') != settings.COMMUNITY_CHANNEL_ID:
        return
    stamp = event.get('date')
    if type(stamp) is not int or not 0 <= stamp <= int(now.timestamp()) + 300:
        raise ValueError('invalid_date')
    when = datetime.fromtimestamp(stamp, utc.utc)
    value = event.get('new_chat_member')
    present = member_status(value)
    member = CommunityMember.objects.filter(telegram_id=value['user']['id']).first()
    if not member:
        return
    with transaction.atomic():
        row, _ = MemberStatus.objects.get_or_create(member=member, channel_id=settings.COMMUNITY_CHANNEL_ID)
        row = MemberStatus.objects.select_for_update().get(pk=row.pk)
        if row.last_event_at and (when, update_id) <= (row.last_event_at, row.last_event_id):
            return
        row.last_event_at, row.last_event_id = when, update_id
        if not row.observed_at or when >= row.observed_at:
            row.observed_at, row.verified_at = when, None
            row.state = 'unknown' if present else 'left'
            if not present:
                row.missing_since = row.missing_since or when
            row.revision += 1
        row.save()


def dispatch(update, bot):
    if 'chat_member' in update:
        observe(update['chat_member'], update['update_id'])
        return
    message = update.get('message')
    if isinstance(message, dict):
        chat, sender = message.get('chat', {}), message.get('from', {})
        text = message.get('text', '')
        if chat.get('type') != 'private' or chat.get('id') != sender.get('id') or sender.get('is_bot') is not False:
            return
        match = re.fullmatch(r'/start ([A-Za-z0-9_-]{32})', text) if isinstance(text, str) else None
        if not match:
            return
        # Do not send prompts for expired/forged challenges.
        if not DevicePairing.objects.filter(bot_token_hash=digest(match[1]), consumed_at=None,
                                             expires_at__gt=timezone.now()).exists():
            return
        bot.call('sendMessage', chat_id=chat['id'], text='Подключите расширенные возможности Nelviro: подпишитесь на канал и нажмите «Проверить». Базовые функции приложения работают без подписки.',
            reply_markup={'inline_keyboard': [[{'text': 'Открыть канал', 'url': settings.COMMUNITY_CHANNEL_URL}],
                [{'text': 'Проверить подписку', 'callback_data': 'join:' + match[1]}]]})
        return
    callback = update.get('callback_query')
    if not isinstance(callback, dict):
        return
    sender, chat = callback.get('from', {}), callback.get('message', {}).get('chat', {})
    value = callback.get('data', '')
    match = re.fullmatch(r'join:([A-Za-z0-9_-]{32})', value) if isinstance(value, str) else None
    if not match or chat.get('type') != 'private' or chat.get('id') != sender.get('id') or sender.get('is_bot') is not False:
        return
    if bot.membership(sender['id']):
        try:
            offer(match[1], sender['id'])
            text = 'Готово. Вернитесь в приложение — расширенные возможности подключатся автоматически.'
        except ValueError:
            text = 'Запрос истёк. Начните подключение ещё раз в приложении.'
    else:
        text = 'Подписка пока не найдена. Подпишитесь и повторите проверку.'
    bot.call('answerCallbackQuery', callback_query_id=callback['id'], text=text)


@csrf_exempt
@require_POST
@experiment
def webhook(request):
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not secret or not supplied.isascii() or not hmac.compare_digest(secret, supplied):
        return error('invalid_webhook', 403)
    try:
        update = body(request)
        if type(update.get('update_id')) is not int or update['update_id'] < 0:
            raise ValueError()
        dispatch(update, Telegram())
        return JsonResponse({'ok': True})
    except TelegramUnavailable:
        return error('telegram_temporarily_unavailable', 503)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return error('invalid_update', 400)
