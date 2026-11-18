import contextlib
import getpass
import io
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings

from readonly_agent import local_env
from readonly_agent.live_run import run_pair

FAKE = 'SYNTHETIC-LOCAL-ENV-NOT-A-CREDENTIAL'


class LocalEnvTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project, self.legacy = self.root/'project', self.root/'legacy'
        for root in (self.project, self.legacy):
            root.mkdir()
            (root/'.gitignore').write_text('.env\n.env.*\n!.env.example\n')

    def save(self, root, text):
        p = root/'.env'
        p.write_text(text)
        p.chmod(0o600)
        return p

    def test_reuse_legacy_without_copy_prompt_or_environment_changes(self):
        p = self.save(self.legacy, '# retain\nDEEPSEEK_API_KEY='+FAKE+'\nLOCAGENT_ALLOW_PAID=1\n')
        before = p.read_bytes(), p.stat().st_mtime_ns
        with patch.dict(os.environ, {}, clear=True), patch.object(local_env.getpass, 'getpass') as prompt:
            output = local_env.setup(project=self.project, legacy=self.legacy)
            self.assertEqual(dict(os.environ), {})
            prompt.assert_not_called()
        self.assertNotIn(FAKE, output)
        self.assertEqual(before, (p.read_bytes(), p.stat().st_mtime_ns))
        self.assertFalse((self.project/'.env').exists())

    def test_local_priority_and_no_fallback_for_invalid_local(self):
        self.save(self.legacy, 'DEEPSEEK_API_KEY='+FAKE)
        local = self.save(self.project, 'DEEPSEEK_API_KEY=short')
        selected = local_env.select_path(self.project, self.legacy)
        self.assertEqual(selected, local)
        with self.assertRaises(ValueError):
            local_env.load_key(selected)

    def test_parser_quoted_key_and_ignored_legacy_flags(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'DO-NOT-USE-ENV'}, clear=True):
            key = local_env.parse_key('export DEEPSEEK_API_KEY="'+FAKE+'" # comment\nLOCAGENT_ALLOW_PAID=1\n')
            self.assertEqual(key, FAKE)
            self.assertEqual(os.environ['DEEPSEEK_API_KEY'], 'DO-NOT-USE-ENV')
            self.assertNotIn('LOCAGENT_ALLOW_PAID', os.environ)

    def test_bad_duplicate_missing_interpolated_keys_rejected_without_echo(self):
        for text in ('DEEPSEEK_API_KEY='+FAKE+'\nDEEPSEEK_API_KEY='+FAKE,
                     "DEEPSEEK_API_KEY='unclosed", 'OTHER=value',
                     'DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}', 'DEEPSEEK_API_KEY=`do-not-execute`'):
            with self.subTest(kind=text[:10]):
                with self.assertRaises(ValueError) as error:
                    local_env.parse_key(text)
                self.assertNotIn(FAKE, str(error.exception))

    def test_permissions_symlink_hardlink_and_oversize_rejected(self):
        p = self.save(self.project, 'DEEPSEEK_API_KEY='+FAKE)
        p.chmod(0o644)
        with self.assertRaises(PermissionError): local_env.load_key(p)
        p.chmod(0o600)
        os.link(p, self.root/'hardlink')
        with self.assertRaises(PermissionError): local_env.load_key(p)
        (self.root/'hardlink').unlink()
        other = self.legacy/'.env'
        other.symlink_to(p)
        with self.assertRaises(PermissionError): local_env.load_key(other)
        p.write_bytes(b'x'*(local_env.MAX_BYTES+1))
        with self.assertRaises(PermissionError): local_env.load_key(p)

    def test_missing_ignore_rules_refuse_before_secret_read_or_write(self):
        p = self.save(self.project, 'DEEPSEEK_API_KEY='+FAKE)
        (self.project/'.gitignore').unlink()
        with patch.object(local_env.os, 'open') as opened:
            with self.assertRaises(PermissionError): local_env.load_key(p)
            with self.assertRaises(PermissionError): local_env.write_new(p, FAKE)
            opened.assert_not_called()

    def test_git_ignore_and_tracked_file_fence(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True, capture_output=True)
        p = self.project/'.env'
        local_env.write_new(p, FAKE)
        local_env.check_ignored(p)
        subprocess.run(['git','-C',str(self.project),'add','-f','.env'],check=True,capture_output=True)
        with self.assertRaisesRegex(PermissionError, 'tracked'):
            local_env.load_key(p)

    def test_new_setup_hidden_prompt_mode_and_exclusive_creation(self):
        with patch.object(local_env.sys.stdin, 'isatty', return_value=True), \
             patch.object(local_env.getpass, 'getpass', return_value=FAKE):
            output = local_env.setup(project=self.project, legacy=self.legacy)
        p = self.project/'.env'
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(local_env.load_key(p), FAKE)
        self.assertNotIn(FAKE, output)
        before = p.read_bytes()
        with self.assertRaises(FileExistsError): local_env.write_new(p, FAKE+'-other')
        self.assertEqual(p.read_bytes(), before)

    def test_no_tty_or_echo_fallback_never_saves(self):
        with patch.object(local_env.sys.stdin, 'isatty', return_value=False), \
             patch.object(local_env.getpass, 'getpass') as prompt:
            with self.assertRaises(PermissionError): local_env.setup(project=self.project, legacy=self.legacy)
            prompt.assert_not_called()
        def fallback(*args):
            warnings.warn('synthetic fallback', getpass.GetPassWarning)
        with patch.object(local_env.sys.stdin, 'isatty', return_value=True), \
             patch.object(local_env.getpass, 'getpass', side_effect=fallback):
            with self.assertRaises(getpass.GetPassWarning):
                local_env.setup(project=self.project, legacy=self.legacy)
        self.assertFalse((self.project/'.env').exists())

    def test_live_admission_checked_before_loading_and_no_implicit_source(self):
        authority = SimpleNamespace(read=lambda h: {'plan':{'version':1}},
                                    folder=lambda h: self.root/'authority',
                                    claim=lambda h: (_ for _ in ()).throw(RuntimeError('stop_before_transport')))
        with patch('readonly_agent.live_run.Authority', return_value=authority), \
             patch('readonly_agent.live_run.pilot', return_value=(None,None,{'version':1})), \
             patch('readonly_agent.live_run.sys.stdin.isatty', return_value=True), \
             patch('readonly_agent.local_env.load_selected_key', return_value=FAKE) as load:
            for flags in ({}, {'env_api_key':True}, {'live':True},
                          {'live':True,'env_api_key':True,'prompt_api_key':True}):
                with self.assertRaises(PermissionError): run_pair('unused', **flags)
            load.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'stop_before_transport'):
                run_pair('unused', live=True, env_api_key=True)
            load.assert_called_once_with()

    def test_bad_or_consumed_grant_and_non_tty_never_load_secret(self):
        for failure in ('read', 'mismatch', 'claimed', 'tty'):
            with self.subTest(failure=failure):
                folder=self.root/failure;folder.mkdir()
                if failure=='claimed': (folder/'claim.json').touch()
                authority=SimpleNamespace(folder=lambda h:folder,
                    read=lambda h:{'plan':{'version':1}})
                if failure=='read':
                    authority.read=lambda h: (_ for _ in ()).throw(PermissionError('invalid_grant'))
                plan={'version':2 if failure=='mismatch' else 1}
                with patch('readonly_agent.live_run.Authority',return_value=authority), \
                     patch('readonly_agent.live_run.pilot',return_value=(None,None,plan)), \
                     patch('readonly_agent.live_run.sys.stdin.isatty',return_value=failure!='tty'), \
                     patch('readonly_agent.local_env.load_selected_key') as load:
                    with self.assertRaises(PermissionError): run_pair('unused',live=True,env_api_key=True)
                    load.assert_not_called()

    def test_cli_errors_only_print_safe_status_and_no_traceback(self):
        self.save(self.project, "DEEPSEEK_API_KEY='"+FAKE)
        out,err=io.StringIO(),io.StringIO()
        with patch.object(local_env, 'select_path', return_value=self.project/'.env'), \
             patch.object(local_env.sys, 'argv', ['local_env','check']), \
             contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as failure: local_env.cli()
        self.assertNotIn(FAKE, out.getvalue()+err.getvalue()+str(failure.exception))
        self.assertNotIn('Traceback', err.getvalue())
        self.assertIn('Local configuration stopped: ValueError.', err.getvalue())


if __name__ == '__main__':
    unittest.main()
