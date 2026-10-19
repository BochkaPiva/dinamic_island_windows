# SPDX-License-Identifier: GPL-3.0-only
"""Independent helper: stop, back up, install, validate, restart or recover."""
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from . import __version__
from .storage import data_dir
from .update_manager import verify_installer,version_tuple


def atomic_json(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def process_image(pid):
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.argtypes=(ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes=(ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong))
    kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle: return None
    try:
        buffer=ctypes.create_unicode_buffer(32768)
        length=ctypes.c_ulong(len(buffer))
        return Path(buffer.value).resolve() if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)) else None
    finally: kernel.CloseHandle(handle)


def matching_processes(executable):
    ids=(ctypes.c_ulong*16384)()
    size=ctypes.c_ulong()
    if not ctypes.windll.psapi.EnumProcesses(ids,ctypes.sizeof(ids),ctypes.byref(size)):
        raise OSError('Не удалось проверить завершение приложения')
    return [pid for pid in ids[:size.value//ctypes.sizeof(ctypes.c_ulong)] if pid and process_image(pid)==executable]


def validate_handoff(path,directory):
    if Path(path).is_symlink(): raise ValueError('Неверное расположение задания обновления')
    path=Path(path).resolve()
    if not path.is_relative_to((directory/'updates').resolve()) or path.name!='handoff.json':
        raise ValueError('Неверное расположение задания обновления')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise ValueError('Неверный формат задания обновления')
    target_version=version_tuple(value.get('version'))
    if not target_version or target_version<version_tuple(__version__) or value.get('current_version')!=__version__:
        raise ValueError('Версия задания обновления не подходит этому приложению')
    if Path(value['data_dir']).resolve()!=directory.resolve():
        raise ValueError('Неверная папка данных обновления')
    if path.parent.name!=value['version'] or Path(value['installer']).is_symlink():
        raise ValueError('Неверный путь установщика')
    installer=Path(value['installer']).resolve()
    if installer.parent!=path.parent or installer.name!=f"CloudIsland-Setup-{value['version']}-win-x64.exe" or installer.is_symlink():
        raise ValueError('Неверный путь установщика')
    verify_installer(installer,value['sha256'],value['size'])
    source=Path(value['source_exe']).resolve()
    if source.name.casefold()!='cloudisland.exe' or source==Path(sys.executable).resolve():
        raise ValueError('Помощник обновления должен работать отдельно от приложения')
    pid=value.get('parent_pid')
    if type(pid) is not int or pid<=0 or process_image(pid)!=source:
        raise ValueError('Исходный процесс уже изменился. Запусти обновление ещё раз')
    value['source_exe']=str(source)
    return value


def snapshot_data(directory,version):
    backup=directory/'backups'/('before-'+version+'-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    for path in directory.iterdir():
        if path.name in {'updates','backups'}: continue
        target=backup/path.name
        if path.is_symlink(): continue
        if path.is_dir(): shutil.copytree(path,target,symlinks=True)
        elif path.is_file(): shutil.copy2(path,target)
    return backup


def resume_timer(directory,current=__version__,now=None):
    """Consume fresh update-only timer state; normal exits keep normal semantics."""
    now=time.time() if now is None else now
    path=directory/'update-resume.json'
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or not isinstance(value.get('timer'),dict): return None
        version=version_tuple(value['version'])
        if not version or version>version_tuple(current) or not 0<=now-value['at']<7200: return None
        timer=value['timer']
        remaining=timer['remaining']
        if type(remaining) is not int or not 0<=remaining<=86400 or type(timer['running']) is not bool: return None
        if timer['running']:
            if type(timer['deadline']) not in (float,int) or not math.isfinite(timer['deadline']): return None
            remaining=max(0,min(86400,math.ceil(timer['deadline']-now)))
        path.unlink()
        return {'remaining':remaining,'running':timer['running']}
    except (OSError,ValueError,KeyError,TypeError,OverflowError): return None


def snapshot_application(target,backup):
    """Save the executable and its complete matching shared runtime for rollback."""
    if target.is_file(): shutil.copy2(target,backup/'previous-CloudIsland.exe')
    runtime=target.parent/'_internal'
    if runtime.is_dir(): shutil.copytree(runtime,backup/'previous-runtime')


def remove_runtime(path,application_dir):
    path=Path(path)
    if path.is_symlink() or path.resolve().parent!=application_dir.resolve() or path.name not in {'_internal','_internal.rollback'}:
        raise ValueError('Unsafe runtime restoration path')
    if path.exists(): shutil.rmtree(path)


def restore_application(target,backup):
    """Restore runtime before executable; never combine two Qt/Python releases."""
    previous=backup/'previous-CloudIsland.exe'
    if not previous.is_file(): return False
    saved_runtime=backup/'previous-runtime'
    runtime=target.parent/'_internal'
    # These paths are derived only from a validated handoff, not external input.
    if saved_runtime.is_dir():
        staging=target.parent/'_internal.rollback'
        remove_runtime(staging,target.parent)
        shutil.copytree(saved_runtime,staging)
        remove_runtime(runtime,target.parent)
        staging.replace(runtime)
    temporary=target.with_suffix('.rollback.tmp')
    shutil.copy2(previous,temporary)
    temporary.replace(target)
    return True


def apply_update(manifest):
    from PySide6.QtCore import QCoreApplication
    from .instance import notify_existing,query_status
    app=QCoreApplication.instance() or QCoreApplication([])
    directory=data_dir()
    value=None
    stopped=False
    backup=None
    target=None
    installer_started=False
    try:
        value=validate_handoff(manifest,directory)
        source=Path(value['source_exe'])
        installed=(source.parent/'unins000.exe').is_file()
        target=source if installed else Path(os.environ['LOCALAPPDATA'])/'Programs/Cloud Island/CloudIsland.exe'
        if not notify_existing('quit'): raise OSError('Не удалось завершить приложение. Оно осталось открытым')
        limit=time.monotonic()+25
        while matching_processes(source):
            if time.monotonic()>limit: raise TimeoutError('Приложение ещё завершает работу. Попробуй обновление позже')
            time.sleep(.15)
        stopped=True
        backup=snapshot_data(directory,value['version'])
        snapshot_application(target,backup)
        if isinstance(value.get('timer'),dict):
            atomic_json(directory/'update-resume.json',{'version':value['version'],'at':time.time(),'timer':value['timer']})
        installer=Path(value['installer'])
        # Recheck after backup and immediately before execution.
        verify_installer(installer,value['sha256'],value['size'])
        command=[str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
            '/CLOUDUPDATE','/TASKS=',f'/DIR={target.parent}',f'/LOG={installer.parent / "install.log"}']
        installer_started=True
        result=subprocess.run(command,timeout=300,creationflags=0x08000000)
        if result.returncode!=0: raise OSError('Установщик не завершил обновление. Предыдущая версия восстановлена')
        diagnostic=installer.parent/'installed-check.json'
        test=subprocess.run([str(target),'--self-test',str(diagnostic)],timeout=25,creationflags=0x08000000)
        if test.returncode or json.loads(diagnostic.read_text(encoding='utf-8')).get('version')!=value['version']:
            raise OSError('Новая версия не прошла проверку запуска. Предыдущая версия восстановлена')
        atomic_json(directory/'update-result.json',{'status':'installed','version':value['version'],'from':value['current_version'],
            'at':time.time(),'backup':str(backup),'seen':False})
        subprocess.Popen([str(target),'--updated'],creationflags=0x08000000)
        limit=time.monotonic()+25
        while time.monotonic()<limit:
            status=query_status()
            if status.get('version')==value['version']: return 0
            time.sleep(.3)
        raise OSError('Новая версия не ответила после перезапуска')
    except Exception as error:
        message=str(error) if isinstance(error,(ValueError,OSError)) else 'Обновление не завершено. Данные сохранены в резервной копии'
        try:
            atomic_json(directory/'update-result.json',{'status':'error','version':value.get('version','') if value else '',
                'at':time.time(),'backup':str(backup) if backup else '', 'message':message,'seen':False})
            if stopped and value and query_status().get('running'):
                notify_existing('quit')
                limit=time.monotonic()+15
                while target and matching_processes(target) and time.monotonic()<limit: time.sleep(.15)
            if stopped and value and not query_status().get('running'):
                previous=backup/'previous-CloudIsland.exe' if backup else None
                if installer_started and previous and previous.exists() and target and not matching_processes(target):
                    restore_application(target,backup)
                if isinstance(value.get('timer'),dict):
                    atomic_json(directory/'update-resume.json',{'version':value['current_version'],'at':time.time(),'timer':value['timer']})
                fallback=Path(value['source_exe'])
                if fallback.is_file(): subprocess.Popen([str(fallback),'--updated'],creationflags=0x08000000)
        except Exception: pass
        return 1
