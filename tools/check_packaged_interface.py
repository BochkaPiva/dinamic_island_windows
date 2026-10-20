# SPDX-License-Identifier: GPL-3.0-only
"""Smoke-test the real frozen settings UI using a separate installation identity."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from island.instance import query_status,notify_existing
from island import __version__
app=QCoreApplication([])
executable=Path(sys.argv[1]).resolve();report_path=Path(sys.argv[2])
previous=os.environ.get('CLOUD_ISLAND_DATA_DIR')
with tempfile.TemporaryDirectory(prefix='nelviro-packaged-ui-') as folder:
 os.environ['CLOUD_ISLAND_DATA_DIR']=folder
 settings={'updates':False,'autostart':False,'group_collect_shortcuts':False,'island_enabled':False,'desktop_enabled':False,'search_enabled':False,'spectrum':False,'layouts_enabled':False,'workspaces_enabled':False,'hotkey_hub':'','hotkey_search':'','hotkey_island':'','hub_animations':False}
 (Path(folder)/'settings.json').write_text(json.dumps(settings),encoding='utf-8')
 process=subprocess.Popen([str(executable)],env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  deadline=time.monotonic()+25;status={}
  while time.monotonic()<deadline:
   status=query_status()
   if status.get('version')==__version__ and status.get('hub_visible'):break
   if process.poll() is not None:raise RuntimeError('Candidate exited during startup')
   time.sleep(.2)
  else:raise RuntimeError('Isolated candidate did not open its settings')
  time.sleep(1)
  crash=Path(folder)/'crash.log'
  assert not crash.exists() or crash.stat().st_size==0,'Qt/runtime paint exception in candidate'
  notify_existing('quit');process.wait(timeout=15)
  assert process.returncode==0
  report={'version':status['version'],'frozen_ui_opened':True,'qt_runtime_errors':False,'graceful_exit':True,'isolated_data':True,'installed_profile_used':False}
  report_path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
 finally:
  if process.poll() is None:process.terminate();process.wait(timeout=10)
  if previous is None:os.environ.pop('CLOUD_ISLAND_DATA_DIR',None)
  else:os.environ['CLOUD_ISLAND_DATA_DIR']=previous
