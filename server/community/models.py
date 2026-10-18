# SPDX-License-Identifier: GPL-3.0-or-later
import uuid
from django.conf import settings
from django.db import models


class TelegramLink(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    telegram_id = models.PositiveBigIntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Pairing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    telegram_id = models.PositiveBigIntegerField(null=True)
    consumed_at = models.DateTimeField(null=True)


class Membership(models.Model):
    link = models.ForeignKey(TelegramLink, on_delete=models.CASCADE)
    channel_id = models.BigIntegerField()
    state = models.CharField(max_length=12, default='unknown')
    observed_at = models.DateTimeField(null=True)
    verified_at = models.DateTimeField(null=True)
    last_member_at = models.DateTimeField(null=True)
    missing_since = models.DateTimeField(null=True)
    revision = models.PositiveBigIntegerField(default=0)
    last_event_at = models.DateTimeField(null=True)
    last_event_id = models.BigIntegerField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['link', 'channel_id'], name='community_membership')]
