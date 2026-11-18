import unittest
from unittest.mock import Mock
from locagent_service.rag_offline import (Version,chunk_snapshot,allowed,ExactIndex,
    Hit,rrf,search,SearchConfig,ProviderError,IndexNotReady)

class Fake:
    model='fake-v1';dimensions=3
    def __init__(self):self.calls=[]
    def embed(self,texts):
        self.calls.extend(texts)
        return [[1+text.count('sign'),1+text.count('age'),1] for text in texts]

class RagTests(unittest.TestCase):
    def setUp(self):
        self.v=Version('a/repo','a'*40,'fake-v1')
        self.chunks=chunk_snapshot({'a.py':b'VALUE = 1\n\ndef sign(x):\n    return x\n\ndef age(x):\n    return x + 1\n'},self.v)
        self.p=Fake()
    def test_default_is_identity_no_provider(self):
        expected=object();lex=Mock(return_value=expected);provider=Mock()
        result=search('q',self.v,lex,provider=provider)
        self.assertIs(result.hits,expected);provider.embed.assert_not_called();lex.assert_called_once_with('q')
    def test_entity_lines_decorators_and_nested(self):
        raw=b'X=1\n@deco\nclass A:\n    async def f(self):\n        def nested():\n            pass\n        return 1\n'
        chunks=chunk_snapshot({'a.py':raw},self.v)
        self.assertEqual({c.entity for c in chunks},{'','A','A.f','A.f.nested'})
        cls=next(c for c in chunks if c.entity=='A');self.assertEqual((cls.start,cls.end),(2,7))
    def test_long_function_bounded_and_lossless(self):
        raw=('def long():\n'+''.join('    x = '+repr('a'*100)+'\n' for _ in range(50))).encode()
        chunks=chunk_snapshot({'a.py':raw},Version('a/repo','a'*40,'fake-v1',max_chars=64))
        self.assertTrue(all(len(c.text)<=64 for c in chunks))
        self.assertEqual(''.join(c.text for c in chunks),raw.decode())
        self.assertEqual(len({c.id for c in chunks}),len(chunks))
    def test_filter_paths(self):
        for path in ['.env','secrets.py','config.py','x/settings.py','.venv/a.py','venv/a.py','outputs/a.py','generated/a.py','../a.py','/a.py','x/../a.py','x//a.py','x\\a.py','x:a.py','a.py\n']:
            with self.subTest(path=path):self.assertFalse(allowed(path))
        self.assertTrue(allowed('src/example.py'))
    def test_binary_skipped(self):
        self.assertEqual(chunk_snapshot({'a.py':b'\0\xff'},self.v),())
    def test_invalid_python_fails(self):
        with self.assertRaises(ValueError):chunk_snapshot({'a.py':b'def ?'},self.v)
    def test_snapshot_and_chunk_limits(self):
        for kw in [{'max_bytes':1},{'max_files':0},{'max_chunks':1},{'max_chars':1}]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):chunk_snapshot({'a.py':b'def a():\n pass\ndef b():\n pass'},self.v,**kw)
    def test_line_shift_reuses_vector_not_membership(self):
        a=chunk_snapshot({'a.py':b'def f():\n return 1\n'},self.v)
        b=chunk_snapshot({'a.py':b'\n\ndef f():\n return 1\n'},Version('a/repo','b'*40,'fake-v1'))
        self.assertEqual(a[0].vector_key,b[0].vector_key);self.assertNotEqual(a[0].id,b[0].id)
        self.assertEqual(b[0].start,3)
        cache={};ExactIndex.build(self.v,a,self.p,cache);calls=len(self.p.calls)
        idx=ExactIndex.build(b[0].version,b,self.p,cache)
        self.assertEqual(len(self.p.calls),calls);self.assertEqual(idx.rows[0][0].start,3)
    def test_repo_commit_model_chunker_isolation(self):
        c=self.chunks[0]
        for v in [Version('b/repo','a'*40,'fake-v1'),Version('a/repo','b'*40,'fake-v1'),Version('a/repo','a'*40,'fake-v2'),Version('a/repo','a'*40,'fake-v1','v2')]:
            cc=chunk_snapshot({'a.py':c.text.encode()},v)[0]
            self.assertNotEqual(cc.id,c.id)
        with self.assertRaises(ValueError):ExactIndex.build(self.v,self.chunks,Mock(model='other'))
    def test_foreign_index_never_silent_fallback(self):
        idx=ExactIndex.build(self.v,self.chunks,self.p)
        with self.assertRaises(ValueError):search('q',Version('b/repo','a'*40,'fake-v1'),Mock(),index=idx,provider=self.p,config=SearchConfig('hybrid','bm25'))
    def test_exact_order_and_empty_query(self):
        idx=ExactIndex.build(self.v,self.chunks,self.p)
        one=idx.search('sign',self.v,self.p);two=idx.search('sign',self.v,self.p)
        self.assertEqual(one,two);self.assertEqual(idx.search('',self.v,self.p),[])
    def test_failed_build_does_not_publish_cache(self):
        provider=Fake();provider.embed=Mock(side_effect=[[[1,2,3]],RuntimeError('SECRET')]);cache={}
        with self.assertRaisesRegex(ProviderError,'^Embedding provider failed; no index published$'):
            ExactIndex.build(self.v,self.chunks,provider,cache)
        self.assertEqual(cache,{})
    def test_bad_vectors_fail(self):
        for out in [[],[[1,2]],[[0,0,0]],[[float('nan'),1,2]],[[True,1,2]],[[float('inf'),1,2]]]:
            self.p.embed=Mock(return_value=out)
            with self.subTest(out=out),self.assertRaises(ProviderError):ExactIndex.build(self.v,self.chunks,self.p)
    def test_not_ready_fallback_explicit(self):
        lex=Mock(return_value=[])
        with self.assertRaises(IndexNotReady):search('q',self.v,lex,config=SearchConfig('dense'))
        lex.assert_not_called()
        result=search('q',self.v,lex,config=SearchConfig('hybrid','bm25'))
        self.assertTrue(result.degraded);self.assertEqual(result.reason,'IndexNotReady')
    def test_provider_error_fallback(self):
        idx=ExactIndex.build(self.v,self.chunks,self.p);self.p.embed=Mock(side_effect=RuntimeError())
        result=search('q',self.v,lambda _:[],index=idx,provider=self.p,config=SearchConfig('dense','bm25'))
        self.assertEqual(result.reason,'ProviderError')
    def test_rrf_duplicates_and_tie(self):
        a,b=self.chunks[:2]
        result=rrf([[Hit(a,100),Hit(a,90)],[Hit(b,1)]])
        self.assertEqual(len(result),2);self.assertEqual(result[0].score,result[1].score)
        self.assertEqual([h.chunk.id for h in result],sorted([a.id,b.id]))
    def test_rrf_rejects_mixed_versions(self):
        foreign=chunk_snapshot({'a.py':b'x=1'},Version('b/repo','b'*40,'fake-v1'))[0]
        with self.assertRaises(ValueError):rrf([[Hit(self.chunks[0],1)],[Hit(foreign,1)]])
    def test_hybrid_lexical_failure_visible(self):
        idx=ExactIndex.build(self.v,self.chunks,self.p)
        with self.assertRaisesRegex(RuntimeError,'lexical'):
            search('q',self.v,Mock(side_effect=RuntimeError('lexical')),index=idx,provider=self.p,config=SearchConfig('hybrid','bm25'))
    def test_hybrid_combines_and_dense_skips_lexical(self):
        idx=ExactIndex.build(self.v,self.chunks,self.p);lex=Mock(return_value=[Hit(self.chunks[0],100)])
        out=search('sign',self.v,lex,index=idx,provider=self.p,config=SearchConfig('hybrid'))
        self.assertFalse(out.degraded);self.assertEqual(out.mode,'hybrid')
        lex.reset_mock();search('sign',self.v,lex,index=idx,provider=self.p,config=SearchConfig('dense'));lex.assert_not_called()
    def test_chunk_size_is_versioned(self):
        with self.assertRaises(ValueError):chunk_snapshot({'a.py':b'x=1'},self.v,max_chars=64)
        v=Version('a/repo','a'*40,'fake-v1',max_chars=64)
        a=chunk_snapshot({'a.py':b'x=1'},self.v)[0]
        b=chunk_snapshot({'a.py':b'x=1'},v)[0]
        self.assertNotEqual(a.id,b.id)

    def test_config_and_version_reject_invalid(self):
        with self.assertRaises(ValueError):SearchConfig('unknown')
        with self.assertRaises(ValueError):Version('a/repo','main','fake')

if __name__=='__main__':unittest.main()
