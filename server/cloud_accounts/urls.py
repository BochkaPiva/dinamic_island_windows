# SPDX-License-Identifier: GPL-3.0-only
from django.urls import path
from community import direct as community

urlpatterns = [
    path('api/v2/community/health', community.health),
    path('api/v2/community/config', community.configuration),
    path('api/v2/community/pairings', community.pairing_start),
    path('api/v2/community/pairings/<uuid:pairing_id>/status', community.pairing_status),
    path('api/v2/community/pairings/<uuid:pairing_id>/confirm', community.pairing_confirm),
    path('api/v2/community/permit', community.membership_permit),
    path('api/v2/community/disconnect', community.disconnect),
    path('hooks/telegram', community.webhook),
]
