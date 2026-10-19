# SPDX-License-Identifier: GPL-3.0-only
from django.core.management.base import BaseCommand
from accounts.billing import queue_renewals, send_payment, OPEN
from accounts.models import Payment, ReceiptTask
from accounts.provider import ProviderUnavailable


class Command(BaseCommand):
    help = 'One bounded worker tick: renewals, pending payment reconciliation, receipt backlog.'

    def handle(self, **options):
        queued = queue_renewals()
        pending = Payment.objects.filter(status__in=OPEN).exclude(status='manual_review').order_by('created_at')[:100]
        failed = 0
        for payment in pending:
            try:
                send_payment(payment.id)
            except (ProviderUnavailable, ValueError):
                failed += 1
        backlog = ReceiptTask.objects.filter(status='needs_operator').count()
        self.stdout.write(f'queued={queued} retry_needed={failed} receipt_backlog={backlog}')
