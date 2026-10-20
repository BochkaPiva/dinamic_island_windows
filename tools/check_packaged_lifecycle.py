"""Own validation installer only: fresh install, real legacy upgrade, onedir update and rollback."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from island.instance import query_status,notify_existing
from island.update_helper import atomic_json
from island.update_manager import UpdateChecker
from island import __version__


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_process(pid,seconds=8):
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD);kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    kernel.GetProcessTimes.argtypes=(wintypes.HANDLE,)+(ctypes.POINTER(wintypes.FILETIME),)*4
    memory_info=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
    memory_info.argtypes=(wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD)
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    def ticks():
        values=[wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*map(ctypes.byref,values)): raise ctypes.WinError(ctypes.get_last_error())
        return sum((v.dwHighDateTime<<32)|v.dwLowDateTime for v in values[2:])/10_000_000
    try:
        time.sleep(2) # Exclude startup/import work from the idle measurement.
        before=ticks();start=time.monotonic();samples=[]
        while time.monotonic()-start<seconds:
            memory=Memory();memory.cb=ctypes.sizeof(memory)
            if not memory_info(handle,ctypes.byref(memory),memory.cb): raise ctypes.WinError(ctypes.get_last_error())
            samples.append(memory.working/1024**2)
            time.sleep(.5)
        elapsed=time.monotonic()-start
        return {'seconds':round(elapsed,1),'working_set_mb_mean':round(sum(samples)/len(samples),1),
                'cpu_percent_of_machine':round((ticks()-before)/elapsed/os.cpu_count()*100,3)}
    finally: kernel.CloseHandle(handle)


def close_own_hub(pid):
    """Close only the verification process's own settings window, not the island."""
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    user.GetWindowTextW.argtypes=(wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
    user.PostMessageW.argtypes=(wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
    def visit(hwnd,unused):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid:
            title=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,title,256)
            if title.value in ('Cloud Hub','Nelviro'): user.PostMessageW(hwnd,0x0010,0,0)
        return True
    user.EnumWindows(callback_type(visit),0)
    until=time.monotonic()+3
    while time.monotonic()<until and query_status().get('hub_visible'): time.sleep(.1)
    assert not query_status().get('hub_visible')


def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--installer',type=Path,required=True)
    parser.add_argument('--legacy-exe',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args()
    base=args.directory.resolve();base.mkdir(parents=True,exist_ok=True)
    # The companion file is produced with /DValidationBuild and prevents calling a
    # normal installer, which would alter the owner's production uninstall entry.
    receipt=json.loads(args.installer.with_suffix('.validation.json').read_text())
    if receipt.get('purpose')!='isolated-verification' or receipt.get('sha256')!=digest(args.installer):
        raise ValueError('Not an approved validation installer')
    folder=Path(tempfile.mkdtemp(prefix='lifecycle-',dir=base))
    data=folder/'data';data.mkdir()
    install=folder/'installed'
    executable=install/'CloudIsland.exe'
    os.environ['CLOUD_ISLAND_DATA_DIR']=str(data)
    app=QCoreApplication([])
    app.setApplicationName('Cloud Hub package verification')
    env={**os.environ}
    legacy_original=digest(args.legacy_exe)
    report={'version':__version__,'distribution':'preview'}
    installer=args.installer.resolve()
    def execute(command,timeout=180):
        return subprocess.run(list(map(str,command)),env=env,timeout=timeout,creationflags=0x08000000,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
    def wait_version(version,timeout=30):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            status=query_status()
            if status.get('version')==version: return status
            time.sleep(.1)
        raise RuntimeError('Expected version did not answer: '+version)
    def preserved(snapshot):
        for name,value in snapshot.items():
            if digest(data/name)!=value: raise AssertionError('Data changed: '+name)
    try:
        execute([installer,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TASKS=',f'/DIR={install}',f'/LOG={folder / "fresh-install.log"}'])
        execute([executable,'--self-test',folder/'fresh-check.json'])
        fresh=json.loads((folder/'fresh-check.json').read_text())
        assert fresh['binding']=='PySide6' and fresh['frozen'] and fresh['version']==__version__
        report['fresh_install']=True
        print('Fresh packaged PySide6 install: PASS',flush=True)

        # Seed non-personal data. Do not use desktop roots or collect user shortcuts.
        atomic_json(data/'settings.json',{'updates':False,'autostart':False,'group_collect_shortcuts':False,
            'hotkey_hub':'','hotkey_search':'','hotkey_island':''})
        (data/'notch-notes.txt').write_text('Проверка: заметки не теряются при переходе',encoding='utf-8')
        owned=data/'shortcuts'/'fixture';owned.mkdir(parents=True)
        links=[]
        for i in range(8):
            path=owned/f'App-{i}.url';path.write_text('[InternetShortcut]\nURL=https://example.invalid/\n',encoding='utf-8');links.append(str(path))
        groups=[{'id':str(uuid.uuid4()),'title':f'Group {i+1}','items':links[2*i:2*i+2],
            'x':.03+i*.24,'y':.2,'screen':''} for i in range(4)]
        atomic_json(data/'desktop-groups.json',{'version':1,'groups':groups})
        shutil.copy2(args.legacy_exe,executable)
        legacy=subprocess.Popen([str(executable),'--background'],env=env,creationflags=0x08000000)
        status=wait_version('0.5.1')
        assert status['desktop_groups']==4
        assert notify_existing('hub')
        time.sleep(.4)
        close_own_hub(status['pid'])
        report['legacy_idle_sample']=sample_process(status['pid'])
        snapshot={p.relative_to(data).as_posix():digest(p) for p in [data/'settings.json',data/'desktop-groups.json',data/'notch-notes.txt',*owned.glob('*.url')]}
        stage=data/'updates'/__version__;stage.mkdir(parents=True)
        staged=stage/f'CloudIsland-Setup-{__version__}-win-x64.exe';shutil.copy2(installer,staged)
        helper=stage/'Legacy-UpdateHelper.exe';shutil.copy2(executable,helper)
        handoff={'version':__version__,'current_version':'0.5.1','installer':str(staged),
            'sha256':digest(staged),'size':staged.stat().st_size,'data_dir':str(data),
            'source_exe':str(executable),'parent_pid':status['pid'],
            'timer':{'remaining':90,'running':True,'deadline':time.time()+90}}
        atomic_json(stage/'handoff.json',handoff)
        execute([helper,'--apply-update',stage/'handoff.json'],timeout=300)
        status=wait_version(__version__)
        assert status['binding']=='PySide6' and status['desktop_groups']==4
        assert status['timer_running'] and 0<status['timer_remaining']<=90
        preserved(snapshot)
        report.update(legacy_singlefile_upgrade=True,data_preserved=True,timer_resumed=True)
        close_own_hub(status['pid'])
        report['pyside_idle_sample']=sample_process(status['pid'])
        report['performance_scope']='Same four groups and opened-then-hidden Hub, 8 seconds each; not a battery or long-running benchmark'
        print('Real 0.5.1 single-file → PySide6 onedir upgrade: PASS',flush=True)

        # Modern helper must accept the public Nelviro filename too.
        primary=stage/f'Nelviro-Setup-{__version__}-win-x64.exe'
        shutil.copy2(staged,primary)
        staged=primary
        manager=UpdateChecker(directory=data)
        manager.path=str(staged);manager.sha256=digest(staged)
        manager.info={'version':__version__,'installer':{'size':staged.stat().st_size}}
        manager._handoff({'source_exe':str(executable),'parent_pid':status['pid']})
        status=wait_version(__version__)
        result=json.loads((data/'update-result.json').read_text(encoding='utf-8'))
        assert result['status']=='installed',result
        assert (stage/'_internal'/'PySide6'/'Qt6Core.dll').exists()
        assert (Path(result['backup'])/'previous-runtime'/'PySide6'/'Qt6Core.dll').exists()
        preserved(snapshot)
        report['onedir_helper_update']=True
        print('External-runtime helper and full runtime backup: PASS',flush=True)

        # A locally generated invalid installer tests rollback without altering the
        # owner's actual app. It passes SHA verification but Windows rejects its PE.
        qt_digest=digest(install/'_internal'/'PySide6'/'Qt6Core.dll')
        exe_digest=digest(executable)
        staged.write_bytes(b'MZinvalid-validation-installer')
        manager.sha256=digest(staged)
        manager.info['installer']['size']=staged.stat().st_size
        manager._handoff({'source_exe':str(executable),'parent_pid':status['pid']})
        wait_version(__version__)
        result=json.loads((data/'update-result.json').read_text(encoding='utf-8'))
        assert result['status']=='error',result
        assert digest(executable)==exe_digest
        assert digest(install/'_internal'/'PySide6'/'Qt6Core.dll')==qt_digest
        preserved(snapshot)
        report['failed_install_runtime_rollback']=True
        print('Failed installer → matching Qt runtime and app restored: PASS',flush=True)
        assert notify_existing('quit')
        time.sleep(.6)

        # A modified, compatible Qt DLL remains replaceable; no app hash check
        # rejects the library. Append only a PE overlay marker to a test copy.
        core=install/'_internal'/'PySide6'/'Qt6Core.dll'
        with core.open('ab') as stream: stream.write(b'CloudHub-LGPL-replacement-check')
        execute([executable,'--self-test',folder/'replacement-check.json'])
        report['external_qt_replacement_loads']=True
        report['replacement_scope']='Compatible DLL with a harmless PE overlay; not a rebuilt Qt source tree'
        print('Replaceable external Qt library: PASS',flush=True)
    finally:
        notify_existing('quit')
        time.sleep(.4)
        uninstall=next(install.glob('unins*.exe'),None) if install.exists() else None
        if uninstall:
            execute([uninstall,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={folder / "uninstall.log"}'])
            report['verification_uninstalled']=True
        report['production_executable_unchanged']=digest(args.legacy_exe)==legacy_original
        (base/'lifecycle-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__': main()
