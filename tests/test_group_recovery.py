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

    def test_transient_missing_file_retries_before_defaults(self):
        read=Path.read_text
        calls=[]
        def missing_once(path,*args,**kwargs):
            if path==self.path and not calls:
                calls.append(True)
                raise FileNotFoundError('temporary disappearance')
            return read(path,*args,**kwargs)
        with patch.object(Path,'read_text',missing_once):
            store=GroupStore(self.root,desktop_roots=[])
        self.assertEqual(store.groups[0]['title'],'Programming')
        self.assertEqual(self.path.read_bytes(),self.content)

    def test_missing_primary_recovers_complete_last_good_not_defaults(self):
        backup=self.path.with_suffix('.last-good.json')
        backup.write_bytes(self.content)
        self.path.unlink()
        store=GroupStore(self.root,desktop_roots=[])
        self.assertFalse(store._read_failed)
        self.assertEqual(store.groups[0]['title'],'Programming')
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['groups'],store.groups)
        self.assertEqual(backup.read_bytes(),self.content)

    def test_missing_primary_recovers_update_backup(self):
        self.path.with_suffix('.last-good.json').unlink()
        backup=self.root/'backups'/'before-update'/'desktop-groups.json'
        backup.parent.mkdir(parents=True)
        backup.write_bytes(self.content)
        self.path.unlink()
        store=GroupStore(self.root,desktop_roots=[])
        self.assertEqual(store.groups[0]['title'],'Programming')
        self.assertEqual(backup.read_bytes(),self.content)

    def test_invalid_backup_is_not_treated_as_new_install(self):
        backup=self.path.with_suffix('.last-good.json')
        backup.write_bytes(b'{truncated')
        self.path.unlink()
        store=GroupStore(self.root,desktop_roots=[])
        self.assertTrue(store._read_failed)
        self.assertEqual(store.groups,[])
        self.assertFalse(self.path.exists())
        self.assertEqual(backup.read_bytes(),b'{truncated')

    def test_late_restored_document_replaces_stale_defaults_without_restart(self):
        fresh=self.root/'another-profile'
        store=GroupStore(fresh,desktop_roots=[])
        self.assertEqual(store.groups[0]['title'],'Работа')
        store.path.write_bytes(self.content)
        store.retry_load()
        self.assertEqual(store.groups[0]['title'],'Programming')
        self.assertEqual(store.path.read_bytes(),self.content)
        self.assertTrue(store.rename(store.groups[0]['id'],'Recovered'))

    def test_stale_writer_cannot_overwrite_restored_groups(self):
        store=GroupStore(self.root,desktop_roots=[])
        newest=json.loads(self.content)
        newest['groups'][0]['title']='Restored externally'
        saved=json.dumps(newest,ensure_ascii=False).encode()
        self.path.write_bytes(saved)
        self.assertFalse(store.rename(store.groups[0]['id'],'Stale name'))
        self.assertEqual(self.path.read_bytes(),saved)
        store.retry_load()
        self.assertEqual(store.groups[0]['title'],'Restored externally')
        self.assertFalse(store._read_failed)

    def test_second_store_does_not_erase_first_store_commit(self):
        stale=GroupStore(self.root,desktop_roots=[])
        self.assertTrue(self.original.rename(self.original.groups[0]['id'],'First writer'))
        saved=self.path.read_bytes()
        self.assertFalse(stale.remove(stale.groups[0]['id']))
        self.assertEqual(self.path.read_bytes(),saved)
        stale.retry_load()
        self.assertEqual(stale.groups[0]['title'],'First writer')

    def test_bad_later_record_never_leaves_partial_model(self):
        document=json.loads(self.content)
        document['groups'][1]['id']='not-a-uuid'
        saved=json.dumps(document).encode()
        self.path.write_bytes(saved)
        store=GroupStore(self.root,desktop_roots=[])
        self.assertEqual(store.groups,[])
        self.assertTrue(store._read_failed)
        self.assertFalse(store.save())
        self.assertEqual(self.path.read_bytes(),saved)

    def test_corruption_during_runtime_retains_loaded_groups(self):
        self.path.write_bytes(b'{broken')
        self.original.retry_load()
        self.assertEqual(self.original.groups[0]['title'],'Programming')
        self.assertTrue(self.original._read_failed)
        self.assertFalse(self.original.rename(self.original.groups[0]['id'],'Must not save'))
        self.assertEqual(self.path.read_bytes(),b'{broken')
