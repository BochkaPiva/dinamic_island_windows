# SPDX-License-Identifier: GPL-3.0-only
"""Native shortcut/scroll acceptance using isolated copies, never launching apps."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PyQt6.QtCore import Qt,QPoint,QPointF,QBuffer,QIODevice
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication,QMenu
from PyQt6.QtTest import QTest
from island.app import IslandWindow
from island.group_icons import group_icons
from island.storage import Settings
from island.desktop_groups import GroupStore

out=Path(sys.argv[1])
out.mkdir(parents=True,exist_ok=True)
source_data=Path(sys.argv[2])
recovery=Path(sys.argv[3])
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
records=json.loads((recovery/'recovery.json').read_text(encoding='utf-8-sig'))
recovered={r['Original']:r['Recovered'] for r in records}

def wheel(view,pixel=0,angle=0):
    event=QWheelEvent(QPointF(30,30),QPointF(view.mapToGlobal(QPoint(30,30))),QPoint(0,pixel),QPoint(0,angle),
        Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(view.viewport(),event)

def png(widget):
    buffer=QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(buffer,'PNG')
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert('RGBA')

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    desktop=root/'Desktop'
    desktop.mkdir()
    document=json.loads((source_data/'desktop-groups.json').read_text(encoding='utf-8'))
    before={}
    for group in document['groups']:
        items=[]
        for value in group['items']:
            source=Path(value) if Path(value).exists() else Path(recovered[value])
            destination=desktop/Path(value).name
            shutil.copy2(source,destination)
            before[destination.name]=destination.read_bytes()
            items.append(str(destination))
        group['items']=items
    (root/'desktop-groups.json').write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    with patch('island.shortcut_library.desktop_directories',return_value=[desktop]):
        w=IslandWindow(Settings(root),services=False)
    w._system_timer.stop()
    w._notch_pointer_timer.stop()
    w._notch_pointer.enabled=False
    try:
        manager=w.modules.desktop
        assert not list(desktop.glob('*.lnk')) and not list(desktop.glob('*.url'))
        count=0
        for group in manager.store.groups:
            for item in group['items']:
                stored=Path(item)
                assert manager.store.library.owns(stored)
                assert stored.read_bytes()==before[stored.name]
                count+=1
        assert count==34,count
        deadline=time.monotonic()+15
        while group_icons().pending and time.monotonic()<deadline: QTest.qWait(30)
        assert not group_icons().pending
        for title in ('Programming','Games','Tools and apps'):
            group=next(g for g in manager.store.groups if g['title']==title)
            panel=manager.panels[group['id']]
            panel.move(300,150)
            panel.show()
            panel.raise_()
            panel.animate(True)
            QTest.qWait(700)
            panel.collapse.stop()
            panel.grab().save(str(out/(title.split()[0].lower()+'.png')))
            shelf=panel.shelf
            assert all(not shelf.item(i).text().endswith(('.lnk','.url')) for i in range(shelf.count()))
            with patch('island.hub.QDesktopServices.openUrl',return_value=True) as launch:
                item=shelf.item(0)
                QTest.mouseClick(shelf.viewport(),Qt.MouseButton.LeftButton,pos=shelf.visualItemRect(item).center())
                QTest.mouseDClick(shelf.viewport(),Qt.MouseButton.LeftButton,pos=shelf.visualItemRect(item).center())
                assert launch.called,('not clickable',title)
                assert Path(launch.call_args.args[0].toLocalFile()).exists()
            if title=='Tools and apps':
                shelf.verticalScrollBar().setValue(0)
                wheel(shelf,angle=-120)
                assert shelf.verticalScrollBar().value()==0
                frames=[]
                positions=[]
                for _ in range(42):
                    QTest.qWait(16)
                    positions.append(shelf.verticalScrollBar().value())
                    frames.append(png(panel))
                assert positions==sorted(positions)
                assert len(set(positions))>5
                assert not shelf.smooth_scroll.timer.isActive()
                frames[0].save(out/'scroll.gif',save_all=True,append_images=frames[1:],duration=16,loop=0)
                initial=shelf.verticalScrollBar().value()
                wheel(shelf,pixel=11)
                assert shelf.verticalScrollBar().value()==initial-11
                assert not shelf.smooth_scroll.timer.isActive()
                wheel(shelf,angle=-2400)
                QTest.qWait(650)
                assert shelf.verticalScrollBar().value()==shelf.verticalScrollBar().maximum()
                panel.grab().save(str(out/'tools-bottom.png'))
                # Same references/rename must preserve current viewport position.
                position=shelf.verticalScrollBar().value()
                shelf.reload()
                assert shelf.verticalScrollBar().value()==position
                menu=QMenu(shelf)
                shelf.extra_context_actions(menu,shelf.item(0))
                assert len(menu.actions())==1
                menu.actions()[0].trigger()
                assert (desktop/Path(group['items'][0]).name).exists()
                menu.deleteLater()
            panel.hide()
        reloaded=GroupStore(root,collect_desktop=False,desktop_roots=[desktop])
        assert [(g['id'],g['items']) for g in reloaded.groups]==[(g['id'],g['items']) for g in manager.store.groups]
        assert count==sum(Path(p).is_file() for g in reloaded.groups for p in g['items'])
        report={'managed_shortcuts':count,'verified_byte_identical':True,'desktop_duplicates_collected':True,
            'source_programs_not_started':True,'native_double_click_routes_to_owned_shortcuts':True,
            'wheel_has_multiple_monotonic_frames':True,'touchpad_pixels_direct':True,
            'wheel_bounds_and_idle_stop':True,'reload_preserves_scroll':True,
            'desktop_restore_action':True,'reload_keeps_all_groups':True}
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        w.cleanup()
        w.hide()
