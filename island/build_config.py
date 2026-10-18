# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
"""Build-time distribution policy. Never read commercial mode or keys from settings."""
PRODUCT_ID = "cloud-hub"
DISTRIBUTION = "preview"  # preview preserves the existing feature set; never sell it.
UPDATE_CHANNEL_URL = ""  # Commercial releases must use their own signed channel.
PUBLIC_RELEASE_REPOSITORY = ""  # Separate binary release repository, not legacy GPL latest.
LICENSE_API_URL = ""
ACCOUNT_API_ORIGIN = ""  # Our HTTPS account service origin; no provider secret in a desktop build.
LICENSE_PUBLIC_KEYS = {}  # key id -> base64 Ed25519 public key; private keys never ship.
UPDATE_PUBLIC_KEYS = {}
# Open-source transition: opt-in infrastructure only, no public gate or network requests.
COMMUNITY_API_ORIGIN = ''
COMMUNITY_CHANNEL_ID = 0
COMMUNITY_PUBLIC_KEYS = {}
COMMUNITY_ENFORCEMENT_ENABLED = False
