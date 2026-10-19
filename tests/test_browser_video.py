# SPDX-License-Identifier: GPL-3.0-only
import unittest
from unittest.mock import patch
from island.browser_video import pip_candidates, browser_for
from island.window_layouts import Window
from island.media import Snapshot


class BrowserVideoTests(unittest.TestCase):
    def test_only_known_pip_titles_from_real_browser_processes_are_candidates(self):
        windows=[Window(1,10,'Picture in picture'),Window(2,11,'Picture in picture'),
            Window(3,10,'YouTube video - Picture in picture tutorial'),Window(4,10,'Картинка в картинке')]
        names={10:'opera.exe',11:'notepad.exe'}
        self.assertEqual([w.hwnd for w in pip_candidates(windows,names.get)],[1,4])

    def test_ambiguous_or_unrelated_browser_is_not_activated(self):
        windows=[Window(1,10,'YouTube — Opera'),Window(2,10,'Other — Opera')]
        with patch('island.browser_video.list_windows',return_value=windows),patch('island.browser_video.process_name',return_value='opera.exe'):
            self.assertIsNone(browser_for(Snapshot(aumid='Opera GX',title='Unknown')))
            self.assertEqual(browser_for(Snapshot(aumid='Opera GX',title='YouTube')).hwnd,1)
            self.assertIsNone(browser_for(Snapshot(aumid='Telegram',title='Voice message')))
