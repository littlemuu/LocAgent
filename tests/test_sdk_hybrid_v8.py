import json,os,subprocess,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
from unittest.mock import patch
from readonly_agent.core import Limits,encoded
from experiments.sdk_hybrid_v8.config import RetrievalConfig
from experiments.sdk_hybrid_v8.demo import fixture,response,QUERY
from experiments.sdk_hybrid_v8.bridge import ProcessRetriever,RetrievalFailed
from experiments.sdk_hybrid_v8.sdk_adapter import run_offline

class SdkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=RetrievalConfig();self.snapshot,self.cache=fixture(self.root/'source',self.cfg)
    def retriever(self,cfg=None):return ProcessRetriever(self.snapshot,cfg or self.cfg,python=os.environ['V8_RETRIEVAL_PYTHON'],cache=self.cache)
    def finish(self):return response('finish',{'files':['cache.py'],'entities':['cache.py:purge_cache'],'answer':'Offline scripted fixture.'},'done')
    def run_case(self,script,r=None,limits=None):
        result=run_offline(snapshot=self.snapshot,issue=QUERY,script=script,output_dir=self.root/'sdk',retriever=r or self.retriever(),limits=limits or Limits(max_requests=4))
        self.assertEqual(result['network_attempts'],0)
        return result
    def test_real_sdk_hybrid_evidence_read_and_finish(self):
        script=[response('locagent_retrieve',{'query':QUERY,'offset':0},'r'),response('read_file',{'path':'cache.py','start_line':1,'end_line':4},'read'),self.finish()]
        r=self.run_case(script);self.assertEqual(r['status'],'completed');self.assertEqual(r['worker_calls'],1);self.assertEqual(r['real_llm_requests'],0);self.assertEqual(r['real_embedding_requests'],0)
        self.assertEqual(r['retrieval_audit'][0]['executed_mode'],'hybrid')
        events=[json.loads(x) for x in (self.root/'sdk/trace.jsonl').read_text().splitlines()]
        requests=[e for e in events if e['event']=='request'];self.assertIn('cache.py:purge_cache',json.dumps(requests[1]['request']['messages']))
        self.assertIn('return {k: v',json.dumps(requests[2]['request']['messages']))
    def test_missing_query_is_terminal_not_successful_fallback(self):
        r=self.run_case([response('locagent_retrieve',{'query':'uncached query','offset':0}),self.finish()])
        self.assertEqual(r['status'],'failed');self.assertEqual(r['failure'],'retrieval_failed');self.assertEqual(r['requests'],1);self.assertIsNone(r['answer'])
    def test_explicit_fallback_completes_and_is_audited(self):
        r=self.run_case([response('locagent_retrieve',{'query':'stale entries','offset':0}),self.finish()],r=self.retriever(replace(self.cfg,fallback='body_bm25')))
        self.assertEqual(r['status'],'completed');self.assertTrue(r['retrieval_audit'][0]['degraded']);self.assertEqual(r['retrieval_audit'][0]['executed_mode'],'body_bm25')
    def test_sdk_source_budget_closes_investigation(self):
        r=self.run_case([response('locagent_retrieve',{'query':QUERY,'offset':0}),self.finish()],limits=Limits(max_requests=4,source_bytes=500,page_bytes=500))
        self.assertEqual(r['status'],'completed');self.assertLessEqual(r['source_bytes'],500)
        events=[json.loads(x) for x in (self.root/'sdk/trace.jsonl').read_text().splitlines()];req=[x for x in events if x['event']=='request']
        self.assertTrue(req[1]['request']['closing'])
    def test_closed_tools_cannot_reopen(self):
        r=self.run_case([response('locagent_retrieve',{'query':QUERY,'offset':0}),response('read_file',{'path':'cache.py'})],limits=Limits(max_requests=2))
        self.assertEqual(r['status'],'failed');self.assertEqual(r['failure'],'unavailable_tool')
    def test_request_size_limit(self):
        r=self.run_case([self.finish()],limits=Limits(max_requests=2,request_bytes=20));self.assertEqual(r['failure'],'request_budget_exhausted');self.assertEqual(r['worker_calls'],0)
    def test_response_size_limit(self):
        r=self.run_case([self.finish()],limits=Limits(max_requests=2,response_bytes=20))
        self.assertEqual(r['status'],'failed');self.assertEqual(r['failure'],'response_budget_exhausted');self.assertIsNone(r['answer'])
    def test_worker_network_attempt_is_terminal(self):
        r=self.retriever();bad={'snapshot':r.snapshot_id,'text':'x','audit':{},'network_attempts':1}
        with patch('experiments.sdk_hybrid_v8.bridge.subprocess.run',return_value=subprocess.CompletedProcess([],0,encoded(bad),b'')) as call:
            with self.assertRaises(RetrievalFailed):r.retrieve(QUERY)
            with self.assertRaises(RetrievalFailed):r.retrieve(QUERY)
            self.assertEqual(call.call_count,1)
    def test_worker_timeout_is_sticky_and_not_retried(self):
        r=self.retriever()
        with patch('experiments.sdk_hybrid_v8.bridge.subprocess.run',side_effect=subprocess.TimeoutExpired('fixture',.01)) as call:
            with self.assertRaises(RetrievalFailed):r.retrieve(QUERY)
            with self.assertRaises(RetrievalFailed):r.retrieve(QUERY)
            self.assertEqual(call.call_count,1)
    def test_worker_identity_tamper_is_terminal(self):
        r=self.retriever();bad={'snapshot':'wrong','text':'x','audit':{},'network_attempts':0}
        with patch('experiments.sdk_hybrid_v8.bridge.subprocess.run',return_value=subprocess.CompletedProcess([],0,encoded(bad),b'')):
            with self.assertRaises(RetrievalFailed):r.retrieve(QUERY)
        self.assertIsNotNone(r.failure)
    def test_multi_page_same_query_only_one_worker(self):
        from readonly_agent.core import FileTools
        r=self.retriever();tools=FileTools(self.snapshot,r);offset=0;pages=[]
        for _ in range(100):
            page=tools.respond('locagent_retrieve',{'query':QUERY,'offset':offset},350);pages.append(page['text'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        self.assertGreater(len(pages),1);self.assertEqual(r.worker_calls,1)
    def test_cancelled_investigation_calls_no_worker(self):
        from readonly_agent.openhands_tools import ToolSession
        r=self.retriever();s=ToolSession(self.snapshot,retriever=r);s.close_investigation();s.execute('locagent_retrieve',{'query':QUERY,'offset':0})
        self.assertEqual(r.worker_calls,0);self.assertEqual(s.audit[-1]['result']['error'],'investigation_closed')
    def test_no_live_or_credentials_argument(self):
        with self.assertRaises(TypeError):run_offline(snapshot=self.snapshot,issue=QUERY,script=[],output_dir=self.root/'none',retriever=self.retriever(),live=True)
        self.assertFalse((self.root/'none').exists())
    def test_invalid_finish_preserved_as_failure(self):
        r=self.run_case([response('finish',{'files':[],'entities':['cache.py'],'answer':'invalid'})]);self.assertEqual(r['status'],'failed');self.assertIsNone(r['answer'])

if __name__=='__main__':unittest.main()
