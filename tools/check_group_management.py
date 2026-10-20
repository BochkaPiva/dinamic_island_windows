# SPDX-License-Identifier: GPL-3.0-only
"""Exercise native list, editing, popup dispatch and dialogs in isolated data."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox, QMenu, QLineEdit, QDialogButtonBox
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.desktop_groups import GroupStore
from island.storage import Settings

out=Path(sys.argv[1] if len(sys.argv)>1 else 'build/group-management-check')
out.mkdir(parents=True,exist_ok=True)
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
failures=[]

def schedule_dialog(value=None,delete=None,cancel=False):
    def finish():
        try:
            dialog=QApplication.activeModalWidget()
            assert dialog is not None,'No active native dialog'
            dialog.grab().save(str(out/('dialog-'+('title' if isinstance(dialog,QInputDialog) else 'delete')+'.png')))
            if cancel:
                QTest.keyClick(dialog,Qt.Key.Key_Escape)
            elif isinstance(dialog,QInputDialog):
                assert dialog.findChild(QLineEdit).maxLength()==60
                dialog.setTextValue('  ')
                assert not dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).isEnabled()
                dialog.setTextValue(value)
                QTest.keyClick(dialog,Qt.Key.Key_Return)
            else:
                assert isinstance(dialog,QMessageBox),type(dialog)
                QTest.mouseClick(dialog.button(QMessageBox.StandardButton.Yes if delete else QMessageBox.StandardButton.No),Qt.MouseButton.LeftButton)
        except Exception as exc:
            failures.append(repr(exc))
            if QApplication.activeModalWidget(): QApplication.activeModalWidget().reject()
    QTimer.singleShot(130,finish)

def menu_action(panel,key,**dialog):
    panel.raise_()
    panel.activateWindow()
    QTest.qWait(90)
    selected=[]
    def choose():
        try:
            menu=QApplication.activePopupWidget()
            assert isinstance(menu,QMenu)
            action=next(a for a in menu.actions() if a.data()==key)
            selected.append(key)
            menu.grab().save(str(out/'quick-actions.png'))
            if dialog: schedule_dialog(**dialog)
            QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(action).center())
        except Exception as exc:
            failures.append(repr(exc))
            if QApplication.activePopupWidget(): QApplication.activePopupWidget().close()
    QTimer.singleShot(100,choose)
    panel._header_state(True)
    QTest.mouseClick(panel.menu_button,Qt.MouseButton.LeftButton)
    assert not failures,failures
    assert selected==[key],('menu dismissed before selection',key)
    QTest.qWait(40)

with tempfile.TemporaryDirectory() as folder:
    w=IslandWindow(Settings(folder),services=False)
    w._system_timer.stop()
    w._notch_pointer_timer.stop()
    w._notch_pointer.enabled=False
    # Five-group management fixture; membership limits have their own signed-permit tests.
    w.access.distribution='preview';w.access.reload()
    manager=w.modules.desktop
    try:
        for group in list(manager.store.groups): manager.store.remove(group['id'])
        ids=[manager.store.add('Новая группа')['id'] for _ in range(5)]
        manager.open_settings(ids[2])
        center=w.control_center
        editor=center.group_editor
        QTest.qWait(180)
        center.grab().save(str(out/'groups-list.png'))
        assert editor.groups.count()==5
        for i in range(5):
            rect=editor.groups.visualItemRect(editor.groups.item(i))
            assert editor.groups.viewport().rect().contains(rect),('hidden row',i,rect)
        center.grab().save(str(out/'groups-list.png'))
        editor.name.setFocus()
        editor.name.selectAll()
        QTest.keyClicks(editor.name,'Projects')
        QTest.keyClick(editor.name,Qt.Key.Key_Return)
        assert manager.store.find(ids[2])['title']=='Projects'
        assert editor.selected_id==ids[2]
        schedule_dialog(value='Работа')
        QTest.mouseClick(editor.create,Qt.MouseButton.LeftButton)
        created=editor.selected_id
        assert created not in ids
        assert manager.store.find(created)['title']=='Работа'
        original=Path(folder)/'Бриф.txt'
        original.write_text('Original retained',encoding='utf-8')
        editor.files.add_paths([str(original)])
        assert manager.panels[created].shelf.paths()==[str(original)]
        # The exact group is addressed by its own popup, even with duplicate titles.
        center.hide()
        panel=manager.panels[ids[3]]
        panel.move(300,250)
        panel.show()
        panel.raise_()
        panel.activateWindow()
        QTest.qWait(120)
        menu_action(panel,'rename',value='Личное')
        assert manager.store.find(ids[3])['title']=='Личное'
        assert editor.groups.item(3).text().startswith('Личное')
        menu_action(panel,'settings')
        assert center.isVisible() and editor.selected_id==ids[3]
        center.hide()
        menu_action(panel,'delete',delete=False)
        assert ids[3] in manager.panels
        menu_action(panel,'delete',delete=True)
        assert ids[3] not in manager.panels
        manager.open_settings(created)
        schedule_dialog(delete=True)
        editor.delete_action.trigger()
        assert manager.store.find(created) is None
        assert original.read_text(encoding='utf-8')=='Original retained'
        assert [g['id'] for g in GroupStore(folder).groups]==[i for i in ids if i!=ids[3]]
        # A named creation and both settings tabs remain available after deletion.
        schedule_dialog(value='Работа')
        QTest.mouseClick(editor.create,Qt.MouseButton.LeftButton)
        center.resize(900,600)
        QTest.qWait(100)
        center.grab().save(str(out/'groups-small-window.png'))
        assert center.size().width()==900,('minimum grew',center.size().width())
        assert center.size().height()==600,('minimum grew',center.size().height())
        scroll=center.pages.currentWidget()
        for widget in (editor.create,editor.more,editor.name,editor.add_files,editor.remove_links):
            assert widget.isVisible()
            scroll.ensureWidgetVisible(widget)
            QTest.qWait(20)
            assert scroll.viewport().rect().contains(widget.mapTo(scroll.viewport(),widget.rect().center())),widget.text()
        center.grab().save(str(out/'groups-small-window.png'))
        center.resize(1100,740)
        scroll.verticalScrollBar().setValue(0)
        editor.files.add_paths([str(original)])
        QTest.qWait(100)
        center.grab().save(str(out/'groups-editor.png'))
        center.open_detail(center.group_settings)
        QTest.qWait(80)
        center.grab().save(str(out/'appearance.png'))
        assert not failures,failures
        report={'all_duplicate_groups_visible':True,'keyboard_rename_persisted':True,
            'native_create_dialog':True,'popup_rename':True,'popup_selects_matching_settings':True,
            'cancel_keeps_group':True,'popup_delete_safe_after_menu':True,'editor_delete':True,
            'original_file_preserved':True,'reload_keeps_ids_and_changes':True,
            'small_window_controls_accessible_by_scroll':True,'separate_appearance_screen':True}
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        w.cleanup()
        w.hide()
