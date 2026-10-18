# SPDX-License-Identifier: GPL-3.0-or-later
"""Disabled-by-default API experiment, behind existing first-party account auth."""
import functools
import hmac
import re
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from accounts.api import body
from accounts.auth import account_api, error
from accounts.models import Device
from .models import Pairing, TelegramLink
from .provider import Telegram, TelegramUnavailable
from .service import start_pairing, offer_pairing, confirm_pairing, observe_event, permit_for


def experiment(view):
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.COMMUNITY_EXPERIMENT_ENABLED:
            return error('community_not_enabled', 503)
        return view(request, *args, **kwargs)
    return wrapped


@require_GET
def configuration(request):
    return JsonResponse({'schema': 1, 'enabled': settings.COMMUNITY_EXPERIMENT_ENABLED,
        'enforcement': False, 'requires_first_party_account': True,
        'channel_url': settings.COMMUNITY_CHANNEL_URL if settings.COMMUNITY_EXPERIMENT_ENABLED else '',
        'check_interval_seconds': 21600, 'offline_seconds': 259200, 'leave_grace_seconds': 86400})


@csrf_exempt
@require_POST
@experiment
@account_api()
def pairing_start(request):
    try:
        bot = settings.TELEGRAM_BOT_USERNAME
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', bot):
            raise ValueError('bot_not_configured')
        pairing, token = start_pairing(request.account)
        return JsonResponse({'id': str(pairing.pk), 'expires_at': pairing.expires_at.isoformat(),
                             'bot_url': f'https://t.me/{bot}?start={token}'})
    except ValueError as exc:
        return error(str(exc), 409)


@require_GET
@experiment
@account_api()
def pairing_status(request, pairing_id):
    from django.utils import timezone
    pairing = Pairing.objects.filter(pk=pairing_id, user=request.account,
        consumed_at=None, expires_at__gt=timezone.now()).first()
    if not pairing:
        return error('pairing_unavailable', 404)
    return JsonResponse({'state': 'confirm' if pairing.telegram_id else 'waiting',
                         'telegram_id': pairing.telegram_id})


@csrf_exempt
@require_POST
@experiment
@account_api()
def pairing_confirm(request, pairing_id):
    try:
        link = confirm_pairing(request.account, pairing_id, body(request)['telegram_id'])
        return JsonResponse({'linked': True, 'telegram_id': link.telegram_id})
    except (ValueError, KeyError, TypeError):
        return error('pairing_not_confirmed', 409)


@csrf_exempt
@require_POST
@experiment
@account_api('license')
def membership_permit(request):
    device = Device.objects.filter(user=request.account, token_family=request.token_family, active=True).first()
    if not device:
        return error('register_device_first', 409)
    try:
        return JsonResponse({'permit': permit_for(device)})
    except TelegramUnavailable:
        # Failure is not evidence of leaving the channel. The client retains its signed lease.
        return error('community_temporarily_unavailable', 503)
    except (ValueError, OSError):
        return error('community_permit_unavailable', 409)


@csrf_exempt
@require_POST
@experiment
@account_api()
def disconnect(request):
    with transaction.atomic():
        type(request.account).objects.select_for_update().get(pk=request.account.pk)
        Pairing.objects.filter(user=request.account).delete()
        TelegramLink.objects.filter(user=request.account).delete()
    return JsonResponse({'disconnected': True})


def dispatch(update, bot):
    if 'chat_member' in update:
        observe_event(update['chat_member'], update['update_id'])
        return
    message = update.get('message')
    if isinstance(message, dict):
        chat, sender = message.get('chat', {}), message.get('from', {})
        text = message.get('text', '')
        if (chat.get('type') != 'private' or chat.get('id') != sender.get('id') or
                sender.get('is_bot') is not False or not isinstance(text, str)):
            return
        match = re.fullmatch(r'/start ([A-Za-z0-9_-]{32})', text)
        if not match:
            return
        # Starting the bot never silently links an account.
        bot.call('sendMessage', chat_id=chat['id'], text='Подпишитесь на канал и подтвердите подключение. Затем вернитесь в приложение.',
                 reply_markup={'inline_keyboard': [
                     [{'text': 'Открыть канал', 'url': settings.COMMUNITY_CHANNEL_URL}],
                     [{'text': 'Проверить подписку', 'callback_data': 'pair:' + match[1]}]]})
        return
    callback = update.get('callback_query')
    if not isinstance(callback, dict):
        return
    sender = callback.get('from', {})
    chat = callback.get('message', {}).get('chat', {})
    match = re.fullmatch(r'pair:([A-Za-z0-9_-]{32})', callback.get('data', ''))
    if (not match or chat.get('type') != 'private' or chat.get('id') != sender.get('id') or
            sender.get('is_bot') is not False):
        return
    if bot.membership(sender['id']):
        try:
            offer_pairing(match[1], sender['id'])
            text = 'Подписка подтверждена. Подтвердите подключение в приложении.'
        except ValueError:
            text = 'Запрос истёк или уже использован. Начните подключение из приложения.'
    else:
        text = 'Подписка пока не найдена. Подпишитесь на канал и попробуйте снова.'
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
