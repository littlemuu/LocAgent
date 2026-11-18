import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import unittest
from locagent_service import demo

class SchemaNoticeTests(unittest.TestCase):
    def test_existing_database_initialized_before_v3_notice(self):
        store=MagicMock();store.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'server_version':'16-test'}
        runtime={'database_url':'postgresql://local/test'}
        with patch.object(demo,'require_own_resource',return_value=True),patch.object(demo,'CONFIG',SimpleNamespace(exists=lambda:True)),patch.object(demo,'load_runtime',return_value=runtime),patch.object(demo,'docker') as docker,patch.object(demo,'TaskStore',return_value=store),redirect_stdout(io.StringIO()) as output:
            self.assertEqual(demo.database_up(),runtime)
        store.initialize.assert_called_once_with();docker.assert_called_once_with('start',demo.CONTAINER)
        self.assertIn('schema version 3',output.getvalue());self.assertNotIn('schema version 2',output.getvalue())
    def test_failed_migration_never_reports_ready(self):
        store=MagicMock();store.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'server_version':'16-test'}
        store.initialize.side_effect=RuntimeError('migration failed')
        with patch.object(demo,'require_own_resource',return_value=True),patch.object(demo,'CONFIG',SimpleNamespace(exists=lambda:True)),patch.object(demo,'load_runtime',return_value={'database_url':'postgresql://local/test'}),patch.object(demo,'docker'),patch.object(demo,'TaskStore',return_value=store),redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(RuntimeError):demo.database_up()
        self.assertEqual(output.getvalue(),'')
