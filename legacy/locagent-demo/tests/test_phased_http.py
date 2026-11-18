from phased_test_support import install_synthetic_cohorts
"""Live branch exercised only with temporary synthetic approvals and MockTransport."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from locagent_service import phased as p, phased_admission as a, deepseek_http as h
from locagent_service.offline import offline_engine
from locagent_service.sources import canonical,digest
from util.localization_contract import LocalizationResult,ResultStatus


def compete(path,plan,approval,start,queue):
    start.wait()
    try:p.initialize(path,plan,live=True,approval_id=approval);queue.put('won')
    except Exception:queue.put('lost')


class HTTPAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.addCleanup(patch.stopall)
        install_synthetic_cohorts(self)
        patch.object(p,'OWNERSHIP_ROOT',self.root/'offline').start()
        patch.object(p,'LIVE_OWNERSHIP_ROOT',self.root/'live').start()
        patch.object(p,'SIMULATION_OWNERSHIP_ROOT',self.root/'simulation').start()
        patch.object(a,'APPROVAL_ROOT',self.root/'approvals').start()
        patch.object(a,'CONSUMED_ROOT',self.root/'consumed').start()
        patch.object(p,'verify_sources').start();patch.object(p,'check_labels').start()
        self.guard=offline_engine();self.guard.__enter__()
        self.addCleanup(self.guard.__exit__,None,None,None)
        self.plan=p.expected_plan('new20','synthetic-http-test','live')
        self.path=self.root/'ledger.json'
        self.switch=patch.object(a,'require_switch').start()
        patch.dict(os.environ,{'DEEPSEEK_API_KEY':'synthetic-test-only','LOCAGENT_ALLOW_PAID':'0'}).start()
        self.approval=self.approve()

    def approve(self,name='synthetic-approval',plan=None):
        plan=plan or self.plan
        record=a.proposal(plan,name)
        when=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()
        record.update(approved=True,independent_review_passed=True,
                      approval_reference='SYNTHETIC UNIT TEST; NO HUMAN SPENDING AUTHORITY',approved_at_utc=when)
        record['pricing'].update(all_charges_included=True,confirmed_at_utc=when)
        a.APPROVAL_ROOT.mkdir(exist_ok=True)
        (a.APPROVAL_ROOT/(name+'.json')).write_bytes(canonical(record))
        return name

    def initialize(self):
        return p.initialize(self.path,self.plan,live=True,approval_id=self.approval)

    def claim(self):
        self.initialize()
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path)
            state.update(status='running',active_run={'token':'run','arm_index':0,'phase':'initial-five'})
            state['arms'][0]['status']='running';p.commit(self.path,state)
        return p.Provider(self.path,0,'run')

    @contextmanager
    def transport(self,handler):
        original=h.client
        with patch.object(h,'client',side_effect=lambda transport=None:original(httpx.MockTransport(handler))):
            yield

    def test_unapproved_template_old_shape_wrong_binding_and_stale_price_rejected(self):
        valid=json.loads((a.APPROVAL_ROOT/(self.approval+'.json')).read_text())
        for change in ['approved','review','plan','model','endpoint','limit','price','stale','old']:
            bad=deepcopy(valid)
            if change=='approved':bad['approved']=False
            if change=='review':bad['independent_review_passed']=False
            if change=='plan':bad['binding']['plan_hash']='0'*64
            if change=='model':bad['binding']['model']='other'
            if change=='endpoint':bad['binding']['endpoint']='http://localhost'
            if change=='limit':bad['binding']['limit_cny']='80'
            if change=='price':bad['pricing']['input_cache_miss_peak_per_million']='3'
            if change=='stale':bad['pricing']['confirmed_at_utc']='2020-01-01T00:00:00Z'
            if change=='old':bad={'policy':p.followup.POLICY,'limit':'5','plan_hash':'old'}
            with self.subTest(change=change),self.assertRaises(Exception):
                a.validate_record(self.plan,bad,fresh=True)
        self.assertFalse(self.path.exists());self.assertFalse(a.CONSUMED_ROOT.exists())

    def test_switch_off_and_missing_approval_never_read_existing_key(self):
        # Real gate implementation, without consulting any key value.
        with patch.object(os,'environ',{'LOCAGENT_ALLOW_PAID':'0'}):
            from importlib.util import spec_from_file_location,module_from_spec
            spec=spec_from_file_location('admission_gate_check',a.__file__)
            fresh=module_from_spec(spec);spec.loader.exec_module(fresh)
            with self.assertRaises(RuntimeError):fresh.require_switch()
        with self.assertRaises(Exception):
            p.initialize(self.path,self.plan,live=True,approval_id='does-not-exist')
        self.assertFalse(self.path.exists())

    def test_concurrent_admission_and_duplicate_approval_have_one_winner(self):
        ctx=mp.get_context('fork');start=ctx.Event();queue=ctx.Queue()
        children=[ctx.Process(target=compete,args=(self.root/f'l{i}.json',self.plan,self.approval,start,queue)) for i in range(4)]
        for child in children:child.start()
        start.set()
        for child in children:child.join(20);self.assertEqual(child.exitcode,0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in children),['lost','lost','lost','won'])
        with self.assertRaises(FileExistsError):self.initialize()
        self.assertEqual(len(list(a.CONSUMED_ROOT.glob('*.json'))),1)

    def test_second_approval_same_plan_and_partial_claim_cannot_reset(self):
        self.initialize()
        other=self.approve('second-synthetic')
        with self.assertRaises(FileExistsError):
            p.initialize(self.root/'other.json',self.plan,live=True,approval_id=other)
        self.path.unlink()
        with self.assertRaises(FileExistsError):self.initialize()

    def test_simulation_uses_same_live_plan_without_consuming_authority(self):
        p.initialize(self.path,self.plan,simulate_http=True)
        self.assertFalse(a.CONSUMED_ROOT.exists())
        self.assertEqual(p.load_state(self.path)[0]['mode'],'simulation')
        with self.assertRaises(ValueError):
            p.initialize(self.root/'x.json',self.plan,simulate_http=True,approval_id=self.approval)
        with self.assertRaises(RuntimeError):
            p.run_phase(self.path,'initial-five',live=True)

    def test_success_reserves_then_serializes_official_request_and_persists_raw(self):
        provider=self.claim();seen=[]
        def handler(request):
            state,_,_=p.load_state(self.path)
            self.assertEqual(state['calls'][0]['status'],'reserved')
            self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
            seen.append(request)
            return httpx.Response(200,content=p.scripted_raw(0),request=request)
        with self.transport(handler):
            provider(messages=[{'role':'user','content':'issue','function_call':None}],
                     model='override',api_base='http://bad',num_retries=9,max_tokens=99)
        self.assertEqual(len(seen),1);self.assertEqual(str(seen[0].url),h.ENDPOINT)
        payload=json.loads(seen[0].content)
        self.assertEqual(payload['model'],h.WIRE_MODEL);self.assertEqual(payload['max_tokens'],512)
        self.assertNotIn('function_call',payload['messages'][0])
        state,_,_=p.load_state(self.path);call=state['calls'][0]
        self.assertEqual(call['status'],'settled')
        self.assertEqual(p.response_body(self.path,call),p.scripted_raw(0))
        self.assertEqual(call['raw_body_sha256'],digest(p.scripted_raw(0)))

    def test_redirect_http_errors_preserve_body_never_retry_or_follow(self):
        for status in [301,302,401,429,500,503]:
            with self.subTest(status=status),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'ledger.json'
                self.plan=p.expected_plan('new20','http-'+str(status),'live')
                self.approval=self.approve('http-'+str(status));provider=self.claim();seen=[]
                def handler(request):
                    seen.append(request)
                    return httpx.Response(status,content=b'original error bytes',
                                          headers={'location':'https://example.invalid'},request=request)
                with self.transport(handler):
                    with self.assertRaises(ValueError):provider(messages=[])
                    with self.assertRaises(RuntimeError):provider(messages=[])
                state,_,_=p.load_state(self.path)
                self.assertEqual(len(seen),1);self.assertEqual(state['status'],'halted')
                self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                self.assertEqual(p.response_body(self.path,state['calls'][0]),b'original error bytes')
                self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_timeout_and_send_disconnect_stop_without_resending(self):
        for kind in ['timeout','disconnect']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'l.json';self.plan=p.expected_plan('new20',kind,'live')
                self.approval=self.approve(kind);provider=self.claim();seen=[]
                class Broken(httpx.SyncByteStream):
                    def __iter__(stream):
                        yield b'{"partial":'
                        raise httpx.ReadError('synthetic post-send disconnect')
                def handler(request):
                    seen.append(1)
                    if kind=='timeout':raise httpx.ReadTimeout('synthetic timeout',request=request)
                    return httpx.Response(200,stream=Broken(),request=request)
                with self.transport(handler):
                    with self.assertRaises(Exception):provider(messages=[])
                    with self.assertRaises(Exception):provider(messages=[])
                state,_,_=p.load_state(self.path)
                self.assertEqual(len(seen),1);self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                if kind=='disconnect':
                    self.assertEqual(p.response_body(self.path,state['calls'][0]),b'{"partial":')
                    self.assertFalse(state['calls'][0]['response_complete'])
                self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_missing_invalid_truncated_corrupt_usage_retains_full_reservation(self):
        for kind in ['missing','float','bool','negative','wrong_total','truncated','utf8','duplicate']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'l.json';self.plan=p.expected_plan('new20',kind,'live')
                self.approval=self.approve(kind);provider=self.claim()
                raw=json.loads(p.scripted_raw(0))
                if kind=='missing':raw.pop('usage')
                if kind=='float':raw['usage']['prompt_tokens']=100.0
                if kind=='bool':raw['usage']['prompt_tokens']=True
                if kind=='negative':raw['usage']['prompt_tokens']=-1
                if kind=='wrong_total':raw['usage']['total_tokens']=999
                body=canonical(raw)
                if kind=='truncated':body=body[:-5]
                if kind=='utf8':body=b'\xff\xfe'
                if kind=='duplicate':body=b'{"usage":{},"usage":{}}'
                with self.transport(lambda req:httpx.Response(200,content=body,request=req)):
                    with self.assertRaises(Exception):provider(messages=[])
                state,_,_=p.load_state(self.path)
                self.assertEqual(p.response_body(self.path,state['calls'][0]),body)
                self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_invalid_request_and_size_gate_precede_reservation(self):
        provider=self.claim()
        with patch.object(h,'exchange',side_effect=AssertionError('Must not send')):
            for messages in [[{'role':'invalid'}],[{'role':'user','content':float('nan')}],
                             [{'role':'user','content':'x'*65536}]]:
                with self.assertRaises((ValueError,RuntimeError)):provider(messages=messages)
        self.assertEqual(p.load_state(self.path)[0]['calls'],[])

    def test_reservation_raw_and_settlement_disk_failures_keep_safe_boundaries(self):
        for point in ['reserved','raw_received','settled']:
            with self.subTest(point=point),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'l.json';self.plan=p.expected_plan('new20',point,'live')
                self.approval=self.approve(point);provider=self.claim();seen=[]
                original=p.budget.save
                def fail(path,value):
                    if Path(path)==self.path and value.get('calls') and value['calls'][-1]['status']==point:
                        raise OSError('synthetic disk failure')
                    original(path,value)
                def handler(request):
                    seen.append(1);return httpx.Response(200,content=p.scripted_raw(0),request=request)
                with self.transport(handler),patch.object(p.budget,'save',side_effect=fail):
                    with self.assertRaises(OSError):provider(messages=[])
                state,_,_=p.load_state(self.path)
                self.assertEqual(len(seen),0 if point=='reserved' else 1)
                if point=='reserved':self.assertEqual(state['calls'],[])
                else:
                    self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                    audit=p.audit_recovery(self.path)
                    self.assertFalse(audit['recoverable'])
                    if point=='settled':
                        state,_,_=p.load_state(self.path)
                        self.assertEqual(state['calls'][0]['status'],'settled')

    def test_revoked_approval_and_mode_cannot_send_or_promote_offline_ledger(self):
        provider=self.claim()
        record=a.APPROVAL_ROOT/(self.approval+'.json')
        value=json.loads(record.read_text());value['approved']=False;record.write_bytes(canonical(value))
        with patch.object(h,'exchange',side_effect=AssertionError('Must not send')):
            with self.assertRaises(ValueError):provider(messages=[])
        state=p.read_json(self.path);self.assertEqual(state['calls'],[])
        self.assertEqual(state['mode'],'live')

    def test_partial_approval_claim_fails_closed_after_persistence_error(self):
        original=p.budget.save
        def fail(path,value):
            if Path(path).parent==a.CONSUMED_ROOT:raise OSError('claim persistence fault')
            original(path,value)
        with patch.object(p.budget,'save',side_effect=fail):
            with self.assertRaises(OSError):self.initialize()
        with self.assertRaises(FileExistsError):self.initialize()
        self.assertFalse(self.path.exists())

    def test_complete_mock_http_stage_checkpoint_and_shared_budget(self):
        self.initialize();seen=[]
        def executor(path,index,token):
            provider=p.Provider(path,index,token)
            for ordinal in range(3):
                with self.transport(lambda request:httpx.Response(200,content=p.scripted_raw(ordinal),request=request)):
                    provider(messages=[{'role':'user','content':str(ordinal)}])
                    seen.append(1)
            state,_,_=p.load_state(path)
            result=LocalizationResult(p.arms_for(state['plan'])[index]['instance_id'],ResultStatus.EMPTY,
                iterations=3,diagnostics={'termination_reason':'finished'}).to_dict()
            p.finish_arm(path,index,token,result,.01)
        p.run_phase(self.path,'initial-five',executor=executor,live=True)
        first=p.read_json(self.path)
        p.run_phase(self.path,'remaining-fifteen',executor=executor,live=True)
        last=p.load_state(self.path)[0]
        self.assertEqual(first['calls'],last['calls'][:30])
        self.assertEqual(len(seen),120);self.assertEqual(last['status'],'complete')
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'remaining-fifteen',executor=executor,live=True)

    def test_http_client_contract_no_retry_redirect_or_proxy(self):
        with patch('httpx.Client') as client,patch('httpx.HTTPTransport') as transport:
            h.client()
            transport.assert_called_once_with(retries=0)
            self.assertEqual(client.call_args.kwargs['timeout'],60)
            self.assertFalse(client.call_args.kwargs['follow_redirects'])
            self.assertFalse(client.call_args.kwargs['trust_env'])

    def test_actual_process_crashes_after_http_settlement_and_checkpoints(self):
        ctx=mp.get_context('fork')
        for point in ['sent','raw_saved','settled','before_checkpoint','checkpoint_saved']:
            with self.subTest(point=point),tempfile.TemporaryDirectory(dir=self.root) as folder:
                self.path=Path(folder)/'l.json';self.plan=p.expected_plan('new20','crash-'+point,'live')
                self.approval=self.approve('crash-'+point);self.initialize();counter=ctx.Value('i',0)
                def executor(path,index,token,crash=None):
                    hook=lambda name:os._exit(91) if name==crash else None
                    provider=p.Provider(path,index,token,hook=hook)
                    for ordinal in range(3):
                        def handler(request):
                            with counter.get_lock():counter.value+=1
                            return httpx.Response(200,content=p.scripted_raw(ordinal),request=request)
                        with self.transport(handler):
                            provider(messages=[{'role':'user','content':str(ordinal)}])
                    state,_,_=p.load_state(path)
                    result=LocalizationResult(p.arms_for(state['plan'])[index]['instance_id'],ResultStatus.EMPTY,
                        iterations=3,diagnostics={'termination_reason':'finished'}).to_dict()
                    p.finish_arm(path,index,token,result,.01)
                def run():
                    p.run_phase(self.path,'initial-five',live=True,
                        executor=lambda x,y,z:executor(x,y,z,point),
                        hook=lambda name:os._exit(91) if name==point else None)
                child=ctx.Process(target=run);child.start();child.join(60)
                if child.is_alive():child.kill();child.join();self.fail('Crash simulation timed out')
                self.assertEqual(child.exitcode,91)
                if point=='checkpoint_saved':
                    self.assertEqual(counter.value,30)
                    with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=executor)
                    continue
                audit=p.audit_recovery(self.path)
                if point=='sent':
                    self.assertFalse(audit['recoverable']);self.assertEqual(counter.value,1)
                    self.assertEqual(Decimal(p.load_state(self.path)[0]['reserved_cny']),p.followup.RESERVE)
                else:
                    self.assertFalse(audit['recoverable'])
                    before=counter.value
                    with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=executor)
                    self.assertEqual(counter.value,before,'Unverified exit cannot authorize resumption')
