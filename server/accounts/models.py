# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class Identity(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='identities')
    provider = models.CharField(max_length=24)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['provider', 'subject'], name='identity_subject')]


class Device(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='devices')
    installation_id = models.UUIDField()
    name = models.CharField(max_length=80)
    token_family = models.UUIDField(unique=True)
    active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'installation_id'], name='user_installation')]


class Plan(models.Model):
    code = models.SlugField(primary_key=True)
    name = models.CharField(max_length=80)
    amount_kopecks = models.PositiveIntegerField()
    months = models.PositiveSmallIntegerField()
    enabled = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount_kopecks__gt=0), name='positive_price'),
                       models.CheckConstraint(condition=Q(months__in=[1, 12]), name='plan_period')]


class Subscription(models.Model):
    user = models.OneToOneField(User, primary_key=True, on_delete=models.PROTECT)
    plan = models.ForeignKey(Plan, null=True, on_delete=models.PROTECT)
    auto_renew = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=80, blank=True)
    consent_at = models.DateTimeField(null=True)
    revision = models.PositiveIntegerField(default=0)
    # A provider reference, never a card number. Restrict database/backup access.
    payment_method_id = models.CharField(max_length=128, blank=True)
    next_due = models.DateTimeField(null=True)
    anchor_day = models.PositiveSmallIntegerField(default=1)
    amount_kopecks = models.PositiveIntegerField(default=0)
    months = models.PositiveSmallIntegerField(default=1)


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payments')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    amount_kopecks = models.PositiveIntegerField()
    months = models.PositiveSmallIntegerField()
    provider_id = models.CharField(max_length=128, unique=True, null=True)
    status = models.CharField(max_length=24, default='created')
    created_at = models.DateTimeField(auto_now_add=True)
    first_sent_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    confirmation_url = models.URLField(max_length=2000, blank=True)
    request_payload = models.JSONField(default=dict)
    renewal_due = models.DateTimeField(null=True)
    subscription_revision = models.PositiveIntegerField(default=0)
    wants_renewal = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=80, blank=True)
    consent_at = models.DateTimeField(null=True)
    applied_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'renewal_due'], name='one_renewal_per_due'),
                       models.UniqueConstraint(fields=['user'], condition=Q(status__in=[
                           'created', 'sending', 'unknown', 'pending', 'manual_review']), name='one_open_payment')]


class GrantPeriod(models.Model):
    payment = models.OneToOneField(Payment, primary_key=True, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='periods')
    start = models.DateTimeField()
    end = models.DateTimeField()
    revoked = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=models.F('start')), name='positive_period')]


class Refund(models.Model):
    provider_id = models.CharField(max_length=128, primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    amount_kopecks = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class ReceiptTask(models.Model):
    """NPD receipt workflow; no claim that a YooKassa payment is a My Tax receipt."""
    key = models.CharField(max_length=160, primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    status = models.CharField(max_length=24, default='needs_operator')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    receipt_reference = models.CharField(max_length=255, blank=True)
