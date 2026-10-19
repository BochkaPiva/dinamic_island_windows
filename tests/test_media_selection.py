# SPDX-License-Identifier: GPL-3.0-only
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from island.media import choose_source, playback_status, session_map, MediaWorker


class Session:
    def __init__(self, source, status):
        self.source_app_user_model_id=source;self.status=status
    def get_playback_info(self):
        controls=NS(is_play_enabled=True,is_pause_enabled=True,is_previous_enabled=False,
            is_next_enabled=False,is_playback_position_enabled=False)
        return NS(playback_status=self.status,controls=controls)
    def get_timeline_properties(self):
        return NS(start_time=timedelta(),end_time=timedelta(seconds=60),position=timedelta(),
            last_updated_time=datetime.now(timezone.utc))
    async def try_get_media_properties_async(self):
        return NS(title=self.source_app_user_model_id,artist='',thumbnail=None)


class MediaSelectionTests(unittest.TestCase):
    def test_playing_browser_outranks_stopped_or_paused_current_telegram(self):
        for state in ('Stopped','Paused'):
            self.assertEqual(choose_source({'telegram':state,'browser':'Playing'},'telegram',previous='telegram'),'browser')

    def test_stopped_closed_and_yesterdays_paused_session_do_not_display_old_metadata(self):
        self.assertEqual(playback_status(3),'Stopped')
        self.assertEqual(playback_status(0),'Stopped')
        self.assertEqual(choose_source({'telegram':'Stopped'},'telegram'),'')
        self.assertEqual(choose_source({'telegram':'Paused'},'telegram',updated={'telegram':1000},now=90000),'')
        self.assertEqual(choose_source({'browser':'Paused'},'browser',updated={'browser':89990},now=90000),'browser')

    def test_explicit_choice_is_preserved_but_stopped_is_not_paused(self):
        self.assertEqual(choose_source({'music':'Paused','browser':'Playing'},preferred='music'),'music')
        self.assertEqual(choose_source({'music':'Stopped','browser':'Playing'},preferred='music'),'')

    def test_last_stopped_browser_tab_does_not_overwrite_playing_tab(self):
        first=Session('browser',4);second=Session('browser',3)
        self.assertIs(session_map([first,second])['browser'],first)
        self.assertIs(session_map([second,first])['browser'],first)


class WorkerSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_polling_path_switches_to_playing_source_then_clears_stopped(self):
        worker=MediaWorker();snapshots=[];telegram=Session('telegram',3);browser=Session('browser',4)
        class Manager:
            polls=0
            def get_sessions(self):
                self.polls+=1
                if self.polls==2:browser.status=3
                if self.polls>2:worker.stop()
                return [telegram,browser]
            def get_current_session(self):return telegram
        manager=Manager()
        class Provider:
            @staticmethod
            async def request_async():return manager
        worker.snapshot_updated.connect(snapshots.append)
        with patch('winrt.windows.media.control.GlobalSystemMediaTransportControlsSessionManager',Provider),patch('island.media.asyncio.sleep',new=AsyncMock()):
            await worker._run()
        self.assertEqual(snapshots[0].aumid,'browser')
        self.assertEqual(snapshots[0].status,'Playing')
        self.assertFalse(snapshots[-1].has_session)
        self.assertEqual(snapshots[-1].title,'')
        self.assertEqual(snapshots[-1].thumb,b'')

    async def test_metadata_failure_clears_display_and_disables_stale_control_target(self):
        worker=MediaWorker();snapshots=[]
        broken=Session('browser',4)
        async def fail():worker.stop();raise OSError('fixture failure')
        broken.try_get_media_properties_async=fail
        manager=NS(get_sessions=lambda:[broken],get_current_session=lambda:broken)
        class Provider:
            @staticmethod
            async def request_async():return manager
        worker.snapshot_updated.connect(snapshots.append)
        worker._cover=b'old';worker._displayed_session=broken;worker._displayed_source='browser'
        with patch('winrt.windows.media.control.GlobalSystemMediaTransportControlsSessionManager',Provider):
            await worker._run()
        self.assertFalse(snapshots[-1].has_session)
        self.assertEqual(worker._cover,b'')
        self.assertIsNone(worker._displayed_session)
