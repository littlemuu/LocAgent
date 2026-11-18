"""Portable launcher checks. No web service, provider, or network is started."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DemoPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="locagent demo launcher ")
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / "start-local-web.command", self.root)
        shutil.copy2(ROOT / "configure-api-key.command", self.root)
        self.python = self.root / "fake python"
        self.python.write_text('#!/bin/sh\nprintf "paid=%s\\n" "$LOCAGENT_ALLOW_PAID"\nprintf "%s\\n" "$@"\n')
        self.python.chmod(0o755)
        self.env = {k:v for k,v in os.environ.items() if k not in {"LOCAGENT_PYTHON", "LOCAGENT_ALLOW_PAID"}}

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args, configured=True):
        env = self.env | ({"LOCAGENT_PYTHON": str(self.python)} if configured else {})
        return subprocess.run(["sh", str(self.root / "start-local-web.command"), *args], env=env, text=True, capture_output=True)

    def test_missing_environment_has_actionable_error(self):
        result = self.call(configured=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requirements-runtime.txt", result.stderr)

    def test_explicit_interpreter_and_port_with_spaces(self):
        result = self.call("--port", "8766")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["paid=0", "-B", "-m", "locagent_service.local_web", "serve", "--port", "8766"])

    def test_config_is_optional_and_paid_flag_is_explicit(self):
        (self.root / "provider.local.json").write_text("{}")
        result = self.call("--enable-paid-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["paid=0", "-B", "-m", "locagent_service.local_web", "serve", "--provider-config", "provider.local.json", "--enable-paid-run"])

    def test_local_environment_does_not_need_external_path(self):
        binary = self.root / ".venv" / "bin" / "python"
        binary.parent.mkdir(parents=True)
        shutil.copy2(self.python, binary)
        result = self.call(configured=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("/Users/", (ROOT / "start-local-web.command").read_text())

    def test_key_launcher_forwards_port_without_secret_arguments(self):
        env = self.env | {"LOCAGENT_PYTHON": str(self.python)}
        result = subprocess.run(["sh", str(self.root / "configure-api-key.command"), "--port", "8766"], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-4:], ["--prompt-api-key", "--enable-paid-run", "--port", "8766"])
