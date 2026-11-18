"""Real SDK on both arms, simulated helper only; verify sole initial wire delta."""
import base64,json,subprocess,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from experiments.sdk_finish_selfcheck_v7.freeze import candidate
from experiments.sdk_finish_selfcheck_v7.parent import Parent,BatchLedger
from experiments.sdk_finish_selfcheck_v7.guard import CohortAuthority,CohortWire,verify,RehearsalAuthority
from experiments.sdk_finish_selfcheck_v7.sdk_adapter import run_sdk_case
from experiments.sdk_finish_selfcheck_v7.common_contract import FINISH
from readonly_agent.core import digest,encoded,Limits
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from tests.test_sdk_selfcheck_v7_batch import base_surface

class FairnessTests(unittest.TestCase):
 def test_real_sdk_initial_wire_only_selfcheck_delta(self):
  p=candidate('live');h=digest(p)
  with TemporaryDirectory() as td:
   root=Path(td).resolve()
   with no_network(root/'profiles') as attempts:
    parent=Parent(root/'SYNTHETIC-ONLY');parent.prepare(p,consent=f'APPROVE SDKSELFCHECK7 {h} NEW48 NEWCNY102 TOTAL474 TOTALCNY107',currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
    token=parent.claim();b=BatchLedger.create(parent,token);c=p['cases'][0];b.begin(c['id'])
    auth=CohortAuthority(parent.root/'run/children'/c['id']);auth.approve(c['plan'],c['hash'],currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True,consent=f"APPROVE {c['hash']} CNY 17")
    ticket=auth.claim(c['hash']);ledger=Ledger.create(Path(ticket.validate()['run_dir'])/'ledger.sqlite',c['plan'],admission=ticket);_,snapshot,_=verify(c['plan'],'live');key='SYNTHETIC-NOT-A-CREDENTIAL';seen=[]
    def helper(*args,**kw):
     self.assertNotIn(key,str(args));self.assertNotIn(key,str(kw['env']));q=json.loads(json.loads(kw['input'])['body']);seen.append(q)
     raw={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'finish','type':'function','function':{'name':'finish','arguments':json.dumps({'message':{'files':[],'entities':[],'answer':'fixture'}})}}]}}],'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
     return subprocess.CompletedProcess(args[0],0,encoded({'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}),b'')
    class R:
     snapshot_id=snapshot.identity
     def retrieve(self,query):raise AssertionError('not used by fixture')
    with patch('readonly_agent.live_transport.subprocess.run',side_effect=helper) as transport:
     for arm in c['plan']['arm_order']:
      wire=CohortWire(ledger,arm,ticket,key,snapshot=snapshot)
      r=run_sdk_case(snapshot=snapshot,issue=c['plan']['issue'],script=None,output_dir=root/arm,retriever=R(),limits=Limits(max_requests=4),live=wire)
      self.assertEqual(r['status'],'completed')
     self.assertEqual(transport.call_count,2)
    off,on=seen;self.assertEqual(len(off['tools']),5);self.assertEqual(len(on['tools']),5)
    from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION
    self.assertEqual(on['messages'][0]['content'].count(SELF_CHECK_INSTRUCTION),1)
    self.assertNotIn(SELF_CHECK_INSTRUCTION,off['messages'][0]['content'])
    on['messages'][0]['content']=on['messages'][0]['content'].replace('\n'+SELF_CHECK_INSTRUCTION,'')
    self.assertEqual(off,on)
    self.assertFalse(attempts)
    for f in root.rglob('*'):
     if f.is_file():self.assertNotIn(key.encode(),f.read_bytes())
    b.finish(c['id'],ledger);b.halt('synthetic-test-finished-no-real-consent')

 def test_backend_arm_maps_to_actual_immutable_implementations(self):
  from tests.test_retrieval_evidence_v6 import fixture
  from experiments.sdk_finish_selfcheck_v7.backends import select_retriever
  from experiments.path_retrieval_v4.retriever import PathAwareRetriever
  from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever
  r,s=fixture({'a.py':'def f(): return 1\n'})
  self.assertIs(type(select_retriever(r.base,s,'baseline')),EvidenceRetriever)
  self.assertEqual(select_retriever(r.base,s,'baseline').retrieve('f'),select_retriever(r.base,s,'retrieval').retrieve('f'))
  self.assertIs(type(select_retriever(r.base,s,'retrieval')),EvidenceRetriever)
  with self.assertRaises(PermissionError):select_retriever(r.base,s,'unknown')

 def test_both_arms_require_same_retrieval_tool_surface(self):
  import httpx
  p=candidate('rehearsal')
  for arm in ('baseline','retrieval'):
   with TemporaryDirectory() as td:
    parent=Parent(Path(td).resolve()/'p');parent.prepare(p);token=parent.claim();b=BatchLedger.create(parent,token);c=p['cases'][0];b.begin(c['id'])
    auth=RehearsalAuthority(parent.root/'run/children'/c['id']);auth.prepare_fixture(c['plan']);ticket=auth.claim(c['hash']);l=Ledger.create(Path(ticket.validate()['run_dir'])/'ledger.sqlite',c['plan']);_,snapshot,_=verify(c['plan'],'rehearsal')
    seen=[];wire=CohortWire(l,arm,ticket,None,snapshot=snapshot,transport=httpx.MockTransport(lambda q:seen.append(q)))
    without=[t for t in base_surface() if t['function']['name']!='locagent_retrieve']
    with self.assertRaises(PermissionError):wire.exchange([{'role':'user','content':'fixture'}],without,False)
    self.assertFalse(seen);self.assertFalse(l.summary()['calls'])
    b.halt('offline fixture complete')

if __name__=='__main__':unittest.main()

class PromptBoundaryTests(unittest.TestCase):
 def test_wrong_prompt_cannot_reserve_or_send(self):
  import httpx
  from experiments.sdk_finish_selfcheck_v7.sdk_adapter import SDK_SYSTEM
  from experiments.sdk_finish_selfcheck_v7.finish_policy import SELF_CHECK_INSTRUCTION
  p=candidate('rehearsal')
  for arm in ('baseline','retrieval'):
   with TemporaryDirectory() as td:
    parent=Parent(Path(td).resolve()/'p');parent.prepare(p);token=parent.claim();b=BatchLedger.create(parent,token);c=p['cases'][0];b.begin(c['id'])
    auth=RehearsalAuthority(parent.root/'run/children'/c['id']);auth.prepare_fixture(c['plan']);ticket=auth.claim(c['hash']);l=Ledger.create(Path(ticket.validate()['run_dir'])/'ledger.sqlite',c['plan']);_,snapshot,_=verify(c['plan'],'rehearsal')
    seen=[];wire=CohortWire(l,arm,ticket,None,snapshot=snapshot,transport=httpx.MockTransport(lambda q:seen.append(q)))
    wrong=SDK_SYSTEM + ('\n'+SELF_CHECK_INSTRUCTION if arm=='baseline' else '')
    with self.assertRaisesRegex(PermissionError,'prompt_treatment_binding_changed'):
     wire.exchange([{'role':'system','content':wrong},{'role':'user','content':'fixture'}],base_surface(),False)
    self.assertFalse(seen);self.assertFalse(l.summary()['calls'])
    b.halt('offline fixture complete')
 def test_selfcheck_never_rewrites_predictions(self):
  from experiments.sdk_finish_selfcheck_v7.finish_policy import validate_finish,SELF_CHECK_INSTRUCTION
  from experiments.sdk_retrieval_compare_v6.finish_policy import validate_finish as prior
  from tests.test_retrieval_evidence_v6 import fixture
  _,snapshot=fixture({'a.py':'def first(): return second()\ndef second(): return 1\n'})
  for answer in ({'files':['a.py'],'entities':['a.py:first'],'answer':'second may be relevant but only its call was seen.'}, {'files':[],'entities':[],'answer':'Insufficient evidence.'}):
   self.assertEqual(validate_finish(answer,snapshot),answer)
   self.assertEqual(validate_finish(answer,snapshot),prior(answer,snapshot))
  self.assertNotIn('sqlglot',SELF_CHECK_INSTRUCTION.lower())
  self.assertNotIn('xcdat',SELF_CHECK_INSTRUCTION.lower())
