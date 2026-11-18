import importlib.util,json,math,random,sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from copy import deepcopy
from unittest.mock import patch
from readonly_agent.core import Snapshot,digest,FileTools,encoded
from experiments.sdk_hybrid_v8.config import RetrievalConfig
from experiments.sdk_hybrid_v8.corpus import Corpus
from experiments.sdk_hybrid_v8.ranking import entity_ranking,fuse,BodyBM25,file_projection
from experiments.sdk_hybrid_v8.vectors import CachedDense,QueryVectorMissing,make_synthetic_cache,query_key
from experiments.sdk_hybrid_v8.retriever import HybridRetriever
from experiments.sdk_hybrid_v8.demo import fixture,QUERY

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=RetrievalConfig();self.snapshot,self.cache=fixture(self.root/'source',self.config);self.corpus=Corpus(self.snapshot)
    def snapshot_of(self,files,hidden=()):
        root=self.root/'extra';root.mkdir()
        for path,text in files.items():
            p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode())
        return Snapshot(root,list(files),hidden_python_paths=hidden)
    def dense(self,cache=None,config=None):
        cache=self.cache if cache is None else cache
        return CachedDense(cache,self.corpus,config or self.config,digest(cache))
    def retriever(self,config=None,cache=None):
        cache=self.cache if cache is None else cache
        return HybridRetriever(self.snapshot,config or self.config,cache=cache,cache_hash=digest(cache))
    def test_bm25_retrieves_body_terms_absent_from_names(self):
        lex=BodyBM25(self.corpus.documents);names,scores=lex.search('stale entries')
        self.assertEqual(names,['cache.py:purge_cache']);self.assertGreater(scores[names[0]],0)
    def test_bm25_empty_positive_pool(self):
        lex=BodyBM25(self.corpus.documents)
        self.assertEqual(lex.search('zzzzzzzzzz'),([],{}));self.assertEqual(lex.search('...'),([],{}))
    def test_dense_and_weighted_fusion_reference_formula(self):
        rank,s=fuse(['b','a'],['a','b']);self.assertEqual(rank,['a','b']);self.assertAlmostEqual(s['a'],1/62+2/61)
    def test_legacy_fusion_equivalence_many_rankings(self):
        # Load only the historical pure functions, without importing experiment runners.
        import ast,os
        legacy=Path(os.environ['V8_LEGACY_ROOT'])/'scripts/offline_bailian_rrf.py'
        tree=ast.parse(legacy.read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('rrf','entity_ranking')]
        scope={'math':math};exec(compile(ast.Module(body=functions,type_ignores=[]),str(legacy),'exec'),scope)
        rng=random.Random(8)
        for _ in range(50):
            ids=[f'm.py:f{i}' for i in range(12)];a=rng.sample(ids,rng.randrange(13));b=rng.sample(ids,rng.randrange(13))
            self.assertEqual(fuse(a,b),scope['rrf'](a,b,60,1,2))
        docs=self.corpus.documents;scores=[1.,0.,-1.]
        self.assertEqual(entity_ranking(docs,scores,True),scope['entity_ranking']([{'entity':d.entity} for d in docs],scores,True))
    def test_max_chunk_entity_and_lexical_tie(self):
        d=self.corpus.documents[0];docs=[replace(d,entity='b'),replace(d,entity='a'),replace(d,entity='b'),replace(d,entity='zero')]
        self.assertEqual(entity_ranking(docs,[.5,1.,1.,0.],True),(['a','b'],{'b':1.,'a':1.}))
    def test_nonfinite_and_duplicate_rank_rejected(self):
        with self.assertRaises(ValueError):entity_ranking(self.corpus.documents,[float('nan')]*3)
        with self.assertRaises(ValueError):fuse(['a','a'],['b'])
    def test_no_pretruncation_before_rrf(self):
        a=['a'+str(i) for i in range(30)];b=list(reversed(a));rank,_=fuse(a,b)
        self.assertEqual(len(rank),30);self.assertEqual(rank[0],b[0])
    def test_file_projection_uses_full_entity_ranking(self):
        rows=file_projection(['a.py:f','a.py:g','a.py:h','b.py:f','c.py:f'],2)
        self.assertEqual(rows,[{'path':'a.py','best_entity':'a.py:f','entity_rank':1},{'path':'b.py','best_entity':'b.py:f','entity_rank':4}])
    def test_dense_max_block_before_topk(self):
        s=self.snapshot_of({'a.py':'def many():\n'+('    x = 1\n'*30)+'def other():\n    return 2\n'})
        cfg=replace(self.config,max_chars=32,top_k=2);corpus=Corpus(s,cfg.max_chars)
        docs={d.id:([1.,0.] if d.entity.endswith('many') else [.8,.6]) for d in corpus.documents}
        cache=make_synthetic_cache(corpus,cfg,docs,{'query':[1.,0.]})
        rank,_=CachedDense(cache,corpus,cfg,digest(cache)).search('query')
        self.assertEqual(rank,['a.py:many','a.py:other'])
    def test_source_not_executed_and_bom_crlf_ranges_preserved(self):
        src='\ufeffraise RuntimeError("DO NOT EXECUTE")\r\nclass 容器:\r\n    async def 计算(self):\r\n        return "字"\r\n'
        s=self.snapshot_of({'m.py':src});c=Corpus(s);self.assertEqual(s.files['m.py'],src)
        self.assertIn('m.py:容器.计算',c.nodes);self.assertEqual(c.documents[0].start,3)
        r=HybridRetriever(s,RetrievalConfig(mode='body_bm25'));text=r.retrieve('容器.计算');self.assertIn('4:         return "字"',text)
    def test_snapshot_scope_includes_explicit_hidden_tests_and_config(self):
        s=self.snapshot_of({'tests/test_a.py':'def test_x(): pass\n','.pkg/a.py':'def x(): pass\n','settings.py':'def get(): pass\n'},hidden=['.pkg/a.py'])
        c=Corpus(s);self.assertEqual(len(c.documents),3);self.assertEqual(c.excluded,[])
    def test_decorators_nested_functions_and_long_line_splits(self):
        s=self.snapshot_of({'a.py':'@decorator\ndef outer():\n    def inner(): return "'+('x'*80)+'"\n    return inner()\n'})
        c=Corpus(s,32);self.assertEqual({d.entity for d in c.documents},{'a.py:outer','a.py:outer.inner'})
        self.assertEqual(c.documents[0].start,1);self.assertGreater(len(c.documents),2)
    def test_function_chunk_text_matches_legacy_on_common_scope(self):
        import os
        path=Path(os.environ['V8_LEGACY_ROOT'])/'locagent_service/rag_offline.py'
        spec=importlib.util.spec_from_file_location('v8_legacy_rag_reference',path)
        legacy=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{spec.name:legacy}):spec.loader.exec_module(legacy)
        source='class A:\r\n    @dec\r\n    async def f(self):\r\n        if True:\r\n            def inner(): return "'+('x'*80)+'"\r\n        return inner()\r\n'
        snapshot=self.snapshot_of({'tests/a.py':source})
        for size in (32,12000):
            version=legacy.Version('fixture/repo','a'*40,'synthetic-v8-fixture',max_chars=size)
            old=[(c.path+':'+c.entity,c.start,c.end,c.part,c.path+':'+c.entity+'\n'+c.text) for c in legacy.chunk_snapshot({'tests/a.py':source.encode()},version) if c.kind=='function']
            new=[(d.entity,d.start,d.end,d.part,d.text) for d in Corpus(snapshot,size).documents]
            self.assertEqual(new,old)
    def test_duplicate_entity_definition_is_not_silently_overwritten(self):
        s=self.snapshot_of({'a.py':'def f(): pass\ndef f(): pass\n'})
        with self.assertRaisesRegex(ValueError,'duplicate_entity'):Corpus(s)
    def test_no_function_corpus_is_explicit_and_exact_files_work(self):
        s=self.snapshot_of({'a.py':'value = 1\n'})
        r=HybridRetriever(s,RetrievalConfig(mode='body_bm25'));self.assertIn('No locations',r.retrieve('find a computation'))
        self.assertIn('value = 1',r.retrieve('a.py'))
    def test_cache_hash_snapshot_corpus_model_dimension_binding(self):
        with self.assertRaisesRegex(ValueError,'hash'):CachedDense(self.cache,self.corpus,self.config,'0'*64)
        for key,value in [('snapshot','other'),('corpus','other'),('model','other'),('dimensions',3)]:
            c=deepcopy(self.cache);c[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.dense(c)
    def test_corrupt_vectors_and_membership_never_fallback(self):
        for value in [[0.,0.],[True,0.],[float('inf'),0.],[1.]]:
            c=deepcopy(self.cache);c['documents'][next(iter(c['documents']))]=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.dense(c)
        c=deepcopy(self.cache);c['documents']['foreign']=[1.,0.]
        with self.assertRaises(ValueError):self.retriever(replace(self.config,fallback='body_bm25'),c)
    def test_real_cache_kind_and_extra_fields_rejected(self):
        for key,val in [('kind','real-provider'),('endpoint','https://example.invalid')]:
            c=deepcopy(self.cache);c[key]=val
            with self.assertRaises(ValueError):self.dense(c)
    def test_query_exact_utf8_cache_miss(self):
        with self.assertRaises(QueryVectorMissing):self.dense().search(QUERY+' ')
    def test_missing_query_error_is_not_empty_result(self):
        with self.assertRaises(QueryVectorMissing):self.retriever().retrieve('uncached prose')
    def test_explicit_fallback_reports_actual_mode_and_reason(self):
        r=self.retriever(replace(self.config,fallback='body_bm25'));text=r.retrieve('stale entries')
        self.assertTrue(r.last_audit['degraded']);self.assertEqual(r.last_audit['executed_mode'],'body_bm25');self.assertIn('Explicit fallback',text)
    def test_dense_mode_does_not_run_lexical_search(self):
        r=self.retriever(replace(self.config,mode='dense'))
        with patch.object(r.lexical,'search',side_effect=AssertionError('should not query')):r.retrieve(QUERY)
        self.assertEqual(r.last_audit['lexical_candidates'],0)
    def test_exact_route_bypasses_dense_search_and_preserves_ambiguity(self):
        r=self.retriever()
        with patch.object(r.dense,'search',side_effect=AssertionError('exact')):text=r.retrieve('cache.py:purge_cache')
        self.assertEqual(r.last_audit['executed_mode'],'exact');self.assertIn('purge_cache',text)
    def test_renderer_preserves_fusion_order(self):
        r=self.retriever();r.retrieve(QUERY);rows=r.last_audit['candidates']
        self.assertEqual(rows[0]['id'],'cache.py:purge_cache');self.assertEqual(rows[0]['bm25_rank'],1);self.assertEqual(rows[0]['dense_rank'],1)
        self.assertAlmostEqual(rows[0]['fusion_score'],3/61)
    def test_configuration_fails_closed(self):
        for kw in [{'mode':'live'},{'dense_weight':1},{'dimensions':True},{'top_k':6},{'max_chars':0},{'embedding_model':'real-model'}]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):RetrievalConfig(**kw)
    def test_preview_pagination_uses_cached_ranking(self):
        r=self.retriever();tools=FileTools(self.snapshot,r);parts=[];offset=0
        with patch.object(r,'retrieve',wraps=r.retrieve) as call:
            for _ in range(200):
                page=tools.respond('locagent_retrieve',{'query':QUERY,'offset':offset},350)
                self.assertLessEqual(len(encoded(page)),350);parts.append(page['text'])
                if page['next_offset'] is None:break
                offset=page['next_offset']
            self.assertEqual(call.call_count,1)
        self.assertGreater(len(parts),1);self.assertIn('cache.py:purge_cache',''.join(parts))

if __name__=='__main__':unittest.main()
