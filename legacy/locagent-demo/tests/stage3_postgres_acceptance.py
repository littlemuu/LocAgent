"""Real PostgreSQL fault acceptance; inherited Stage 2 cases are regression coverage."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import signal
import time
from uuid import uuid4
from psycopg import sql
from psycopg.types.json import Jsonb

from stage2_postgres_acceptance import PostgresAcceptance
from locagent_service.models import CreateTask, PublicError
from locagent_service.store import StateConflict, IdempotencyConflict, TaskStore
from locagent_service.worker import run_one


def slow_engine(request, channel, parent_pid):
    time.sleep(20)




def partial_result_then_hang(request, channel, parent_pid):
    from pathlib import Path
    Path(request['problem_statement']).write_text(str(os.getpid()))
    (channel.directory/'partial.json').write_bytes(b'["completed",{"unfinished":')
    time.sleep(20)


def returned_result(request, channel, parent_pid):
    from locagent_service.fixture import localize_demo
    result=localize_demo(CreateTask(problem_statement='Controlled unknown outcome'))
    channel.send(('completed',result.to_dict()))
    channel.close()


class FailingPersistenceStore(TaskStore):
    def _finish(self,*args,**kwargs):
        # A real PostgreSQL backend disconnect exactly at result persistence.
        import psycopg
        with self.connect() as victim:
            with self.connect() as killer:
                killer.execute('SELECT pg_terminate_backend(%s)',(victim.info.backend_pid,))
            victim.execute('SELECT 1')


class LifecycleAcceptance(PostgresAcceptance):

    def test_lock_wait_crossing_expiry_rejects_renewal_and_completion(self):
        result=self.result()
        for action in ('heartbeat','complete'):
            task=self.create()
            claim=self.store.claim_next('blocked-'+action,0.8)
            with self.store.connect() as blocker:
                blocker.execute(sql.SQL('SELECT id FROM {} WHERE id=%s FOR UPDATE').format(
                    self.store.table),(task.id,))
                with ThreadPoolExecutor(max_workers=1) as pool:
                    operation=(lambda:self.store.heartbeat(claim,15)) if action=='heartbeat' else (
                        lambda:self.store.complete(claim,result))
                    future=pool.submit(operation)
                    deadline=time.monotonic()+3
                    while True:
                        with self.store.connect() as probe:
                            waiting=probe.execute("SELECT count(*) AS n FROM pg_stat_activity "
                                "WHERE wait_event_type='Lock' AND query LIKE %s",
                                ('%'+self.schema+'%',)).fetchone()['n']
                        if waiting:break
                        self.assertLess(time.monotonic(),deadline)
                        time.sleep(0.01)
                    # Wait until the DATABASE clock proves expiry, while blocker changes no data.
                    while True:
                        with self.store.connect() as probe:
                            expired=probe.execute(sql.SQL(
                                'SELECT lease_until <= clock_timestamp() AS expired FROM {} WHERE id=%s'
                            ).format(self.store.table),(task.id,)).fetchone()['expired']
                        if expired:break
                        time.sleep(0.02)
                    blocker.commit()
                    with self.assertRaises(StateConflict):future.result(timeout=3)
            self.expire(task.id)
            self.store.recover()
            # Cancel requeued row to avoid stealing it in the next subcase.
            self.store.cancel(task.id)

    def test_partial_result_cannot_block_timeout_or_cancel_and_engine_exits(self):
        from pathlib import Path
        for mode in ('timeout','cancel'):
            marker=self.artifacts/(mode+'-child.pid')
            task=self.store.create(CreateTask(problem_statement=str(marker),timeout_seconds=2,max_attempts=1))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(run_one,self.store,'partial-'+mode,lease_seconds=0.6,
                                   executor=partial_result_then_hang)
                deadline=time.monotonic()+5
                while not marker.exists():
                    self.assertLess(time.monotonic(),deadline)
                    time.sleep(0.02)
                pid=int(marker.read_text())
                self.assertTrue(Path('/proc',str(pid)).exists())
                if mode=='cancel':self.store.cancel(task.id)
                future.result(timeout=5)
                self.assertFalse(Path('/proc',str(pid)).exists(),'Engine was not reaped')
            expected='failed' if mode=='timeout' else 'cancelled'
            self.assertEqual(self.store.get(task.id).status,expected)
            if mode=='timeout':self.assertEqual(self.store.get(task.id).error.code,'timeout')

    def test_idempotency_different_payloads_race_has_one_winner(self):
        from threading import Barrier
        barrier=Barrier(2)
        def submit(text):
            barrier.wait(timeout=3)
            try:return self.store.create(CreateTask(problem_statement=text),'race-different')
            except IdempotencyConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(submit,('left','right')))
        self.assertEqual(sum(row is not None for row in rows),1)

    def test_http_idempotency_replays_prepared_request_after_source_disappears(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from locagent_service.api import create_app
        from locagent_service.sources import canonical,digest
        registry=self.artifacts/'sources'
        bundle=registry/'bundle';bundle.mkdir(parents=True)
        task={'instance_id':'fixed-1','repo':'owner/repo','base_commit':'a'*40,
              'problem_statement':'Fixed immutable problem'}
        manifest={'bundle':'bundle','artifacts':{},'engine':{},'task':task,'config':{'max_calls':4}}
        data=canonical(manifest);source='prepared-'+digest(data)
        path=registry/(source+'.json');path.write_bytes(data)
        request={'source_id':source,'problem_statement':task['problem_statement'],
                 'options':{'max_iterations':4},'max_attempts':1}
        with patch.dict(os.environ,{'LOCAGENT_SOURCE_ROOT':str(registry)}):
            with TestClient(create_app(self.settings)) as client:
                first=client.post('/tasks',json=request,headers={'Idempotency-Key':'source-key'})
                self.assertEqual(first.status_code,202)
                path.rename(registry/'removed-manifest.json')
                repeat=client.post('/tasks',json=request,headers={'Idempotency-Key':'source-key'})
                self.assertEqual(repeat.status_code,202)
                self.assertEqual(repeat.json()['id'],first.json()['id'])
                self.assertEqual(client.post('/tasks',json=request,
                    headers={'Idempotency-Key':'new-key'}).status_code,422)
                request['problem_statement']='changed'
                self.assertEqual(client.post('/tasks',json=request,
                    headers={'Idempotency-Key':'source-key'}).status_code,409)
    def test_result_returned_then_database_disconnect_blocks_paid_replay(self):
        import psycopg
        task=self.create(max_attempts=1)
        with self.store.connect() as c:
            c.execute(sql.SQL("UPDATE {} SET request=jsonb_set(request,'{{source_id}}',%s) WHERE id=%s"
                              ).format(self.store.table),(Jsonb('prepared-'+'b'*64),task.id))
        with self.assertRaises(psycopg.OperationalError):
            run_one(FailingPersistenceStore(self.settings),'lost-result',executor=returned_result)
        self.assertEqual(self.store.get(task.id).status,'running')
        self.assertIsNone(self.store.get(task.id).result)
        self.expire(task.id)
        self.store.recover()
        self.assertEqual(self.store.get(task.id).status,'needs_review')
        self.assertIsNone(self.store.claim_next('no-replay'))

    def test_live_process_cancellation_stops_engine_and_preserves_terminal(self):
        task=self.create()
        process=self.child('locagent_service.worker','--once','--lease-seconds','1')
        deadline=time.monotonic()+10
        while self.store.get(task.id).status=='queued':
            self.assertLess(time.monotonic(),deadline)
            time.sleep(0.01)
        self.store.cancel(task.id)
        self.await_worker(process)
        self.assertEqual(self.store.get(task.id).status,'cancelled')
        self.assertEqual(self.store.history(task.id)[0]['outcome'],'cancelled')

    def test_v1_migration_retains_completed_history_and_quarantines_running(self):
        from pathlib import Path
        from locagent_service.store import TaskStore
        legacy_schema='acceptance_'+uuid4().hex
        from locagent_service.config import Settings
        legacy=TaskStore(Settings(self.settings.database_url,legacy_schema))
        with legacy.connect() as c:
            text=(Path(__file__).resolve().parents[1]/'locagent_service/migrations/001_tasks.sql').read_text()
            c.execute(sql.SQL(text).format(schema=sql.Identifier(legacy_schema)))
            legacy_id=uuid4()
            completed_id=uuid4()
            completed_result=self.result().to_dict()
            c.execute(sql.SQL("INSERT INTO {}(id,request,status,started_at,finished_at,worker_id,claim_token,result) "
                              "VALUES (%s,%s,'completed',clock_timestamp(),clock_timestamp(),'old-success',%s,%s)"
                              ).format(legacy.table),
                      (completed_id,Jsonb(CreateTask(problem_statement='historical success').model_dump(mode='json')),
                       uuid4(),Jsonb(completed_result)))
            c.execute(sql.SQL("INSERT INTO {}(id,request,status,started_at,worker_id,claim_token) "
                              "VALUES (%s,%s,'running',clock_timestamp(),'legacy',%s)").format(legacy.table),
                      (legacy_id,Jsonb(CreateTask(problem_statement='legacy').model_dump(mode='json')),uuid4()))
        try:
            legacy.initialize()
            self.assertEqual(legacy.get(completed_id).status,'completed')
            self.assertEqual(legacy.get(completed_id).result.model_dump(),completed_result)
            self.assertEqual(legacy.get(legacy_id).status,'needs_review')
            self.assertEqual(legacy.get(legacy_id).error.code,'legacy_interrupted')
            legacy.initialize()
            self.assertEqual(legacy.get(legacy_id).request.problem_statement,'legacy')
            self.assertIsNone(legacy.claim_next('do-not-replay-history'))
        finally:
            with legacy.connect() as c:
                c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(legacy_schema)))

    def expire(self, task_id, deadline=False):
        column = 'deadline' if deadline else 'lease_until'
        with self.store.connect() as c:
            c.execute(sql.SQL("UPDATE {} SET {}=clock_timestamp()-interval '1 second' WHERE id=%s"
                             ).format(self.store.table,sql.Identifier(column)),(task_id,))

    def test_idempotent_concurrent_same_key_and_mismatched_body(self):
        body=CreateTask(problem_statement='Same immutable payload')
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows=list(pool.map(lambda _:self.store.create(body,'shared-key'),range(8)))
        self.assertEqual(len({r.id for r in rows}),1)
        with self.assertRaises(IdempotencyConflict):
            self.store.create(CreateTask(problem_statement='Different payload'),'shared-key')
        self.assertEqual(self.store.create(body,'shared-key').id,rows[0].id)

    def test_expired_claim_cannot_renew_complete_fail_even_before_reclaim(self):
        task=self.create()
        old=self.store.claim_next('same-worker')
        result=self.result()
        self.expire(task.id)
        for action in (lambda:self.store.heartbeat(old),
                       lambda:self.store.complete(old,result),
                       lambda:self.store.fail(old,PublicError(code='bad',message='stale'))):
            with self.assertRaises(StateConflict): action()
        new=self.store.claim_next('same-worker')
        self.assertEqual(new.attempt,2)
        self.assertNotEqual(new.token,old.token)
        for stale in (old,replace(new,attempt=old.attempt)):
            with self.assertRaises(StateConflict): self.store.complete(stale,result)
        self.store.complete(new,result)
        self.assertEqual([a['outcome'] for a in self.store.history(task.id)],
                         ['lease_expired','completed'])

    def test_heartbeat_extends_lease_but_never_deadline(self):
        task=self.create(timeout_seconds=10)
        claim=self.store.claim_next('renew',1)
        first=self.store.get(task.id)
        self.store.heartbeat(claim,30)
        second=self.store.get(task.id)
        self.assertGreater(second.lease_until,first.lease_until)
        self.assertLessEqual(second.lease_until,second.deadline)
        self.assertEqual(first.deadline,second.deadline)

    def test_cancel_queued_running_and_terminal_never_resurrects(self):
        queued=self.create()
        self.assertEqual(self.store.cancel(queued.id).status,'cancelled')
        running=self.create()
        claim=self.store.claim_next('cancel')
        result=self.result()
        self.store.cancel(running.id)
        with self.assertRaises(StateConflict): self.store.complete(claim,result)
        with self.assertRaises(StateConflict): self.store.heartbeat(claim)
        self.assertIsNone(self.store.claim_next('replacement'))
        done=self.create()
        new=self.store.claim_next('complete')
        self.store.complete(new,result)
        self.assertEqual(self.store.cancel(done.id).status,'completed')

    def test_cancel_success_race_has_one_terminal_winner(self):
        result=self.result()
        for _ in range(5):
            task=self.create()
            claim=self.store.claim_next('race')
            def complete():
                try: self.store.complete(claim,result)
                except StateConflict: pass
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(complete),pool.submit(self.store.cancel,task.id)]
                for f in futures:f.result()
            final=self.store.get(task.id)
            self.assertIn(final.status,('completed','cancelled'))
            self.assertEqual(len(self.store.history(task.id)),1)
            self.assertEqual(self.store.history(task.id)[0]['outcome'],final.status.value)

    def test_timeout_wins_over_success_and_retries_are_bounded(self):
        task=self.create(max_attempts=2)
        first=self.store.claim_next('timeout')
        result=self.result()
        self.expire(task.id,deadline=True)
        with self.assertRaises(StateConflict): self.store.complete(first,result)
        self.store.recover()
        second=self.store.claim_next('retry')
        self.assertEqual(second.attempt,2)
        self.expire(task.id,deadline=True)
        self.store.recover()
        final=self.store.get(task.id)
        self.assertEqual(final.status,'failed')
        self.assertEqual(final.error.code,'timeout')
        self.assertIsNone(self.store.claim_next('exhausted'))
        with self.assertRaises(StateConflict):self.store.retry(task.id)

    def test_supervisor_kills_hung_child_at_hard_deadline(self):
        task=self.create(timeout_seconds=1,max_attempts=1)
        start=time.monotonic()
        run_one(self.store,'hung',lease_seconds=0.6,executor=slow_engine)
        self.assertLess(time.monotonic()-start,5)
        self.assertEqual(self.store.get(task.id).status,'failed')
        self.assertEqual(self.store.get(task.id).error.code,'timeout')

    def test_expired_paid_or_unknown_source_is_never_replayed(self):
        task=self.create()
        claim=self.store.claim_next('unknown')
        with self.store.connect() as c:
            c.execute(sql.SQL("UPDATE {} SET request=jsonb_set(request,'{{source_id}}',%s) WHERE id=%s"
                              ).format(self.store.table),(Jsonb('prepared-'+'a'*64),task.id))
        self.expire(task.id)
        self.store.recover()
        with self.store.connect() as c:
            row=c.execute(sql.SQL('SELECT status,error FROM {} WHERE id=%s').format(
                self.store.table),(task.id,)).fetchone()
        self.assertEqual(row['status'],'needs_review')
        self.assertEqual(row['error']['code'],'outcome_unknown')
        self.assertIsNone(self.store.claim_next('no-replay'))
        with self.assertRaises(StateConflict):self.store.retry(task.id)

    def test_manual_retry_failure_only_and_keeps_attempt_history(self):
        task=self.create()
        claim=self.store.claim_next('one')
        self.store.fail(claim,PublicError(code='test',message='controlled'))
        self.assertEqual(self.store.retry(task.id).status,'queued')
        second=self.store.claim_next('two')
        self.assertEqual(second.attempt,2)
        self.store.complete(second,self.result())
        self.assertEqual([r['outcome'] for r in self.store.history(task.id)],['failed','completed'])
        with self.assertRaises(StateConflict):self.store.retry(task.id)

    def test_e2e_sigkill_then_expiry_and_new_worker_recovers(self):
        task=self.create()
        worker=self.child('locagent_service.worker','--once','--lease-seconds','1')
        deadline=time.monotonic()+10
        while self.store.get(task.id).status=='queued':
            self.assertLess(time.monotonic(),deadline)
            time.sleep(0.01)
        worker.kill()
        worker.wait(5)
        time.sleep(1.1)
        self.await_worker(self.worker())
        final=self.store.get(task.id)
        self.assertEqual(final.status,'completed')
        self.assertEqual(final.attempt,2)
        self.assertEqual(self.store.history(task.id)[0]['outcome'],'lease_expired')

    def test_database_session_termination_does_not_allow_stale_commit(self):
        task=self.create()
        claim=self.store.claim_next('connection-loss')
        # Actual server-side backend termination, no mocked database.
        with self.store.connect() as victim:
            pid=victim.info.backend_pid
            with self.store.connect() as killer:
                killer.execute('SELECT pg_terminate_backend(%s)',(pid,))
            import psycopg
            with self.assertRaises(psycopg.OperationalError):
                victim.execute('SELECT 1')
        self.expire(task.id)
        replacement=self.store.claim_next('new')
        with self.assertRaises(StateConflict):self.store.complete(claim,self.result())
        self.store.complete(replacement,self.result())

    def test_http_idempotency_cancel_retry_and_history(self):
        _,client,_=self.api()
        body={'problem_statement':'HTTP idempotency'}
        headers={'Idempotency-Key':'http-key'}
        first=client.post('/tasks',json=body,headers=headers)
        second=client.post('/tasks',json=body,headers=headers)
        self.assertEqual(first.json()['id'],second.json()['id'])
        self.assertEqual(client.post('/tasks',json={'problem_statement':'different'},
                                     headers=headers).status_code,409)
        self.assertEqual(client.post('/tasks',json=body,
                                     headers={'Idempotency-Key':'bad key'}).status_code,422)
        loc=first.headers['Location']
        self.assertEqual(client.post(loc+'/cancel').json()['status'],'cancelled')
        self.assertEqual(client.post(loc+'/retry').status_code,409)
        self.assertEqual(client.get(loc+'/attempts').json(),[])


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromTestCase(LifecycleAcceptance)
