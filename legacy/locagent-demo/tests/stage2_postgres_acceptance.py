"""Requires real PostgreSQL; every test owns a unique temporary schema."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
import io
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from threading import Barrier
import time
import unittest
from uuid import UUID, uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from locagent_service.config import Settings
from locagent_service.demo import ROOT, process_env, settings_from_runtime
from locagent_service.fixture import localize_demo
from locagent_service.models import CreateTask, PublicError
from locagent_service.store import StateConflict, TaskStore
from locagent_service.worker import run_one


class PostgresAcceptance(unittest.TestCase):
    def setUp(self):
        base = Settings.from_env() if os.environ.get('LOCAGENT_DATABASE_URL') else settings_from_runtime()
        self.schema = 'acceptance_' + uuid4().hex
        self.settings = Settings(base.database_url, self.schema)
        self.store = TaskStore(self.settings)
        self.store.initialize()
        self.artifacts = ROOT / 'outputs/stage2/acceptance' / self.schema
        self.artifacts.mkdir(parents=True)
        self.processes = []
        self.logs = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in self.logs:
            log.close()
        # Only delete this test's generated schema, never the demo/user schema.
        if self.schema.startswith('acceptance_') and len(self.schema) == 43:
            with self.store.connect() as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def create(self, scenario='success', **kwargs):
        return self.store.create(CreateTask(problem_statement='Locate render', demo_scenario=scenario,
                                             **kwargs))

    def result(self):
        with redirect_stdout(io.StringIO()):
            return localize_demo(CreateTask(problem_statement='Locate render'))

    def child(self, module, *args):
        log = (self.artifacts / f'{module.split(".")[-1]}-{len(self.processes)}.log').open('w')
        self.logs.append(log)
        process = subprocess.Popen([sys.executable, '-B', '-m', module, *args], cwd=ROOT,
                                   env=process_env(self.settings), stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process

    def api(self, port=None):
        if port is None:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
        process = self.child('locagent_service.api', '--port', str(port))
        client = httpx.Client(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=3)
        self.addCleanup(client.close)
        deadline = time.monotonic() + 20
        while True:
            try:
                if client.get('/health').status_code == 200:
                    return process, client, port
            except httpx.HTTPError:
                pass
            self.assertIsNone(process.poll(), 'API exited; inspect acceptance artifacts')
            if time.monotonic() >= deadline:
                self.fail('API startup timeout')
            time.sleep(0.1)

    def worker(self):
        process = self.child('locagent_service.worker', '--once')
        return process

    def await_worker(self, process):
        self.assertEqual(process.wait(timeout=40), 0, 'Worker failed; inspect acceptance artifacts')

    def test_creation_commits_and_new_connection_reads_exact_request(self):
        request = CreateTask(problem_statement="Locate render; '; DROP TABLE tasks; --")
        task = self.store.create(request)
        retrieved = TaskStore(self.settings).get(task.id)
        self.assertEqual(retrieved.request, request)
        self.assertEqual(retrieved.status, 'queued')
        self.assertIsNone(retrieved.result)

    def test_initialization_is_additive_and_repeatable(self):
        task = self.create()
        self.store.initialize()
        self.assertEqual(self.store.get(task.id).status, 'queued')

    def test_claim_commits_before_execution_and_does_not_reclaim_running(self):
        task = self.create()
        claim = self.store.claim_next('claim-test')
        self.assertEqual(claim.id, task.id)
        self.assertEqual(TaskStore(self.settings).get(task.id).status, 'running')
        self.assertIsNone(self.store.claim_next('another-worker'))
        with self.store.connect() as connection:
            count = connection.execute("SELECT count(*) AS n FROM pg_stat_activity "
                                       "WHERE application_name = 'locagent-stage2' "
                                       "AND state = 'idle in transaction'").fetchone()['n']
        self.assertEqual(count, 0)

    def test_concurrent_claimers_claim_one_task_exactly_once(self):
        task = self.create()
        barrier = Barrier(6)

        def claim(index):
            barrier.wait(timeout=5)
            return TaskStore(self.settings).claim_next(f'contender-{index}')

        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(claim, range(6)))
        winners = [value for value in claims if value is not None]
        self.assertEqual([value.id for value in winners], [task.id])

    def test_skip_locked_claims_next_row_without_waiting_for_oldest(self):
        first, second = self.create(), self.create()
        with self.store.connect() as connection:
            connection.execute(sql.SQL('SELECT id FROM {} WHERE id = %s FOR UPDATE').format(
                self.store.table), (first.id,))
            before = time.monotonic()
            claim = self.store.claim_next('skip-locked')
            self.assertEqual(claim.id, second.id)
            self.assertLess(time.monotonic() - before, 2)
        self.assertEqual(self.store.claim_next('oldest-now-free').id, first.id)

    def test_claim_owner_token_and_terminal_write_are_guarded(self):
        task = self.create()
        claim = self.store.claim_next('owner')
        result = self.result()
        for wrong in (replace(claim, token=uuid4()), replace(claim, worker_id='not-owner')):
            with self.assertRaises(StateConflict):
                self.store.complete(wrong, result)
        self.assertEqual(self.store.get(task.id).status, 'running')
        self.store.complete(claim, result)
        with self.assertRaises(StateConflict):
            self.store.fail(claim, PublicError(code='execution_error', message='must not overwrite'))
        retrieved = self.store.get(task.id)
        self.assertEqual(retrieved.status, 'completed')
        self.assertEqual(retrieved.result.model_dump(), result.to_dict())
        self.assertIsNone(retrieved.error)

    def test_database_rejects_inconsistent_terminal_payloads(self):
        task = self.create()
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.store.connect() as connection:
                connection.execute(sql.SQL("UPDATE {} SET status = 'completed' WHERE id = %s").format(
                    self.store.table), (task.id,))
        self.store.claim_next('constraint-test')
        for status, result, error in (('completed', {}, None),
                                      ('completed', {'status': 'unknown'}, None),
                                      ('completed', {'status': None}, None),
                                      ('failed', None, {'message': 'missing code'})):
            with self.subTest(status=status, result=result, error=error):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with self.store.connect() as connection:
                        connection.execute(sql.SQL('UPDATE {} SET status = %s, result = %s, error = %s, '
                                                   'finished_at = clock_timestamp() WHERE id = %s').format(
                            self.store.table), (status, Jsonb(result) if result is not None else None,
                                               Jsonb(error) if error is not None else None, task.id))
        self.assertEqual(self.store.get(task.id).status, 'running')

    def test_worker_persists_sanitized_engine_error(self):
        task = self.create('provider_error')
        with redirect_stdout(io.StringIO()):
            self.assertTrue(run_one(self.store, 'error-worker'))
        retrieved = self.store.get(task.id)
        self.assertEqual(retrieved.status, 'failed')
        self.assertEqual(retrieved.error.code, 'model_error')
        self.assertNotIn('private', retrieved.error.message)
        self.assertIsNone(retrieved.result)
        self.assertIsNotNone(retrieved.finished_at)

    def test_empty_and_limit_are_distinct_completed_engine_outcomes(self):
        for scenario in ('empty', 'iteration_limit'):
            with self.subTest(scenario=scenario):
                task = self.create(scenario, options={'max_iterations': 2})
                with redirect_stdout(io.StringIO()):
                    self.assertTrue(run_one(self.store, 'outcome-worker'))
                retrieved = self.store.get(task.id)
                self.assertEqual(retrieved.status, 'completed')
                self.assertEqual(retrieved.result.status, scenario)
                self.assertEqual(retrieved.result.found_files, [])
                self.assertIsNone(retrieved.error)

    def test_e2e_api_queues_worker_executes_and_restart_keeps_history(self):
        api, client, port = self.api()
        before = time.monotonic()
        response = client.post('/tasks', json={'problem_statement': 'Locate render'})
        self.assertEqual(response.status_code, 202)
        self.assertLess(time.monotonic() - before, 2)
        task_id = response.json()['id']
        location = response.headers['Location']
        self.assertEqual(client.get(location).json()['status'], 'queued')
        self.assertEqual(str(self.store.get(UUID(task_id)).id), task_id)
        worker = self.worker()
        self.assertNotEqual(worker.pid, api.pid)
        self.await_worker(worker)
        task = client.get(location).json()
        self.assertEqual(task['status'], 'completed')
        self.assertIn(f'worker-{worker.pid}-', task['worker_id'])
        self.assertEqual(task['result']['found_files'], ['demo.py'])
        self.assertEqual(task['result']['found_entities'], ['demo.py:render'])
        ledger = task['result']['return_records']['demo.py:render']
        self.assertEqual([row['repeated'] for row in ledger], [False, True])
        self.assertIn('def render(', ledger[1]['content'])
        api.terminate()
        self.assertIn(api.wait(timeout=10), (0, -signal.SIGTERM))
        restarted, client2, _ = self.api(port)
        self.assertNotEqual(restarted.pid, api.pid)
        self.assertEqual(client2.get(location).json(), task)
        queued = client2.post('/tasks', json={'problem_statement': 'Another independent attempt'}).json()
        self.assertEqual(client2.get(f'/tasks/{queued["id"]}').json()['status'], 'queued')
        self.await_worker(self.worker())
        self.assertEqual(client2.get(f'/tasks/{queued["id"]}').json()['status'], 'completed')

    def test_e2e_failure_is_stored_and_queryable_over_http(self):
        _, client, _ = self.api()
        response = client.post('/tasks', json={'problem_statement': 'Locate render',
                                              'demo_scenario': 'provider_error'})
        self.assertEqual(response.status_code, 202)
        self.await_worker(self.worker())
        retrieved = client.get(response.headers['Location'])
        self.assertEqual(retrieved.status_code, 200)
        task = retrieved.json()
        self.assertEqual(task['status'], 'failed')
        self.assertEqual(task['error']['code'], 'model_error')
        self.assertNotIn('private', retrieved.text)
        self.assertIsNone(task['result'])

    def test_e2e_two_worker_processes_have_distinct_claims(self):
        _, client, _ = self.api()
        locations = []
        for scenario in ('empty', 'iteration_limit'):
            response = client.post('/tasks', json={'problem_statement': 'Locate render',
                                                  'demo_scenario': scenario,
                                                  'options': {'max_iterations': 2}})
            self.assertEqual(response.status_code, 202)
            locations.append(response.headers['Location'])
        workers = [self.worker(), self.worker()]
        for worker in workers:
            self.await_worker(worker)
        tasks = [client.get(location).json() for location in locations]
        self.assertEqual([task['result']['status'] for task in tasks], ['empty', 'iteration_limit'])
        self.assertTrue(all(task['status'] == 'completed' for task in tasks))
        self.assertEqual(len({task['worker_id'] for task in tasks}), 2)

    def test_e2e_killed_worker_does_not_reclaim_before_lease_expiry(self):
        _, client, _ = self.api()
        response = client.post('/tasks', json={'problem_statement': 'Crash limitation demonstration'})
        location = response.headers['Location']
        worker = self.worker()
        deadline = time.monotonic() + 20
        while client.get(location).json()['status'] == 'queued':
            self.assertIsNone(worker.poll())
            if time.monotonic() >= deadline:
                self.fail('Worker did not claim queued task')
            time.sleep(0.01)
        self.assertEqual(client.get(location).json()['status'], 'running')
        worker.kill()
        self.assertNotEqual(worker.wait(timeout=5), 0)
        replacement = self.worker()
        self.await_worker(replacement)
        task = client.get(location).json()
        self.assertEqual(task['status'], 'running')
        self.assertIsNone(task['result'])
        self.assertIsNone(task['error'])
        self.assertIsNone(task['finished_at'])
