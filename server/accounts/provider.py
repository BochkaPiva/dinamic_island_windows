# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""Real YooKassa transport. Offline fixtures belong only in tests."""
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from urllib.parse import urlencode
import requests
from django.conf import settings


class ProviderUnavailable(Exception):
    pass


def kopecks(value):
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError('invalid_amount')
        return int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('invalid_amount') from None


def confirmation_url(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('invalid_checkout_url')
    if not any(host == domain or host.endswith('.' + domain) for domain in ('yookassa.ru', 'yoomoney.ru')):
        raise ValueError('invalid_checkout_host')
    return value


class YooKassa:
    def _request(self, method, path, payload=None, key=None):
        if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
            raise ProviderUnavailable('provider_not_configured')
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.request(method, 'https://api.yookassa.ru/v3/' + path,
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                    headers={'Idempotence-Key': key} if key else {}, json=payload,
                    timeout=(5, 20), allow_redirects=False, stream=True) as response:
                    response.raise_for_status()
                    if response.status_code not in (200, 201):
                        raise ProviderUnavailable('unexpected_provider_status')
                    chunks, size = [], 0
                    for chunk in response.iter_content(8192):
                        size += len(chunk)
                        if size > 65536:
                            raise ProviderUnavailable('provider_response_too_large')
                        chunks.append(chunk)
                    import json
                    result = json.loads(b''.join(chunks))
                    if not isinstance(result, dict):
                        raise ValueError('invalid_response')
                    return result
        except (requests.RequestException, ValueError):
            # Never expose response bodies or credentials in API errors/logs.
            raise ProviderUnavailable('provider_request_failed') from None

    @staticmethod
    def _identifier(value):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
            raise ValueError('invalid_provider_id')
        return value

    def create(self, payment):
        return self._request('POST', 'payments', payment.request_payload, str(payment.id))

    def payment(self, identifier):
        return self._request('GET', 'payments/' + self._identifier(identifier))

    def refund(self, identifier):
        return self._request('GET', 'refunds/' + self._identifier(identifier))

    def refunds(self, cursor=None):
        params = {'limit': 50}
        if cursor:
            params['cursor'] = cursor
        return self._request('GET', 'refunds?' + urlencode(params))
