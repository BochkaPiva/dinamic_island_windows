# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import ReceiptTask


class Command(BaseCommand):
    help = 'List NPD receipt tasks or record a receipt already issued and sent by the seller.'

    def add_arguments(self, parser):
        parser.add_argument('--complete')
        parser.add_argument('--reference')

    def handle(self, **options):
        if options['complete']:
            reference = options.get('reference', '')
            if not reference or len(reference) > 255:
                raise CommandError('Provide a reference for the real My Tax receipt already issued and delivered.')
            with transaction.atomic():
                task = ReceiptTask.objects.select_for_update().filter(pk=options['complete']).first()
                if not task:
                    raise CommandError('Receipt task not found')
                task.status = 'completed'
                task.completed_at = timezone.now()
                task.receipt_reference = reference
                task.save()
            self.stdout.write('Recorded. This command does not issue or send a tax receipt.')
        else:
            for task in ReceiptTask.objects.filter(status='needs_operator').order_by('created_at')[:100]:
                self.stdout.write(f'{task.key} {task.kind} account={task.payment.user_id} created={task.created_at.isoformat()}')
