# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-only Bot API adapter. Never expose response bodies or token-bearing URLs."""
import re
import requests
from urllib3.exceptions import HTTPError as TransportError
from django.conf import settings


class TelegramUnavailable(Exception):
    pass


def member_status(value):
    if not isinstance(value, dict):
        raise TelegramUnavailable('invalid_member')
    status = value.get('status')
    if status in ('creator', 'administrator', 'member'):
        return True
    if status == 'restricted' and type(value.get('is_member')) is bool:
        return value['is_member']
    if status in ('left', 'kicked'):
        return False
    raise TelegramUnavailable('unknown_member_status')


class Telegram:
    def __init__(self):
        token = settings.TELEGRAM_BOT_TOKEN
        if not isinstance(token, str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
            raise TelegramUnavailable('not_configured')
        self.root = 'https://api.telegram.org/bot' + token + '/'
        self.session = requests.Session()
        self.session.trust_env = False

    def call(self, method, **payload):
        if method not in ('getChatMember', 'sendMessage', 'answerCallbackQuery', 'getUpdates',
                          'getWebhookInfo', 'setWebhook', 'getMe', 'getChat'):
            raise ValueError('Unsupported bot method')
        try:
            with self.session.post(self.root + method, json=payload,
                                   timeout=(5, 35 if method == 'getUpdates' else 10),
                                   allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise TelegramUnavailable('telegram_unavailable')
                raw = response.raw.read(65537, decode_content=True)
                if len(raw) > 65536:
                    raise TelegramUnavailable('invalid_response')
                import json
                result = json.loads(raw)
                if not isinstance(result, dict) or result.get('ok') is not True or 'result' not in result:
                    raise TelegramUnavailable('invalid_response')
                return result['result']
        except (requests.RequestException, TransportError, OSError, ValueError):
            raise TelegramUnavailable('telegram_unavailable') from None

    def membership(self, telegram_id):
        value = self.call('getChatMember', chat_id=settings.COMMUNITY_CHANNEL_ID, user_id=telegram_id)
        if (not isinstance(value, dict) or not isinstance(value.get('user'), dict) or
                type(value['user'].get('id')) is not int or value['user']['id'] != telegram_id):
            raise TelegramUnavailable('wrong_member')
        return member_status(value)
