# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import json
import uuid
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from oauth2_provider.models import RefreshToken
from .auth import account_api, error
from .billing import active_until, checkout, send_payment, cancel_renewal, apply_payment, apply_refund, sales_ready
from .models import User, Device, Payment, Plan, Subscription
from .licensing import license_for
from .provider import YooKassa, ProviderUnavailable


def body(request):
    if request.content_type != 'application/json' or len(request.body) > 16384:
        raise ValueError('invalid_body')
    result = json.loads(request.body)
    if not isinstance(result, dict):
        raise ValueError('invalid_body')
    return result


@require_GET
def configuration(request):
    return JsonResponse({'schema': 1, 'login_providers': ['yandex'] if settings.YANDEX_CLIENT_ID and
        settings.YANDEX_CLIENT_SECRET else [], 'sales_enabled': sales_ready(),
        'renewals_enabled': settings.RENEWALS_ENABLED and sales_ready(),
        'consent_version': settings.CONSENT_VERSION, 'max_devices': settings.MAX_DEVICES})


@account_api()
@require_GET
def account(request):
    user = request.account
    until = active_until(user)
    sub = Subscription.objects.filter(user=user).first()
    return JsonResponse({'id': str(user.id), 'email': user.email,
        'providers': list(user.identities.values_list('provider', flat=True)),
        'subscription': {'edition': 'pro' if until else 'free',
                         'paid_until': until.isoformat() if until else None,
                         'auto_renew': bool(sub and sub.auto_renew),
                         'next_charge': sub.next_due.isoformat() if sub and sub.auto_renew and sub.next_due else None},
        'devices': [{'id': str(d.id), 'name': d.name, 'active': d.active,
                     'current': d.token_family == request.token_family, 'last_seen': d.last_seen.isoformat()}
                    for d in user.devices.order_by('-last_seen')],
        'payments': [{'id': str(p.id), 'status': p.status, 'amount_kopecks': p.amount_kopecks,
                      'currency': 'RUB', 'created_at': p.created_at.isoformat(),
                      'refunded_kopecks': sum(r.amount_kopecks for r in p.refunds.all())}
                     for p in user.payments.prefetch_related('refunds').order_by('-created_at')[:30]],
        'plans': list(Plan.objects.filter(enabled=True).values('code', 'name', 'amount_kopecks', 'months'))
                 if sales_ready() else []})


@account_api()
@require_POST
def register_device(request):
    try:
        data = body(request)
        identifier = uuid.UUID(data['installation_id'])
        name = data['name']
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError('invalid_device_name')
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.account.pk)
            device = Device.objects.filter(user=request.account, installation_id=identifier).first()
            bound = Device.objects.filter(token_family=request.token_family).first()
            if bound and (not device or bound.pk != device.pk):
                return error('session_already_bound', 409)
            if (not device or not device.active) and Device.objects.filter(user=request.account, active=True).count() >= settings.MAX_DEVICES:
                return error('device_limit', 409)
            if device:
                if device.token_family != request.token_family:
                    RefreshToken.revoke_family(device.token_family)
                device.token_family = request.token_family
                device.name = name.strip()
                device.active = True
                device.save()
            else:
                device = Device.objects.create(user=request.account, installation_id=identifier,
                    name=name.strip(), token_family=request.token_family)
        return JsonResponse({'id': str(device.id)})
    except (ValueError, KeyError, TypeError):
        return error('invalid_device')


@account_api()
@require_POST
def revoke_device(request, device_id):
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.account.pk)
        device = Device.objects.filter(pk=device_id, user=request.account).first()
        if not device:
            return error('device_not_found', 404)
        device.active = False
        device.save(update_fields=['active'])
        RefreshToken.revoke_family(device.token_family)
    return JsonResponse({'revoked': True})


@account_api('license')
@require_POST
def license_view(request):
    device = Device.objects.filter(user=request.account, token_family=request.token_family, active=True).first()
    if not device:
        return error('register_device_first', 409)
    Device.objects.filter(pk=device.pk).update(last_seen=timezone.now())
    try:
        return JsonResponse({'license': license_for(device)})
    except (ValueError, OSError):
        return error('license_temporarily_unavailable', 503)


@account_api()
@require_POST
def create_checkout(request):
    try:
        data = body(request)
        consent = data.get('auto_renew', False)
        if type(consent) is not bool or not isinstance(data.get('plan'), str):
            raise ValueError('invalid_checkout')
        plan = Plan.objects.get(pk=data['plan'], enabled=True)
        if (type(data.get('expected_amount_kopecks')) is not int or type(data.get('expected_months')) is not int or
                data['expected_amount_kopecks'] != plan.amount_kopecks or data['expected_months'] != plan.months):
            raise ValueError('price_changed')
        payment = checkout(request.account, data['plan'], consent, data.get('consent_version', ''))
        payment = send_payment(payment.id)
        return JsonResponse({'id': str(payment.id), 'status': payment.status,
                             'confirmation_url': payment.confirmation_url or None})
    except Plan.DoesNotExist:
        return error('plan_not_found', 404)
    except (ValueError, KeyError, TypeError):
        return error('checkout_not_available', 409)
    except ProviderUnavailable:
        return error('payment_pending_reconciliation', 503)


@account_api()
@require_POST
def cancel(request):
    cancel_renewal(request.account)
    return JsonResponse({'auto_renew': False})


@account_api()
@require_POST
def logout(request):
    RefreshToken.revoke_family(request.token_family)
    Device.objects.filter(user=request.account, token_family=request.token_family).update(active=False)
    return JsonResponse({'logged_out': True})


@csrf_exempt
@require_POST
def webhook(request):
    try:
        data = body(request)
        event, obj = data.get('event'), data.get('object')
        if not isinstance(obj, dict) or not isinstance(obj.get('id'), str):
            return error('invalid_event')
        provider = YooKassa()
        if event in ('payment.succeeded', 'payment.canceled', 'payment.waiting_for_capture'):
            # Lookup metadata only selects a local record. Authority comes from the canonical GET.
            local = Payment.objects.filter(provider_id=obj['id']).first()
            if not local:
                metadata = obj.get('metadata') or {}
                local = Payment.objects.filter(pk=uuid.UUID(metadata['cloud_payment_id'])).first()
            if local:
                apply_payment(local.id, provider.payment(obj['id']))
        elif event == 'refund.succeeded':
            apply_refund(provider.refund(obj['id']))
        return JsonResponse({'received': True})
    except ProviderUnavailable:
        return error('retry_later', 503)  # Provider retries. Scheduled reconciliation also covers missed events.
    except (ValueError, KeyError, TypeError, AttributeError, Payment.DoesNotExist):
        return error('invalid_event')
