import json,tempfile,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from locagent_e2e.common import ROOT,manifest,allow,CONFIG,encoded
from locagent_e2e.driver import smoke,config_binding
from locagent_e2e.coding_tools import Session
class ResumeTests(unittest.TestCase):
 def test_non_smoke_dev_and_unknown_ids_fail_before_tools(self):
  m=manifest();other=next(r['instance_id'] for r in m['instances'] if r['instance_id'] not in m['smoke_ids'])
  with self.assertRaises(PermissionError):allow(other,smoke=True)
  with self.assertRaises(PermissionError):allow('unknown__repo-123')
 def test_resume_failure_and_changed_code_never_send_request(self):
  from locagent_e2e.common import write_json
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);write_json(p/'state.json',{'code_binding':config_binding(),'steps':{'one':{'status':'running'}},'failed':None})
   with patch('locagent_e2e.transport.LiveTransport.exchange') as exchange:
    with self.assertRaisesRegex(RuntimeError,'no_automatic_retry'):smoke(p,'does-not-exist','does-not-exist')
    exchange.assert_not_called()
   write_json(p/'state.json',{'code_binding':'wrong','steps':{},'failed':None})
   with self.assertRaisesRegex(RuntimeError,'binding_changed'):smoke(p,'none','none')
 def test_tool_byte_budget_and_gate(self):
  class Huge:
   def execute(self,**kwargs):return {'exit_code':0,'stdout':'界'*100000}
  session=Session(Huge())
  for _ in range(20):session.execute('terminal',{'command':'fixture','timeout_seconds':1})
  self.assertLessEqual(session.used,CONFIG['coding']['evidence_bytes']);self.assertTrue(session.closed)
 def test_actual_sdk_locator_preserves_existing_final_answer(self):
  from locagent_e2e.baseline import CurrentRetriever
  from locagent_e2e.agent import run
  from locagent_e2e.transport import ScriptedTransport
  from readonly_agent.core import Snapshot
  from readonly_agent.offline import no_network
  from test_preparation import response
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'a.py').write_text('def method(): return 1\n');snap=Snapshot(root,['a.py']);snap.e2e_source_root=root
   final={'files':['a.py'],'entities':['a.py:method'],'answer':'Inspect method; uncertain.'}
   t=ScriptedTransport([response('locagent_retrieve',{'query':'method','offset':0},1),response('finish',{'message':final},2)])
   with no_network(root/'profiles') as attempts:result=run(issue='inspect method',output=root/'result',transport=t,locator=CurrentRetriever(snap),scripted=True)
   self.assertEqual(result['status'],'completed',result);self.assertEqual(result['finished'],final);self.assertEqual(attempts,[])
 def test_guard_rejects_holdout_content_without_opening_file(self):
  fake=ROOT/'freezes/holdout-v1/sealed/verified-test.parquet'
  with self.assertRaisesRegex(PermissionError,'holdout_content_forbidden'):fake.open('rb')
