import unittest
from unittest.mock import Mock
from contextlib import AbstractContextManager
from collections import deque
from pathlib import Path
from psycopg import sql, OperationalError
from locagent_service.config import Settings
from locagent_service.rag_offline import Version,chunk_snapshot,SearchConfig,IndexNotReady,ProviderError
from locagent_service.rag_postgres import BuildSpec,PgVectorStore,PgExactIndex,BuildConflict,module_retriever,vector_text

class Connection(AbstractContextManager):
    def __init__(self,results):self.results=deque(results);self.calls=[];self.rolled_back=False;self.batches=[]
    def execute(self,q,args=None):
        self.calls.append((q.as_string() if isinstance(q,sql.Composable) else q,args))
        result=self.results.popleft()
        if isinstance(result,Exception):raise result
        return Mock(fetchone=lambda:result,fetchall=lambda:result)
    def cursor(self):return self
    def executemany(self,q,args):self.batches.append((q.as_string(),args))
    def __exit__(self,typ,value,tb):self.rolled_back=typ is not None;return False

class PersistentPreviewTests(unittest.TestCase):
    def setUp(self):
        self.v=Version('a/repo','a'*40,'fake-pinned-v1')
        self.chunks=chunk_snapshot({'a.py':b'def a():\n return 1\ndef b():\n return 2\n'},self.v)
        self.spec=BuildSpec(self.v,2,self.chunks)
        self.settings=Settings('postgresql://unused','public_preview_vector_test')
        self.provider=Mock(model=self.v.model,dimensions=2);self.provider.embed.return_value=[[1.,0.]]
    def store(self,results):
        self.c=Connection(results);return PgVectorStore(self.settings,enabled=True,connect=lambda:self.c)
    def test_explicit_gate_and_default_bm25_no_dependencies(self):
        with self.assertRaises(ValueError):PgVectorStore(self.settings)
        with self.assertRaises(ValueError):PgVectorStore(Settings('postgresql://unused','locagent'),enabled=True)
        lexical=object();self.assertIs(module_retriever(lexical,config=SearchConfig()),lexical)
        with self.assertRaises(ValueError):module_retriever(lexical,config=SearchConfig('hybrid'))
    def test_spec_identity_is_order_independent_but_dimension_and_membership_bound(self):
        self.assertEqual(self.spec.identity,BuildSpec(self.v,2,tuple(reversed(self.chunks))).identity)
        self.assertNotEqual(self.spec.identity,BuildSpec(self.v,3,self.chunks).identity)
        self.assertNotEqual(self.spec.identity,BuildSpec(self.v,2,self.chunks[:1]).identity)
    def test_mixed_membership_and_invalid_dimensions_rejected(self):
        for dim in (0,True,2001):
            with self.assertRaises(ValueError):BuildSpec(self.v,dim,self.chunks)
        with self.assertRaises(ValueError):BuildSpec(self.v,2,self.chunks+self.chunks)
    def test_extension_missing_prevents_ddl(self):
        s=self.store([None])
        with self.assertRaises(IndexNotReady):s.initialize()
        self.assertEqual(len(self.c.calls),1)
    def test_sql_template_renders_without_installing_extension(self):
        s=self.store([{'present':1},None,None]);s.initialize()
        ddl=self.c.calls[-1][0]
        self.assertIn('{64}',ddl);self.assertIn('"public_preview_vector_test".rag_vector_builds',ddl)
        self.assertNotIn('CREATE EXTENSION vector',ddl)
    def test_duplicate_or_ready_build_rejected_without_reset(self):
        s=self.store([None,None])
        with self.assertRaises(BuildConflict):s.begin(self.spec)
        self.assertNotIn("b.state='ready'",self.c.calls[1][0]);self.assertEqual(len(self.c.calls),2)
    def test_begin_lease_is_bounded_and_token_returned(self):
        s=self.store([None,{'token':'unused'}]);self.assertIsNotNone(s.begin(self.spec))
        with self.assertRaises(ValueError):s.begin(self.spec,lease_seconds=601)
    def test_begin_does_not_hide_unrelated_integrity_errors(self):
        from psycopg.errors import UniqueViolation
        failure=UniqueViolation('unrelated constraint')
        s=self.store([None,failure])
        with self.assertRaises(UniqueViolation) as caught:s.begin(self.spec)
        self.assertIs(caught.exception,failure);self.assertTrue(self.c.rolled_back)
    def test_partial_or_bad_vectors_never_open_publication_transaction(self):
        connect=Mock();s=PgVectorStore(self.settings,enabled=True,connect=connect)
        with self.assertRaises(ValueError):s.publish(self.spec,'token',[[1,0]])
        with self.assertRaises(ProviderError):s.publish(self.spec,'token',[[0,0]]*2)
        connect.assert_not_called()
    def test_publication_writes_complete_batch_then_ready(self):
        s=self.store([{'build_key':self.spec.identity},None,{'build_key':self.spec.identity}])
        s.publish(self.spec,'token',[[1,0],[0,1]])
        self.assertEqual(len(self.c.batches[0][1]),2);self.assertIn("state='ready'",self.c.calls[-1][0])
        self.assertFalse(self.c.rolled_back)
    def test_expired_final_fence_rolls_back_publication(self):
        s=self.store([{'build_key':self.spec.identity},None,None])
        with self.assertRaises(BuildConflict):s.publish(self.spec,'old',[[1,0],[0,1]])
        self.assertTrue(self.c.rolled_back)
    def test_cancel_and_stale_owner_fencing(self):
        s=self.store([None])
        with self.assertRaises(BuildConflict):s.terminate(self.spec,'old',cancelled=True)
        self.assertEqual(len(self.c.calls),1)
        s=self.store([{'build_key':self.spec.identity},None]);s.terminate(self.spec,'current',cancelled=True)
        self.assertEqual(self.c.calls[-1][1][0],'cancelled')
    def test_exact_query_sql_groups_entities_before_limit(self):
        s=self.store([{'ready':1},[{'chunk_id':self.chunks[0].id,'score':1.}]])
        hits=s.query(self.spec,[1,0],1);self.assertEqual(hits[0].chunk,self.chunks[0])
        q,args=self.c.calls[-1];self.assertIn('PARTITION BY entity_id',q);self.assertIn('WHERE rank=1',q)
        self.assertEqual(args[1],self.spec.identity)
    def test_query_not_ready_and_storage_errors_are_safe(self):
        s=self.store([None])
        with self.assertRaises(IndexNotReady):s.query(self.spec,[1,0],2)
        s=self.store([OperationalError('secret DSN')])
        with self.assertRaisesRegex(IndexNotReady,'^Vector storage unavailable$'):s.status(self.spec)
    def test_index_version_rejected_before_embedding(self):
        s=Mock();idx=PgExactIndex(s,self.spec)
        with self.assertRaises(ValueError):idx.search('q',Version('other/repo','a'*40,self.v.model),self.provider)
        self.provider.embed.assert_not_called();s.status.assert_not_called()
    def test_not_ready_fallback_preserves_all_lexical_nodes(self):
        s=Mock();s.status.return_value={'state':'building'}
        lex=Mock(stemmer=None);expected=[Mock(text='unindexed',score=9)];lex.retrieve.return_value=expected
        adapter=module_retriever(lex,config=SearchConfig('hybrid','bm25'),enabled=True,store=s,spec=self.spec,provider=self.provider,graph_nodes=['a.py:a','a.py:b'])
        self.assertIs(adapter.retrieve('q'),expected);self.provider.embed.assert_not_called()
    def test_ready_index_uses_injected_fake_provider_and_store(self):
        s=Mock();s.status.return_value={'state':'ready'};s.query.return_value=[]
        self.assertEqual(PgExactIndex(s,self.spec).search('q',self.v,self.provider),[])
        s.query.assert_called_once();self.provider.embed.assert_called_once_with(['q'])
