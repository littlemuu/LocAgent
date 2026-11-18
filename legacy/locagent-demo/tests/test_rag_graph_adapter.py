import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory
from pathlib import Path
from locagent_service.rag_offline import Version,chunk_snapshot,ExactIndex,SearchConfig
from locagent_service.rag_graph_adapter import GraphModuleRetriever
from locagent_service.offline import offline_engine

class FakeEmbedding:
    model='fake-v1';dimensions=2
    def embed(self,texts):return [[1.,1.] for _ in texts]

class GraphAdapterTests(unittest.TestCase):
    def setUp(self):
        self.v=Version('demo/demo','a'*40,'fake-v1')
        self.code='def render(value):\n' + '    # deterministic fixture body\n'*8 + '    return value\n'
        self.chunks=chunk_snapshot({'src/demo.py':self.code.encode()},self.v)
        self.lex=Mock(stemmer=None);self.lex.retrieve.return_value=[SimpleNamespace(text='src/demo.py:render',score=1)]
        self.embedding=FakeEmbedding();self.index=ExactIndex.build(self.v,self.chunks,self.embedding)
    def adapter(self,mode='hybrid'):
        return GraphModuleRetriever(self.lex,self.v,self.chunks,['src/demo.py','src/demo.py:render'],index=self.index,provider=self.embedding,config=SearchConfig(mode))
    def test_bm25_identity(self):
        a=self.adapter('bm25');expected=self.lex.retrieve.return_value
        self.assertIs(a.retrieve('value'),expected)
    def test_fallback_preserves_missing_index_results(self):
        self.check_fallback(False)
    def test_fallback_preserves_provider_error_results(self):
        self.check_fallback(True)
    def check_fallback(self, fail_provider):
        expected=[SimpleNamespace(text='src/demo.py:render',score=5),
                  SimpleNamespace(text='settings.py',score=4)]
        self.lex.retrieve.return_value=expected
        if fail_provider:self.embedding.embed=Mock(side_effect=RuntimeError('offline failure'))
        a=GraphModuleRetriever(self.lex,self.v,self.chunks,
            ['src/demo.py:render','settings.py'],
            index=self.index if fail_provider else None,provider=self.embedding,
            config=SearchConfig('hybrid','bm25'))
        self.assertIs(a.retrieve('value'),expected)
        self.lex.retrieve.assert_called_once_with('value')
        self.assertTrue(a.last_diagnostics['degraded'])
        self.assertEqual(a.last_diagnostics['mode'],'bm25')
    def test_reject_cross_task(self):
        with self.assertRaises(ValueError):self.adapter().validate_task({'repo':'other/repo','base_commit':'a'*40})
    def test_hybrid_maps_to_existing_graph_entities(self):
        a=self.adapter();nodes=a.retrieve('value')
        self.assertEqual([n.text for n in nodes],['src/demo.py:render'])
        self.assertEqual(a.last_diagnostics,{'mode':'hybrid','degraded':False,'reason':None})
    def test_fake_agent_tool_loop_uses_adapter(self):
        with offline_engine():
            import networkx as nx
            from litellm import ModelResponse
            from util.localizer import GraphLocalizer
            from util.localization_contract import LocalizationRequest,LocalizationOptions
            graph=nx.MultiDiGraph()
            graph.add_node('src/demo.py',type='file',code=self.code)
            graph.add_node('src/demo.py:render',type='function',code=self.code.rstrip('\n'),start_line=1,end_line=10)
            graph.add_edge('src/demo.py','src/demo.py:render',type='contains')
            responses=iter([('search_code_snippets',{'search_terms':['mysterious transformation']}),('finish',{'files':['src/demo.py'],'entities':['src/demo.py:render']})])
            def provider(**kwargs):
                tool,args=next(responses)
                return ModelResponse(model='offline',choices=[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'call','type':'function','function':{'name':tool,'arguments':json.dumps(args)}}]}}],usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
            from plugins.location_tools.repo_ops import repo_ops
            temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
            corpus=Path(temp.name)/'demo-1';corpus.mkdir();(corpus/'corpus.jsonl').write_text('')
            fallback=patch.object(repo_ops,'bm25_content_retrieve',return_value=[])
            fallback.start();self.addCleanup(fallback.stop)
            adapter=self.adapter()
            engine=GraphLocalizer.from_graph(graph,provider=provider,model_name='offline',module_retriever=adapter,bm25_index_dir=temp.name,options=LocalizationOptions(max_iterations=2,search_protocol='bounded-v1'))
            result=engine.localize(LocalizationRequest('demo-1','demo/demo','a'*40,'Find transformation.'))
            self.assertIn('src/demo.py:render',result.found_entities)
            self.lex.retrieve.assert_called()
            self.assertEqual(adapter.last_diagnostics['mode'],'hybrid')

class PayloadModeTests(unittest.TestCase):
    def test_explicit_nonthinking_and_model_override_are_bound(self):
        from locagent_service.public_authorization import request_payload
        config={'model':'deepseek-flash','output_tokens':1024,'request_bytes':65536,'disable_thinking':True}
        payload=json.loads(request_payload(config,{'messages':[{'role':'user','content':'test'}],'model':'unapproved','thinking':{'type':'enabled'}}))
        self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['max_tokens'],1024)
    def test_generic_default_omits_provider_specific_parameter(self):
        from locagent_service.public_authorization import request_payload
        payload=json.loads(request_payload({'model':'stub','output_tokens':1,'request_bytes':1024},{'messages':[]}))
        self.assertNotIn('thinking',payload)
