# SPDX-License-Identifier: GPL-3.0-only
"""Group selection is bound to IDs even when every visible title is identical."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from island.app import IslandWindow
from island.desktop_groups import GroupStore
from island.group_editor import GroupEditor
from island.storage import Settings


class GroupManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.w=IslandWindow(Settings(self.temp.name),services=False)
        self.w.access.distribution='preview'  # Editing/identity tests are independent of membership policy.
        self.w.access.reload()
        self.manager=self.w.modules.desktop
        self.store=self.manager.store
        for group in list(self.store.groups):
            self.store.remove(group['id'])
        self.ids=[self.store.add('Новая группа')['id'] for _ in range(5)]
        self.messages=[]
        self.editor=GroupEditor(self.manager,self.messages.append)

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.w.cleanup()
        self.w.hide()
        self.w.deleteLater()
        QTest.qWait(10)
        self.temp.cleanup()

    def edit_name(self,text):
        self.editor.name.setText(text)
        self.editor.name.textEdited.emit(text)

    def test_all_duplicate_titles_visible_and_only_selected_id_renamed(self):
        self.assertEqual(self.editor.groups.count(),5)
        self.editor.select_id(self.ids[3])
        self.edit_name('Работа')
        self.assertTrue(self.editor.rename_current())
        self.assertEqual([g['title'] for g in self.store.groups],['Новая группа']*3+['Работа','Новая группа'])
        self.assertEqual(self.editor.selected_id,self.ids[3])
        self.assertEqual(self.manager.panels[self.ids[3]].group['title'],'Работа')
        self.assertEqual(GroupStore(self.temp.name).find(self.ids[3])['title'],'Работа')

    def test_switch_commits_draft_without_refresh_stealing_selection(self):
        self.edit_name('Первый проект')
        self.editor.select_id(self.ids[4])
        self.assertEqual(self.store.find(self.ids[0])['title'],'Первый проект')
        self.assertEqual(self.editor.selected_id,self.ids[4])
        self.assertEqual(self.editor.groups.currentItem().data(Qt.ItemDataRole.UserRole),self.ids[4])
        self.assertEqual(self.editor.name.text(),'Новая группа')

    def test_store_refresh_keeps_draft_and_empty_title_cannot_switch(self):
        self.edit_name('Черновик')
        self.store.rename(self.ids[1],'Другая группа')
        self.assertEqual(self.editor.name.text(),'Черновик')
        self.edit_name('  ')
        self.editor.select_id(self.ids[1])
        self.assertEqual(self.editor.selected_id,self.ids[0])
        self.assertEqual(self.editor.groups.currentRow(),0)
        self.assertIn('Название не может быть пустым',self.messages)

    def test_live_reload_updates_existing_panel_and_editor_by_id(self):
        import json
        document=json.loads(self.store.path.read_text(encoding='utf-8'))
        document['groups'][2]['title']='Restored group'
        self.store.path.write_text(json.dumps(document),encoding='utf-8')
        self.store.retry_load()
        self.assertEqual(self.manager.panels[self.ids[2]].group['title'],'Restored group')
        self.assertIs(self.manager.panels[self.ids[2]].group,self.store.find(self.ids[2]))
        self.editor.select_id(self.ids[2])
        self.assertEqual(self.editor.name.text(),'Restored group')

    def test_menu_actions_target_exact_group_and_settings_select_it(self):
        panel=self.manager.panels[self.ids[2]]
        menu=panel.build_menu()
        self.assertTrue({'rename','delete','settings','create','files','folder'} <= {a.data() for a in menu.actions()})
        menu.deleteLater()
        with patch('island.desktop_groups.ask_group_title',return_value=('Игры',True)):
            panel.perform_action('rename')
        self.assertEqual(self.store.find(self.ids[2])['title'],'Игры')
        panel.perform_action('settings')
        center=self.w.control_center
        self.assertEqual(center.group_editor.selected_id,self.ids[2])
        self.assertEqual(center.navigation.currentRow(),center.page_indices['desktop'])

    def test_create_name_cancel_and_safe_target_deletion(self):
        with patch('island.desktop_groups.ask_group_title',return_value=('',False)):
            self.editor.create_group()
        self.assertEqual(self.editor.groups.count(),5)
        with patch('island.desktop_groups.ask_group_title',return_value=('Мои проекты',True)):
            self.editor.create_group()
        created=self.editor.selected_id
        self.assertEqual(self.store.find(created)['title'],'Мои проекты')
        with patch('island.desktop_groups.QMessageBox.exec',return_value=QMessageBox.StandardButton.No):
            self.editor.delete_group()
        self.assertIsNotNone(self.store.find(created))
        with patch('island.desktop_groups.QMessageBox.exec',return_value=QMessageBox.StandardButton.Yes):
            self.editor.delete_group()
        self.assertIsNone(self.store.find(created))
        self.assertNotIn(created,self.manager.panels)
        self.assertEqual([g['id'] for g in self.store.groups],self.ids)

    def test_link_edits_sync_both_surfaces_and_never_delete_original(self):
        original=Path(self.temp.name)/'original.txt'
        original.write_text('keep me')
        self.editor.select_id(self.ids[1])
        self.editor.files.add_paths([str(original)])
        self.assertEqual(self.manager.panels[self.ids[1]].shelf.paths(),[str(original)])
        self.editor.files.item(0).setSelected(True)
        self.editor.files.remove_selected()
        self.assertEqual(self.store.find(self.ids[1])['items'],[])
        self.assertEqual(self.manager.panels[self.ids[1]].shelf.paths(),[])
        self.store.add_paths(self.store.find(self.ids[1]),[str(original)])
        self.store.remove(self.ids[1])
        self.assertEqual(original.read_text(),'keep me')

    def test_delete_last_group_keeps_empty_collection_and_creation_available(self):
        for identifier in self.ids:
            self.store.remove(identifier)
        self.assertIsNone(self.editor.selected_id)
        self.assertFalse(self.editor.remove.isEnabled())
        self.assertTrue(self.editor.create.isEnabled())
        self.assertEqual(GroupStore(self.temp.name).groups,[])
        self.assertEqual(self.store.add()['title'],'Новая группа')
        self.assertEqual(self.store.add()['title'],'Новая группа 2')

    def test_failed_write_rolls_back_all_group_changes(self):
        group=self.store.find(self.ids[0])
        original=Path(self.temp.name)/'keep.txt'
        original.touch()
        with patch.object(self.store,'save',return_value=False):
            self.assertFalse(self.store.rename(group['id'],'Lost'))
            self.assertFalse(self.store.set_paths(group['id'],[str(original)]))
            self.assertFalse(self.store.remove(group['id']))
            self.assertIsNone(self.store.add('Lost'))
        self.assertEqual([g['id'] for g in self.store.groups],self.ids)
        self.assertEqual(group['title'],'Новая группа')
        self.assertEqual(group['items'],[])

    def test_file_dialog_result_keeps_original_target_if_selection_changes(self):
        original=Path(self.temp.name)/'keep.txt'
        original.touch()
        def choose(*args):
            self.editor.select_id(self.ids[1])
            return [str(original)],''
        with patch('island.group_editor.QFileDialog.getOpenFileNames',side_effect=choose):
            self.editor.files.add_files()
        self.assertEqual(self.store.find(self.ids[0])['items'],[str(original)])
        self.assertEqual(self.store.find(self.ids[1])['items'],[])
        self.assertEqual(self.editor.files.paths(),[])

    def test_unchanged_title_normalizes_and_leaves_save_disabled(self):
        self.edit_name('  Новая группа  ')
        self.assertTrue(self.editor.rename_current())
        self.assertEqual(self.editor.name.text(),'Новая группа')
        self.assertFalse(self.editor.rename.isEnabled())


if __name__=='__main__':
    unittest.main()
