# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
from django.urls import path
from oauth2_provider.views import AuthorizationView, TokenView, RevokeTokenView
from accounts import api, auth
from community import api as community

urlpatterns = [
    path('auth/login/', auth.login_page), path('auth/yandex/start/', auth.yandex_start),
    path('auth/yandex/callback/', auth.yandex_callback), path('auth/done/', auth.done),
    path('o/authorize/', AuthorizationView.as_view(), name='authorize'),
    path('o/token/', TokenView.as_view(), name='token'),
    path('o/revoke/', RevokeTokenView.as_view(), name='revoke-token'),
    path('api/v1/config', api.configuration), path('api/v1/account', api.account),
    path('api/v1/devices', api.register_device),
    path('api/v1/devices/<uuid:device_id>/revoke', api.revoke_device),
    path('api/v1/license', api.license_view), path('api/v1/checkout', api.create_checkout),
    path('api/v1/subscription/cancel', api.cancel), path('api/v1/logout', api.logout),
    path('hooks/yookassa', api.webhook),
    path('api/v1/community/config', community.configuration),
    path('api/v1/community/pairings', community.pairing_start),
    path('api/v1/community/pairings/<uuid:pairing_id>', community.pairing_status),
    path('api/v1/community/pairings/<uuid:pairing_id>/confirm', community.pairing_confirm),
    path('api/v1/community/permit', community.membership_permit),
    path('api/v1/community/disconnect', community.disconnect),
    path('hooks/telegram', community.webhook),
]
