# SPDX-License-Identifier: GPL-3.0-only
"""Build-time distribution policy. Never read commercial mode or keys from settings."""
PRODUCT_ID = "cloud-hub"
DISTRIBUTION = "community"  # Free base; optional membership unlocks additional groups.
UPDATE_CHANNEL_URL = ""  # Commercial releases must use their own signed channel.
PUBLIC_RELEASE_REPOSITORY = ""  # Separate binary release repository, not legacy GPL latest.
LICENSE_API_URL = ""
ACCOUNT_API_ORIGIN = ""  # Our HTTPS account service origin; no provider secret in a desktop build.
LICENSE_PUBLIC_KEYS = {}  # key id -> base64 Ed25519 public key; private keys never ship.
UPDATE_PUBLIC_KEYS = {}
# Optional Telegram membership service; free tools remain usable without connecting.
COMMUNITY_API_ORIGIN = 'https://nelviro-community.vercel.app'
COMMUNITY_CHANNEL_ID = -1004359060579
COMMUNITY_CHANNEL_URL = 'https://t.me/Nelviro'
COMMUNITY_BOT_USERNAME = 'nelviro_bot'
COMMUNITY_PUBLIC_KEYS = {'nelviro-2026-01': 'lIMEX23SRTMXK5LsfqE3XCa1peUvThBeEzQZwT9h2nI='}
COMMUNITY_ENFORCEMENT_ENABLED = False
