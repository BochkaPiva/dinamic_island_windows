# SPDX-License-Identifier: GPL-3.0-only
"""Release trust, real download state transitions, installer recovery and data retention."""
import hashlib
import io
import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from island import __version__,REPO_URL
from island.update_manager import (UpdateChecker,release_info,trusted_url,checksum_for,verify_installer)
from island.update_helper import validate_handoff,snapshot_data,resume_timer,apply_update,atomic_json


def payload(version='9.0.0',content=b'MZ'+b'installer'*256):
    tag='v'+version
    name=f'CloudIsland-Setup-{version}-win-x64.exe'
    digest=hashlib.sha256(content).hexdigest()
    return {'tag_name':tag,'html_url':REPO_URL+'/releases/tag/'+tag,'body':'Изменения',
        'assets':[{'name':name,'size':len(content),'digest':'sha256:'+digest,
            'browser_download_url':REPO_URL+'/releases/download/'+tag+'/'+name},
            {'name':'SHA256SUMS.txt','size':100,'browser_download_url':REPO_URL+'/releases/download/'+tag+'/SHA256SUMS.txt'}]}


class ReleaseTrustTests(unittest.TestCase):
    def test_generated_release_channel_matches_exact_files_and_notes(self):
        from tools.release_channel import build_channel
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            name=f'CloudIsland-Setup-{__version__}-win-x64.exe'
            (directory/name).write_bytes(b'MZinstaller')
            (directory/f'Nelviro-Setup-{__version__}-win-x64.exe').write_bytes(b'MZinstaller')
            (directory/'SHA256SUMS.txt').write_bytes(b'checksums')
            channel=build_channel(directory,f'# Changelog\n\n## v{__version__}\n\nНаш релиз\n\n## v0.0.0\nOld')
            info=release_info(channel,current='0.0.0')
            self.assertEqual(info['notes'],'Наш релиз')
            self.assertEqual(info['installer']['size'],11)
            self.assertEqual(info['checksums']['size'],9)
            self.assertEqual(info['installer']['digest'],'sha256:'+hashlib.sha256(b'MZinstaller').hexdigest())

    def test_exact_repository_and_asset_identity(self):
        good=payload()
        info=release_info(good)
        self.assertEqual(info['version'],'9.0.0')
        for change in ({'html_url':REPO_URL+'/releases/tag/v8.0.0'},{'draft':True},{'prerelease':True},
                       {'tag_name':'v9.0.0-rc1'},{'tag_name':'../../9.0.0'}):
            self.assertIsNone(release_info({**good,**change}))
        bad=json.loads(json.dumps(good))
        bad['assets'][0]['browser_download_url']='https://example.com/update.exe'
        self.assertIsNone(release_info(bad)['installer'])
        self.assertIsNone(release_info({**good,'assets':good['assets']+[good['assets'][0]]}))
        bad['assets'][0]=dict(good['assets'][0],size=True)
        self.assertIsNone(release_info(bad)['installer'])
        self.assertIsNone(release_info(good,current='9.0.0'))

    def test_nelviro_primary_and_legacy_update_names_are_both_supported(self):
        old=payload();primary=dict(old['assets'][0]);primary['name']='Nelviro-Setup-9.0.0-win-x64.exe'
        primary['browser_download_url']=REPO_URL+'/releases/download/v9.0.0/'+primary['name']
        for assets in ([primary,old['assets'][0],old['assets'][1]],[old['assets'][0],primary,old['assets'][1]]):
            self.assertEqual(release_info({**old,'assets':assets})['installer']['name'],primary['name'])
        self.assertEqual(release_info(old)['installer']['name'],old['assets'][0]['name'])
        self.assertIsNone(release_info({**old,'assets':[primary,primary]}))

    def test_redirects_only_allow_secure_known_hosts(self):
        for url in ('https://github.com/a','https://release-assets.githubusercontent.com/a',
                    'https://objects.githubusercontent.com/a?signature=example'):
            self.assertTrue(trusted_url(url))
        for url in ('http://github.com/a','https://github.com.evil.test/a','https://github.com:123/a',
                    'https://user:password@github.com/a','file:///a','https://github.com:bad/a',None):
            self.assertFalse(trusted_url(url))

    def test_checksum_must_match_one_exact_filename(self):
        digest='1'*64
        name='CloudIsland-Setup-9.0.0-win-x64.exe'
        self.assertEqual(checksum_for((digest+'  '+name+'\n').encode(),name),digest)
        self.assertEqual(checksum_for((digest+' *'+name).encode(),name),digest)
        for value in (digest+'  other.exe',digest+'  '+name+'\n'+digest+'  '+name,'invalid '+name):
            with self.assertRaises(ValueError): checksum_for(value.encode(),name)

    def test_installer_requires_size_header_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'test.exe'
            data=b'MZinstaller'
            file.write_bytes(data)
            sha=hashlib.sha256(data).hexdigest()
            verify_installer(file,sha,len(data))
            for digest,size in ((sha,len(data)+1),('0'*64,len(data)),(sha,True),('bad',len(data))):
                with self.assertRaises(ValueError): verify_installer(file,digest,size)
            file.write_bytes(b'not an exe')
            with self.assertRaises(ValueError): verify_installer(file,hashlib.sha256(file.read_bytes()).hexdigest(),file.stat().st_size)


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.manager=UpdateChecker(directory=self.temp.name,channel_url=REPO_URL+'/releases/latest/download/update.json')
        self.content=b'MZ'+b'x'*400000
        self.manager.info=release_info(payload(content=self.content))
        self.states=[]
        self.manager.changed.connect(lambda value:self.states.append(value['state']))

    def tearDown(self):
        self.manager.deleteLater()
        QTest.qWait(10)
        self.temp.cleanup()

    def wait_terminal(self):
        limit=time.monotonic()+4
        while self.manager.busy and time.monotonic()<limit: QTest.qWait(10)
        self.assertFalse(self.manager.busy)

    def response(self,url):
        if url.endswith('SHA256SUMS.txt'):
            data=(hashlib.sha256(self.content).hexdigest()+'  '+self.manager.info['installer']['name']).encode()
        else: data=self.content
        return io.BytesIO(data)

    def test_download_verified_then_ready_without_blocking_gui(self):
        with patch('island.update_manager.open_release',side_effect=self.response):
            self.assertTrue(self.manager.download())
            self.assertFalse(self.manager.download())
            self.wait_terminal()
        self.assertEqual(self.manager.state,'ready')
        self.assertEqual(Path(self.manager.path).read_bytes(),self.content)
        self.assertEqual(self.manager.snapshot()['progress'],100)
        self.assertIn('verifying',self.states)
        self.assertFalse(self.manager.check(),'background check must not discard ready installer')
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_public_channel_check_does_not_use_anonymous_api_quota(self):
        with patch('island.update_manager.open_release',side_effect=lambda url:io.BytesIO(json.dumps(payload()).encode())) as opened:
            self.manager.check()
            self.wait_terminal()
        self.assertEqual(self.manager.state,'available')
        opened.assert_called_once_with(REPO_URL+'/releases/latest/download/update.json')

    def test_missing_channel_never_falls_back_to_public_legacy_api(self):
        def response(url):
            if url.endswith('update.json'): raise OSError('missing legacy channel')
            return io.BytesIO(json.dumps(payload()).encode())
        with patch('island.update_manager.open_release',side_effect=response) as opened:
            self.manager.check()
            self.wait_terminal()
        self.assertEqual(self.manager.state,'error')
        self.assertEqual(opened.call_count,1)

    def test_truncated_and_overlong_files_never_become_installable(self):
        for data in (self.content[:-1],self.content+b'extra'):
            self.manager.info=release_info(payload(content=self.content))
            def response(url):
                return self.response(url) if url.endswith('SHA256SUMS.txt') else io.BytesIO(data)
            with patch('island.update_manager.open_release',side_effect=response):
                self.manager.download()
                self.wait_terminal()
            self.assertEqual(self.manager.state,'error')
            self.assertIsNone(self.manager.path)
            self.assertFalse(self.manager.install({}))
            self.assertFalse(list(Path(self.temp.name).rglob('*.part')))

    def test_cancellation_cleans_up_before_immediate_retry(self):
        manager=self.manager
        content=self.content
        class CancelOnRead(io.BytesIO):
            def read(self,count=-1):
                chunk=super().read(count)
                manager.cancel_event.set()
                return chunk
        with patch('island.update_manager.open_release',side_effect=lambda url:self.response(url) if url.endswith('SHA256SUMS.txt') else CancelOnRead(content)):
            manager.download()
            self.wait_terminal()
        self.assertEqual(manager.state,'available')
        self.assertFalse(list(Path(self.temp.name).rglob('*.part')))
        with patch('island.update_manager.open_release',side_effect=self.response):
            manager.download()
            self.wait_terminal()
        self.assertEqual(manager.state,'ready')

    def test_checksum_disagreement_does_not_fetch_executable(self):
        self.manager.info['installer']['digest']='sha256:'+'0'*64
        with patch('island.update_manager.open_release',side_effect=self.response) as opened:
            self.manager.download()
            self.wait_terminal()
            self.assertEqual(opened.call_count,1)
        self.assertEqual(self.manager.state,'error')

    def test_network_failure_and_downgrade_are_recoverable(self):
        with patch('island.update_manager.open_release',side_effect=OSError('offline')):
            self.manager.check()
            self.wait_terminal()
        self.assertEqual(self.manager.state,'error')
        self.manager.info=release_info(payload('0.4.2'),current='0.0.0')
        self.assertFalse(self.manager.download())
        self.assertEqual(self.manager.state,'error')

    def test_changed_installer_cannot_launch_helper(self):
        with patch('island.update_manager.open_release',side_effect=self.response):
            self.manager.download()
            self.wait_terminal()
        Path(self.manager.path).write_bytes(b'MZchanged')
        with patch('island.update_manager.subprocess.Popen') as launch:
            self.manager._handoff({'source_exe':'CloudIsland.exe','parent_pid':1})
            QTest.qWait(10)
            launch.assert_not_called()
        self.assertEqual(self.manager.state,'error')

    def test_corrupt_previous_result_does_not_break_startup(self):
        for data in ('[]','null','{"at": "invalid"}','{'):
            (Path(self.temp.name)/'update-result.json').write_text(data,encoding='utf-8')
            checker=UpdateChecker(directory=self.temp.name)
            self.assertEqual(checker.state,'idle')
            checker.deleteLater()


class HelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name).resolve()/'data'
        self.stage=self.directory/'updates'/__version__
        self.stage.mkdir(parents=True)
        self.source=Path(self.temp.name).resolve()/'installed'/'CloudIsland.exe'
        self.source.parent.mkdir()
        self.source.write_bytes(b'MZprevious')
        (self.source.parent/'unins000.exe').write_bytes(b'MZuninstall')
        self.installer=self.stage/f'CloudIsland-Setup-{__version__}-win-x64.exe'
        self.installer.write_bytes(b'MZinstaller')
        self.value={'version':__version__,'current_version':__version__,'installer':str(self.installer),
            'sha256':hashlib.sha256(self.installer.read_bytes()).hexdigest(),'size':self.installer.stat().st_size,
            'data_dir':str(self.directory),'source_exe':str(self.source),'parent_pid':123,
            'timer':{'remaining':900,'running':True,'deadline':time.time()+900}}
        self.manifest=self.stage/'handoff.json'
        atomic_json(self.manifest,self.value)
        for name in ('settings.json','desktop-groups.json','notes.json','shortcut-library.json'):
            (self.directory/name).write_text('{"preserved":true}',encoding='utf-8')
        owned=self.directory/'shortcuts'/'hash'/'Steam.url'
        owned.parent.mkdir(parents=True)
        owned.write_bytes(b'[InternetShortcut]\nURL=steam://run/123')

    def tearDown(self): self.temp.cleanup()

    def test_handoff_rechecks_process_version_file_and_stage(self):
        with patch('island.update_helper.process_image',return_value=self.source):
            self.assertEqual(validate_handoff(self.manifest,self.directory)['version'],__version__)
            for change in ({'version':'0.0.1'},{'current_version':'0.0.1'},{'parent_pid':False},
                           {'sha256':'0'*64},{'data_dir':str(self.source.parent)}):
                atomic_json(self.manifest,{**self.value,**change})
                with self.assertRaises(ValueError): validate_handoff(self.manifest,self.directory)
            atomic_json(self.manifest,self.value)
            outside=self.directory/'handoff.json'
            atomic_json(outside,self.value)
            with self.assertRaises(ValueError): validate_handoff(outside,self.directory)
        with patch('island.update_helper.process_image',return_value=None):
            with self.assertRaises(ValueError): validate_handoff(self.manifest,self.directory)

    def test_backup_retains_all_owned_data_without_recursive_cache(self):
        backup=snapshot_data(self.directory,__version__)
        for name in ('settings.json','desktop-groups.json','notes.json','shortcut-library.json','shortcuts/hash/Steam.url'):
            self.assertEqual((self.directory/name).read_bytes(),(backup/name).read_bytes())
        self.assertFalse((backup/'updates').exists())
        self.assertFalse((backup/'backups').exists())

    def test_install_closes_then_backs_up_validates_and_restarts(self):
        def run(command,**kwargs):
            if '--self-test' in command:
                atomic_json(Path(command[-1]),{'version':__version__,'qt':True,'winrt':True})
            else:
                self.assertIn('/TASKS=',command)
                self.assertIn('/NORESTART',command)
                self.assertTrue(list((self.directory/'backups').glob('*/desktop-groups.json')))
                self.source.write_bytes(b'MZnew')
            return Mock(returncode=0)
        with patch('island.update_helper.data_dir',return_value=self.directory), \
             patch('island.update_helper.process_image',return_value=self.source), \
             patch('island.update_helper.matching_processes',return_value=[]), \
             patch('island.instance.notify_existing',return_value=True) as quit_app, \
             patch('island.instance.query_status',return_value={'running':True,'version':__version__}), \
             patch('island.update_helper.subprocess.run',side_effect=run), \
             patch('island.update_helper.subprocess.Popen') as launch:
            self.assertEqual(apply_update(self.manifest),0)
            quit_app.assert_called_once_with('quit')
            launch.assert_called_once_with([str(self.source),'--updated'],creationflags=0x08000000)
        result=json.loads((self.directory/'update-result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'],'installed')
        self.assertEqual((Path(result['backup'])/'previous-CloudIsland.exe').read_bytes(),b'MZprevious')
        self.assertEqual(resume_timer(self.directory)['running'],True)

    def test_failed_installer_restores_previous_exe_and_keeps_data(self):
        def fail(command,**kwargs):
            self.source.write_bytes(b'MZfailed')
            return Mock(returncode=1)
        with patch('island.update_helper.data_dir',return_value=self.directory), \
             patch('island.update_helper.process_image',return_value=self.source), \
             patch('island.update_helper.matching_processes',return_value=[]), \
             patch('island.instance.notify_existing',return_value=True), \
             patch('island.instance.query_status',return_value={'running':False}), \
             patch('island.update_helper.subprocess.run',side_effect=fail), \
             patch('island.update_helper.subprocess.Popen') as launch:
            self.assertEqual(apply_update(self.manifest),1)
            self.assertEqual(self.source.read_bytes(),b'MZprevious')
            launch.assert_called_once()
        self.assertEqual(json.loads((self.directory/'notes.json').read_text()),{'preserved':True})
        self.assertEqual(json.loads((self.directory/'update-result.json').read_text(encoding='utf-8'))['status'],'error')

    def test_failed_quit_never_runs_installer_or_changes_application(self):
        with patch('island.update_helper.data_dir',return_value=self.directory), \
             patch('island.update_helper.process_image',return_value=self.source), \
             patch('island.instance.notify_existing',return_value=False), \
             patch('island.update_helper.subprocess.run') as install:
            self.assertEqual(apply_update(self.manifest),1)
            install.assert_not_called()
        self.assertFalse((self.directory/'backups').exists())
        self.assertEqual(self.source.read_bytes(),b'MZprevious')

    def test_timer_elapsed_pause_expiry_and_invalid_input(self):
        path=self.directory/'update-resume.json'
        def write(timer,**extra): atomic_json(path,{'at':1000,'version':__version__,'timer':timer,**extra})
        timer={'remaining':120,'running':True,'deadline':1120}
        write(timer)
        self.assertEqual(resume_timer(self.directory,now=1025),{'remaining':95,'running':True})
        self.assertIsNone(resume_timer(self.directory,now=1026),'resume consumed only once')
        write({**timer,'running':False})
        self.assertEqual(resume_timer(self.directory,now=1025),{'remaining':120,'running':False})
        write(timer)
        self.assertEqual(resume_timer(self.directory,now=1200),{'remaining':0,'running':True})
        for changed in ({'deadline':float('nan')},{'remaining':True},{'remaining':999999},{'running':1},{'deadline':'bad'}):
            write({**timer,**changed})
            self.assertIsNone(resume_timer(self.directory,now=1025))
        for changed in ({'at':-10000},{'at':5000},{'version':'99.0.0'}):
            write(timer,**changed)
            self.assertIsNone(resume_timer(self.directory,now=1025))
        path.write_text('[]')
        self.assertIsNone(resume_timer(self.directory,now=1025))


if __name__=='__main__': unittest.main()
