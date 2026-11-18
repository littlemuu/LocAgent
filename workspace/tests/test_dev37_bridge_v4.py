"""Synthetic live-protocol fixture: no credential lookup and no network transport."""
import base64,json,subprocess,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from experiments.cohort_dev37_v4.freeze import candidate
from experiments.cohort_dev37_v4.parent import Parent,BatchLedger
from experiments.cohort_dev37_v4.guard import CohortAuthority,CohortWire,verify
from experiments.eval_preflight.common_contract import FINISH
from readonly_agent.core import digest,encoded
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network

class BridgeTest(unittest.TestCase):
 def test_parent_to_real_protocol_with_stubbed_transport_only(self):
  plan=candidate('live');h=digest(plan)
  with TemporaryDirectory() as td:
   root=Path(td).resolve()
   with no_network(root/'profiles') as attempts:
    parent=Parent(root/'SYNTHETIC-TEST-ONLY');parent.prepare(plan,consent=f'APPROVE DEV37 {h} NEW296 NEWCNY629 TOTAL349 TOTALCNY630',currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
    token=parent.claim();b=BatchLedger.create(parent,token);item=plan['cases'][0];b.begin(item['id'])
    a=CohortAuthority(parent.root/'run/children'/item['id']);a.approve(item['plan'],item['hash'],currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True,consent=f"APPROVE {item['hash']} CNY 17")
    t=a.claim(item['hash']);l=Ledger.create(Path(t.validate()['run_dir'])/'ledger.sqlite',item['plan'],admission=t)
    _,snapshot,_=verify(item['plan'],'live');key='SYNTHETIC-NOT-A-CREDENTIAL'
    raw={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'finish-fixture','type':'function','function':{'name':'finish','arguments':json.dumps({'message':{'files':[],'entities':[],'answer':'fixture'}})}}]}}],'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
    def helper(*args,**kw):
     self.assertNotIn(key,str(args));self.assertNotIn(key,str(kw['env']))
     return subprocess.CompletedProcess(args[0],0,encoded({'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}),b'')
    with patch('readonly_agent.live_transport.subprocess.run',side_effect=helper) as transport:
     wire=CohortWire(l,'baseline',t,key,snapshot=snapshot)
     wire.exchange([{'role':'user','content':'synthetic'}],[FINISH],False);wire.finish();wire.forget_key()
     self.assertEqual(transport.call_count,1)
    self.assertFalse(attempts)
    for path in root.rglob('*'):
     if path.is_file():self.assertNotIn(key.encode(),path.read_bytes())
    b.halt('test_complete_no_actual_authorization')
if __name__=='__main__':unittest.main()
