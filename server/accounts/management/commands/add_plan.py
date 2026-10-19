# SPDX-License-Identifier: GPL-3.0-only
from django.core.management.base import BaseCommand, CommandError
from accounts.models import Plan


class Command(BaseCommand):
    help = 'Create a new disabled plan. Existing plan prices are not edited by this command.'

    def add_arguments(self, parser):
        parser.add_argument('code')
        parser.add_argument('--name', required=True)
        parser.add_argument('--kopecks', required=True, type=int)
        parser.add_argument('--months', required=True, choices=[1, 12], type=int)

    def handle(self, **options):
        plan = Plan(code=options['code'], name=options['name'], amount_kopecks=options['kopecks'], months=options['months'])
        try:
            plan.full_clean()
            plan.save(force_insert=True)
        except Exception:
            raise CommandError('Plan not created: check the code, price, name, and existing records.') from None
        self.stdout.write('Disabled plan created. Enabling it is a separate sales-launch operation.')
