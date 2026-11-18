"""Synthetic authority and mocked helper only; no real keys or network."""
import base64,json,subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from readonly_agent.authority import Admission,Authority
from readonly_agent.core import Snapshot,Limits,digest,encoded
from readonly_agent.preparation import make_plan
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from experiments.eval_preflight.common_contract import FINISH
from experiments.eval_preflight.live_guard import ComparisonAuthority,SharedLiveWire,verify_comparison_plan,native_provider

FAKE='SYNTHETIC-NOT-A-REAL-CREDENTIAL'

class LiveGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        (self.root/'a.py').write_text('def a():\n    return 1\n')
        engine=self.root/'engine';(engine/'evaluation').mkdir(parents=True)
        (engine/'evaluation/eval_metric.py').write_text('# synthetic fixture')
        self.snap=Snapshot(self.root,['a.py']);self.plan=make_plan(self.snap,'synthetic issue',engine)
        self.guard=no_network(self.root/'profiles');self.guard.__enter__();self.addCleanup(self.guard.__exit__,None,None,None)
        self.seen=[]

    def admitted_fixture(self):
        # Replace index attestation validation ONLY for this tiny synthetic
        # fixture; real one-use authority, ledger and transport ticket stay active.
        guard=patch('experiments.eval_preflight.live_guard.verify_comparison_plan',return_value=None)
        guard.start();self.addCleanup(guard.stop)
        authority=ComparisonAuthority(self.root/'authority');h=digest(self.plan)
        authority.approve(self.plan,h,currency='CNY',input_ceiling='2',output_ceiling='8',
            all_charges_included=True,consent=f'APPROVE {h} CNY 17')
        admission=authority.claim(h)
        ledger=Ledger.create(authority.folder(h)/'run/ledger.sqlite',self.plan,admission=admission)
        return admission,ledger

    def helper(self,*args,**kwargs):
        data=json.loads(kwargs['input']);self.assertEqual(data['key'],FAKE)
        request=json.loads(data['body']);self.seen.append(request)
        raw={'id':'synthetic','model':'deepseek-flash','usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100},
             'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
             'tool_calls':[{'id':'end','type':'function','function':{'name':'finish','arguments':json.dumps({'message':{'files':['a.py'],'entities':['a.py:a'],'answer':'fixture'}})}}]}}]}
        envelope={'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}
        return subprocess.CompletedProcess(args[0],0,encoded(envelope),b'')

    def test_unapproved_plan_and_generic_authority_denied(self):
        with self.assertRaises(PermissionError):verify_comparison_plan(self.plan)
        admission=Admission(Authority(self.root/'old'),digest(self.plan),'fake-token')
        with self.assertRaises(PermissionError):SharedLiveWire(None,'baseline',admission,object(),snapshot=self.snap)
        self.assertFalse((self.root/'old').exists())

    def test_native_real_transport_adapter_mocked_helper(self):
        admission,ledger=self.admitted_fixture()
        wire=SharedLiveWire(ledger,'baseline',admission,FAKE,snapshot=self.snap)
        with patch('readonly_agent.live_transport.subprocess.run',side_effect=self.helper) as helper:
            response=native_provider(wire)(messages=[{'role':'user','content':'fixture'}],tools=[FINISH])
        self.assertEqual(response.choices[0].message.tool_calls[0].function.name,'finish')
        self.assertEqual(helper.call_count,1);wire.finish();wire.forget_key()
        self.assertIsNone(wire._key)
        with ledger.transaction() as db:self.assertEqual(db.execute('SELECT transport_started FROM calls').fetchone()[0],1)

    def test_sdk_real_transport_adapter_mocked_helper(self):
        from experiments.eval_preflight.sdk_adapter import run_sdk_case
        admission,ledger=self.admitted_fixture()
        wire=SharedLiveWire(ledger,'baseline',admission,FAKE,snapshot=self.snap)
        with patch('readonly_agent.live_transport.subprocess.run',side_effect=self.helper) as helper:
            result=run_sdk_case(snapshot=self.snap,issue='synthetic issue',script=None,output_dir=self.root/'output',
                limits=Limits(max_requests=4),live=wire)
        self.assertEqual(result['status'],'completed',result);self.assertEqual(helper.call_count,1)
        self.assertIsNone(wire._key)
        for p in self.root.rglob('*'):
            if p.is_file():self.assertNotIn(FAKE.encode(),p.read_bytes())

    def test_timeout_keeps_ticket_and_no_second_helper(self):
        admission,ledger=self.admitted_fixture()
        wire=SharedLiveWire(ledger,'baseline',admission,FAKE,snapshot=self.snap)
        with patch('readonly_agent.live_transport.subprocess.run',side_effect=subprocess.TimeoutExpired('mock',60)) as helper:
            with self.assertRaises(RuntimeError):wire.exchange([{'role':'user','content':'x'}],[FINISH],True)
            with self.assertRaises(RuntimeError):wire.exchange([{'role':'user','content':'x'}],[FINISH],True)
        self.assertEqual(helper.call_count,1);self.assertTrue(ledger.summary()['needs_review'])

if __name__=='__main__':unittest.main()
