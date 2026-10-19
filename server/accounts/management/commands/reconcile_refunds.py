# SPDX-License-Identifier: GPL-3.0-only
from django.core.management.base import BaseCommand, CommandError
from accounts.billing import reconcile_refunds
from accounts.provider import ProviderUnavailable


class Command(BaseCommand):
    help = 'Reconcile refunds from provider API, including lost webhooks. Read-only provider operation.'

    def add_arguments(self, parser):
        parser.add_argument('--max-pages', type=int, default=20)

    def handle(self, **options):
        pages = options['max_pages']
        if not 1 <= pages <= 1000:
            raise CommandError('max-pages must be between 1 and 1000')
        try:
            self.stdout.write(f'processed={reconcile_refunds(max_pages=pages)}')
        except (ProviderUnavailable, ValueError):
            raise CommandError('Refund reconciliation incomplete; inspect provider availability and scan capacity.') from None
