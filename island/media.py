# SPDX-License-Identifier: GPL-3.0-only
"""Independent Windows SMTC adapter. Commands always target the displayed source."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import queue
import threading
import time
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class Snapshot:
    title: str = ""
    artist: str = ""
    status: str = "Stopped"
    has_session: bool = False
    aumid: str = ""
    thumb: bytes = b""
    pos_sec: float = 0
    dur_sec: float = 0
    start_sec: float = 0
    sources: tuple = ()
    can_play: bool = False
    can_pause: bool = False
    can_prev: bool = False
    can_next: bool = False
    can_seek: bool = False


class MediaWorker(QThread):
    snapshot_updated = pyqtSignal(object)
    failure = pyqtSignal(str)

    def __init__(self, source="", parent=None):
        super().__init__(parent)
        self.preferred_source = source
        self.stopped = threading.Event()
        self.commands = queue.SimpleQueue()
        self._cover_key = None
        self._cover = b""

    def command(self, source, action, value=None):
        self.commands.put((source, action, value))

    def stop(self):
        self.stopped.set()

    def run(self):
        try:
            asyncio.run(self._run())
        except Exception as error:
            self.failure.emit(str(error))

    async def _run(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
        from winrt.windows.storage.streams import DataReader
        while not self.stopped.is_set():
            try:
                manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                while not self.stopped.is_set():
                    sessions = {s.source_app_user_model_id: s for s in manager.get_sessions()}
                    while not self.commands.empty():
                        source, action, value = self.commands.get()
                        session = sessions.get(source)
                        if session is None:
                            continue
                        try:
                            if action == "seek":
                                await session.try_change_playback_position_async(round(max(0, value)*10_000_000))
                            else:
                                method = {"play_pause": "try_toggle_play_pause_async",
                                          "previous": "try_skip_previous_async", "next": "try_skip_next_async"}.get(action)
                                if method:
                                    await getattr(session, method)()
                        except Exception:
                            pass
                    session = sessions.get(self.preferred_source) if self.preferred_source else manager.get_current_session()
                    if session is None and not self.preferred_source and sessions:
                        session = next(iter(sessions.values()))
                    snap = Snapshot(sources=tuple(sessions))
                    if session is not None:
                        props = await session.try_get_media_properties_async()
                        info = session.get_playback_info()
                        timeline = session.get_timeline_properties()
                        playing = info.playback_status == Status.PLAYING
                        start = timeline.start_time.total_seconds()
                        duration = max(0, (timeline.end_time-timeline.start_time).total_seconds())
                        position = max(0, timeline.position.total_seconds()-start)
                        if playing:
                            elapsed = (datetime.now(timezone.utc)-timeline.last_updated_time).total_seconds()
                            position += max(0, elapsed)
                        controls = info.controls
                        key = (session.source_app_user_model_id, props.title, props.artist)
                        # Retry missing art: some players publish metadata before the image.
                        if key != self._cover_key or not self._cover:
                            self._cover_key, self._cover = key, b""
                            if props.thumbnail:
                                try:
                                    stream = await props.thumbnail.open_read_async()
                                    try:
                                        if stream.size <= 8*1024*1024:
                                            reader = DataReader(stream)
                                            try:
                                                count = await reader.load_async(stream.size)
                                                data = bytearray(count)
                                                reader.read_bytes(data)
                                                self._cover = bytes(data)
                                            finally:
                                                reader.detach_stream()
                                                reader.close()
                                    finally:
                                        stream.close()
                                except Exception:
                                    pass
                        snap = Snapshot(title=props.title or "", artist=props.artist or "",
                                        status="Playing" if playing else "Paused", has_session=True,
                                        aumid=session.source_app_user_model_id, thumb=self._cover,
                                        pos_sec=min(position, duration) if duration else 0,
                                        dur_sec=duration, start_sec=start, sources=tuple(sessions),
                                        can_play=controls.is_play_enabled, can_pause=controls.is_pause_enabled,
                                        can_prev=controls.is_previous_enabled, can_next=controls.is_next_enabled,
                                        can_seek=controls.is_playback_position_enabled)
                    self.snapshot_updated.emit(snap)
                    await asyncio.sleep(.28)
            except Exception as error:
                self.failure.emit(str(error))
                for _ in range(20):
                    if self.stopped.is_set():
                        return
                    await asyncio.sleep(.1)
