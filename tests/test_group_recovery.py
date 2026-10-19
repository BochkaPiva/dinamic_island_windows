import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from island.desktop_groups import GroupStore


class GroupRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = GroupStore(self.root, desktop_roots=[])
        self.original.rename(self.original.groups[0]['id'], 'Programming')
        self.path = self.original.path
        self.content = self.path.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_transient_read_error_retries_without_default_groups(self):
        read = Path.read_text
        calls = []
        def flaky(path, *args, **kwargs):
            if path == self.path and not calls:
                calls.append(True)
                raise PermissionError('sharing violation')
            return read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', flaky):
            store = GroupStore(self.root, desktop_roots=[])
        self.assertEqual(store.groups[0]['title'], 'Programming')
        self.assertEqual(self.path.read_bytes(), self.content)

    def test_persistent_read_failure_never_writes_defaults_and_can_reload(self):
        read = Path.read_text
        def denied(path, *args, **kwargs):
            if path == self.path:
                raise PermissionError('locked')
            return read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', denied):
            store = GroupStore(self.root, desktop_roots=[])
            self.assertTrue(store._read_failed)
            self.assertIsNone(store.add('Must not replace data'))
        self.assertEqual(self.path.read_bytes(), self.content)
        store.retry_load()
        self.assertFalse(store._read_failed)
        self.assertEqual(store.groups[0]['title'], 'Programming')

    def test_corrupt_document_is_preserved_and_blocks_save(self):
        self.path.write_bytes(b'{truncated')
        store = GroupStore(self.root, desktop_roots=[])
        self.assertTrue(store._read_failed)
        self.assertFalse(store.save())
        store.retry_load()
        self.assertEqual(self.path.read_bytes(), b'{truncated')

    def test_failed_atomic_replace_retains_original_and_valid_backup(self):
        replace = Path.replace
        def denied(path, target):
            if target == self.path:
                raise PermissionError('locked')
            return replace(path, target)
        with patch.object(Path, 'replace', denied):
            self.assertFalse(self.original.rename(self.original.groups[0]['id'], 'Changed'))
        self.assertEqual(self.path.read_bytes(), self.content)
        self.assertEqual(self.path.with_suffix('.last-good.json').read_bytes(), self.content)

    def test_explicit_empty_group_list_does_not_create_defaults(self):
        self.path.write_text(json.dumps({'version': 1, 'groups': []}), encoding='utf-8')
        self.assertEqual(GroupStore(self.root, desktop_roots=[]).groups, [])
