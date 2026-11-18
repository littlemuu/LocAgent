import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from readonly_agent.core import Snapshot,digest,FileTools
from experiments.sdk_hybrid_v8.config import RetrievalConfig
from experiments.sdk_hybrid_v8.corpus import Corpus
from experiments.sdk_hybrid_v8.retriever import HybridRetriever
from experiments.sdk_hybrid_v8.vectors import make_synthetic_cache
from query_contract import validate_retrieval_query

SOURCE='''from typing import overload
class Model:
    @property
    def value(self):
        return self._value
    @value.setter
    def value(self, new):
        """adjust sentinelsetter"""
        self._value = new
@overload
def parse(x: str): ...
@overload
def parse(x: int): ...
def parse(x):
    return x
if True:
    def conditional(): return "first"
else:
    def conditional(): return "second"
'''
class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=Path(self.tmp.name);(p/'m.py').write_text(SOURCE)
        self.snapshot=Snapshot(p,['m.py']);self.corpus=Corpus(self.snapshot)
    def test_getter_setter_overloads_and_conditional_retained(self):
        for entity,n in [('m.py:Model.value',2),('m.py:parse',3),('m.py:conditional',2)]:
            ids=self.corpus.nodes[entity]['definitions'];self.assertEqual(len(ids),n);self.assertEqual(len(set(ids)),n)
        self.assertEqual(len(self.corpus.documents),7)
    def test_body_query_selects_setter_span_and_discloses_other(self):
        r=HybridRetriever(self.snapshot,RetrievalConfig(mode='body_bm25'))
        text=r.retrieve('sentinelsetter')
        candidate=r.last_audit['candidates'][0]
        self.assertEqual(candidate['id'],'m.py:Model.value')
        definition=self.corpus.definitions[candidate['definition_id']]
        self.assertEqual(definition['start_line'],7)
        self.assertIn('self._value = new',text);self.assertIn('2 source definitions',text)
    def test_dense_query_selects_overload_implementation(self):
        q='implementation semantic test';cfg=RetrievalConfig(mode='dense')
        vectors={d.id:([1.,0.] if d.entity=='m.py:parse' and 'return x' in d.text else [0.,1.]) for d in self.corpus.documents}
        cache=make_synthetic_cache(self.corpus,cfg,vectors,{q:[1.,0.]})
        r=HybridRetriever(self.snapshot,cfg,cache=cache,cache_hash=digest(cache));text=r.retrieve(q)
        self.assertEqual(self.corpus.definitions[r.last_audit['candidates'][0]['definition_id']]['start_line'],14)
        self.assertIn('return x',text)
    def test_exact_name_discloses_ambiguity_and_query_resets_scores(self):
        r=HybridRetriever(self.snapshot,RetrievalConfig(mode='body_bm25'))
        r.retrieve('sentinelsetter');text=r.retrieve('m.py:Model.value')
        self.assertEqual(r.last_audit['candidates'][0]['definition_selection'],'source_order_with_ambiguity_disclosed')
        self.assertIn('2 source definitions',text)
    def test_query_exact_unicode_byte_boundary_and_no_truncation(self):
        from readonly_agent.openhands_tools import RetrievalQueryAction,QueryAction
        q='界'*5333+'a'
        self.assertEqual(len(q.encode()),16000)
        validate_retrieval_query(q);self.assertEqual(RetrievalQueryAction(query=q).query,q)
        for bad in [q+'b','', '  ', '\ud800']:
            with self.assertRaises(ValueError):validate_retrieval_query(bad)
            with self.assertRaises(ValueError):RetrievalQueryAction(query=bad)
        with self.assertRaises(ValueError):QueryAction(query='x'*257)
    def test_filetools_preserves_long_query_and_rejects_bytes_overflow(self):
        class Recording:
            snapshot_id=self.snapshot.identity
            def retrieve(self,q):self.query=q;return 'source'
        r=Recording();t=FileTools(self.snapshot,r);q='long query '*300
        t.respond('locagent_retrieve',{'query':q,'offset':0},14000);self.assertEqual(r.query,q)
        with self.assertRaises(ValueError):t.respond('locagent_retrieve',{'query':'界'*6000,'offset':0},14000)
