"""Diagnostic-only proposed regressions; no real keyring or device operations."""
import hashlib, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from c64u_browser.credentials import Credentials, SessionCredentials
from c64u_browser.profiles import Preferences, Profile
from c64u_browser.package_self_test import _check_credential_channel, PackageSelfTestFailure
from c64u_browser.core import ArgonautCore
from c64u_browser.api import BrowserError

class CredentialChannelProposalTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        for target in ('c64u_browser.profiles.config_base','c64u_browser.platform_support.config_base'):
            p=patch(target,return_value=self.root);p.start();self.addCleanup(p.stop)
        p=patch('c64u_browser.platform_support.portable_root',return_value=None);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'ARGONAUT_DEVELOPMENT':'0'});p.start();self.addCleanup(p.stop)

    def check(self, dev):
        checks=[];_check_credential_channel({'development':dev},checks)
        self.assertEqual(3,len(checks))

    def test_stable_persistent_backend(self):self.check(False)
    def test_development_session_backend(self):
        os.environ['ARGONAUT_DEVELOPMENT']='1';self.check(True)
    def test_stable_rejects_session_backend(self):
        with patch.object(Credentials,'__new__',return_value=SessionCredentials()):
            with self.assertRaises(PackageSelfTestFailure):self.check(False)
    def test_development_rejects_stable_backend(self):
        wrong=Credentials();os.environ['ARGONAUT_DEVELOPMENT']='1'
        with patch.object(Credentials,'__new__',return_value=wrong):
            with self.assertRaises(PackageSelfTestFailure):self.check(True)
    def test_metadata_environment_disagreement_both_directions(self):
        for dev in (False,True):
            os.environ['ARGONAUT_DEVELOPMENT']='0' if dev else '1'
            with self.assertRaises(PackageSelfTestFailure) as caught:self.check(dev)
            self.assertEqual('runtime.credential_channel',caught.exception.check_id)
    def test_wrong_settings_root_both_directions(self):
        for dev in (False,True):
            os.environ['ARGONAUT_DEVELOPMENT']='1' if dev else '0'
            wrong=self.root/('argonaut' if dev else 'argonaut-development')/'config.json'
            with patch('c64u_browser.profiles.Preferences',return_value=Mock(path=wrong)):
                with self.assertRaises(PackageSelfTestFailure) as caught:self.check(dev)
                self.assertEqual('runtime.credential_settings_path',caught.exception.check_id)
    def test_alias_to_stable_is_rejected(self):
        (self.root/'argonaut').mkdir()
        (self.root/'argonaut-development').symlink_to(self.root/'argonaut',target_is_directory=True)
        os.environ['ARGONAUT_DEVELOPMENT']='1'
        with self.assertRaises(PackageSelfTestFailure):self.check(True)
    def test_stable_portable_retains_explicit_session_only_contract(self):
        with patch('c64u_browser.platform_support.portable_root',return_value=self.root),patch('c64u_browser.credentials.portable_root',return_value=self.root):
            self.check(False)
    def test_session_backend_error_or_flag_mismatch_rejected(self):
        os.environ['ARGONAUT_DEVELOPMENT']='1'
        for field,value in [('session_only',False),('error','broken')]:
            with patch.object(SessionCredentials,field,value):
                with self.assertRaises(PackageSelfTestFailure):self.check(True)
    def test_development_never_accesses_store_and_core_secret_does_not_persist(self):
        stable=Preferences();stable.usb_backup_root='/stable/sentinel';stable.save()
        before=stable.path.read_bytes()
        os.environ['ARGONAUT_DEVELOPMENT']='1'
        with patch.object(Credentials,'call',side_effect=AssertionError('Stable store accessed')):
            credentials=Credentials()
            self.assertEqual('',credentials.get('existing-stable-profile'))
            with self.assertRaises(BrowserError):credentials.set('existing-stable-profile','synthetic-secret')
            credentials.delete('existing-stable-profile')
            def observing_factory(expected):
                def factory(host, password, **kwargs):
                    self.assertTrue(password == expected, 'Unexpected credential resolution')
                    return Mock(test_connection=lambda: {})
                return factory
            core=ArgonautCore(preferences=Preferences(),
                              client_factory=observing_factory('synthetic-secret'))
            try:
                profile=core.save_profile(Profile.new('fixture','127.0.0.1'),'synthetic-secret',False)
                core.test_profile(profile)
            finally:core.close()
            self.assertNotIn(b'synthetic-secret',Preferences().path.read_bytes())
            fresh=ArgonautCore(preferences=Preferences().load(), client_factory=observing_factory(''))
            try:fresh.test_profile(profile)
            finally:fresh.close()
        self.assertEqual(before,stable.path.read_bytes())
    def test_development_secret_is_absent_after_process_termination(self):
        import subprocess, sys
        env={**os.environ,'ARGONAUT_DEVELOPMENT':'1','XDG_CONFIG_HOME':str(self.root),
             'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
        common="from c64u_browser.core import ArgonautCore; from c64u_browser.profiles import Preferences,Profile; c=ArgonautCore(preferences=Preferences().load()); "
        first="c.save_profile(Profile.new('fixture','127.0.0.1'),'synthetic-secret',False); c.close()"
        second="""
from types import SimpleNamespace
c.close()
def factory(host, password, **kwargs):
    if password: raise RuntimeError('Credential survived process termination')
    return SimpleNamespace(test_connection=lambda: {})
c=ArgonautCore(preferences=Preferences().load(), client_factory=factory)
c.test_profile(c.preferences.profiles[0])
c.close()
"""
        subprocess.run([sys.executable,'-B','-c',common+first],env=env,check=True)
        subprocess.run([sys.executable,'-B','-c',common+second],env=env,check=True)
        for path in self.root.rglob('*'):
            if path.is_file():self.assertNotIn(b'synthetic-secret',path.read_bytes())

    def test_stable_persistence_uses_backend_not_preferences(self):
        # Fake native backend, shared across two instances. Never contacts keyring.
        saved={};backend=Mock()
        backend.password_store_sync.side_effect=lambda schema,attrs,collection,label,value,cancel:saved.__setitem__(attrs['profile-id'],value) or True
        backend.password_lookup_sync.side_effect=lambda schema,attrs,cancel:saved.get(attrs['profile-id'])
        first=Credentials();first.secret=backend;first.set('fixture','synthetic-secret')
        second=Credentials();second.secret=backend
        self.assertEqual('synthetic-secret',second.get('fixture'))
        self.assertFalse(Preferences().path.exists())

if __name__=='__main__':unittest.main()
