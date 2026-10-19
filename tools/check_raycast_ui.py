# SPDX-License-Identifier: GPL-3.0-only
"""Render real Qt widgets in isolated data; fresh process per QT_SCALE_FACTOR."""
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
from island.search import Result
from island.module_preview import ModulePreview

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
errors=[]
sys.excepthook=lambda kind,value,tb:errors.append(str(value))
report={'scale':os.environ.get('QT_SCALE_FACTOR','1'),'platform':app.platformName(),'pages':[]}
with tempfile.TemporaryDirectory() as folder:
    w=IslandWindow(Settings(folder),services=False)
    w._system_timer.stop();w._notch_pointer_timer.stop();w._notch_pointer.enabled=False
    try:
        w.show_hub();c=w.control_center
        c._setting('hub_animations',False)
        report['device_pixel_ratio']=c.devicePixelRatioF()
        groups_before=w.modules.desktop.store.path.read_bytes()
        for theme in ('dark','light'):
            c._setting('hub_theme',theme)
            for width,height in ((1120,760),(900,600)):
                c.resize(width,height)
                for key in c.page_indices:
                    c.navigate(key);c.feedback.hide();QTest.qWait(25)
                    scroll=c.pages.currentWidget()
                    horizontal=scroll.horizontalScrollBar().maximum()
                    report['pages'].append({'page':key,'theme':theme,'width':width,'horizontal':horizontal})
                    c.grab().save(str(out/f'{key}-{theme}-{width}.png'))
                    assert horizontal==0,(theme,width,key,horizontal)
        c.navigate('hub')
        for key,button in c.catalog_buttons.items():
            button.click();QTest.qWait(15)
            previews=[p for p in c.catalog_stack.findChildren(ModulePreview) if p.isVisible()]
            assert len(previews)<=1
        c.catalog_buttons['island'].click()
        from island.hub_ui import SettingsSection
        c.resize(900,600);c.navigate('island')
        for section in c.findChildren(SettingsSection):
            if section.window()!=c or not section.isVisible(): continue
            section.button.setChecked(True);QTest.qWait(10)
            assert c.pages.currentWidget().horizontalScrollBar().maximum()==0,section.title
            section.button.setChecked(False)
        c.navigate('hub')
        c.toggle_sidebar();QTest.qWait(20)
        assert c.sidebar.width()==54
        c.grab().save(str(out/'collapsed-navigation.png'))
        c.focus_settings_search()
        assert not c.sidebar_collapsed and c.settings_search.hasFocus()
        search=w.modules.search
        search.apply_brand_theme()
        search._set_rows([Result('Очень длинное название приложения '*6,'C:/Папка/'+'Очень длинный путь/'*15,'fixture','command')])
        search.show();QTest.qWait(20);search.grab().save(str(out/'search-long-result.png'));search.hide()
        assert search.results.horizontalScrollBar().maximum()==0
        assert w.modules.desktop.store.path.read_bytes()==groups_before
        c.hide()
        assert not c.focus_tick.isActive() and not c.refresh_timer.isActive()
        assert not any(p.clock.isActive() for p in c.findChildren(ModulePreview))
        assert not errors,errors
        report.update(no_horizontal_overflow=True,hidden_preview_timers_stopped=True,data_preserved=True,qt_errors=errors)
    finally:
        w.cleanup();w.hide();c.hide()
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='pages'}))
