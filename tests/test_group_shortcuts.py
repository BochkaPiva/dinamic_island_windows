# SPDX-License-Identifier: GPL-3.0-only
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import Qt,QPoint,QPointF
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QListWidget
from island.desktop_groups import GroupStore
from island.shortcut_library import ShortcutLibrary
from island.scrolling import SmoothScroll


class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.desktop=self.root/'Desktop'
        self.desktop.mkdir()
        self.store=GroupStore(self.root/'data',desktop_roots=[self.desktop])
        self.group=self.store.groups[0]

    def tearDown(self): self.temp.cleanup()

    def shortcut(self,name='Game.url'):
        path=self.desktop/name
        path.write_bytes(b'[InternetShortcut]\r\nURL=steam://rungameid/123\r\n')
        return path

    def test_desktop_shortcut_is_owned_before_original_is_collected_and_survives_reload(self):
        original=self.shortcut()
        content=original.read_bytes()
        self.assertTrue(self.store.add_paths(self.group,[str(original)]))
        owned=Path(self.group['items'][0])
        self.assertTrue(self.store.library.owns(owned))
        self.assertEqual(owned.read_bytes(),content)
        self.assertFalse(original.exists())
        reloaded=GroupStore(self.root/'data',desktop_roots=[self.desktop])
        self.assertEqual(reloaded.find(self.group['id'])['items'],[str(owned)])
        self.assertEqual(owned.read_bytes(),content)
        self.store.remove(self.group['id'])
        self.assertEqual(owned.read_bytes(),content)

    def test_failed_group_commit_keeps_original_and_previous_group(self):
        original=self.shortcut()
        with patch.object(self.store,'save',return_value=False):
            self.assertFalse(self.store.add_paths(self.group,[str(original)]))
        self.assertTrue(original.exists())
        self.assertEqual(self.group['items'],[])

    def test_failed_library_commit_never_removes_source(self):
        original=self.shortcut()
        with patch.object(self.store.library,'save',side_effect=OSError('full')):
            self.assertFalse(self.store.add_paths(self.group,[str(original)]))
        self.assertTrue(original.exists())
        self.assertEqual(self.group['items'],[])

    def test_opt_out_keeps_desktop_copy_but_still_owns_shortcut(self):
        self.store.collect_desktop=False
        original=self.shortcut()
        self.store.add_paths(self.group,[str(original)])
        self.assertTrue(original.exists())
        original.unlink()
        self.assertTrue(Path(self.group['items'][0]).is_file())

    def test_ordinary_files_and_non_desktop_shortcuts_are_not_removed(self):
        document=self.desktop/'work.txt'
        document.write_text('document')
        external=self.root/'Menu.lnk'
        external.write_bytes(b'shortcut fixture')
        self.store.add_paths(self.group,[str(document),str(external)])
        self.assertEqual(self.group['items'][0],str(document))
        self.assertTrue(document.exists() and external.exists())
        self.assertNotEqual(self.group['items'][1],str(external))

    def test_reimport_is_deduplicated_and_changed_shortcut_does_not_overwrite_old(self):
        self.store.collect_desktop=False
        original=self.shortcut()
        self.store.add_paths(self.group,[str(original),str(original)])
        self.store.add_paths(self.group,[str(original)])
        self.assertEqual(len(self.group['items']),1)
        first=Path(self.group['items'][0])
        content=first.read_bytes()
        original.write_text('updated shortcut')
        self.store.add_paths(self.group,[str(original)])
        self.assertEqual(len(self.group['items']),2)
        self.assertEqual(first.read_bytes(),content)

    def test_legacy_migration_is_backed_up_and_collects_only_after_commit(self):
        original=self.shortcut()
        self.store.set_paths(self.group['id'],[str(original)])
        migrated=GroupStore(self.root/'data',desktop_roots=[self.desktop])
        self.assertTrue(migrated.path.with_suffix('.before-shortcuts.json').exists())
        self.assertFalse(original.exists())
        self.assertTrue(Path(migrated.find(self.group['id'])['items'][0]).exists())

    def test_collect_rechecks_both_source_and_durable_copy_before_unlink(self):
        original=self.shortcut()
        captured=self.store.library.capture(original)
        original.write_text('changed since copy')
        with self.assertRaises(OSError): self.store.library.collect(captured)
        self.assertEqual(original.read_text(),'changed since copy')

    def test_restore_keeps_library_and_does_not_overwrite_a_different_desktop_file(self):
        original=self.shortcut()
        captured=self.store.library.capture(original)
        self.store.library.collect(captured)
        self.assertEqual(self.store.library.restore(captured),original)
        self.assertEqual(original.read_bytes(),Path(captured).read_bytes())
        original.write_text('different')
        with self.assertRaises(OSError): self.store.library.restore(captured)
        self.assertEqual(original.read_text(),'different')

    def test_failed_upgrade_commit_keeps_legacy_shortcut_and_retries_safely(self):
        original=self.shortcut()
        self.store.set_paths(self.group['id'],[str(original)])
        with patch.object(GroupStore,'save',return_value=False):
            failed=GroupStore(self.root/'data',desktop_roots=[self.desktop])
        self.assertTrue(original.exists())
        self.assertEqual(failed.find(self.group['id'])['items'],[str(original)])
        retried=GroupStore(self.root/'data',desktop_roots=[self.desktop])
        self.assertFalse(original.exists())
        self.assertTrue(Path(retried.find(self.group['id'])['items'][0]).exists())

    def test_collection_permission_failure_keeps_working_group_and_reports_duplicate(self):
        original=self.shortcut()
        with patch.object(self.store.library,'collect',side_effect=PermissionError('denied')):
            self.assertTrue(self.store.add_paths(self.group,[str(original)]))
        self.assertTrue(original.exists())
        self.assertTrue(Path(self.group['items'][0]).exists())
        self.assertIn('убрать',self.store.last_warning)


class GroupScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.view=QListWidget()
        self.view.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.view.resize(240,180)
        self.view.addItems([f'Item {n}' for n in range(100)])
        self.view.show()
        QTest.qWait(20)
        self.scroll=SmoothScroll(self.view)

    def tearDown(self):
        self.scroll.stop()
        self.view.close()
        self.view.deleteLater()

    def event(self,pixel=0,angle=0):
        return QWheelEvent(QPointF(20,20),QPointF(20,20),QPoint(0,pixel),QPoint(0,angle),
            Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)

    def test_wheel_retargets_continuously_stays_in_bounds_and_stops_at_rest(self):
        self.scroll.wheel(self.event(angle=-120))
        self.assertEqual(self.scroll.bar.value(),0)
        QTest.qWait(75)
        value=self.scroll.bar.value()
        self.assertGreater(value,0)
        self.assertLess(value,60)
        self.scroll.wheel(self.event(angle=-120))
        self.assertEqual(self.scroll.bar.value(),value)
        QTest.qWait(650)
        self.assertEqual(self.scroll.bar.value(),120)
        self.assertFalse(self.scroll.timer.isActive())
        self.scroll.wheel(self.event(angle=12000))
        QTest.qWait(650)
        self.assertEqual(self.scroll.bar.value(),0)

    def test_touchpad_pixels_are_direct_and_cancel_pending_wheel_animation(self):
        self.scroll.bar.setValue(200)
        self.scroll.wheel(self.event(angle=-120))
        self.scroll.wheel(self.event(pixel=13))
        self.assertEqual(self.scroll.bar.value(),187)
        self.assertFalse(self.scroll.timer.isActive())
        QTest.qWait(90)
        self.assertEqual(self.scroll.bar.value(),187)

    def test_dense_wheel_stream_does_not_postpone_every_animation_frame(self):
        for _ in range(35):
            self.scroll.wheel(self.event(angle=-15))
            QTest.qWait(3)
        self.assertGreater(self.scroll.bar.value(),0)
        QTest.qWait(650)
        self.assertFalse(self.scroll.timer.isActive())
