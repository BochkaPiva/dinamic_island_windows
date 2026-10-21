"""Exercise real frozen group reload and missing-primary recovery in isolated profiles."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from island.instance import query_status, notify_existing
from island.update_helper import atomic_json
from island import __version__


def main():
    executable=Path(sys.argv[1]).resolve()
    report_path=Path(sys.argv[2]).resolve()
    app=QCoreApplication([])
    previous=os.environ.get('CLOUD_ISLAND_DATA_DIR')
    report={'version':__version__,'installed_profile_used':False}
    settings={'updates':False,'autostart':False,'group_collect_shortcuts':False,
        'island_enabled':False,'search_enabled':False,'layouts_enabled':False,
        'hotkey_hub':'','hotkey_search':'','hotkey_island':''}
    document={'version':1,'groups':[{'id':str(uuid.uuid4()),'title':f'Saved group {i}',
        'items':[],'x':.03+i*.33,'y':.25,'screen':''} for i in range(3)]}

    def wait_count(count):
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            status=query_status()
            if status.get('version')==__version__ and status.get('desktop_groups')==count:
                return status
            time.sleep(.1)
        raise AssertionError(f'Expected {count} panels: {status}')

    try:
        for scenario in ('late-restore','missing-primary'):
            with tempfile.TemporaryDirectory(prefix='nelviro-groups-') as folder:
                data=Path(folder)
                os.environ['CLOUD_ISLAND_DATA_DIR']=str(data)
                atomic_json(data/'settings.json',settings)
                if scenario=='missing-primary':
                    atomic_json(data/'desktop-groups.last-good.json',document)
                process=subprocess.Popen([str(executable),'--background'],env=os.environ.copy(),
                    creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    if scenario=='late-restore':
                        wait_count(2)
                        atomic_json(data/'desktop-groups.json',document)
                    wait_count(3)
                    saved=json.loads((data/'desktop-groups.json').read_text(encoding='utf-8'))
                    assert [(g['id'],g['title']) for g in saved['groups']]==[(g['id'],g['title']) for g in document['groups']]
                    if scenario=='missing-primary':
                        assert json.loads((data/'desktop-groups.last-good.json').read_text(encoding='utf-8'))==document
                    assert notify_existing('quit')
                    process.wait(timeout=20)
                    assert process.returncode==0
                    assert not (data/'crash.log').exists()
                    native=(data/'native-crash.log').read_text(encoding='utf-8')
                    assert 'started' in native and 'clean exit' in native
                    report[scenario]=True
                finally:
                    if process.poll() is None:
                        notify_existing('quit')
                        process.wait(timeout=20)
    finally:
        if previous is None:
            os.environ.pop('CLOUD_ISLAND_DATA_DIR',None)
        else:
            os.environ['CLOUD_ISLAND_DATA_DIR']=previous
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
