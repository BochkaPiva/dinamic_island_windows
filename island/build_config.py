# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""Build-time distribution policy. Never read commercial mode or keys from settings."""
PRODUCT_ID = "cloud-hub"
DISTRIBUTION = "preview"  # preview preserves the existing feature set; never sell it.
UPDATE_CHANNEL_URL = ""  # Commercial releases must use their own signed channel.
PUBLIC_RELEASE_REPOSITORY = ""  # Separate binary release repository, not legacy GPL latest.
LICENSE_API_URL = ""
LICENSE_PUBLIC_KEYS = {}  # key id -> base64 Ed25519 public key; private keys never ship.
UPDATE_PUBLIC_KEYS = {}
