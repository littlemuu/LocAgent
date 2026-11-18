"""Offline key setup tests: synthetic values only; no supplier requests."""
import contextlib
import getpass
import io
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch
from locagent_service import local_web as web
from test_public_authorization import CONFIG


class KeySetupTests(unittest.TestCase):
    def test_missing_config_and_noninteractive_fail_before_read(self):
        with patch.object(web.getpass, 'getpass') as read:
            with self.assertRaises(web.WebError):
                web.prompt_api_key(None)
            with patch.object(web.sys.stdin, 'isatty', return_value=False):
                with self.assertRaises(web.WebError):
                    web.prompt_api_key(CONFIG)
            read.assert_not_called()

    def test_hidden_input_and_no_secret_output(self):
        out = io.StringIO()
        with patch.object(web.sys.stdin, 'isatty', return_value=True), patch.object(web.getpass, 'getpass', return_value='synthetic-only'), contextlib.redirect_stdout(out):
            self.assertEqual(web.prompt_api_key(CONFIG), 'synthetic-only')
        self.assertNotIn('synthetic-only', out.getvalue())
        self.assertIn(CONFIG['endpoint'], out.getvalue())

    def test_echo_fallback_is_error(self):
        def fallback(*args):
            warnings.warn('fallback', getpass.GetPassWarning)
            self.fail('must never reach echoed input')
        with patch.object(web.sys.stdin, 'isatty', return_value=True), patch.object(web.getpass, 'getpass', side_effect=fallback), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(getpass.GetPassWarning):
                web.prompt_api_key(CONFIG)

    def test_blank_and_control_input_rejected(self):
        for key in ['', ' synthetic ', 'synthetic\nvalue']:
            with patch.object(web.sys.stdin, 'isatty', return_value=True), patch.object(web.getpass, 'getpass', return_value=key), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(web.WebError):
                    web.prompt_api_key(CONFIG)

    def test_process_only_and_shutdown_cleanup(self):
        config = CONFIG | {'input_bound':'full-context'}
        name = config['credential_env']
        for previous in [None, 'previous-synthetic']:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
                if previous is not None:
                    os.environ[name] = previous
                file = Path(tmp) / 'provider.json'
                import json
                file.write_text(json.dumps(config))
                server = MagicMock()
                server.host = '127.0.0.1:0'
                def serve():
                    self.assertEqual(os.environ[name], 'new-synthetic')
                server.serve_forever.side_effect = serve
                with patch.object(web, 'Controller') as cls, patch.object(web, 'Server', return_value=server), patch.object(web, 'prompt_api_key', return_value='new-synthetic'), patch.object(web.signal, 'signal'), contextlib.redirect_stdout(io.StringIO()):
                    cls.return_value.config = config
                    self.assertEqual(web.main(['serve', '--provider-config', str(file), '--prompt-api-key']), 0)
                    self.assertFalse(cls.call_args.kwargs['enable_paid'])
                self.assertEqual(os.environ.get(name), previous)
                self.assertNotIn('new-synthetic', file.read_text())
                cls.return_value.close.assert_called_once()

    def test_cancel_does_not_serve(self):
        with patch.object(web, 'Controller'), patch.object(web, 'Server') as server, patch.object(web, 'prompt_api_key', side_effect=KeyboardInterrupt), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(web.main(['serve', '--prompt-api-key']), 2)
            server.return_value.serve_forever.assert_not_called()
            server.return_value.server_close.assert_called_once()

    def test_real_pty_input_is_not_echoed(self):
        import pty
        import select
        import subprocess
        import sys
        master, slave = pty.openpty()
        code = "from locagent_service.local_web import prompt_api_key; assert prompt_api_key({'endpoint':'https://provider.example/test'}) == 'synthetic-pty-only'; print('PTY_OK')"
        process = subprocess.Popen([sys.executable, '-B', '-c', code], stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        captured = b''
        try:
            import time
            deadline = time.monotonic() + 20
            sent = False
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    if not chunk:
                        break
                    captured += chunk
                    if b'API Key: ' in captured and not sent:
                        os.write(master, b'synthetic-pty-only\n')
                        sent = True
                elif process.poll() is not None:
                    break
            self.assertEqual(process.wait(timeout=2), 0)
            self.assertIn(b'PTY_OK', captured)
            self.assertNotIn(b'synthetic-pty-only', captured)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def test_reference_configuration_cannot_enable_unverified_pricing(self):
        import json
        file = Path(__file__).resolve().parents[1] / 'provider.deepseek.reference.json'
        config = json.loads(file.read_text())
        with self.assertRaises(web.WebError):
            web.config_value(config)
        self.assertNotIn('api_key', config)
