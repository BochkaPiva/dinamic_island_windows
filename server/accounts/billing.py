# SPDX-License-Identifier: GPL-3.0-only
"""Durable payment ledger. Network I/O never runs inside a database transaction."""
import calendar
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import User, Plan, Subscription, Payment, GrantPeriod, Refund, ReceiptTask
from .provider import YooKassa, ProviderUnavailable, kopecks, confirmation_url

OPEN = ('created', 'sending', 'unknown', 'pending', 'manual_review')


def add_months(value, months, anchor_day):
    year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
    month += 1
    return value.replace(year=year, month=month, day=min(anchor_day, calendar.monthrange(year, month)[1]))


def active_until(user, now=None):
    """Return only uninterrupted, unrefunded coverage containing now, never a future gap."""
    now = now or timezone.now()
    end = now
    for period in GrantPeriod.objects.filter(user=user, revoked=False, end__gt=now).order_by('start'):
        if period.start > end:
            break
        end = max(end, period.end)
    return end if end > now else None


def locked_subscription(user):
    User.objects.select_for_update().get(pk=user.pk)
    sub, _ = Subscription.objects.get_or_create(user=user)
    return Subscription.objects.select_for_update().get(pk=sub.pk)


def sales_ready():
    return bool(settings.SALES_ENABLED and settings.CONSENT_VERSION and
                settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY)


def _payment(user, plan, sub, consent=False, due=None):
    payment = Payment(user=user, plan=plan, amount_kopecks=sub.amount_kopecks if due else plan.amount_kopecks,
        months=sub.months if due else plan.months, wants_renewal=consent,
        consent_version=settings.CONSENT_VERSION if consent else '', consent_at=timezone.now() if consent else None,
        subscription_revision=sub.revision, renewal_due=due)
    payload = {'amount': {'value': f'{payment.amount_kopecks // 100}.{payment.amount_kopecks % 100:02}', 'currency': 'RUB'},
        'capture': True, 'description': f'Cloud Hub: {payment.months} мес.',
        'metadata': {'cloud_payment_id': str(payment.id)}}
    if due:
        payload['payment_method_id'] = sub.payment_method_id
    else:
        payload['confirmation'] = {'type': 'redirect', 'return_url': settings.PUBLIC_ORIGIN + '/auth/done/'}
        if consent:
            payload['save_payment_method'] = True
    payment.request_payload = payload
    payment.save()
    return payment


@transaction.atomic
def checkout(user, plan_code, consent=False, consent_version=''):
    if not sales_ready():
        raise ValueError('sales_not_configured')
    if consent and (not settings.RENEWALS_ENABLED or consent_version != settings.CONSENT_VERSION):
        raise ValueError('renewal_consent_required')
    sub = locked_subscription(user)
    existing = Payment.objects.filter(user=user, status__in=OPEN).first()
    if existing:
        if existing.plan_id != plan_code or existing.wants_renewal != consent or existing.renewal_due:
            raise ValueError('payment_already_in_progress')
        return existing
    plan = Plan.objects.get(pk=plan_code, enabled=True)
    return _payment(user, plan, sub, consent)


def send_payment(payment_id, provider=None):
    provider = provider or YooKassa()
    now = timezone.now()
    payment_user = Payment.objects.get(pk=payment_id).user
    with transaction.atomic():
        sub = locked_subscription(payment_user)
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status not in OPEN or payment.status == 'manual_review':
            return payment
        if payment.provider_id:
            retrieve_id = payment.provider_id
        else:
            retrieve_id = None
            if payment.lease_until and payment.lease_until > now:
                return payment
            if payment.first_sent_at and payment.first_sent_at < now - timedelta(hours=23):
                # YooKassa only guarantees idempotency for 24 hours. Never risk a new charge.
                payment.status = 'manual_review'
                payment.save(update_fields=['status'])
                return payment
            if not sales_ready():
                raise ValueError('sales_not_configured')
            if payment.renewal_due and (not settings.RENEWALS_ENABLED or not sub.auto_renew or
                    sub.revision != payment.subscription_revision):
                payment.status = 'canceled'
                payment.save(update_fields=['status'])
                return payment
            payment.first_sent_at = payment.first_sent_at or now
            payment.lease_until = now + timedelta(minutes=2)
            payment.status = 'sending'
            payment.save(update_fields=['first_sent_at', 'lease_until', 'status'])
    try:
        result = provider.payment(retrieve_id) if retrieve_id else provider.create(payment)
        return apply_payment(payment.pk, result)
    except ProviderUnavailable:
        Payment.objects.filter(pk=payment_id, status='sending').update(status='unknown', lease_until=None)
        raise


def validate_payment(payment, remote):
    if not isinstance(remote, dict) or remote.get('metadata', {}).get('cloud_payment_id') != str(payment.id):
        raise ValueError('payment_metadata_mismatch')
    identifier = remote.get('id', '')
    YooKassa._identifier(identifier)
    if payment.provider_id and payment.provider_id != identifier:
        raise ValueError('payment_identifier_mismatch')
    if remote.get('recipient', {}).get('account_id') != settings.YOOKASSA_SHOP_ID:
        raise ValueError('payment_recipient_mismatch')
    if type(remote.get('test')) is not bool or remote['test'] != settings.YOOKASSA_TEST:
        raise ValueError('payment_environment_mismatch')
    if (remote.get('amount', {}).get('currency') != 'RUB' or
            kopecks(remote['amount']['value']) != payment.amount_kopecks):
        raise ValueError('payment_amount_mismatch')
    if remote.get('status') not in ('pending', 'waiting_for_capture', 'succeeded', 'canceled'):
        raise ValueError('invalid_payment_status')
    if remote['status'] == 'succeeded' and remote.get('paid') is not True:
        raise ValueError('payment_not_paid')


@transaction.atomic
def apply_payment(payment_id, remote):
    initial = Payment.objects.get(pk=payment_id)
    sub = locked_subscription(initial.user)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    validate_payment(payment, remote)
    if payment.applied_at or payment.status == 'canceled':
        return payment  # Terminal state never moves backwards on a stale notification.
    payment.provider_id = remote['id']
    payment.lease_until = None
    status = remote['status']
    payment.status = 'pending' if status == 'waiting_for_capture' else status
    url = remote.get('confirmation', {}).get('confirmation_url')
    if url:
        payment.confirmation_url = confirmation_url(url)
    if status == 'succeeded':
        now = timezone.now()
        until = active_until(payment.user, now)
        start = until or now
        if not until:
            sub.anchor_day = start.day
        end = add_months(start, payment.months, sub.anchor_day)
        GrantPeriod.objects.create(payment=payment, user=payment.user, start=start, end=end)
        payment.applied_at = now
        method = remote.get('payment_method') or {}
        # A canceled consent cannot be resurrected by a delayed success callback.
        if payment.wants_renewal and sub.revision == payment.subscription_revision:
            sub.auto_renew = bool(method.get('saved') is True and method.get('id'))
            sub.payment_method_id = method.get('id', '') if sub.auto_renew else ''
            sub.consent_version = payment.consent_version
            sub.consent_at = payment.consent_at
        elif not payment.renewal_due and not payment.wants_renewal:
            # A one-off purchase must never silently change an existing recurring contract.
            sub.auto_renew = False
            sub.payment_method_id = ''
            sub.revision += 1
        sub.plan = payment.plan
        sub.amount_kopecks = payment.amount_kopecks
        sub.months = payment.months
        sub.next_due = end
        sub.save()
        ReceiptTask.objects.get_or_create(key='payment:' + str(payment.id),
            defaults={'payment': payment, 'kind': 'income'})
    elif status == 'canceled' and payment.renewal_due:
        sub.auto_renew = False
        sub.revision += 1
        sub.save(update_fields=['auto_renew', 'revision'])
    payment.save()
    return payment


@transaction.atomic
def cancel_renewal(user):
    sub = locked_subscription(user)
    sub.auto_renew = False
    sub.payment_method_id = ''
    sub.revision += 1
    sub.save(update_fields=['auto_renew', 'payment_method_id', 'revision'])
    Payment.objects.filter(user=user, renewal_due__isnull=False, status='created').update(status='canceled')
    return sub


def queue_renewals(now=None):
    if not settings.RENEWALS_ENABLED or not sales_ready():
        return 0
    now = now or timezone.now()
    count = 0
    ids = list(Subscription.objects.filter(auto_renew=True, next_due__lte=now).values_list('user_id', flat=True))
    for identifier in ids:
        with transaction.atomic():
            user = User.objects.get(pk=identifier)
            sub = locked_subscription(user)
            if (not sub.auto_renew or not sub.payment_method_id or not sub.next_due or sub.next_due > now or
                    not sub.plan or not sub.plan.enabled):
                continue
            if Payment.objects.filter(user=user, status__in=OPEN).exists():
                continue
            if Payment.objects.filter(user=user, renewal_due=sub.next_due).exists():
                continue
            _payment(user, sub.plan, sub, due=sub.next_due)
            count += 1
    return count


@transaction.atomic
def apply_refund(remote):
    if remote.get('status') != 'succeeded':
        return
    identifier = remote.get('id', '')
    YooKassa._identifier(identifier)
    initial = Payment.objects.get(provider_id=remote.get('payment_id'), status='succeeded')
    sub = locked_subscription(initial.user)
    payment = Payment.objects.select_for_update().get(pk=initial.pk)
    amount = kopecks(remote.get('amount', {}).get('value'))
    if remote.get('amount', {}).get('currency') != 'RUB':
        raise ValueError('refund_currency_mismatch')
    old = Refund.objects.filter(pk=identifier).first()
    if old:
        if old.payment_id != payment.id or old.amount_kopecks != amount:
            raise ValueError('refund_changed')
        return
    total = (payment.refunds.aggregate(total=Sum('amount_kopecks'))['total'] or 0) + amount
    if total > payment.amount_kopecks:
        raise ValueError('refund_exceeds_payment')
    Refund.objects.create(provider_id=identifier, payment=payment, amount_kopecks=amount)
    ReceiptTask.objects.create(key='refund:' + identifier, payment=payment, kind='refund')
    if total == payment.amount_kopecks:
        GrantPeriod.objects.filter(payment=payment).update(revoked=True)
        sub.auto_renew = False
        sub.payment_method_id = ''
        sub.revision += 1
        sub.next_due = active_until(payment.user)
        sub.save()


def reconcile_refunds(provider=None, max_pages=20):
    """Bounded full scan for a pilot shop; a truncated scan fails visibly for the operator."""
    provider = provider or YooKassa()
    cursor = None
    seen = set()
    count = 0
    for _ in range(max_pages):
        page = provider.refunds(cursor)
        for item in page['items']:
            if item.get('status') == 'succeeded' and Payment.objects.filter(
                    provider_id=item.get('payment_id'), status='succeeded').exists():
                apply_refund(item)
                count += 1
        cursor = page.get('next_cursor')
        if not cursor:
            return count
        if not isinstance(cursor, str) or cursor in seen or len(cursor) > 512:
            raise ValueError('invalid_refund_cursor')
        seen.add(cursor)
    raise ValueError('refund_scan_incomplete')
