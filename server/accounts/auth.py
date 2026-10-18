# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import hashlib
import uuid
from functools import wraps
from urllib.parse import urlsplit

import requests
from authlib.integrations.django_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from django.conf import settings
from django.contrib.auth import login
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from oauth2_provider.oauth2_backends import get_oauthlib_core
from oauth2_provider.models import AccessToken, RefreshToken
from .models import Identity, User


def error(code, status=400):
    return JsonResponse({'error': code}, status=status)


def account_api(scope='account'):
    """Only header bearer tokens; never a browser cookie or a query-string token."""
    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            header = request.headers.get('Authorization', '')
            if not header.startswith('Bearer ') or len(header) > 8192:
                response = error('authentication_required', 401)
                response['WWW-Authenticate'] = 'Bearer'
                return response
            valid, oauth_request = get_oauthlib_core().verify_request(request, scopes=[scope])
            if not valid or not oauth_request.user or not oauth_request.user.is_active:
                return error('invalid_token', 401)
            checksum = hashlib.sha256(header[7:].encode()).hexdigest()
            token = AccessToken.objects.filter(token_checksum=checksum).first()
            family = RefreshToken.objects.filter(access_token=token, revoked__isnull=True).first()
            if not token or not family:
                return error('session_revoked', 401)
            request.account = oauth_request.user
            request.token_family = family.token_family
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def yandex_client():
    if not settings.YANDEX_CLIENT_ID or not settings.YANDEX_CLIENT_SECRET:
        raise ValueError('provider_not_configured')
    oauth = OAuth()
    return oauth.register('yandex', client_id=settings.YANDEX_CLIENT_ID,
        client_secret=settings.YANDEX_CLIENT_SECRET,
        authorize_url='https://oauth.yandex.ru/authorize',
        access_token_url='https://oauth.yandex.ru/token',
        client_kwargs={'scope': 'login:info login:email', 'code_challenge_method': 'S256',
                       'token_endpoint_auth_method': 'client_secret_post'},
        timeout=15)


def safe_next(value):
    # Only our native-client authorization endpoint, no external/open redirects.
    parsed = urlsplit(value)
    return value if not parsed.netloc and not parsed.scheme and parsed.path == '/o/authorize/' else '/auth/done/'


@require_GET
def login_page(request):
    request.session['login_next'] = safe_next(request.GET.get('next', ''))
    configured = bool(settings.YANDEX_CLIENT_ID and settings.YANDEX_CLIENT_SECRET)
    return render(request, 'accounts/login.html', {'configured': configured}, status=200 if configured else 503)


@require_POST
def yandex_start(request):
    try:
        return yandex_client().authorize_redirect(request, settings.PUBLIC_ORIGIN + '/auth/yandex/callback/')
    except ValueError:
        return error('provider_not_configured', 503)


@transaction.atomic
def identity_user(subject, email=''):
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError('invalid_identity')
    if not isinstance(email, str):
        email = ''
    existing = Identity.objects.filter(provider='yandex', subject=subject).select_related('user').first()
    if existing:
        return existing.user
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=uuid.uuid4().hex, email=email[:254])
            user.set_unusable_password()
            user.save(update_fields=['password'])
            Identity.objects.create(user=user, provider='yandex', subject=subject)
            return user
    except IntegrityError:
        return Identity.objects.get(provider='yandex', subject=subject).user


@require_GET
def yandex_callback(request):
    try:
        token = yandex_client().authorize_access_token(request)
        # Access token is used transiently and is not retained as an account credential.
        response = requests.get('https://login.yandex.ru/info', params={'format': 'json'},
            headers={'Authorization': 'OAuth ' + token['access_token']}, timeout=(5, 15), allow_redirects=False)
        response.raise_for_status()
        profile = response.json()
        if profile.get('client_id') != settings.YANDEX_CLIENT_ID:
            raise ValueError('wrong_provider_client')
        user = identity_user(profile.get('id'), profile.get('default_email', ''))
        if not user.is_active:
            return error('account_disabled', 403)
        target = safe_next(request.session.pop('login_next', ''))
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return HttpResponseRedirect(target)
    except (ValueError, KeyError, OAuthError, requests.RequestException):
        return error('login_failed', 400)


@require_GET
def done(request):
    return render(request, 'accounts/done.html')
