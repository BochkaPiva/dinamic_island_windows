"""Security boundaries, non-destructive entitlements and complete-runtime recovery."""
import base64
import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from PySide6.QtCore import QCoreApplication
from island.entitlements import FeatureAccess,verify_license
from island.signed_payload import verify_envelope
from island.desktop_groups import GroupStore
from island.update_helper import snapshot_application,restore_application,remove_runtime
from island.update_manager import UpdateChecker
from tools.release_readiness import problems


class CommercialFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.folder=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate() # Ephemeral test key, never shipped as an activation key.
        self.keys={'test':base64.b64encode(self.key.public_key().public_bytes_raw()).decode()}
        self.access=FeatureAccess(self.folder,distribution='commercial',keys=self.keys,clock=lambda:1000)

    def tearDown(self): self.temp.cleanup()

    def envelope(self,changes=None,purpose='cloud-hub/license/v1'):
        payload={'schema':1,'product':'cloud-hub','installation_id':self.access.installation_id,
            'edition':'pro','issued_at':900,'not_before':900,'offline_until':2000,'paid_until':4000,
            'features':['island.focus'],'limits':{'desktop.groups.active':None}}
        payload.update(changes or {})
        raw=json.dumps(payload).encode()
        return {'key_id':'test','payload':base64.b64encode(raw).decode(),
            'signature':base64.b64encode(self.key.sign(purpose.encode()+b'\0'+raw)).decode()}

    def test_free_defaults_without_network_and_no_settings_flag_bypass(self):
        (self.folder/'settings.json').write_text('{"is_pro":true,"edition":"pro"}')
        self.access.reload()
        self.assertEqual(self.access.grant.edition,'free')
        self.assertTrue(self.access.capacity('desktop.groups.active',1).allowed)
        self.assertFalse(self.access.capacity('desktop.groups.active',2).allowed)
        self.assertFalse(self.access.feature('island.focus').allowed)
        self.assertFalse(self.access.feature('unregistered.feature').allowed)
        self.assertFalse(self.access.capacity('unregistered.limit',0).allowed)

    def test_valid_grant_persists_and_expires_without_deleting_groups(self):
        store=GroupStore(self.folder,collect_desktop=False,access=self.access)
        self.assertEqual(len(store.groups),2)
        self.assertIsNone(store.add('Third'))
        self.access.install_license(self.envelope())
        self.assertIsNotNone(store.add('Third'))
        before=store.path.read_bytes()
        self.assertTrue(self.access.feature('island.focus').allowed)
        self.assertFalse(self.access.feature('island.video').allowed,'No feature escalation from edition label')
        self.access.clock=lambda:2000
        self.assertFalse(self.access.feature('island.focus').allowed)
        self.assertEqual(len(self.access.active_ids(store.groups)),2)
        self.assertEqual(store.path.read_bytes(),before)
        self.assertEqual(len(store.groups),3)
        self.assertIsNone(store.add('Fourth'))

    def test_identity_stable_but_not_serial_number_based(self):
        other=FeatureAccess(self.folder,distribution='commercial',keys=self.keys)
        self.assertEqual(self.access.installation_id,other.installation_id)
        self.assertFalse((self.folder/'settings.json').exists())
        self.assertNotIn(self.access.installation_id.encode(),(self.folder/'installation-id.bin').read_bytes())

    def test_corrupt_protected_identity_invalidates_an_old_license(self):
        self.access.install_license(self.envelope())
        (self.folder/'installation-id.bin').write_bytes(b'copied or corrupt identity')
        other=FeatureAccess(self.folder,distribution='commercial',keys=self.keys,clock=lambda:1000)
        self.assertNotEqual(self.access.installation_id,other.installation_id)
        self.assertEqual(other.grant.edition,'free')

    def test_windows_storage_failure_keeps_app_usable_without_granting_pro(self):
        with patch('island.entitlements.protect',side_effect=OSError('unavailable')):
            other=FeatureAccess(self.folder/'blocked',distribution='commercial',keys=self.keys,clock=lambda:1000)
        self.assertFalse(other.storage_available)
        self.assertEqual(other.grant.edition,'free')
        self.assertFalse(other.feature('island.focus').allowed)

    def test_rejects_forgery_wrong_device_wrong_product_and_dates(self):
        cases=[{'product':'other'},{'installation_id':'other'},{'edition':'enterprise'},
            {'offline_until':1000},{'not_before':1100},{'paid_until':950},
            {'issued_at':True},{'offline_until':float('nan')},{'limits':{'desktop.groups.active':True}},
            {'features':['island.unregistered']},{'limits':{'unregistered':None}}]
        for change in cases:
            with self.subTest(change=change),self.assertRaises(ValueError):
                verify_license(self.envelope(change),self.keys,self.access.installation_id,1000)
        envelope=self.envelope();envelope['payload']=base64.b64encode(b'{}').decode()
        with self.assertRaises(ValueError): self.access.install_license(envelope)
        with self.assertRaises(ValueError): self.access.install_license(self.envelope(purpose='cloud-hub/update/v1'))
        with self.assertRaises(ValueError): verify_license(self.envelope(),{},self.access.installation_id,1000)

    def test_missing_cap_does_not_mean_unlimited(self):
        self.access.install_license(self.envelope({'limits':{}}))
        self.assertFalse(self.access.capacity('desktop.groups.active',2).allowed)

    def test_malformed_cache_falls_back_to_free(self):
        (self.folder/'license.json').write_text('{"key_id":[]}')
        self.access.reload()
        self.assertEqual(self.access.grant.edition,'free')

    def test_duplicate_signed_keys_and_overlarge_envelopes_rejected(self):
        with self.assertRaises(ValueError): verify_envelope('{"key_id":1,"key_id":2}',self.keys,'x')
        with self.assertRaises(ValueError): verify_envelope('x'*65537,self.keys,'x')

    def test_preview_preserves_all_current_features(self):
        preview=FeatureAccess(self.folder,distribution='preview')
        self.assertEqual(preview.grant.edition,'preview')
        self.assertTrue(preview.feature('island.focus').allowed)
        self.assertTrue(preview.capacity('desktop.groups.active',30).allowed)

    def test_unconfigured_private_build_never_polls_public_release_channel(self):
        checker=UpdateChecker(directory=self.folder,channel_url='')
        with patch('island.update_manager.open_release') as request:
            self.assertFalse(checker.check())
            request.assert_not_called()
        self.assertEqual(checker.state,'current')

    def test_community_build_uses_the_public_release_channel(self):
        from island import build_config
        checker=UpdateChecker(directory=self.folder)
        self.assertEqual(build_config.DISTRIBUTION,'community')
        self.assertEqual(checker.channel_url,
            'https://github.com/BochkaPiva/dinamic_island_windows/releases/latest/download/update.json')

    def test_sales_release_fails_closed_until_keys_and_legal_configuration_exist(self):
        self.assertEqual(problems(),[])
        self.assertIn('Preview distribution cannot be sold',problems(sales=True))
        self.assertIn('Not approved: code_rights',problems(sales=True))

    def test_runtime_backup_and_restore_replaces_the_entire_matching_runtime(self):
        install=self.folder/'installed';install.mkdir()
        target=install/'CloudIsland.exe';target.write_bytes(b'old exe')
        runtime=install/'_internal';runtime.mkdir()
        (runtime/'Qt6Core.dll').write_bytes(b'old Qt')
        backup=self.folder/'backup';backup.mkdir()
        snapshot_application(target,backup)
        target.write_bytes(b'bad new exe')
        (runtime/'Qt6Core.dll').write_bytes(b'new Qt')
        (runtime/'obsolete.dll').write_bytes(b'extra')
        self.assertTrue(restore_application(target,backup))
        self.assertEqual(target.read_bytes(),b'old exe')
        self.assertEqual((runtime/'Qt6Core.dll').read_bytes(),b'old Qt')
        self.assertFalse((runtime/'obsolete.dll').exists())
        with self.assertRaises(ValueError): remove_runtime(self.folder,install)

    def test_handoff_stages_runtime_with_helper(self):
        from island.update_manager import UpdateChecker
        install=self.folder/'installed';install.mkdir()
        source=install/'CloudIsland.exe';source.write_bytes(b'MZapp')
        runtime=install/'_internal';runtime.mkdir()
        (runtime/'Qt6Core.dll').write_bytes(b'Qt')
        stage=self.folder/'updates'/'9.0.0';stage.mkdir(parents=True)
        installer=stage/'CloudIsland-Setup-9.0.0-win-x64.exe';installer.write_bytes(b'MZsetup')
        import hashlib
        checker=UpdateChecker(directory=self.folder)
        checker.path=str(installer);checker.sha256=hashlib.sha256(installer.read_bytes()).hexdigest()
        checker.info={'version':'9.0.0','installer':{'size':installer.stat().st_size}}
        with patch('island.update_manager.subprocess.Popen',return_value=Mock(wait=lambda timeout:0)):
            checker._handoff({'source_exe':str(source),'parent_pid':123})
        self.assertEqual((stage/'_internal'/'Qt6Core.dll').read_bytes(),b'Qt')
        self.assertTrue((stage/'CloudHub-UpdateHelper.exe').exists())


if __name__=='__main__': unittest.main()
