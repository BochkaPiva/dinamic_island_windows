# SPDX-License-Identifier: GPL-3.0-only
"""Stable releases, cancellable verified downloads and installer handoff."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from PyQt6.QtCore import QObject, pyqtSignal
from . import __version__, APP_NAME, REPOSITORY, REPO_URL

MAX_INSTALLER=256*1024*1024
TRUSTED_HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','api.github.com'}


def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value))
    return tuple(map(int,match.groups())) if match else None


def trusted_url(url):
    try:
        parsed=urllib.parse.urlsplit(url)
        return parsed.scheme=='https' and parsed.hostname in TRUSTED_HOSTS and not parsed.username and not parsed.password and parsed.port in (None,443)
    except (ValueError,TypeError): return False


class ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,newurl):
        if not trusted_url(newurl): raise ValueError('Недопустимый адрес загрузки')
        return super().redirect_request(request,fp,code,message,headers,newurl)


def open_release(url):
    if not trusted_url(url): raise ValueError('Недопустимый адрес загрузки')
    request=urllib.request.Request(url,headers={'User-Agent':f'{APP_NAME}/{__version__}',
        'Accept':'application/vnd.github+json' if 'api.github.com/' in url else 'application/octet-stream'})
    return urllib.request.build_opener(ReleaseRedirects()).open(request,timeout=15)


def release_info(payload,current=__version__):
    if not isinstance(payload,dict) or payload.get('draft') or payload.get('prerelease'): return None
    tag=str(payload.get('tag_name',''))
    version=version_tuple(tag)
    if not version or not version_tuple(current) or version<=version_tuple(current): return None
    if payload.get('html_url')!=REPO_URL+'/releases/tag/'+tag: return None
    value='.'.join(map(str,version))
    result={'version':value,'url':payload['html_url'],'notes':str(payload.get('body') or '')[:30000],
            'installer':None,'checksums':None}
    for asset in payload.get('assets',[]) if isinstance(payload.get('assets',[]),list) else []:
        if not isinstance(asset,dict): continue
        name=asset.get('name')
        key='installer' if name==f'CloudIsland-Setup-{value}-win-x64.exe' else 'checksums' if name=='SHA256SUMS.txt' else None
        expected=REPO_URL+'/releases/download/'+tag+'/'+str(name)
        size=asset.get('size')
        if key and asset.get('browser_download_url')==expected and type(size) is int and 0<size<=(MAX_INSTALLER if key=='installer' else 65536):
            if result[key] is not None: return None
            result[key]={'name':name,'url':expected,'size':size,'digest':asset.get('digest')}
    return result


def checksum_for(content,name):
    matches=[]
    for line in content.decode('utf-8-sig').splitlines():
        found=re.fullmatch(r'([a-fA-F0-9]{64})[ \t]+\*?([^\r\n]+)',line)
        if found and found.group(2)==name: matches.append(found.group(1).lower())
    if len(matches)!=1: raise ValueError('В релизе нет однозначной контрольной суммы установщика')
    return matches[0]


def verify_installer(path,expected,size):
    path=Path(path)
    if type(size) is not int or path.stat().st_size!=size or not 0<size<=MAX_INSTALLER: raise ValueError('Размер загруженного установщика не совпадает')
    if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected): raise ValueError('Неверная контрольная сумма установщика')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        if stream.read(2)!=b'MZ': raise ValueError('Загружен неверный формат установщика')
        stream.seek(0)
        while chunk:=stream.read(1024*1024): digest.update(chunk)
    if digest.hexdigest()!=expected: raise ValueError('Проверка SHA-256 не пройдена. Установка отменена')


class Cancelled(Exception): pass


class UpdateChecker(QObject):
    finished=pyqtSignal(object)
    changed=pyqtSignal(object)
    _event=pyqtSignal(object)

    def __init__(self,parent=None,directory=None):
        super().__init__(parent)
        from .storage import data_dir
        self.directory=Path(directory) if directory is not None else (parent.settings.directory if parent is not None else data_dir())
        self.running=False
        self.state='idle'
        self.info=None
        self.path=None
        self.sha256=None
        self.message='Проверь, доступна ли новая версия Cloud Hub.'
        self.received=self.total=0
        self.cancel_event=threading.Event()
        self._event.connect(self._receive)
        self.finished.connect(self._checked)
        self.last_result=None
        result_path=self.directory/'update-result.json'
        try:
            result=json.loads(result_path.read_text(encoding='utf-8'))
            if isinstance(result,dict) and not result.get('seen') and 0<=time.time()-result['at']<172800:
                self.last_result=result
                self.state='updated' if result['status']=='installed' and result['version']==__version__ else 'error'
                self.message='Cloud Hub обновлён. Всё готово к работе.' if self.state=='updated' else result.get('message','Установка не завершена')
                result['seen']=True
                result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        except (OSError,ValueError,TypeError,KeyError): pass

    @property
    def busy(self): return self.state in {'checking','downloading','verifying','installing'}

    def snapshot(self):
        return {'state':self.state,'info':self.info,'message':self.message,'received':self.received,'total':self.total,
                'progress':round(100*self.received/self.total) if self.total else 0,'last_result':self.last_result}

    def set_state(self,state,message):
        self.state,self.message=state,message
        self.changed.emit(self.snapshot())

    def check(self):
        if self.busy or self.state=='ready': return False
        self.running=True
        self.set_state('checking','Ищем новую версию…')
        threading.Thread(target=self._fetch,daemon=True).start()
        return True

    def _fetch(self):
        result={'status':'unavailable','message':'Не удалось проверить обновления. Проверь подключение и попробуй ещё раз.'}
        # Public release metadata does not spend the shared anonymous API quota.
        # API fallback keeps compatibility with older releases without a channel file.
        for url in (REPO_URL+'/releases/latest/download/update.json',f'https://api.github.com/repos/{REPOSITORY}/releases/latest'):
            try:
                with open_release(url) as response:
                    raw=response.read(1_000_001)
                    if len(raw)>1_000_000: raise ValueError('Слишком большой ответ сервера')
                    payload=json.loads(raw.decode('utf-8'))
                available=release_info(payload)
                latest=release_info(payload,current='0.0.0')
                if available: result={'status':'available',**available}
                elif latest and version_tuple(latest['version'])<=version_tuple(__version__): result={'status':'current','release':latest}
                else: raise ValueError('Неверные данные релиза')
                break
            except Exception: continue
        self.finished.emit(result)

    def _checked(self,result):
        self.running=False
        if result['status']=='available':
            self.info=result
            self.set_state('available','Доступна новая версия Cloud Hub.')
        elif result['status']=='current':
            self.info=result.get('release')
            self.set_state('current','Установлена последняя версия Cloud Hub.')
        else: self.set_state('error',result['message'])

    def download(self):
        if self.busy or not self.info: return False
        target=version_tuple(self.info.get('version'))
        if not target or target<version_tuple(__version__):
            self.set_state('error','Установлена более новая версия. Переход на предыдущую версию не предлагается.')
            return False
        if not self.info.get('installer') or not self.info.get('checksums'):
            self.set_state('error','Установщик релиза пока недоступен. Повтори проверку чуть позже.')
            return False
        self.cancel_event.clear()
        self.received=0
        self.total=self.info['installer']['size']
        self.path=None
        self.set_state('downloading','Скачиваем обновление…')
        threading.Thread(target=self._download,args=(dict(self.info),),daemon=True).start()
        return True

    def cancel(self):
        if self.state in {'downloading','verifying'}:
            self.cancel_event.set()
            self.message='Отменяем загрузку…'
            self.changed.emit(self.snapshot())

    def _download(self,info):
        destination=self.directory/'updates'/info['version']
        partial=destination/(info['installer']['name']+'.part')
        terminal=None
        try:
            destination.mkdir(parents=True,exist_ok=True)
            with open_release(info['checksums']['url']) as response:
                content=response.read(65537)
                if len(content)>65536: raise ValueError('Неверный файл контрольных сумм')
                expected=checksum_for(content,info['installer']['name'])
            advertised=info['installer'].get('digest')
            if advertised and advertised!='sha256:'+expected: raise ValueError('Контрольные суммы релиза не совпадают')
            size=info['installer']['size']
            received=0
            with open_release(info['installer']['url']) as response,partial.open('wb') as stream:
                last=0.
                while True:
                    if self.cancel_event.is_set(): raise Cancelled()
                    chunk=response.read(128*1024)
                    if not chunk: break
                    received+=len(chunk)
                    if received>size: raise ValueError('Сервер отправил файл неверного размера')
                    stream.write(chunk)
                    if time.monotonic()-last>.08:
                        self._event.emit({'state':'downloading','received':received,'total':size})
                        last=time.monotonic()
            self._event.emit({'state':'verifying','message':'Проверяем целостность установщика…','received':received,'total':size})
            if self.cancel_event.is_set(): raise Cancelled()
            verify_installer(partial,expected,size)
            if self.cancel_event.is_set(): raise Cancelled()
            final=destination/info['installer']['name']
            partial.replace(final)
            terminal={'state':'ready','message':'Обновление скачано и проверено. Можно установить.','path':str(final),'sha256':expected,'received':size,'total':size}
        except Cancelled:
            terminal={'state':'available','message':'Загрузка отменена. Текущая версия продолжает работать.'}
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else 'Не удалось скачать обновление. Проверь подключение и свободное место.'
            terminal={'state':'error','message':message}
        finally:
            try: partial.unlink(missing_ok=True)
            except OSError: pass
        self._event.emit(terminal)

    def _receive(self,event):
        for name in ('received','total','path','sha256'):
            if name in event: setattr(self,name,event[name])
        self.set_state(event['state'],event.get('message',self.message))

    def install(self,context):
        if self.state!='ready' or not self.path or not self.info: return False
        source=Path(context.get('source_exe',''))
        if source.name.casefold()!='cloudisland.exe' or not source.is_file():
            self.set_state('error','Установка доступна в собранном приложении Cloud Hub.')
            return False
        self.set_state('installing','Подготавливаем установку и резервную копию…')
        threading.Thread(target=self._handoff,args=(dict(context),),daemon=True).start()
        return True

    def _handoff(self,context):
        try:
            verify_installer(self.path,self.sha256,self.info['installer']['size'])
            stage=Path(self.path).parent
            source=Path(context['source_exe']).resolve()
            helper=stage/'CloudHub-UpdateHelper.exe'
            shutil.copy2(source,helper)
            manifest={'version':self.info['version'],'current_version':__version__,'installer':str(Path(self.path).resolve()),
                'sha256':self.sha256,'size':self.info['installer']['size'],'data_dir':str(self.directory.resolve()),
                'source_exe':str(source),'parent_pid':context['parent_pid'],'timer':context.get('timer')}
            target=stage/'handoff.json'
            temp=stage/'handoff.tmp'
            temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(target)
            child=subprocess.Popen([str(helper),'--apply-update',str(target)],creationflags=0x08000000)
            if child.wait(timeout=420)!=0:
                message='Установка не завершена. Открой подробности обновления и попробуй ещё раз.'
                try: message=json.loads((self.directory/'update-result.json').read_text(encoding='utf-8')).get('message',message)
                except (OSError,ValueError): pass
                self._event.emit({'state':'error','message':message})
        except Exception:
            self._event.emit({'state':'error','message':'Не удалось запустить установщик. Текущая версия остаётся доступной.'})
