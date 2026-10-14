"""Isolated PostgreSQL/worker acceptance; transport is always an explicit stub."""
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql
from locagent_service import public_authorization as auth, public_pipeline as pipeline, public_repo
from locagent_service.api import create_app
from locagent_service.config import Settings
from locagent_service.models import CreateTask
from locagent_service.store import StateConflict, TaskStore
from locagent_service.worker import execute, run_one
from test_public_authorization import prepare_grant, raw_response
from test_public_pipeline import archive


def stub_execute(request, channel, parent_pid):
    with patch.object(auth, 'exchange', lambda *_: raw_response()):
        execute(request, channel, parent_pid)


def reserved_execute(request, channel, parent_pid):
    request = CreateTask.model_validate(request)
    mode = request.timeout_seconds
    def send(*_):
        if mode == 9:
            os._exit(77)
        if mode == 10:
            raise TimeoutError('stub-only disconnect')
        time.sleep(30)
        return raw_response()
    try:
        provider = auth.AuthorizedProvider(request, channel.claim, channel.report, raw_completion=send)
        provider(messages=[])
    except Exception:
        channel.send(('failed', {'code': 'stub_error', 'message': 'Synthetic interruption'}))


class AuthorizedLifecycle(unittest.TestCase):
    def setUp(self):
        base = Settings.from_env()
        self.schema = 'public_preview_auth_' + uuid4().hex
        self.store = TaskStore(Settings(base.database_url, self.schema))
        self.store.initialize()
        self.root = tempfile.TemporaryDirectory(prefix='public-auth-db-')
        root = Path(self.root.name)
        self.environment = patch.dict(os.environ, {
            'LOCAGENT_PUBLIC_PREVIEW': '1', 'LOCAGENT_PUBLIC_ROOT': str(root/'sources'),
            'LOCAGENT_SOURCE_ROOT': str(root/'sources'), 'LOCAGENT_PUBLIC_AUTH_ROOT': str(root/'authority'),
            'LOCAGENT_PUBLIC_LIVE': '1', 'LOCAGENT_ALLOW_PAID': '0',
            'LITELLM_LOCAL_MODEL_COST_MAP': 'True'})
        self.environment.start()
        self.plan, self.request = prepare_grant()

    def tearDown(self):
        self.environment.stop()
        self.root.cleanup()
        assert self.schema.startswith('public_preview_auth_')
        with self.store.connect() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def create(self, timeout=90):
        self.request.timeout_seconds = timeout
        return self.store.create(self.request, validate_new=auth.validate_request)

    def assert_review(self, task):
        current = self.store.get(task.id)
        self.assertEqual(current.status, 'needs_review')
        self.assertEqual(current.error.code, 'outcome_unknown')
        self.assertEqual(current.attempt, 1)
        with self.assertRaises(StateConflict):
            self.store.retry(task.id)
        self.assertIsNone(self.store.claim_next('no-replay'))

    def test_http_gate_then_real_parser_worker_stub_result_and_settlement(self):
        packed, blobs = archive([('sample.py', b'def serialize(value):\n    """Serialize values into a stable string representation for transport."""\n    return str(value)\n', tarfile.REGTYPE)])
        with patch.object(public_repo, 'download', return_value=(packed, blobs)):
            manifest = pipeline.index('https://github.com/a/b', 'a'*40, lambda **_: None)
        manifest['task']['problem_statement'] = 'Find serialize'
        self.plan, self.request = prepare_grant(manifest=manifest)
        self.request.timeout_seconds = 120
        with TestClient(create_app(self.store.settings)) as client:
            payload = self.request.model_dump(mode='json')
            with patch.dict(os.environ, {'LOCAGENT_PUBLIC_LIVE': '0'}):
                self.assertEqual(client.post('/tasks', json=payload).status_code, 422)
            changed = payload | {'problem_statement': 'unapproved question'}
            self.assertEqual(client.post('/tasks', json=changed).status_code, 422)
            response = client.post('/tasks', json=payload, headers={'Idempotency-Key': 'authorized-stub'})
            self.assertEqual(response.status_code, 202, response.text)
            run_one(self.store, 'authorized-stub', executor=stub_execute)
            result = client.get(response.headers['Location']).json()
            self.assertEqual(result['status'], 'completed', result)
            self.assertEqual(result['result']['status'], 'empty')
            self.assertEqual(result['progress']['provider'], 'operator-authorized')
            marker, _ = auth.grant(self.request.authorization_id)
            state = auth.read_json(Path(marker['ledger_path']))
            self.assertTrue(state['finished'])
            self.assertEqual(state['spent'], '0.00002')
            self.assertEqual(len(state['calls']), 1)
            replay = client.post('/tasks', json=payload, headers={'Idempotency-Key': 'authorized-stub'})
            self.assertEqual(replay.json()['id'], result['id'])

    def test_expired_claim_never_requeues_authorized_task(self):
        task = self.create()
        claim = self.store.claim_next('old')
        with self.store.connect() as connection:
            connection.execute(sql.SQL("UPDATE {} SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s").format(self.store.table), (task.id,))
        self.store.recover()
        self.assert_review(task)
        with self.assertRaises(StateConflict):
            self.store.set_progress(claim, {'stage': 'stale'})

    def test_queued_cancel_has_no_call_and_keeps_normal_cancel_semantics(self):
        task = self.create()
        self.assertEqual(self.store.cancel(task.id).status, 'cancelled')
        self.assertIsNone(self.store.claim_next('cancelled'))
        marker, _ = auth.grant(self.request.authorization_id)
        self.assertEqual(auth.read_json(Path(marker['ledger_path']))['calls'], [])

    def test_running_cancel_preserves_unknown_reservation_and_stops_worker(self):
        task = self.create()
        failures=[]
        def cancel_after_reserve():
            try:
                for _ in range(150):
                    current = self.store.get(task.id)
                    if (current.progress or {}).get('stage') == 'provider_inflight':
                        self.store.cancel(task.id)
                        return
                    time.sleep(.1)
                failures.append('No reservation observed')
            except Exception as exc:
                failures.append(type(exc).__name__)
        thread = threading.Thread(target=cancel_after_reserve)
        thread.start()
        run_one(self.store, 'cancel-stub', executor=reserved_execute)
        thread.join()
        self.assertEqual(failures, [])
        self.assert_review(task)
        marker, _ = auth.grant(self.request.authorization_id)
        state = auth.read_json(Path(marker['ledger_path']))
        self.assertEqual(len(state['calls']), 1)
        self.assertGreater(auth.money(state['reserved']), 0)

    def test_supervisor_timeout_never_replays(self):
        task = self.create(timeout=2)
        run_one(self.store, 'timeout-stub', executor=reserved_execute)
        self.assert_review(task)

    def test_crash_after_reservation_retains_call_and_never_replays(self):
        task = self.create(timeout=9)
        run_one(self.store, 'crash-stub', executor=reserved_execute)
        self.assert_review(task)
        marker, _ = auth.grant(self.request.authorization_id)
        self.assertEqual(len(auth.read_json(Path(marker['ledger_path']))['calls']), 1)

    def test_transport_timeout_is_unknown_and_never_replays(self):
        task = self.create(timeout=10)
        run_one(self.store, 'disconnect-stub', executor=reserved_execute)
        self.assert_review(task)
        marker, _ = auth.grant(self.request.authorization_id)
        state = auth.read_json(Path(marker['ledger_path']))
        self.assertTrue(state['halted'])
        self.assertEqual(state['calls'][0]['status'], 'outcome_unknown')


if __name__ == '__main__':
    unittest.main()
