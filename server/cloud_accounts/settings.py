# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""Separate account service. Desktop data never belongs in this database."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.environ.get('CLOUD_ENV') == 'production'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if PRODUCTION and len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('A private DJANGO_SECRET_KEY is required')
SECRET_KEY = SECRET_KEY or 'local-development-only-never-deploy-this-key'
DEBUG = False
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver').split(',')
PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
origin = urlsplit(PUBLIC_ORIGIN)
if origin.path or origin.query or origin.fragment or not origin.hostname or origin.username:
    raise ImproperlyConfigured('PUBLIC_ORIGIN must be an origin without path or credentials')
if PRODUCTION and (origin.scheme != 'https' or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('Production requires HTTPS and explicit hosts')
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
    'django.contrib.staticfiles', 'oauth2_provider', 'accounts', 'community',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.NoStoreMiddleware',
]
ROOT_URLCONF = 'cloud_accounts.urls'
WSGI_APPLICATION = 'cloud_accounts.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.csrf']}}]
AUTH_USER_MODEL = 'accounts.User'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'ru'
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' if PRODUCTION else None
LOGIN_URL = '/auth/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 3600
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION
SECURE_HSTS_PRELOAD = PRODUCTION
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'no-referrer'
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
# The deployment proxy must strip and set this header; the app is not publicly bound.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if PRODUCTION else None
if os.environ.get('PGHOST'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ['PGHOST'], 'PORT': os.environ.get('PGPORT', '5432'),
        'NAME': os.environ.get('PGDATABASE', 'cloud_accounts'),
        'USER': os.environ.get('PGUSER', 'cloud_accounts'), 'PASSWORD': os.environ.get('PGPASSWORD', ''),
        'CONN_MAX_AGE': 60, 'OPTIONS': {'sslmode': os.environ.get('PGSSLMODE', 'require')}}}
else:
    if PRODUCTION:
        raise ImproperlyConfigured('Production requires PostgreSQL')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'local.sqlite3'}}
OAUTH2_PROVIDER = {
    'SCOPES': {'account': 'Личный кабинет', 'license': 'Лицензия этого устройства'},
    'DEFAULT_SCOPES': ['account', 'license'], 'PKCE_REQUIRED': True,
    'ACCESS_TOKEN_EXPIRE_SECONDS': 600, 'AUTHORIZATION_CODE_EXPIRE_SECONDS': 60,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 30 * 86400, 'ROTATE_REFRESH_TOKEN': True,
    'REFRESH_TOKEN_REUSE_PROTECTION': True, 'REFRESH_TOKEN_GRACE_PERIOD_SECONDS': 0,
    'COMPLIANT_BCP_RFC9700_PKCE_METHOD': True,
    'COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT': True,
    'COMPLIANT_BCP_RFC9700_TOKEN_STORAGE': True,
    'COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT': True,
    'COMPLIANT_BCP_RFC9700_PASSWORD_GRANT': True,
    'DCR_ENABLED': False, 'CIMD_ENABLED': False,
}
YANDEX_CLIENT_ID = os.environ.get('YANDEX_CLIENT_ID', '')
YANDEX_CLIENT_SECRET = os.environ.get('YANDEX_CLIENT_SECRET', '')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', '')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', '')
YOOKASSA_TEST = os.environ.get('YOOKASSA_TEST', '1') == '1'
# Deliberately independent switches. No paid operations enabled by installing this code.
SALES_ENABLED = os.environ.get('SALES_ENABLED', '0') == '1'
RENEWALS_ENABLED = os.environ.get('RENEWALS_ENABLED', '0') == '1'
CONSENT_VERSION = os.environ.get('CONSENT_VERSION', '')
SIGNING_KEY_PATH = os.environ.get('SIGNING_KEY_PATH', '')
SIGNING_KEY_ID = os.environ.get('SIGNING_KEY_ID', '')
MAX_DEVICES = int(os.environ.get('MAX_DEVICES', '3'))
# Membership is an optional factor AFTER first-party authentication, never Telegram-only login.
# The experiment does not enable desktop blocking or publish a service.
COMMUNITY_EXPERIMENT_ENABLED = os.environ.get('COMMUNITY_EXPERIMENT_ENABLED', '0') == '1'
COMMUNITY_CHANNEL_ID = int(os.environ.get('COMMUNITY_CHANNEL_ID', '0'))
COMMUNITY_CHANNEL_URL = os.environ.get('COMMUNITY_CHANNEL_URL', '')
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_WEBHOOK_SECRET = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')
COMMUNITY_SIGNING_KEY_PATH = os.environ.get('COMMUNITY_SIGNING_KEY_PATH', '')
COMMUNITY_SIGNING_KEY_ID = os.environ.get('COMMUNITY_SIGNING_KEY_ID', '')
if PRODUCTION and COMMUNITY_EXPERIMENT_ENABLED:
    import json
    import re
    try:
        community_approvals = json.loads(Path(os.environ.get('COMMUNITY_APPROVALS_PATH', '')).read_text(encoding='utf-8'))
        if not all(community_approvals.get(k) is True for k in
                   ('authentication_review', 'personal_data_review', 'code_rights', 'operational_checks')):
            raise ValueError()
        if not all((YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, COMMUNITY_CHANNEL_ID < 0,
                    urlsplit(COMMUNITY_CHANNEL_URL).scheme == 'https',
                    urlsplit(COMMUNITY_CHANNEL_URL).netloc == 't.me',
                    re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', TELEGRAM_BOT_USERNAME),
                    re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', TELEGRAM_BOT_TOKEN),
                    re.fullmatch(r'[A-Za-z0-9_-]{32,256}', TELEGRAM_WEBHOOK_SECRET), COMMUNITY_SIGNING_KEY_PATH,
                    COMMUNITY_SIGNING_KEY_ID)):
            raise ValueError()
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        if not isinstance(load_pem_private_key(Path(COMMUNITY_SIGNING_KEY_PATH).read_bytes(), None), Ed25519PrivateKey):
            raise ValueError()
    except (OSError, ValueError, TypeError):
        raise ImproperlyConfigured('Community launch review or configuration is incomplete') from None
if PRODUCTION and SALES_ENABLED:
    import json
    try:
        approvals = json.loads(Path(os.environ.get('LAUNCH_APPROVALS_PATH', '')).read_text(encoding='utf-8'))
        needed = ('code_rights', 'dependency_sources', 'seller_documents', 'payment_lifecycle',
                  'signed_installer', 'commercial_channel')
        if not all(approvals.get(key) is True for key in needed):
            raise ValueError()
        if not all((YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET,
                    CONSENT_VERSION, SIGNING_KEY_PATH, SIGNING_KEY_ID)):
            raise ValueError()
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        if not isinstance(load_pem_private_key(Path(SIGNING_KEY_PATH).read_bytes(), None), Ed25519PrivateKey):
            raise ValueError()
    except (OSError, ValueError, TypeError):
        raise ImproperlyConfigured('Sales launch is not approved or signing/provider configuration is incomplete') from None
