# SPDX-License-Identifier: GPL-3.0-only
"""Native visual acceptance of every page, theme and update state, isolated."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QAbstractAnimation
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from island.app import IslandWindow
from island.storage import Settings
from island import __version__
from island.hub_ui import ToggleSwitch,ModuleCard

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
out=Path(sys.argv[1] if len(sys.argv)>1 else 'build/hub-design-check')
out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    w=IslandWindow(Settings(folder),services=False)
    w._system_timer.stop()
    w._notch_pointer_timer.stop()
    w._notch_pointer.enabled=False
    try:
        w.show_hub()
        center=w.control_center
        QTest.qWait(300)
        center.grab().save(str(out/'modules-dark.png'))
        geometry={}
        for key in center.page_indices:
            center.navigate(key)
            QTest.qWait(260)
            center.grab().save(str(out/(key+'-dark.png')))
            scroll=center.pages.currentWidget()
            geometry[key]={'width':scroll.width(),'height':scroll.height(),'scroll':scroll.verticalScrollBar().maximum()}
        center.settings_search.setText('прозрачность')
        assert sum(not center.navigation.item(i).isHidden() for i in range(center.navigation.count()))>=2
        center.settings_search.setText('обновление')
        QTest.keyClick(center.settings_search,Qt.Key.Key_Return)
        assert center.pages.currentIndex()==center.page_indices['updates']
        center.settings_search.clear()
        QTest.qWait(260)
        updates=w.updates
        updates.info={'version':'0.5.1','notes':'• Более удобные инструменты\n• Улучшения плавности и стабильности',
            'installer':{'size':44*1024*1024},'checksums':{'size':379}}
        for state,message in (('available','Доступна новая версия Cloud Hub.'),('downloading','Скачиваем обновление…'),
            ('ready','Обновление скачано и проверено. Можно установить.'),('error','Не удалось скачать обновление. Проверь подключение и попробуй ещё раз.')):
            updates.received=28*1024*1024 if state!='ready' else 44*1024*1024
            updates.total=44*1024*1024
            updates.set_state(state,message)
            QTest.qWait(70)
            center.grab().save(str(out/('update-'+state+'.png')))
        center._setting('hub_theme','light')
        center.navigate('hub')
        QTest.qWait(260)
        center.grab().save(str(out/'modules-light.png'))
        center.navigate('desktop')
        QTest.qWait(260)
        center.grab().save(str(out/'groups-light.png'))
        center.resize(900,600)
        QTest.qWait(120)
        assert center.size().width()==900 and center.size().height()==600,center.size()
        center.grab().save(str(out/'small-window.png'))
        center._setting('hub_animations',False)
        center.navigate('hub')
        assert not center.transition.animation.state()==QAbstractAnimation.State.Running
        center.close()
        assert not center.refresh_timer.isActive() and not center.focus_tick.isActive()
        assert all(widget.animation.state()!=QAbstractAnimation.State.Running for widget in center.findChildren(ToggleSwitch)+center.findChildren(ModuleCard))
        report={'version':__version__,'all_pages_rendered':True,'settings_search':True,'updates_states':True,
            'light_and_dark_themes':True,'small_window_accessible':True,'reduced_motion':True,'hidden_timers_stopped':True,'geometry':geometry}
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        w.cleanup()
        w.hide()
