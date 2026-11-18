import json,unittest,sqlite3,subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from unittest.mock import patch
from datetime import timedelta
from experiments.cohort_five_evidence_v3.freeze import candidate
from experiments.cohort_five_evidence_v3.parent import Parent,BatchLedger,validate,now
from experiments.cohort_five_evidence_v3.guard import IDS,RehearsalAuthority,CohortWire,start_mock
from experiments.cohort_five_evidence_v3.batch import execute
from readonly_agent.journal import Ledger
from readonly_agent.core import encoded
from readonly_agent.deepseek_wire import RawHTTP
from readonly_agent.live_transport import exchange_live

class FiveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.plan=candidate('rehearsal')
 def parent(self,root):
  p=Parent(root/'p');p.prepare(self.plan);t=p.claim();return p,t,BatchLedger.create(p,t)
 def child(self,p,b,item):
  b.begin(item['id']);a=RehearsalAuthority(p.root/'run/children'/item['id']);a.prepare_fixture(item['plan']);t=a.claim(item['hash'])
  l=Ledger.create(Path(t.validate()['run_dir'])/'ledger.sqlite',item['plan']);return t,l
 def test_missing_explicit_live_consent(self):
  with TemporaryDirectory() as td:
   p=Parent(Path(td).resolve()/'p')
   with self.assertRaises(PermissionError):p.prepare(candidate('live'))
   self.assertFalse(p.root.exists())
 def test_changed_case_order_hash_and_budget(self):
  for change in [lambda x:x.update(max_requests=41),lambda x:x.update(budget_micro_cny=85000001),lambda x:x['cases'].reverse(),lambda x:x['sources'].clear()]:
   p=deepcopy(self.plan);change(p)
   with self.assertRaises(PermissionError):validate(p)
 def test_duplicate_parent_and_case_and_wrong_order(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve())
   with self.assertRaises(FileExistsError):p.claim()
   with self.assertRaises(FileExistsError):BatchLedger.create(p,t)
   with self.assertRaises(PermissionError):b.begin(IDS[1])
   b.begin(IDS[0])
   with self.assertRaises(PermissionError):b.begin(IDS[0])
 def test_parent_halt_and_expiry_block_child(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve());ticket,l=self.child(p,b,self.plan['cases'][0])
   with patch('experiments.cohort_five_evidence_v3.parent.now',return_value=now()+timedelta(hours=25)):
    with self.assertRaises(PermissionError):ticket.validate(l.path)
   b.halt('fixture')
   with self.assertRaises(PermissionError):ticket.validate(l.path)
   self.assertEqual(b.summary()['case_hold_micro_cny'],16908288)
 def test_pending_reservation_preserved_no_next_case(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve());ticket,l=self.child(p,b,self.plan['cases'][0]);tok=l.claim('baseline');i=l.reserve('baseline',tok,b'{}')
   start_mock(l,i,b'{}',ticket)
   with self.assertRaises(PermissionError):start_mock(l,i,b'{}',ticket)
   b.halt('timeout')
   with self.assertRaises(PermissionError):b.begin(IDS[1])
   self.assertEqual(l.summary()['reserved_micro_cny'],2113536)
   self.assertEqual([c['status'] for c in b.summary()['cases']],['failed']+['not_started']*4)
 def test_rehearsal_ticket_never_enters_live_transport(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve());ticket,l=self.child(p,b,self.plan['cases'][0])
   with patch('readonly_agent.live_transport.subprocess.run') as helper:
    with self.assertRaises(PermissionError):exchange_live(b'{}',None,admission=ticket,ledger=l,reservation=1,enabled=True)
    helper.assert_not_called()
 def test_coordinator_launch_failure_stops_all(self):
  with TemporaryDirectory() as td:
   p=Parent(Path(td).resolve()/'p');p.prepare(self.plan)
   with patch('experiments.cohort_five_evidence_v3.batch.subprocess.Popen',side_effect=OSError('fixture')) as start:
    result=execute(p,p.claim());self.assertEqual(start.call_count,1)
   self.assertTrue(result['halted']);self.assertEqual(result['all_child_requests'],0)
   self.assertEqual([c['status'] for c in result['cases']],['failed']+['not_started']*4)
 def test_exact_five_case_40_requests_and_85_cap(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve())
   raw=encoded({'id':'fixture','model':'deepseek-flash','usage':{'prompt_tokens':1048576,'completion_tokens':2048,'total_tokens':1050624}})
   for item in self.plan['cases']:
    ticket,l=self.child(p,b,item)
    for arm in item['plan']['arm_order']:
     tok=l.claim(arm)
     for turn in range(4):
      i=l.reserve(arm,tok,b'{}');l.received(i,RawHTTP(200,raw));l.settle(i)
     with self.assertRaises(RuntimeError):l.reserve(arm,tok,b'{}')
     l.finish(arm,tok)
    b.finish(item['id'],l)
   s=b.summary();self.assertEqual(s['completed_case_requests'],40);self.assertEqual(s['settled_cost_micro_cny'],84541440);self.assertEqual(s['case_hold_micro_cny'],0)
   with self.assertRaises(PermissionError):b.begin(IDS[0])
 def test_extra_answer_material_rejected(self):
  from readonly_agent.core import digest
  for name in ('gold','reference_patch','semantic_review'):
   plan=deepcopy(self.plan);plan['cases'][0]['plan'][name]='PRIVATE_LABEL_CANARY'
   plan['cases'][0]['hash']=digest(plan['cases'][0]['plan'])
   with self.assertRaisesRegex(PermissionError,'unexpected_runtime_material'):validate(plan)
 def test_expired_batch_remains_auditable_but_cannot_execute(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve());b.begin(IDS[0])
   with patch('experiments.cohort_five_evidence_v3.parent.now',return_value=now()+timedelta(hours=25)):
    b.halt('expired')
    self.assertEqual(b.audit_summary()['case_hold_micro_cny'],16908288)
    with self.assertRaises(PermissionError):b.active(IDS[0])
 def test_wire_truncation_timeout_and_size_stop_before_next(self):
  import httpx
  from experiments.cohort_five_evidence_v3.guard import verify
  from experiments.eval_preflight.common_contract import FINISH
  for failure in ('length','timeout','oversize'):
   with TemporaryDirectory() as td:
    p,t,b=self.parent(Path(td).resolve());item=self.plan['cases'][0];ticket,l=self.child(p,b,item)
    _,snapshot,_=verify(item['plan'],'rehearsal');seen=[]
    def transport(req):
     seen.append(1)
     if failure=='timeout':raise TimeoutError('fixture')
     return httpx.Response(200,json={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'length','message':{'role':'assistant','content':'partial'}}], 'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
    wire=CohortWire(l,'baseline',ticket,None,snapshot=snapshot,transport=httpx.MockTransport(transport))
    with self.assertRaises((RuntimeError,ValueError)):
     wire.exchange([{'role':'user','content':'x'*65536 if failure=='oversize' else 'fixture'}],[FINISH],False)
    self.assertEqual(len(seen),0 if failure=='oversize' else 1)
    if failure=='length':
     self.assertTrue(l.summary()['halted'])
     with l.transaction() as db:self.assertIsNotNone(db.execute('SELECT response FROM calls').fetchone()[0])
    if failure=='timeout':self.assertEqual(l.summary()['reserved_micro_cny'],2113536)
    b.halt(failure)
    with self.assertRaises(PermissionError):b.begin(IDS[1])
 def test_case_timeout_kills_process_group_without_retry(self):
  from unittest.mock import MagicMock
  with TemporaryDirectory() as td:
   p=Parent(Path(td).resolve()/'p');p.prepare(self.plan)
   proc=MagicMock();proc.pid=999999999;proc.communicate.side_effect=subprocess.TimeoutExpired('fixture',720)
   with patch('experiments.cohort_five_evidence_v3.batch.subprocess.Popen',return_value=proc) as start,patch('experiments.cohort_five_evidence_v3.batch.os.killpg') as kill:
    result=execute(p,p.claim())
   self.assertEqual(start.call_count,1);kill.assert_called_once();proc.wait.assert_called_once()
   self.assertTrue(result['halted']);self.assertEqual(result['all_child_requests'],0)
 def test_partial_completion_preserved(self):
  with TemporaryDirectory() as td:
   p,t,b=self.parent(Path(td).resolve());item=self.plan['cases'][0];ticket,l=self.child(p,b,item)
   raw=encoded({'id':'fixture','model':'deepseek-flash','usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
   for arm in item['plan']['arm_order']:
    tok=l.claim(arm);i=l.reserve(arm,tok,b'{}');l.received(i,RawHTTP(200,raw));l.settle(i);l.finish(arm,tok)
   b.finish(item['id'],l);b.begin(IDS[1]);b.halt('second_case_fixture_failure')
   s=b.summary();self.assertEqual([c['status'] for c in s['cases']],['completed','failed']+['not_started']*3)
   self.assertEqual(s['completed_case_requests'],2)
   self.assertEqual(s['case_hold_micro_cny'],16908288)
if __name__=='__main__':unittest.main()
