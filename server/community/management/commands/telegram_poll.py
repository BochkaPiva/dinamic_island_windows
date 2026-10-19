# SPDX-License-Identifier: GPL-3.0-or-later
"""Local/single-host alternative to webhook. Never run both receivers at once."""
import json
import os
from pathlib import Path
import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from community.provider import Telegram, TelegramUnavailable
from community.direct import dispatch


class Command(BaseCommand):
    def handle(self, *args, **options):
        if not settings.COMMUNITY_EXPERIMENT_ENABLED:
            raise CommandError('Community service is disabled')
        bot=Telegram()
        info=bot.call('getWebhookInfo')
        if info.get('url'):
            raise CommandError('A webhook is already configured. Polling was not started.')
        path=Path(os.environ.get('TELEGRAM_POLL_STATE',str(settings.BASE_DIR/'telegram-poll-state.json')))
        offset=None
        try:
            value=json.loads(path.read_text())
            if time.time()-value['saved_at']<86400:
                offset=value['offset']
        except (OSError,ValueError,KeyError,TypeError):
            pass
        self.stdout.write('Telegram receiver started. Message bodies and tokens are not logged.')
        while True:
            try:
                params={'timeout':25,'allowed_updates':['message','callback_query','chat_member']}
                if offset is not None:params['offset']=offset
                updates=bot.call('getUpdates',**params)
                if not isinstance(updates,list):raise TelegramUnavailable('invalid_updates')
                for update in updates:
                    if not isinstance(update,dict) or type(update.get('update_id')) is not int:
                        continue
                    dispatch(update,bot)
                    offset=update['update_id']+1
                    path.parent.mkdir(parents=True,exist_ok=True)
                    temporary=path.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'offset':offset,'saved_at':time.time()}))
                    temporary.replace(path)
            except KeyboardInterrupt:
                return
            except (TelegramUnavailable,OSError):
                time.sleep(5)
            except (ValueError,KeyError,TypeError,AttributeError):
                # Reject malformed events without printing their contents; don't poison the queue.
                if 'update' in locals() and type(update.get('update_id')) is int:
                    offset=update['update_id']+1
