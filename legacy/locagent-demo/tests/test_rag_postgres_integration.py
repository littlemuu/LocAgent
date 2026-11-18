"""Real optional integration; opt-in exact isolated DSN, fake vectors only."""
import os,time,threading,unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from locagent_service.config import Settings
from locagent_service.rag_offline import Version,Chunk,SearchConfig,IndexNotReady,ProviderError
from locagent_service.rag_postgres import BuildSpec,PgVectorStore,PgExactIndex,BuildConflict,module_retriever

DSN='postgresql://postgres@127.0.0.1:55441/vector_acceptance'

class HookConnection:
    def __init__(self,connection,hook):self.connection=connection;self.hook=hook
    def __enter__(self):self.connection.__enter__();return self
    def __exit__(self,*args):return self.connection.__exit__(*args)
    def execute(self,*args,**kwargs):return self.connection.execute(*args,**kwargs)
    def cursor(self):return HookCursor(self.connection.cursor(),self)

class HookCursor:
    def __init__(self,cursor,owner):self.cursor=cursor;self.owner=owner
    def __enter__(self):self.cursor.__enter__();return self
    def __exit__(self,*args):return self.cursor.__exit__(*args)
    def executemany(self,*args):
        self.cursor.executemany(*args)
        self.owner.hook(self.owner.connection)

@unittest.skipUnless(os.environ.get('LOCAGENT_VECTOR_TEST_DSN')==DSN,'Explicit isolated pgvector DSN required')
class PgRealTests(unittest.TestCase):
    def setUp(self):
        self.schema='public_preview_vi_'+uuid4().hex[:12]
        self.settings=Settings(DSN,self.schema)
        with self.connect() as c:c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.store=PgVectorStore(self.settings,enabled=True);self.store.initialize()
        self.v=Version('a/repo','a'*40,'fake-fixed-v1')
        self.chunks=(Chunk(self.v,'a.py','a','function',1,2,0,'first'),Chunk(self.v,'a.py','a','function',3,4,1,'second'),Chunk(self.v,'a.py','b','function',5,6,0,'third'))
        self.spec=BuildSpec(self.v,2,self.chunks);self.values=[[1,0],[.9,.1],[0,1]]
    def connect(self):return psycopg.connect(DSN,row_factory=dict_row,connect_timeout=3,options='-c statement_timeout=8000 -c lock_timeout=1500')
    def hook_store(self,hook):return PgVectorStore(self.settings,enabled=True,connect=lambda:HookConnection(self.connect(),hook))
    def publish(self):
        token=self.store.begin(self.spec);self.store.publish(self.spec,token,self.values);return token
    def count(self):
        with self.connect() as c:return c.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(self.store.rows)).fetchone()['n']
    def expire(self):
        with self.connect() as c:c.execute(sql.SQL("UPDATE {} SET lease_until=clock_timestamp()-interval '1 second' WHERE build_key=%s").format(self.store.builds),(self.spec.identity,))
    def test_real_extension_and_idempotent_migration(self):
        self.store.initialize()
        with self.connect() as c:
            self.assertEqual(c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()['extversion'],'0.8.7')
    def test_exact_entity_dedup_ranking_and_stable_ties(self):
        self.publish();hits=self.store.query(self.spec,[1,0],2)
        self.assertEqual([h.chunk.entity for h in hits],['a','b']);self.assertAlmostEqual(hits[0].score,1)
        self.assertEqual(hits,self.store.query(self.spec,[1,0],2))
    def test_python_dimension_and_finite_values_fail_without_rows(self):
        token=self.store.begin(self.spec)
        for values in ([[1,0]],[[1],[1],[1]],[[float('nan'),0]]*3,[[float('inf'),0]]*3,[[0,0]]*3):
            with self.subTest(values=str(values)),self.assertRaises((ValueError,ProviderError)):self.store.publish(self.spec,token,values)
        self.assertEqual(self.count(),0);self.assertEqual(self.store.status(self.spec)['state'],'building')
    def test_database_rejects_nonfinite_vector(self):
        for value in ('[NaN,1]','[Infinity,1]'):
            with self.subTest(value=value),self.assertRaises(psycopg.Error):
                with self.connect() as c:c.execute('SELECT %s::public.vector',(value,))
    def test_database_rejects_wrong_dimension_on_insert(self):
        token=self.store.begin(self.spec)
        with self.assertRaises(psycopg.Error):
            with self.connect() as c:
                c.execute(sql.SQL('INSERT INTO {} (build_key,dimensions,chunk_id,entity_id,embedding) VALUES (%s,%s,%s,%s,%s::public.vector)').format(self.store.rows),(self.spec.identity,2,self.chunks[0].id,'a.py:a','[1,2,3]'))
    def test_database_rejects_wrong_build_dimension_and_zero_vector(self):
        self.store.begin(self.spec)
        for dim,value in ((3,'[1,2,3]'),(2,'[0,0]')):
            with self.subTest(dim=dim,value=value),self.assertRaises(psycopg.Error):
                with self.connect() as c:
                    c.execute(sql.SQL('INSERT INTO {} (build_key,dimensions,chunk_id,entity_id,embedding) VALUES (%s,%s,%s,%s,%s::public.vector)').format(self.store.rows),(self.spec.identity,dim,self.chunks[0].id,'a.py:a',value))
    def test_repo_commit_model_and_membership_isolation(self):
        self.publish()
        for v in (Version('b/repo','a'*40,self.v.model),Version('a/repo','b'*40,self.v.model),Version('a/repo','a'*40,'fake-fixed-v2')):
            chunks=tuple(Chunk(v,c.path,c.entity,c.kind,c.start,c.end,c.part,c.text) for c in self.chunks)
            with self.assertRaises(IndexNotReady):self.store.query(BuildSpec(v,2,chunks),[1,0],2)
        with self.assertRaises(IndexNotReady):self.store.query(BuildSpec(self.v,2,self.chunks[:1]),[1,0],2)
    def test_explicit_gate_and_complete_fallback(self):
        lex=Mock(stemmer=None);nodes=[Mock(text='not-indexed',score=8)];lex.retrieve.return_value=nodes
        self.assertIs(module_retriever(lex,config=SearchConfig()),lex)
        with self.assertRaises(ValueError):module_retriever(lex,config=SearchConfig('hybrid'))
        provider=Mock(model=self.v.model,dimensions=2)
        adapter=module_retriever(lex,config=SearchConfig('hybrid','bm25'),enabled=True,store=self.store,spec=self.spec,provider=provider,graph_nodes=['a.py:a','a.py:b'])
        self.assertIs(adapter.retrieve('q'),nodes);provider.embed.assert_not_called()
    def test_two_connections_concurrent_begin_one_winner(self):
        barrier=threading.Barrier(2)
        def claim():
            barrier.wait(timeout=5)
            try:return self.store.begin(self.spec)
            except BuildConflict:return None
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(claim) for _ in range(2)];results=[f.result(timeout=10) for f in futures]
        self.assertEqual(sum(x is not None for x in results),1)
    def test_same_build_claim_waits_then_conflicts_after_commit(self):
        inserted=threading.Event();release=threading.Event();connected=threading.Event();pids=[]
        outer=self
        class PausedInsert(HookConnection):
            def execute(self,q,*args,**kwargs):
                if isinstance(q,sql.Composable) and q.as_string().startswith('INSERT INTO'):
                    inserted.set()
                    if not release.wait(3):raise RuntimeError('claim barrier timeout')
                return self.connection.execute(q,*args,**kwargs)
        first=PgVectorStore(self.settings,enabled=True,connect=lambda:PausedInsert(self.connect(),None))
        def second_connection():
            c=outer.connect();pids.append(c.info.backend_pid);connected.set();return c
        second=PgVectorStore(self.settings,enabled=True,connect=second_connection)
        with ThreadPoolExecutor(2) as pool:
            winner=pool.submit(first.begin,self.spec)
            try:
                self.assertTrue(inserted.wait(2))
                loser=pool.submit(second.begin,self.spec);self.assertTrue(connected.wait(1))
                waiting=False
                with self.connect() as observer:
                    for _ in range(50):
                        waiting=observer.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted) AS waiting",(pids[0],)).fetchone()['waiting']
                        if waiting:break
                        time.sleep(.01)
                self.assertTrue(waiting,'second claim must wait before competing INSERT')
                self.assertFalse(loser.done())
            finally:release.set()
            token=winner.result(timeout=3)
            with self.assertRaises(BuildConflict):loser.result(timeout=3)
        self.store.publish(self.spec,token,self.values);self.assertEqual(self.count(),3)

    def test_failed_claim_rolls_back_and_releases_lock_for_next_connection(self):
        class FailedInsert(HookConnection):
            def execute(self,q,*args,**kwargs):
                result=self.connection.execute(q,*args,**kwargs)
                if isinstance(q,sql.Composable) and q.as_string().startswith('INSERT INTO'):
                    self.connection.execute('SELECT 1/0')
                return result
        broken=PgVectorStore(self.settings,enabled=True,connect=lambda:FailedInsert(self.connect(),None))
        with self.assertRaises(psycopg.errors.DivisionByZero):broken.begin(self.spec)
        with self.connect() as c:
            self.assertEqual(c.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(self.store.builds)).fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT 1 AS n').fetchone()['n'],1)
        token=self.store.begin(self.spec)
        self.store.publish(self.spec,token,self.values);self.assertEqual(self.count(),3)

    def test_expiry_takeover_old_token_rejected(self):
        old=self.store.begin(self.spec);self.expire();new=self.store.begin(self.spec)
        with self.assertRaises(BuildConflict):self.store.publish(self.spec,old,self.values)
        with self.assertRaises(BuildConflict):self.store.terminate(self.spec,old,cancelled=True)
        self.store.publish(self.spec,new,self.values);self.assertEqual(self.count(),3)
    def test_failed_build_recovery_and_ready_immutable(self):
        old=self.store.begin(self.spec);self.store.terminate(self.spec,old)
        self.assertEqual(self.store.status(self.spec)['state'],'failed')
        new=self.store.begin(self.spec);self.store.publish(self.spec,new,self.values)
        with self.assertRaises(BuildConflict):self.store.begin(self.spec)
        with self.assertRaises(BuildConflict):self.store.publish(self.spec,new,self.values)
    def test_cancelled_build_stale_owner_and_recovery(self):
        old=self.store.begin(self.spec);self.store.terminate(self.spec,old,cancelled=True)
        with self.assertRaises(BuildConflict):self.store.publish(self.spec,old,self.values)
        new=self.store.begin(self.spec);self.store.publish(self.spec,new,self.values)
    def test_injected_failure_rolls_back_all_rows(self):
        token=self.store.begin(self.spec)
        def fail(c):raise RuntimeError('injected after vector inserts')
        with self.assertRaisesRegex(RuntimeError,'injected'):self.hook_store(fail).publish(self.spec,token,self.values)
        self.assertEqual(self.count(),0);self.assertEqual(self.store.status(self.spec)['state'],'building')
    def test_atomic_publication_invisible_to_other_connection(self):
        token=self.store.begin(self.spec);inserted=threading.Event();release=threading.Event()
        def hold(c):
            inserted.set()
            if not release.wait(5):raise RuntimeError('barrier timeout')
        with ThreadPoolExecutor(1) as pool:
            f=pool.submit(self.hook_store(hold).publish,self.spec,token,self.values)
            try:
                self.assertTrue(inserted.wait(5));self.assertEqual(self.count(),0)
                with self.assertRaises(IndexNotReady):self.store.query(self.spec,[1,0],2)
            finally:release.set()
            f.result(timeout=10)
        self.assertEqual(self.count(),3);self.assertEqual(self.store.status(self.spec)['state'],'ready')
    def test_lease_expires_during_publication_rolls_back(self):
        token=self.store.begin(self.spec,lease_seconds=5)
        def delay(c):c.execute('SELECT pg_sleep(5.1)')
        with self.assertRaises(BuildConflict):self.hook_store(delay).publish(self.spec,token,self.values)
        self.assertEqual(self.count(),0)
    def test_backend_interruption_rolls_back_and_recovery(self):
        token=self.store.begin(self.spec)
        def kill(c):
            pid=c.info.backend_pid
            with self.connect() as other:other.execute('SELECT pg_terminate_backend(%s)',(pid,))
        with self.assertRaises(psycopg.Error):self.hook_store(kill).publish(self.spec,token,self.values)
        self.assertEqual(self.count(),0);self.expire()
        token=self.store.begin(self.spec);self.store.publish(self.spec,token,self.values)
        self.assertEqual(self.count(),3)
    def test_real_hybrid_adapter_uses_fake_embedding(self):
        self.publish();provider=Mock(model=self.v.model,dimensions=2);provider.embed.return_value=[[1,0]]
        lex=Mock(stemmer=None);lex.retrieve.return_value=[Mock(text='a.py:a',score=8),Mock(text='a.py:b',score=4)]
        adapter=module_retriever(lex,config=SearchConfig('hybrid',k=2),enabled=True,store=self.store,spec=self.spec,provider=provider,graph_nodes=['a.py:a','a.py:b'])
        self.assertEqual([n.text for n in adapter.retrieve('q')],['a.py:a','a.py:b'])

if __name__=='__main__':unittest.main(verbosity=2)
