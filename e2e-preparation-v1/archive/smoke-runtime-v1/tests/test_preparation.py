import json,unittest,tempfile,sys,importlib.util
from pathlib import Path
from locagent_e2e.common import ROOT,encoded,CONFIG
from locagent_e2e.ledger import Ledger,BudgetStop
from locagent_e2e.transport import ScriptedTransport

def response(name,args,i):
 return {'id':f'fixture-{i}','object':'chat.completion','model':'deepseek-flash','choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':f'call-{i}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
class LocalFixture:
 def __init__(self,root):self.root=root
 def file(self,operation,path,content=None,old=None,new=None):
  p=self.root/path
  if operation=='create':p.write_text(content);return {'exit_code':0,'stdout':'created'}
  if operation=='view':return {'exit_code':0,'stdout':p.read_text()}
  text=p.read_text();assert text.count(old)==1;p.write_text(text.replace(old,new));return {'exit_code':0,'stdout':'replaced'}
 def execute(self,command,timeout_seconds):return {'exit_code':0,'stdout':'fixture tests passed'}
class PreparationTests(unittest.TestCase):
 def test_ledger_reservation_uncertain_blocks_retries(self):
  with tempfile.TemporaryDirectory() as td:
   ledger=Ledger(Path(td)/'ledger.json');r=ledger.reserve(1000,2048,'A')
   with self.assertRaises(BudgetStop):ledger.reserve(1000,2048,'A')
   with self.assertRaises(BudgetStop):Ledger(Path(td)/'ledger.json',11)
   ledger.settle(r['sequence'],response('finish',{},1),.5)
   self.assertEqual(ledger.read()['calls'][0]['charged_upper_microcny'],360)
 def test_cap_and_model_drift(self):
  with tempfile.TemporaryDirectory() as td:
   ledger=Ledger(Path(td)/'ledger.json',.001)
   with self.assertRaises(BudgetStop):ledger.reserve(1000,2048,'A')
  with tempfile.TemporaryDirectory() as td:
   ledger=Ledger(Path(td)/'ledger.json');r=ledger.reserve(100,200,'A');ledger.settle(r['sequence'],response('finish',{},1),.1)
   raw=response('finish',{},2);raw['model']='changed-model';r=ledger.reserve(100,200,'B');ledger.settle(r['sequence'],raw,.1)
   with self.assertRaises(BudgetStop):ledger.reserve(100,200,'B')
 def test_actual_sdk_edit_command_finish_and_ab_same_contract(self):
  from locagent_e2e.agent import run
  from readonly_agent.offline import no_network
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);results=[]
   for arm,packet in [('A',None),('B',{'files':['x.py'],'entities':[],'answer':'inspect x.py'})]:
    src=root/arm;src.mkdir();t=ScriptedTransport([response('edit_file',{'operation':'create','path':'x.py','content':'def f(): return 2\n'},1),response('terminal',{'command':'python -m unittest','timeout_seconds':1},2),response('finish',{'message':'Changed x.py and ran tests.'},3)])
    with no_network(root/'profile') as attempts:r=run(issue='fixture',output=root/(arm+'-out'),transport=t,sandbox=LocalFixture(src),packet=packet,scripted=True)
    self.assertEqual(r['status'],'completed',r);self.assertEqual(attempts,[]);self.assertEqual((src/'x.py').read_text(),'def f(): return 2\n');self.assertEqual(r['tool_calls'],2);results.append(r)
   for field in ('system_prompt_sha256','tool_schema_sha256','budget'):self.assertEqual(results[0][field],results[1][field])
 def test_sample_invariants_only_metadata(self):
  m=json.loads((ROOT/'data/dev24/manifest.json').read_text());self.assertEqual(len(m['instances']),24);self.assertGreaterEqual(len(m['repository_counts']),6);self.assertEqual(m['holdout_overlap_count'],0);self.assertEqual(m['smoke_ids'],m['selection_order'][:2])
 def test_locator_frozen_preview_body_terms_not_added(self):
  from locagent_e2e.baseline import CurrentRetriever
  from readonly_agent.core import Snapshot
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);(p/'a.py').write_text('def method():\n    """superuniquebodyword"""\n    return 1\n')
   snapshot=Snapshot(p,['a.py']);snapshot.e2e_source_root=p;r=CurrentRetriever(snapshot)
   self.assertEqual(r.lexical('superuniquebodyword'),[]);self.assertIn('a.py:method',r.retrieve('method'))
   with self.assertRaises(ValueError):r.retrieve('x'*257)
if __name__=='__main__':unittest.main()
