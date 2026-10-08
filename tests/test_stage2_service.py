"""Pure HTTP/fixture tests. PostgreSQL/process acceptance is a separate runner."""
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
import psycopg
from fastapi.testclient import TestClient

from locagent_service.api import create_app
from locagent_service.config import Settings
from locagent_service.fixture import localize_demo
from locagent_service.models import CreateTask, TaskView
from locagent_service.offline import offline_engine
from util.localization_contract import ErrorCode, LocalizationError, ResultStatus


class ServiceContractTests(unittest.TestCase):
    def test_default_controlled_source_and_original_statement(self):
        request = CreateTask(problem_statement='  Locate render.  ')
        self.assertEqual(request.source_id, 'demo-v1')
        self.assertEqual(request.problem_statement, '  Locate render.  ')
        self.assertTrue(request.options.suppress_repeats)

    def test_rejects_arbitrary_sources_paths_models_and_empty_statement(self):
        invalid = [{'source_id': '../repo'}, {'repo': 'other/repo'},
                   {'index_dir': '/tmp/graph'}, {'model': 'paid-model'},
                   {'problem_statement': ''}, {'problem_statement': ' \t'},
                   {'problem_statement': 123}, {'problem_statement': 'a' * 8001},
                   {'demo_scenario': 'unknown'}]
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValidationError):
                    CreateTask.model_validate({'problem_statement': 'Locate render', **values})

    def test_options_have_strict_types_and_small_demo_limits(self):
        for options in ({'max_iterations': True}, {'max_iterations': '6'},
                        {'max_iterations': 0}, {'max_iterations': 13},
                        {'suppress_repeats': 'true'}, {'suppress_repeats': 1}, {'extra': 1}):
            with self.subTest(options=options):
                with self.assertRaises(ValidationError):
                    CreateTask(problem_statement='Locate render', options=options)

    def test_settings_require_postgresql_and_safe_schema(self):
        for url in ('sqlite:///test.db', '', 'mysql://localhost/db'):
            with self.assertRaises(ValueError):
                Settings(url)
        for schema in ('public; DROP TABLE tasks', '../data', 'UPPERCASE'):
            with self.assertRaises(ValueError):
                Settings('postgresql://localhost/demo', schema)
        self.assertNotIn('secret', repr(Settings('postgresql://user:secret@localhost/demo')))


class DemoEngineTests(unittest.TestCase):
    def test_success_uses_real_loop_and_keeps_suppression_ledger(self):
        result = localize_demo(CreateTask(problem_statement='Locate render'))
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.found_files, ['demo.py'])
        self.assertEqual(result.found_entities, ['demo.py:render'])
        self.assertEqual(result.iterations, 3)
        records = result.return_records['demo.py:render']
        self.assertEqual([row['repeated'] for row in records], [False, True])
        self.assertIn('def render(', records[1]['content'])
        self.assertIn('Repeated content for', result.messages[-2]['content'])

    def test_empty_is_a_normal_engine_result(self):
        result = localize_demo(CreateTask(problem_statement='Locate render', demo_scenario='empty'))
        self.assertEqual(result.status, ResultStatus.EMPTY)
        self.assertEqual(result.found_files, [])

    def test_iteration_limit_is_distinct_from_empty(self):
        result = localize_demo(CreateTask(problem_statement='Locate render',
                                         demo_scenario='iteration_limit',
                                         options={'max_iterations': 2}))
        self.assertEqual(result.status, ResultStatus.ITERATION_LIMIT)
        self.assertEqual(result.iterations, 2)

    def test_provider_failure_is_typed_and_sanitized(self):
        with self.assertRaises(LocalizationError) as error:
            localize_demo(CreateTask(problem_statement='Locate render', demo_scenario='provider_error'))
        self.assertEqual(error.exception.code, ErrorCode.MODEL_ERROR)
        self.assertNotIn('private', error.exception.message)

    def test_offline_guard_detects_swallowed_network_attempt(self):
        with self.assertRaisesRegex(RuntimeError, 'forbidden attempt'):
            with offline_engine():
                try:
                    socket.getaddrinfo('must-not-resolve.invalid', 443)
                except RuntimeError:
                    pass


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.id = uuid4()
        self.task = TaskView(id=self.id, status='queued',
                             request=CreateTask(problem_statement='Locate render'),
                             created_at=datetime.now(timezone.utc), started_at=None,
                             finished_at=None, worker_id=None, result=None, error=None)

    def client(self, *, unavailable=False):
        task, task_id = self.task, self.id

        class FakeStore:
            def check_ready(self): pass
            def create(self, request):
                if unavailable:
                    raise psycopg.OperationalError('private database URL')
                return task
            def get(self, value): return task if value == task_id else None

        with patch('locagent_service.api.TaskStore', return_value=FakeStore()):
            return TestClient(create_app(Settings('postgresql://localhost/unit-only')))

    def test_http_acknowledges_queued_task_and_returns_not_found(self):
        with self.client() as client:
            response = client.post('/tasks', json={'problem_statement': 'Locate render'})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.headers['Location'], f'/tasks/{self.id}')
            self.assertEqual(response.json()['status'], 'queued')
            self.assertIsNone(response.json()['result'])
            self.assertEqual(client.get(response.headers['Location']).status_code, 200)
            missing = client.get(f'/tasks/{uuid4()}')
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()['error']['code'], 'not_found')

    def test_http_validation_has_stable_error_without_echoing_input(self):
        with self.client() as client:
            for body in ({'problem_statement': 'private input', 'repo': 'other/repo'},
                         {'problem_statement': 'private input', 'source_id': '/tmp/repo'},
                         {'problem_statement': ''}):
                response = client.post('/tasks', json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()['error']['code'], 'invalid_request')
                self.assertNotIn('private input', response.text)
            self.assertEqual(client.get('/tasks/not-a-uuid').status_code, 422)

    def test_http_database_failure_is_sanitized(self):
        with self.client(unavailable=True) as client:
            response = client.post('/tasks', json={'problem_statement': 'Locate render'})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error']['code'], 'database_unavailable')
            self.assertNotIn('private', response.text)

    def test_api_import_does_not_import_graph_engine(self):
        root = Path(__file__).resolve().parents[1]
        code = "import sys; import locagent_service.api; assert 'util.localizer' not in sys.modules; assert 'litellm' not in sys.modules"
        process = subprocess.run([sys.executable, '-B', '-c', code], cwd=root,
                                 capture_output=True, env={**os.environ, 'HF_HUB_OFFLINE': '1'})
        self.assertEqual(process.returncode, 0, process.stderr.decode())
