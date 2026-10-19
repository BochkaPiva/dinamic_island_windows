# SPDX-License-Identifier: GPL-3.0-only
from django.core.management.base import BaseCommand
from oauth2_provider.models import Application


class Command(BaseCommand):
    help = 'Register the first-party public desktop client. No secret is shipped to the application.'

    def handle(self, **options):
        Application.objects.update_or_create(client_id='cloud-hub-desktop', defaults={
            'name': 'Cloud Hub Desktop', 'client_type': Application.CLIENT_PUBLIC,
            'authorization_grant_type': Application.GRANT_AUTHORIZATION_CODE,
            'redirect_uris': 'http://127.0.0.1/callback', 'skip_authorization': True})
        self.stdout.write('Desktop public client registered (loopback + required S256 PKCE).')
