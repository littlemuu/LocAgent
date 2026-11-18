import json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from experiments.choice_pair.run import PairAuthority,PairLedger,frozen,request,execute,run
from readonly_agent.core import digest,encoded
from readonly_agent.deepseek_wire import RawHTTP,MODEL,RESERVATION,CONTEXT,OUTPUT
from readonly_agent.offline import no_network
class ChoicePairTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.guard=no_network(self.root/'profiles');self.guard.__enter__();self.addCleanup(self.guard.__exit__,None,None,None)
  self.plan=frozen();self.h=digest(self.plan);self.a=PairAuthority(self.root/'a');self.confirm={'consent':f'APPROVE CHOICE {self.h} CNY 5','currency':'CNY','input_ceiling':'2','output_ceiling':'8','all_charges_included':True}
 def admit(self):self.a.approve(self.plan,self.h,**self.confirm);return self.a.claim(self.h)
 def fake(self,body,key,**kw):
  kw['ledger'].start_transport(kw['reservation'],body,kw['admission'])
  raw={'id':'offline','model':MODEL,'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'mock1','type':'function','function':{'name':'locagent_retrieve','arguments':'{"query":"_parse_set_item_assignment"}'}}]}}],'usage':{'prompt_tokens':CONTEXT,'completion_tokens':OUTPUT,'total_tokens':CONTEXT+OUTPUT}}
  return RawHTTP(200,encoded(raw))
 def test_two_exact_payloads_and_max_cost(self):
  a=self.admit();r=execute(a,'offline-not-a-key',self.fake)
  self.assertEqual(r['status'],'completed');self.assertEqual(len(r['rows']),2)
  self.assertEqual(r['budget']['spent_upper_micro_cny'],2*RESERVATION);self.assertLess(2*RESERVATION,5_000_000)
  ledger=PairLedger(Path(a.validate()['run_dir'])/'ledger.sqlite',self.h)
  with self.assertRaises(Exception):ledger.claim('baseline')
 def test_default_no_grant_no_key(self):
  with patch('readonly_agent.local_env.load_selected_key') as key:
   with self.assertRaises(FileNotFoundError):run(self.h,self.a)
   key.assert_not_called()
 def test_duplicate_claim_and_run_before_key(self):
  self.admit()
  with self.assertRaises(FileExistsError):self.a.claim(self.h)
  with patch('readonly_agent.local_env.load_selected_key') as key:
   with self.assertRaises(PermissionError):run(self.h,self.a)
   key.assert_not_called()
 def test_wrong_price_or_old_consent(self):
  for k,v in [('input_ceiling','3'),('currency','USD'),('all_charges_included',False),('consent','APPROVE SQLGLOT old CNY 17')]:
   with self.assertRaises(PermissionError):self.a.approve(self.plan,self.h,**(self.confirm|{k:v}))
 def test_expiry_or_change(self):
  from readonly_agent.authority import now
  self.admit()
  with patch('experiments.choice_pair.run.now',return_value=now()+timedelta(hours=25)):
   with self.assertRaises(PermissionError):self.a.read(self.h)
  with patch('experiments.choice_pair.run.candidate',return_value={}):
   with self.assertRaises(PermissionError):self.a.read(self.h)
 def test_no_tty_before_key(self):
  self.a.approve(self.plan,self.h,**self.confirm)
  with patch('experiments.choice_pair.run.sys.stdin.isatty',return_value=False),patch('readonly_agent.local_env.load_selected_key') as key:
   with self.assertRaises(PermissionError):run(self.h,self.a)
   key.assert_not_called()
 def test_changed_payload_rejected(self):
  a=self.admit();l=PairLedger.create(Path(a.validate()['run_dir'])/'ledger.sqlite',self.plan,admission=a);token=l.claim('baseline')
  with self.assertRaises(PermissionError):l.reserve('baseline',token,b'{}')
 def test_third_request_and_duplicate_transport_rejected(self):
  a=self.admit();l=PairLedger.create(Path(a.validate()['run_dir'])/'ledger.sqlite',self.plan,admission=a)
  for arm in ('baseline','retrieval'):
   token=l.claim(arm);body=request(arm);i=l.reserve(arm,token,body);raw=self.fake(body,'offline',ledger=l,reservation=i,admission=a)
   with self.assertRaises(PermissionError):l.start_transport(i,body,a)
   l.received(i,raw);l.settle(i)
   with self.assertRaises(RuntimeError):l.reserve(arm,token,body)
   l.finish(arm,token)
 def test_first_timeout_stops_second(self):
  a=self.admit();attempts=[]
  def fail(body,key,**kw):
   kw['ledger'].start_transport(kw['reservation'],body,kw['admission']);attempts.append(1);raise TimeoutError('synthetic')
  r=execute(a,'offline',fail);self.assertEqual(len(attempts),1);self.assertEqual(r['status'],'halted');self.assertEqual(r['budget']['reserved_micro_cny'],RESERVATION)
 def test_second_timeout_keeps_first(self):
  a=self.admit();attempts=[]
  def fail(body,key,**kw):
   attempts.append(1)
   if len(attempts)==1:return self.fake(body,key,**kw)
   kw['ledger'].start_transport(kw['reservation'],body,kw['admission']);raise TimeoutError('synthetic')
  r=execute(a,'offline',fail);self.assertEqual(len(attempts),2);self.assertEqual(len(r['rows']),1);self.assertEqual(r['budget']['reserved_micro_cny'],RESERVATION)
 def test_bad_argument_stops_no_tools_execute(self):
  a=self.admit()
  def invalid(body,key,**kw):
   raw=self.fake(body,key,**kw);d=json.loads(raw.body);d['choices'][0]['message']['tool_calls'][0]['function']['arguments']=json.dumps({'query':'x'*257});return RawHTTP(200,encoded(d))
  r=execute(a,'offline',invalid);self.assertEqual(r['status'],'halted');self.assertEqual(len(r['budget']['calls']),1);self.assertEqual(r['budget']['reserved_micro_cny'],0)
 def test_concurrent_claim_one_winner(self):
  self.a.approve(self.plan,self.h,**self.confirm)
  def attempt(_):
   try:self.a.claim(self.h);return True
   except FileExistsError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(attempt,range(2))),1)
if __name__=='__main__':unittest.main()
