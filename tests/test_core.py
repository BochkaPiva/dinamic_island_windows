# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from island.app import IslandWindow
from island.audio import Spectrum
from island.media import Snapshot
from island.motion import CloudMotion
from island.storage import Settings
from island.updates import release_info


class DomainTests(unittest.TestCase):
    def test_updates_only_offer_new_stable_releases_from_this_repo(self):
        valid = {"tag_name": "v0.2.0", "html_url": "https://github.com/BochkaPiva/dinamic_island_windows/releases/tag/v0.2.0"}
        self.assertEqual(release_info(valid, current="0.1.4")["version"], "0.2.0")
        for patch in ({"prerelease": True}, {"draft": True}, {"tag_name": "v0.0.9"},
                      {"tag_name": "v0.2.0-rc1"}, {"html_url": "https://example.com/file.exe"}):
            self.assertIsNone(release_info({**valid, **patch}, current="0.1.4"))

    def test_wave_has_a_wake_then_settles(self):
        cloud = CloudMotion()
        for i in range(45):
            cloud.step(1, .1 + .8*i/44, .016)
        self.assertGreater(cloud.center.value-cloud.wake.value, .05)
        self.assertGreater(cloud.spread.value, .1)
        for _ in range(400):
            cloud.step(1, .9, .016)
        self.assertLess(abs(cloud.center.value-cloud.wake.value), .001)
        self.assertEqual(cloud.spread.value, 0)

    def test_fft_bands_stereo_and_silence(self):
        for band, frequency in enumerate((100, 400, 1200, 4000, 10000)):
            analyzer = Spectrum()
            t = np.arange(4096)/48000
            tone = (.5*32767*np.sin(2*np.pi*frequency*t)).astype(np.int16)
            stereo = np.column_stack((tone, -tone)).tobytes()
            levels = analyzer.process(stereo, 2, .2)
            self.assertEqual(int(np.argmax(levels)), band)
            self.assertGreater(levels[band], .4)
            for _ in range(100):
                levels = analyzer.silence(.025)
            self.assertEqual(max(levels), 0)


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.w = IslandWindow(Settings(self.temp.name), services=False)
        self.w._notch_pointer_timer.stop()
        self.w._notch_pointer.enabled = False
        self.w.show()

    def tearDown(self):
        self.w.cleanup()
        self.w.hide()
        self.w.deleteLater()
        QTest.qWait(10)
        self.temp.cleanup()

    def test_first_launch_center_and_fixed_content_during_reversal(self):
        w = self.w
        self.assertEqual((w.width(), w.height()), (180, 38))
        self.assertEqual(w.y(), w.screen().geometry().top())
        self.assertEqual(w.x()+w.width()//2, w.screen().geometry().center().x()+1)
        panel = w.notch_hub.size()
        w._set_island_expanded(True)
        QTest.qWait(80)
        width = w.width()
        w._set_island_expanded(False)
        self.assertEqual(w.width(), width)
        self.assertEqual(w.notch_hub.size(), panel)
        QTest.qWait(800)
        self.assertEqual(w.width(), 180)

    def test_controls_do_not_switch_to_a_different_player(self):
        w = self.w
        w._handle_snapshot(Snapshot(has_session=True, aumid="displayed.player", title="Song", can_seek=True, dur_sec=180))
        w.worker.preferred_source = "another.player"
        w.send_control("next")
        w.send_seek(32)
        self.assertEqual(w.worker.commands.get(), ("displayed.player", "next", None))
        self.assertEqual(w.worker.commands.get(), ("displayed.player", "seek", 32))
        w._handle_snapshot(Snapshot())
        w.send_control("next")
        self.assertTrue(w.worker.commands.empty())
        self.assertFalse(w.notch_hub.seek.isEnabled())

    def test_system_sound_without_metadata_does_not_show_stale_title_or_controls(self):
        w=self.w
        w._handle_snapshot(Snapshot(has_session=True,aumid='telegram',title='Yesterday',can_play=True))
        w._handle_snapshot(Snapshot(sources=('telegram',),source_states=(('telegram','Stopped'),)))
        w._audio_levels((.6,)*5)
        self.assertEqual(w.notch_hub.title.toolTip(),'Звук Windows')
        self.assertEqual(w.notch_hub.artist.toolTip(),'Без данных о треке')
        self.assertFalse(any(button.isEnabled() for button in w.notch_hub.buttons))
        self.assertFalse(w.notch_hub.seek.isEnabled())
        self.assertFalse(w.art_label.isVisible())
        w._last_audio=0;w._audio_levels((0.,)*5)
        self.assertEqual(w.notch_hub.title.toolTip(),'Ничего не играет')

    def test_bezel_does_not_form_detached_corner(self):
        card = self.w.card
        for x in (0, .08, .5, .92, 1):
            for depth in (.35, .75, 1):
                card.set_retreat(depth, x, 1-x, .7)
                path = card.notch_path()
                for px in range(1, card.width(), 2):
                    outside = False
                    for py in range(card.height()*2):
                        inside = path.contains(QPointF(px+.25, py/2+.01))
                        self.assertFalse(outside and inside, (x, depth, px, py))
                        outside = outside or not inside

    def test_notes_files_and_settings_survive_relaunch(self):
        w = self.w
        original = Path(self.temp.name)/"original.txt"
        original.write_text("do not delete", encoding="utf-8")
        w.notch_hub.shelf.add_paths([str(original), str(original)])
        self.assertEqual(w.notch_hub.shelf.count(), 1)
        w.notch_hub.notes.setPlainText("Локальная заметка")
        w.notch_hub.save_notes()
        w.settings.set("source", "test.player")
        self.assertEqual(Settings(self.temp.name).get("source"), "test.player")
        self.assertEqual((Path(self.temp.name)/"notch-notes.txt").read_text(encoding="utf-8"), "Локальная заметка")
        w.notch_hub.shelf.clear()
        w.notch_hub.shelf.persist()
        self.assertTrue(original.exists())

    def test_desktop_restores_overlay_but_respects_fullscreen_and_user_hide(self):
        w = self.w
        with patch("island.app.is_fullscreen", return_value=True) as fullscreen, \
             patch("island.app.desktop_is_foreground", return_value=True), \
             patch("island.app.keep_desktop_visible") as restore:
            w._sync_visibility()
            QTest.qWait(260)
            self.assertFalse(w.isVisible())
            self.assertTrue(w._fs_hidden)
            restore.assert_not_called()
            fullscreen.return_value = False
            w._sync_visibility()
            self.assertTrue(w.isVisible())
            self.assertFalse(w._fs_hidden)
            restore.assert_called_once_with(w)
            restore.reset_mock()
            w._hide_user()
            w._sync_visibility()
            QTest.qWait(260)
            self.assertFalse(w.isVisible())
            restore.assert_not_called()

    def test_peek_exclusion_is_reapplied_on_show_and_native_window_recreation(self):
        w = self.w
        with patch("island.app.exclude_from_peek") as exclude:
            w.hide()
            w.show()
            exclude.assert_called_once_with(w)
            w.hide()
            w.destroy()
            w.show()
            self.assertEqual(exclude.call_count, 2)


if __name__ == "__main__":
    unittest.main()
