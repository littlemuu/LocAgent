"""Isolated real PostgreSQL + real parser/worker, synthetic source/fake provider."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql

from locagent_service.api import create_app
from locagent_service.config import Settings
from locagent_service.models import CreateTask
from locagent_service.store import StateConflict, TaskStore
from locagent_service.worker import execute, run_one
from test_public_pipeline import archive
import tarfile

SHA = 'a' * 40


def fixture_execute(request, channel, parent_pid):
    packed, blobs = archive([('sample.py', (
        'def serialize(value):\n'
        '    """Serialize a value to a stable string.\n'
        '    This static fixture is parsed and indexed, never imported.\n'
        '    It contains sufficient ordinary text for chunking and retrieval.\n'
        '    """\n'
        '    return str(value)\n').encode(), tarfile.REGTYPE)])
    from locagent_service import public_repo
    def resolve(*args):
        if channel.progress.get('commit'):
            raise AssertionError('Pinned commit must not be resolved again')
        return SHA
    with patch.object(public_repo, 'resolve', resolve), \
         patch.object(public_repo, 'download', return_value=(packed, blobs)):
        execute(request, channel, parent_pid)


def download_failure(request, channel, parent_pid):
    from locagent_service import public_repo
    with patch.object(public_repo, 'resolve', return_value=SHA), \
         patch.object(public_repo, 'download', side_effect=public_repo.PipelineError('download_failed')):
        execute(request, channel, parent_pid)


def waiting_execute(request, channel, parent_pid):
    try:
        channel.report({'stage': 'building_index', 'commit': SHA})
    except StateConflict:
        return
    time.sleep(10)


class PublicLifecycle(unittest.TestCase):
    def setUp(self):
        base = Settings.from_env()
        self.schema = 'public_preview_test_' + uuid4().hex
        self.store = TaskStore(Settings(base.database_url, self.schema))
        self.store.initialize()
        self.root = tempfile.TemporaryDirectory(prefix='public-preview-')
        self.environment = patch.dict(os.environ, {
            'LOCAGENT_PUBLIC_PREVIEW': '1', 'LOCAGENT_PUBLIC_ROOT': self.root.name,
            'LOCAGENT_SOURCE_ROOT': self.root.name, 'LOCAGENT_ALLOW_PAID': '0'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.root.cleanup()
        assert self.schema.startswith('public_preview_test_')
        with self.store.connect() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def create(self, **values):
        return self.store.create(CreateTask(**{
            'source_id': 'github-v1', 'repository_url': 'https://github.com/a/b',
            'problem_statement': 'Find serialize', 'timeout_seconds': 120, **values}))

    def test_api_worker_index_reuse_question_separation_and_result(self):
        with TestClient(create_app(self.store.settings)) as client:
            results = []
            for n in range(2):
                response = client.post('/tasks', json={'source_id': 'github-v1',
                    'repository_url': 'https://github.com/a/b', 'problem_statement': 'Find serialize' + ' ' * n,
                    'timeout_seconds': 120}, headers={'Idempotency-Key': 'public-' + str(n)})
                self.assertEqual(response.status_code, 202, response.text)
                replay = client.post('/tasks', json=response.json()['request'],
                                    headers={'Idempotency-Key': 'public-' + str(n)})
                self.assertEqual(replay.json()['id'], response.json()['id'])
                run_one(self.store, 'fixture', executor=fixture_execute)
                result = client.get(response.headers['Location']).json()
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(result['progress']['cache_hit'], bool(n))
                self.assertEqual(result['result']['diagnostics']['paid_calls'], 0)
                self.assertEqual(result['progress']['commit'], SHA)
                results.append(result)
            self.assertEqual(results[0]['progress']['cache_key'], results[1]['progress']['cache_key'])
            self.assertNotEqual(results[0]['progress']['source_id'], results[1]['progress']['source_id'])
            self.assertEqual(len(list(Path(self.root.name).glob('public-index-*'))), 1)

    def test_restart_persists_commit_and_fences_stale_progress(self):
        task = self.create()
        claim = self.store.claim_next('old')
        self.store.set_progress(claim, {'stage': 'resolved', 'commit': SHA})
        with self.store.connect() as connection:
            connection.execute(sql.SQL("UPDATE {} SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s").format(self.store.table), (task.id,))
        self.assertEqual(self.store.recover(), 1)
        with self.assertRaises(StateConflict):
            self.store.set_progress(claim, {'commit': 'b' * 40})
        run_one(TaskStore(self.store.settings), 'new', executor=fixture_execute)
        result = self.store.get(task.id)
        self.assertEqual(result.status, 'completed', result.error)
        self.assertEqual(result.progress['commit'], SHA)
        self.assertEqual(result.attempt, 2)
        self.assertEqual(self.store.history(task.id)[0]['outcome'], 'lease_expired')

    def test_download_failure_is_queryable_and_safe_to_retry(self):
        task = self.create()
        run_one(self.store, 'failure', executor=download_failure)
        failed = self.store.get(task.id)
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.error.code, 'download_failed')
        self.assertEqual(failed.progress['stage'], 'downloading')
        self.assertIn(failed.progress['diagnostic_id'], failed.error.message)
        retried = self.store.retry(task.id)
        self.assertEqual(retried.progress['commit'], SHA)
        self.assertEqual(retried.status, 'queued')

    def test_cancel_and_timeout_stop_supervised_child(self):
        for cancel in (True, False):
            task = self.create(timeout_seconds=2, max_attempts=1)
            if cancel:
                timer = threading.Timer(0.8, lambda: self.store.cancel(task.id))
                timer.start()
            run_one(self.store, 'bounded', lease_seconds=0.6, executor=waiting_execute)
            if cancel:
                timer.join()
            result = self.store.get(task.id)
            self.assertEqual(result.status, 'cancelled' if cancel else 'failed')
            if not cancel:
                self.assertEqual(result.error.code, 'timeout')


if __name__ == '__main__':
    unittest.main()
