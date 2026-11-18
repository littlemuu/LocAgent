import json, unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import httpx
from readonly_agent.core import digest, encoded
from readonly_agent.journal import Ledger
from readonly_agent.live_transport import exchange_live
from readonly_agent.offline import no_network
from experiments.cohort_admission.freeze import plan_for
from experiments.cohort_admission.guard import (
    verify, CohortAuthority, CohortWire, RehearsalAuthority, start_mock)
from experiments.eval_preflight.common_contract import FINISH

class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = plan_for('rehearsal')

    def fixture(self, root):
        auth=RehearsalAuthority(root/'auth');auth.prepare_fixture(self.plan)
        ticket=auth.claim(digest(self.plan))
        ledger=Ledger.create(root/'auth/run/ledger.sqlite',self.plan)
        _,snapshot,_=verify(self.plan,'rehearsal')
        return auth,ticket,ledger,snapshot

    def test_both_modes_are_frozen_but_not_granted(self):
        for mode in ('live','rehearsal'):
            p=plan_for(mode);verify(p,mode)
            self.assertEqual(p['authorization'],'not_granted')
            self.assertFalse(p['account_pricing_confirmed'])

    def test_old_or_changed_code_contract_case_and_hash_rejected(self):
        mutations=[lambda p:p.pop('cohort_admission_version'),
                   lambda p:p['cohort_sources'].clear(),
                   lambda p:p['cohort_binding'].update(case_id='other'),
                   lambda p:p['cohort_binding'].update(entry_sha256='0'*64),
                   lambda p:p['cohort_binding'].update(body_status_sha256='0'*64),
                   lambda p:p.update(issue='changed'),
                   lambda p:p.update(send_categories=['gold']),
                   lambda p:p.update(budget_micro_cny=18000000)]
        for mutate in mutations:
            p=deepcopy(self.plan);mutate(p)
            with self.assertRaises((ValueError,PermissionError)):verify(p,'rehearsal')

    def test_production_rejects_rehearsal_and_missing_consent_without_grant(self):
        with TemporaryDirectory() as td:
            auth=CohortAuthority(Path(td).resolve()/'prod')
            for p in [self.plan,plan_for('live')]:
                with self.assertRaises(PermissionError):
                    auth.approve(p,digest(p),currency='CNY',input_ceiling='2',output_ceiling='8',
                                 all_charges_included=True,consent='not approved')
            self.assertFalse(auth.root.exists())

    def test_duplicate_claim_and_path_binding(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();auth,ticket,ledger,_=self.fixture(root)
            with self.assertRaises(FileExistsError):auth.claim(digest(self.plan))
            with self.assertRaises(PermissionError):ticket.validate(root/'wrong.sqlite')
            ticket.validate(ledger.path)

    def test_rehearsal_cannot_call_real_transport_or_accept_key(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root)
            with patch('readonly_agent.live_transport.subprocess.run',side_effect=AssertionError('must not spawn')):
                with self.assertRaises(PermissionError):
                    exchange_live(b'{}',None,admission=ticket,ledger=ledger,reservation=1,enabled=True)
            for key,transport in [(None,None),('not-a-real-secret',httpx.MockTransport(lambda r:None))]:
                with self.assertRaises(PermissionError):CohortWire(ledger,'baseline',ticket,key,snapshot=snapshot,transport=transport)

    def test_transport_exception_stops_all_later_work(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root);seen=[]
            def fail(request):seen.append(1);raise TimeoutError('fixture')
            with no_network(root/'profiles'):
                wire=CohortWire(ledger,'baseline',ticket,None,snapshot=snapshot,transport=httpx.MockTransport(fail))
                with self.assertRaises(RuntimeError):wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False)
                with self.assertRaises(RuntimeError):ledger.claim('retrieval')
            self.assertEqual(len(seen),1);self.assertTrue(ledger.summary()['halted'])
            self.assertEqual(ledger.summary()['reserved_micro_cny'],self.plan['reservation_micro_cny'])

    def test_raw_truncation_is_retained_and_halts(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root)
            raw={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'length','message':{'role':'assistant','content':'partial'}}],
                 'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
            with no_network(root/'profiles'):
                wire=CohortWire(ledger,'baseline',ticket,None,snapshot=snapshot,
                    transport=httpx.MockTransport(lambda r:httpx.Response(200,json=raw)))
                with self.assertRaises(RuntimeError):wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False)
            summary=ledger.summary();self.assertTrue(summary['halted'])
            self.assertEqual(summary['calls'][0]['status'],'settled')
            with ledger.transaction() as db:self.assertIsNotNone(db.execute('SELECT response FROM calls').fetchone()[0])

    def test_reservation_one_use_and_pending_prevents_next_call(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,_=self.fixture(root)
            token=ledger.claim('baseline');data=b'{}';i=ledger.reserve('baseline',token,data)
            start_mock(ledger,i,data,ticket)
            with self.assertRaises(PermissionError):start_mock(ledger,i,data,ticket)
            with self.assertRaises(RuntimeError):ledger.reserve('baseline',token,data)

    def test_exact_request_cap_rejects_before_reservation(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root)
            wire=CohortWire(ledger,'baseline',ticket,None,snapshot=snapshot,
                transport=httpx.MockTransport(lambda r:(_ for _ in ()).throw(AssertionError('must not send'))))
            with self.assertRaises(ValueError):wire.exchange([{'role':'user','content':'x'*65536}],[FINISH],False)
            self.assertEqual(ledger.summary()['calls'],[])

    def test_finish_and_duplicate_arm_rejected(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root)
            raw={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':'end','type':'function','function':{'name':'finish','arguments':json.dumps(
                    {'message':{'files':[],'entities':[],'answer':'fixture'}})}}]}}],
                'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
            with no_network(root/'profiles'):
                wire=CohortWire(ledger,'baseline',ticket,None,snapshot=snapshot,
                               transport=httpx.MockTransport(lambda r:httpx.Response(200,json=raw)))
                wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False);wire.finish()
                with self.assertRaises(Exception):ledger.claim('baseline')
                with self.assertRaises(RuntimeError):wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False)

    def test_four_per_arm_eight_total_and_budget_reservation(self):
        from readonly_agent.deepseek_wire import RawHTTP
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,_=self.fixture(root)
            raw=encoded({'id':'fixture','model':'deepseek-flash',
                'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
            for arm in ('baseline','retrieval'):
                token=ledger.claim(arm)
                for turn in range(4):
                    i=ledger.reserve(arm,token,b'{}')
                    self.assertEqual(ledger.summary()['reserved_micro_cny'],self.plan['reservation_micro_cny'])
                    start_mock(ledger,i,b'{}',ticket);ledger.received(i,RawHTTP(200,raw));ledger.settle(i)
                with self.assertRaises(RuntimeError):ledger.reserve(arm,token,b'{}')
                ledger.finish(arm,token)
            self.assertEqual(len(ledger.summary()['calls']),8)
            self.assertLessEqual(ledger.summary()['spent_upper_micro_cny'],17000000)

    def test_parent_loss_blocks_before_reservation(self):
        with TemporaryDirectory() as td:
            root=Path(td).resolve();_,ticket,ledger,snapshot=self.fixture(root)
            def lost():raise RuntimeError('parent_lost')
            wire=CohortWire(ledger,'baseline',ticket,None,snapshot=snapshot,
                transport=httpx.MockTransport(lambda r:None),parent_alive=lost)
            with self.assertRaisesRegex(RuntimeError,'parent_lost'):
                wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False)
            self.assertEqual(ledger.summary()['calls'],[])

    def test_native_timeout_stops_pair_and_duplicate_start(self):
        import subprocess
        from experiments.cohort_admission.run import run_pair
        with TemporaryDirectory() as td:
            root=Path(td).resolve();path=root/'plan.json';path.write_bytes(encoded(self.plan))
            auth=RehearsalAuthority(root/'auth');auth.prepare_fixture(self.plan)
            ticket=auth.claim(digest(self.plan))
            with patch('experiments.cohort_admission.run.subprocess.run',side_effect=subprocess.TimeoutExpired('fixture',300)) as child, \
                 patch('experiments.cohort_admission.run.run_sdk_case') as sdk:
                result=run_pair(path,ticket)
                self.assertEqual(result['status'],'failed');self.assertTrue(result['second_arm_not_started'])
                self.assertTrue(result['budget']['halted']);self.assertEqual(result['mock_requests'],0)
                sdk.assert_not_called();self.assertEqual(child.call_count,1)
                with self.assertRaises(FileExistsError):run_pair(path,ticket)

    def test_production_bridge_with_ephemeral_fixture_and_stubbed_helper(self):
        import base64, subprocess
        from readonly_agent.deepseek_wire import RawHTTP
        with TemporaryDirectory() as td:
            root=Path(td).resolve();plan=plan_for('live');h=digest(plan)
            with no_network(root/'profiles'):
                auth=CohortAuthority(root/'test-only-authority')
                auth.approve(plan,h,currency='CNY',input_ceiling='2',output_ceiling='8',
                             all_charges_included=True,consent=f'APPROVE {h} CNY 17')
                ticket=auth.claim(h);ledger=Ledger.create(auth.folder(h)/'run/ledger.sqlite',plan,admission=ticket)
                _,snapshot,_=verify(plan,'live')
                key='SYNTHETIC-UNIT-FIXTURE-NOT-A-CREDENTIAL'
                raw={'id':'fixture','model':'deepseek-flash','choices':[{'finish_reason':'tool_calls',
                    'message':{'role':'assistant','content':None,'tool_calls':[{'id':'f','type':'function',
                    'function':{'name':'finish','arguments':json.dumps({'message':{'files':[],'entities':[],'answer':'fixture'}})}}]}}],
                    'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
                def helper(*args,**kw):
                    self.assertNotIn(key,str(args));self.assertNotIn(key,str(kw['env']))
                    with ledger.transaction() as db:self.assertEqual(db.execute('SELECT transport_started FROM calls').fetchone()[0],1)
                    reply={'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}
                    return subprocess.CompletedProcess(args[0],0,encoded(reply),b'')
                with patch('readonly_agent.live_transport.subprocess.run',side_effect=helper) as start:
                    wire=CohortWire(ledger,'baseline',ticket,key,snapshot=snapshot)
                    wire.exchange([{'role':'user','content':'fixture'}],[FINISH],False);wire.finish();wire.forget_key()
                    self.assertEqual(start.call_count,1)
                self.assertIsNone(wire._key)
                for p in root.rglob('*'):
                    if p.is_file():self.assertNotIn(key.encode(),p.read_bytes())

if __name__ == '__main__':unittest.main()
