"""Real SDK on both arms, simulated helper only; verify sole initial wire delta."""
import base64,json,subprocess,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from experiments.sdk_ablation_v1.freeze import candidate
from experiments.sdk_ablation_v1.parent import Parent,BatchLedger
from experiments.sdk_ablation_v1.guard import CohortAuthority,CohortWire,verify,RehearsalAuthority
from experiments.sdk_ablation_v1.sdk_adapter import run_sdk_case
from experiments.sdk_ablation_v1.common_contract import FINISH
from readonly_agent.core import digest,encoded,Limits
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from tests.test_sdk_ablation_batch import base_surface

class FairnessTests(unittest.TestCase):
 def test_real_sdk_both_arms_initial_wire_only_differs_by_retrieval(self):
  p=candidate('live');h=digest(p)
  with TemporaryDirectory() as td:
   root=Path(td).resolve()
   with no_network(root/'profiles') as attempts:
    parent=Parent(root/'SYNTHETIC-ONLY');parent.prepare(p,consent=f'APPROVE SDKABLATION1 {h} NEW48 NEWCNY102 TOTAL380 TOTALCNY106',currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
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
      r=run_sdk_case(snapshot=snapshot,issue=c['plan']['issue'],script=None,output_dir=root/arm,retriever=R() if arm=='retrieval' else None,limits=Limits(max_requests=4),live=wire)
      self.assertEqual(r['status'],'completed')
     self.assertEqual(transport.call_count,2)
    off,on=seen;self.assertEqual(len(off['tools']),4);self.assertEqual(len(on['tools']),5)
    extra=[x for x in on['tools'] if x['function']['name']=='locagent_retrieve'];self.assertEqual(len(extra),1)
    on['tools']=[x for x in on['tools'] if x['function']['name']!='locagent_retrieve'];self.assertEqual(off,on)
    self.assertFalse(attempts)
    for f in root.rglob('*'):
     if f.is_file():self.assertNotIn(key.encode(),f.read_bytes())
    b.finish(c['id'],ledger);b.halt('synthetic-test-finished-no-real-consent')
 def test_off_arm_cannot_advertise_retrieval_before_reserving(self):
  import httpx
  p=candidate('rehearsal')
  with TemporaryDirectory() as td:
   parent=Parent(Path(td).resolve()/'p');parent.prepare(p);token=parent.claim();b=BatchLedger.create(parent,token);c=p['cases'][0];b.begin(c['id'])
   auth=RehearsalAuthority(parent.root/'run/children'/c['id']);auth.prepare_fixture(c['plan']);ticket=auth.claim(c['hash']);l=Ledger.create(Path(ticket.validate()['run_dir'])/'ledger.sqlite',c['plan']);_,s,_=verify(c['plan'],'rehearsal')
   seen=[];wire=CohortWire(l,'baseline',ticket,None,snapshot=s,transport=httpx.MockTransport(lambda q:seen.append(q)))
   surface=base_surface()+[{'type':'function','function':{'name':'locagent_retrieve','parameters':{}}}]
   with self.assertRaisesRegex(PermissionError,'ablation_tool_availability_changed'):wire.exchange([{'role':'user','content':'fixture'}],surface,False)
   self.assertFalse(seen);self.assertEqual(len(l.summary()['calls']),0)
   b.halt('fixture-finished')
 def test_unavailable_retrieval_response_stops_off_arm(self):
  import httpx
  p=candidate('rehearsal')
  with TemporaryDirectory() as td:
   parent=Parent(Path(td).resolve()/'p');parent.prepare(p);token=parent.claim();b=BatchLedger.create(parent,token);c=p['cases'][0];b.begin(c['id'])
   auth=RehearsalAuthority(parent.root/'run/children'/c['id']);auth.prepare_fixture(c['plan']);ticket=auth.claim(c['hash']);l=Ledger.create(Path(ticket.validate()['run_dir'])/'ledger.sqlite',c['plan']);_,s,_=verify(c['plan'],'rehearsal')
   seen=[]
   def response(q):
    seen.append(1)
    return httpx.Response(200,json={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'forbidden','type':'function','function':{'name':'locagent_retrieve','arguments':'{"query":"fixture","offset":0}'}}]}}],'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
   wire=CohortWire(l,'baseline',ticket,None,snapshot=s,transport=httpx.MockTransport(response))
   with self.assertRaisesRegex(RuntimeError,'cohort_exchange_stopped'):wire.exchange([{'role':'user','content':'fixture'}],base_surface(),False)
   self.assertTrue(l.summary()['halted']);self.assertEqual(l.summary()['reason'],'invalid_tool_call')
   with self.assertRaises(Exception):wire.exchange([{'role':'user','content':'fixture'}],base_surface(),False)
   self.assertEqual(len(seen),1);b.halt('fixture-finished')
if __name__=='__main__':unittest.main()
