# SPDX-License-Identifier: GPL-3.0-only
import base64
import json
from datetime import timedelta
from pathlib import Path
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.utils import timezone
from .billing import active_until


FEATURES = ['island.overview', 'search.basic', 'notes.local', 'timer.basic', 'desktop.groups',
    'island.focus', 'island.notes', 'island.mirror', 'island.video', 'island.pin',
    'files.bridge', 'desktop.widgets', 'workspaces.scenes']


def license_for(device, now=None):
    now = now or timezone.now()
    until = active_until(device.user, now)
    if not device.active or not until:
        return None
    if not settings.SIGNING_KEY_PATH or not settings.SIGNING_KEY_ID:
        raise ValueError('signing_not_configured')
    key = load_pem_private_key(Path(settings.SIGNING_KEY_PATH).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('invalid_signing_key')
    payload = {'schema': 1, 'product': 'cloud-hub', 'installation_id': str(device.installation_id),
        'edition': 'pro', 'issued_at': int(now.timestamp()), 'not_before': int(now.timestamp()),
        'offline_until': int(min(now + timedelta(days=7), until).timestamp()),
        'paid_until': int(until.timestamp()), 'features': FEATURES,
        'limits': {'desktop.groups.active': None, 'desktop.widgets.active': None}}
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    return {'key_id': settings.SIGNING_KEY_ID, 'payload': base64.b64encode(raw).decode(),
        'signature': base64.b64encode(key.sign(b'cloud-hub/license/v1\0' + raw)).decode()}
