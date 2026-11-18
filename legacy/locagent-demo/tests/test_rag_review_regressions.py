import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from locagent_service.rag_offline import Version,Chunk,ExactIndex,SearchConfig,chunk_snapshot
from locagent_service.rag_graph_adapter import GraphModuleRetriever

class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):self.v=Version('a/repo','a'*40,'fake-v1')
    def adapter(self,mode='hybrid'):
        a1=Chunk(self.v,'a.py','a','function',1,2,0,'first part')
        a2=Chunk(self.v,'a.py','a','function',3,4,1,'matching part')
        b=Chunk(self.v,'a.py','b','function',5,6,0,'other function')
        provider=Mock(model='fake-v1',dimensions=2);provider.embed.return_value=[[1.,0.]]
        index=ExactIndex(self.v,2,((a1,(-1.,0.)),(a2,(1.,0.)),(b,(.8,.6))))
        lexical=Mock(stemmer=None);lexical.retrieve.return_value=[SimpleNamespace(text='a.py:a',score=10),SimpleNamespace(text='a.py:b',score=5)]
        return GraphModuleRetriever(lexical,self.v,[a1,a2,b],['a.py:a','a.py:b'],index=index,provider=provider,config=SearchConfig(mode,k=2))
    def test_module_rrf_agreement_across_chunk_parts(self):
        a=self.adapter()
        self.assertEqual([n.text for n in a.retrieve('q')],['a.py:a','a.py:b'])
    def test_formfeed_function_text(self):
        self.assertEqual(self.v.chunker,'python-ast-lines-v2')
        raw='def f():\n    return "a\fb"\n'
        cs=chunk_snapshot({'a.py':raw.encode()},self.v)
        self.assertEqual(''.join(c.text for c in cs if c.entity=='f'),raw)
    def test_handler_and_match_entities(self):
        raw='try:\n    pass\nexcept Exception:\n    def rescue():\n        return 1\nmatch 1:\n    case 1:\n        def matched():\n            return 2\n'
        cs=chunk_snapshot({'a.py':raw.encode()},self.v)
        self.assertTrue({'rescue','matched'}<={c.entity for c in cs})
    def test_physical_newlines_controls_and_following_function(self):
        for sep in ('\n','\r\n','\r'):
            for control in ('\f','\v','\x85','\u2028','\u2029'):
                with self.subTest(sep=repr(sep),control=repr(control)):
                    lines=['def first():',f'    return "a{control}b"',f'# comment a{control}b','def second():','    return 2']
                    raw=sep.join(lines)+sep
                    cs=chunk_snapshot({'a.py':raw.encode()},self.v)
                    f=next(c for c in cs if c.entity=='first');g=next(c for c in cs if c.entity=='second')
                    self.assertEqual((f.start,f.end,g.start,g.end),(1,2,4,5))
                    self.assertEqual(f.text,sep.join(lines[:2])+sep)
                    self.assertEqual(g.text,sep.join(lines[3:])+sep)
                    self.assertEqual(''.join(c.text for c in cs),raw)
    def test_nested_scopes_handler_star_and_match_no_duplicates(self):
        raw='class C:\n    def outer(self):\n        try:\n            pass\n        except* ValueError:\n            def rescue():\n                pass\n        match 1:\n            case 1:\n                class Inner:\n                    def method(self):\n                        pass\n'
        cs=chunk_snapshot({'a.py':raw.encode()},self.v)
        expected=['C','C.outer','C.outer.rescue','C.outer.Inner','C.outer.Inner.method']
        self.assertEqual(sorted(c.entity for c in cs),sorted(expected))
        self.assertEqual(len(cs),len({c.id for c in cs}))
        self.assertEqual({c.entity:(c.start,c.end) for c in cs}['C.outer.rescue'],(6,7))
    def test_dense_and_hybrid_top_k_after_entity_dedup(self):
        for mode in ('dense','hybrid'):
            with self.subTest(mode=mode):
                a=self.adapter(mode)
                rows=list(a.index.rows);rows[0]=(rows[0][0],(.9,.1));a.index=ExactIndex(self.v,2,tuple(rows))
                self.assertEqual([n.text for n in a.retrieve('q')],['a.py:a','a.py:b'])
    def test_duplicate_lexical_nodes_do_not_change_fusion(self):
        a=self.adapter();expected=[n.text for n in a.retrieve('q')]
        a.lexical.retrieve.return_value.insert(1,a.lexical.retrieve.return_value[0])
        self.assertEqual([n.text for n in a.retrieve('q')],expected)
    def test_expression_depth_does_not_add_recursive_scope_walk(self):
        raw='VALUE = '+ '+'.join(['1']*1200)+'\ndef following():\n    return 1\n'
        cs=chunk_snapshot({'a.py':raw.encode()},self.v)
        self.assertEqual({c.entity for c in cs},{'', 'following'})

    def test_ties_deterministic_and_outside_membership_rejected(self):
        a=self.adapter('dense')
        a.index=ExactIndex(self.v,2,tuple((chunk,(1.,0.)) for chunk,_ in a.index.rows))
        self.assertEqual(a.retrieve('q'),a.retrieve('q'))
        foreign=Chunk(self.v,'other.py','x','function',1,1,0,'foreign')
        a.index=ExactIndex(self.v,2,((foreign,(1.,0.)),))
        with self.assertRaisesRegex(ValueError,'outside graph membership'):a.retrieve('q')

if __name__=='__main__':unittest.main()
