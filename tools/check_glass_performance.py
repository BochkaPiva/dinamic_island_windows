# SPDX-License-Identifier: GPL-3.0-only
"""Scroll CPU timing in an owned temporary Qt profile; never real user data."""
import json,sys,tempfile,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island.app import IslandWindow
from island.storage import Settings
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as folder:
 w=IslandWindow(Settings(folder),services=False)
 try:
  w.show_hub();c=w.control_center;c.resize(900,600);c._setting('hub_animations',False);QTest.qWait(80)
  scroll=c.pages.currentWidget().verticalScrollBar();times=[]
  for i in range(32):
   start=time.perf_counter();scroll.setValue(round(scroll.maximum()*i/31));app.processEvents();times.append((time.perf_counter()-start)*1000)
  report={'dpr':c.devicePixelRatioF(),'material':c.material,'scroll_cpu_median_ms':round(statistics.median(times),2),'p95_ms':round(sorted(times)[30],2),'samples':len(times),'scope':'CPU event processing, not compositor frame latency'}
  print(json.dumps(report))
  if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf-8')
 finally:c.hide();w.cleanup();w.hide()
