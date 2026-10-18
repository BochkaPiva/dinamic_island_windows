# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
from django.urls import path
from oauth2_provider.views import AuthorizationView, TokenView, RevokeTokenView
from accounts import api, auth

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
]
