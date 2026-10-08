"""Short transactions, expiring claims, fencing, bounded safe retries and audit."""
from dataclasses import dataclass
from pathlib import Path
import re
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from locagent_service.config import Settings
from locagent_service.models import CreateTask, PublicError, TaskView


class StateConflict(Exception):
    """The claim expired or a terminal transition already won."""


class IdempotencyConflict(StateConflict):
    """The key already represents a different normalized request."""


@dataclass(frozen=True)
class Claim:
    id: UUID
    request: dict
    worker_id: str
    token: UUID
    attempt: int = 1


class TaskStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.table = sql.Identifier(settings.schema, 'tasks')
        self.attempts = sql.Identifier(settings.schema, 'attempts')

    def connect(self):
        return psycopg.connect(self.settings.database_url, row_factory=dict_row,
                               connect_timeout=3, options='-c statement_timeout=5000',
                               application_name='locagent-stage2')

    def initialize(self):
        migrations = Path(__file__).with_name('migrations')
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                      ('locagent-stage2-init:' + self.settings.schema,))
            exists = c.execute('SELECT to_regclass(%s) AS name',
                               (self.settings.schema + '.schema_version',)).fetchone()['name']
            if not exists:
                c.execute(sql.SQL((migrations/'001_tasks.sql').read_text()).format(
                    schema=sql.Identifier(self.settings.schema)))
            versions = c.execute(sql.SQL('SELECT version FROM {}').format(
                sql.Identifier(self.settings.schema, 'schema_version'))).fetchall()
            if versions == [{'version': 1}]:
                c.execute(sql.SQL((migrations/'002_lifecycle.sql').read_text()).format(
                    schema=sql.Identifier(self.settings.schema)))
            elif versions != [{'version': 2}]:
                raise RuntimeError('Unsupported database schema version')
        self.check_ready()

    def check_ready(self):
        with self.connect() as c:
            rows = c.execute(sql.SQL('SELECT version FROM {}').format(
                sql.Identifier(self.settings.schema, 'schema_version'))).fetchall()
        if rows != [{'version': 2}]:
            raise RuntimeError('Run the explicit database migration first')

    def create(self, request: CreateTask, idempotency_key: str | None = None,
               validate_new=None) -> TaskView:
        if idempotency_key is not None and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', idempotency_key):
            raise ValueError('Invalid Idempotency-Key')
        payload = request.model_dump(mode='json')
        with self.connect() as c:
            if idempotency_key is not None:
                # Serialize validation/creation for the key; uniqueness remains the backstop.
                c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',
                          (self.settings.schema + ':idempotency:' + idempotency_key,))
                existing = c.execute(sql.SQL('SELECT * FROM {} WHERE idempotency_key=%s').format(
                    self.table), (idempotency_key,)).fetchone()
                if existing is not None:
                    if CreateTask.model_validate(existing['request']).model_dump(mode='json') != payload:
                        raise IdempotencyConflict('Idempotency key belongs to another request')
                    return TaskView.model_validate(existing)
            if validate_new is not None:
                validate_new(request)
            row = c.execute(sql.SQL("""
                INSERT INTO {} (id, request, idempotency_key) VALUES (%s,%s,%s)
                ON CONFLICT (idempotency_key) DO NOTHING RETURNING *
            """).format(self.table), (uuid4(), Jsonb(payload), idempotency_key)).fetchone()
            if row is None:
                row = c.execute(sql.SQL('SELECT * FROM {} WHERE idempotency_key=%s').format(
                    self.table), (idempotency_key,)).fetchone()
                if CreateTask.model_validate(row['request']).model_dump(mode='json') != payload:
                    raise IdempotencyConflict('Idempotency key belongs to another request')
        return TaskView.model_validate(row)

    def get(self, task_id: UUID) -> TaskView | None:
        with self.connect() as c:
            row = c.execute(sql.SQL('SELECT * FROM {} WHERE id=%s').format(
                self.table), (task_id,)).fetchone()
        return TaskView.model_validate(row) if row else None

    def history(self, task_id):
        with self.connect() as c:
            return c.execute(sql.SQL(
                'SELECT attempt,worker_id,started_at,finished_at,outcome,error FROM {} '
                'WHERE task_id=%s ORDER BY attempt').format(self.attempts), (task_id,)).fetchall()

    def _end_attempt(self, c, task_id, token, outcome, error=None):
        c.execute(sql.SQL("""
            UPDATE {} SET finished_at=clock_timestamp(),outcome=%s,error=%s
            WHERE task_id=%s AND token=%s AND finished_at IS NULL
        """).format(self.attempts), (outcome, Jsonb(error) if error else None, task_id, token))

    def recover(self):
        with self.connect() as c:
            rows = c.execute(sql.SQL("""
                SELECT *,deadline <= clock_timestamp() AS timed_out FROM {} WHERE status='running'
                 AND (lease_until <= clock_timestamp() OR deadline <= clock_timestamp())
                FOR UPDATE SKIP LOCKED
            """).format(self.table)).fetchall()
            for row in rows:
                safe = row['request'].get('source_id', 'demo-v1') == 'demo-v1'
                retry = safe and row['attempt'] < row['request'].get('max_attempts', 3)
                outcome = 'timeout' if row['timed_out'] else 'lease_expired'
                error = {'code': outcome if safe else 'outcome_unknown',
                         'message': 'Execution interrupted; inspect attempt history'}
                self._end_attempt(c, row['id'], row['claim_token'], outcome, error)
                if retry:
                    self._requeue(c, row['id'])
                else:
                    c.execute(sql.SQL("""
                        UPDATE {} SET status=%s,error=%s,finished_at=clock_timestamp(),
                          lease_until=NULL WHERE id=%s
                    """).format(self.table), ('failed' if safe else 'needs_review',
                                               Jsonb(error), row['id']))
        return len(rows)

    def _requeue(self, c, task_id):
        c.execute(sql.SQL("""
            UPDATE {} SET status='queued',started_at=NULL,finished_at=NULL,
             worker_id=NULL,claim_token=NULL,lease_until=NULL,deadline=NULL,result=NULL,error=NULL
            WHERE id=%s
        """).format(self.table), (task_id,))

    def claim_next(self, worker_id: str, lease_seconds: float = 15) -> Claim | None:
        if not worker_id or len(worker_id) > 100 or not 0.2 <= lease_seconds <= 300:
            raise ValueError('Invalid worker identity or lease duration')
        self.recover()
        token = uuid4()
        with self.connect() as c:
            row = c.execute(sql.SQL("""
                WITH next_task AS (
                    SELECT id FROM {table} WHERE status='queued'
                    ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE {table} AS task SET status='running', started_at=clock_timestamp(),
                 worker_id=%s,claim_token=%s,attempt=attempt+1,
                 lease_until=clock_timestamp() + %s * interval '1 second',
                 deadline=clock_timestamp() + COALESCE((request->>'timeout_seconds')::int,90)
                          * interval '1 second'
                FROM next_task WHERE task.id=next_task.id AND task.status='queued'
                RETURNING task.*
            """).format(table=self.table), (worker_id, token, lease_seconds)).fetchone()
            if row:
                c.execute(sql.SQL('INSERT INTO {} (task_id,attempt,token,worker_id) '
                                  'VALUES (%s,%s,%s,%s)').format(self.attempts),
                          (row['id'],row['attempt'],token,worker_id))
        return Claim(row['id'],row['request'],worker_id,token,row['attempt']) if row else None

    def _lock_claim_row(self, c, claim):
        # Time-sensitive predicates must be evaluated AFTER any row-lock wait.
        c.execute(sql.SQL('SELECT id FROM {} WHERE id=%s FOR UPDATE').format(
            self.table), (claim.id,)).fetchone()

    def heartbeat(self, claim: Claim, lease_seconds=15):
        if not 0.2 <= lease_seconds <= 300:
            raise ValueError('Invalid lease duration')
        with self.connect() as c:
            self._lock_claim_row(c, claim)
            row = c.execute(sql.SQL("""
                UPDATE {} SET lease_until=LEAST(deadline, clock_timestamp()+%s*interval '1 second')
                WHERE id=%s AND status='running' AND worker_id=%s AND claim_token=%s
                  AND attempt=%s AND lease_until>clock_timestamp() AND deadline>clock_timestamp()
                RETURNING id
            """).format(self.table),
                (lease_seconds,claim.id,claim.worker_id,claim.token,claim.attempt)).fetchone()
            if not row:
                raise StateConflict('Task claim is no longer active')

    def complete(self, claim, result):
        self._finish(claim, 'completed', result.to_dict(), None)

    def fail(self, claim, error: PublicError):
        self._finish(claim, 'failed', None, error.model_dump())

    def _finish(self, claim, status, result, error):
        with self.connect() as c:
            self._lock_claim_row(c, claim)
            cursor = c.execute(sql.SQL("""
                UPDATE {} SET status=%s,result=%s,error=%s,finished_at=clock_timestamp(),
                 lease_until=NULL
                WHERE id=%s AND status='running' AND worker_id=%s AND claim_token=%s
                 AND attempt=%s AND lease_until>clock_timestamp() AND deadline>clock_timestamp()
            """).format(self.table), (status, Jsonb(result) if result is not None else None,
                Jsonb(error) if error is not None else None,
                claim.id,claim.worker_id,claim.token,claim.attempt))
            if cursor.rowcount != 1:
                raise StateConflict('Task claim is no longer active')
            self._end_attempt(c,claim.id,claim.token,status,error)

    def interrupt(self, claim, code):
        """Supervisor interruption before lease expires; paid outcomes are never replayed."""
        safe = claim.request.get('source_id', 'demo-v1') == 'demo-v1'
        error = PublicError(code=code if safe else 'outcome_unknown',
                            message='Execution interrupted; inspect attempt history')
        self._finish(claim,'failed' if safe else 'needs_review',None,error.model_dump())

    def cancel(self, task_id):
        with self.connect() as c:
            row = c.execute(sql.SQL('SELECT * FROM {} WHERE id=%s FOR UPDATE').format(
                self.table), (task_id,)).fetchone()
            if row is None:
                return None
            if row['status'] in ('queued','running'):
                self._end_attempt(c,task_id,row['claim_token'],'cancelled')
                row = c.execute(sql.SQL("""
                    UPDATE {} SET status='cancelled',finished_at=clock_timestamp(),
                     lease_until=NULL WHERE id=%s RETURNING *
                """).format(self.table),(task_id,)).fetchone()
        return TaskView.model_validate(row)

    def retry(self, task_id):
        with self.connect() as c:
            row = c.execute(sql.SQL('SELECT * FROM {} WHERE id=%s FOR UPDATE').format(
                self.table), (task_id,)).fetchone()
            if row is None:
                return None
            if (row['status'] != 'failed' or row['request'].get('source_id','demo-v1') != 'demo-v1'
                    or row['attempt'] >= row['request'].get('max_attempts',3)):
                raise StateConflict('Task is not eligible for safe bounded retry')
            self._requeue(c,task_id)
        return self.get(task_id)
