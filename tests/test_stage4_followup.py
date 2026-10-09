"""Follow-up settlement tests: synthetic raw HTTP only; no real key or model calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from locagent_service import followup as f
from locagent_service import budget as old
from locagent_service.sources import canonical, digest
from locagent_service.evaluate import summarize

CONFIG = {**old.LIVE_CONFIG, 'budget_policy': f.POLICY}


def plan():
    sources = ['s' + str(i) for i in range(5)]
    return {'version': 3, 'policy': f.POLICY, 'dataset_revision': f.REVISION,
            'sources': sources, 'arms': [False, True], 'denominator_per_arm': 5,
            'samples': [{'instance_id': n, 'base_commit': f.COMMITS[n],
                         'source_id': sources[i], 'arm_order': f.arm_order(i)}
                        for i, n in enumerate(f.ORDER)],
            'config': dict(CONFIG), 'max_calls': 30, 'budget_cny': 5,
            'reservation_basis': dict(f.BASIS)}


def confirmation(p):
    return {'version': 1, 'plan_hash': digest(canonical(p)), 'provider': 'deepseek-official',
            'currency': 'CNY', 'input_cache_miss_peak_per_million': '2',
            'output_peak_per_million': '8', 'all_charges_included': True,
            'confirmed_at_utc': datetime.now(timezone.utc).isoformat()}


def response(pt=100, ct=20):
    return {'id': 'synthetic-raw-response', 'object': 'chat.completion', 'created': 1,
            'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
             'message': {'role': 'assistant', 'content': 'requests/models.py'}}],
            'usage': {'prompt_tokens': pt, 'completion_tokens': ct, 'total_tokens': pt + ct,
                      'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': pt}}


def raw(pt=100, ct=20):
    return json.dumps(response(pt, ct)).encode()


CHILD = """
import json, os, sys
from pathlib import Path
from locagent_service import followup as f
from locagent_service.sources import canonical,digest
path=Path(sys.argv[1])
state=json.loads(path.read_text())
f.AUTHORIZATION_PATH=path.parent/'approval.json'
f.APPROVED_PLAN_HASH=digest(canonical(state['plan']))
def completion(**kw):
    if sys.argv[2]=='die': os._exit(17)
    return bytes.fromhex(sys.argv[3])
try:
    f.SettlingBudgetProvider(path,'s0',state['plan']['config'],completion)(messages=[])
except RuntimeError:
    sys.exit(2)
"""


class FollowupSettlementTests(unittest.TestCase):
    def ledger(self, root):
        path = Path(root)/'budget.json'
        p = plan()
        for name, value in [('AUTHORIZATION_PATH', Path(root)/'approval.json'),
                            ('APPROVED_PLAN_HASH', digest(canonical(p)))]:
            c = patch.object(f, name, value)
            c.start(); self.addCleanup(c.stop)
        f.initialize_ledger(path, p, confirmation(p))
        return path

    def provider(self, path, completion=None, source='s0', arm=False):
        return f.SettlingBudgetProvider(path, source, CONFIG, completion or (lambda **kw:raw()), arm=arm)

    def test_real_followup_is_disabled_and_old_approval_cannot_be_reused(self):
        with patch.object(f, 'APPROVED_PLAN_HASH', None), self.assertRaises(ValueError):
            f.require_approval(plan())
        self.assertNotEqual(f.AUTHORIZATION_PATH, old.AUTHORIZATION_PATH)
        with self.assertRaises(ValueError):
            f.require_approval(plan())

    def test_selection_commit_denominator_rates_and_arm_order_are_fixed(self):
        p = plan(); f.validate_plan(p)
        self.assertEqual(f.RESERVE, (Decimal(1048576)*2 + Decimal(512)*8)/1000000)
        self.assertEqual(f.RESERVE, Decimal('2.101248'))
        for key, value in [('denominator_per_arm',4),('max_calls',31),('budget_cny',6),
                           ('arms',[0,1]),('dataset_revision','other'),('version',True)]:
            q=deepcopy(p);q[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): f.validate_plan(q)
        for key, value in [('instance_id','psf__requests-3362'),('base_commit','bad'),
                           ('arm_order',[True,False])]:
            q=deepcopy(p);q['samples'][0][key]=value
            with self.assertRaises(ValueError): f.validate_plan(q)
        q=confirmation(p);q['input_cache_miss_peak_per_million']='3'
        with self.assertRaises(ValueError): f.validate_pricing(p,q)

    def test_fresh_separate_marker_is_one_time_across_output_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            with self.assertRaises(FileExistsError):
                f.initialize_ledger(Path(tmp)/'other.json',plan(),confirmation(plan()))
            self.assertEqual(json.loads(path.read_text())['calls'],[])

    def test_full_raw_response_is_durable_before_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp); phases=[]
            real=old.save
            def save(where,state):
                if Path(where)==path and state['calls']:
                    phases.append((state['calls'][-1]['status'],state['reserved']))
                return real(where,state)
            def completion(**kw):
                state=json.loads(path.read_text())
                self.assertEqual(state['calls'][0]['status'],'reserved')
                self.assertEqual(state['reserved'],'2.101248')
                return raw()
            with patch.object(old,'save',save):
                self.provider(path,completion)(messages=[])
            self.assertEqual(phases,[('reserved','2.101248'),('raw_received','2.101248'),('settled','0')])
            state=json.loads(path.read_text())
            self.assertEqual(state['spent_cny'],'0.00036')
            self.assertEqual(state['calls'][0]['raw_body_utf8'].encode(),raw())
            self.assertFalse(path.with_name('budget.json.inflight').exists())

    def test_thirty_small_calls_settle_and_quotas_survive_new_provider_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            for source in plan()['sources']:
                for arm in [False,True]:
                    for _ in range(3): self.provider(path,source=source,arm=arm)(messages=[])
                    with self.assertRaises(RuntimeError):self.provider(path,source=source,arm=arm)(messages=[])
            state=json.loads(path.read_text())
            self.assertEqual(len(state['calls']),30)
            self.assertEqual(Decimal(state['spent_cny']),Decimal('0.0108'))
            self.assertEqual(Decimal(state['reserved']),0)

    def test_budget_exhaustion_blocks_next_reservation_and_keeps_denominator_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            for _ in range(2): self.provider(path,lambda **kw:raw(1048576,512))(messages=[])
            with self.assertRaises(RuntimeError):self.provider(path)(messages=[])
            state=json.loads(path.read_text())
            self.assertEqual(len(state['calls']),2)
            self.assertEqual(state['stop_reason'],'budget_exhausted')
            self.assertEqual(Decimal(state['spent_cny']),Decimal('4.202496'))
        p=plan();labels={s:{'files':['correct.py'],'entities':['correct.py:f']} for s in p['sources']}
        result=summarize(p,[{'source_id':'s0','suppress_repeats':False,'mode':'live',
                            'status':'failed'}],labels)
        self.assertEqual(result['denominator_per_arm'],5)
        for arm in result['arms'].values():
            self.assertEqual(arm['failed_or_missing'],5)
            self.assertEqual(arm['metrics']['files_recall_at_1'],0)

    def test_missing_inconsistent_and_synthetic_usage_never_releases(self):
        cases=[]
        for key in response()['usage']:
            obj=response();obj['usage'].pop(key);cases.append(json.dumps(obj).encode())
        for changes in [{'prompt_tokens':0},{'completion_tokens':True},{'total_tokens':121},
                        {'prompt_cache_hit_tokens':1},{'completion_tokens':513},
                        {'prompt_tokens':1048577},{'total_tokens':120.0}]:
            obj=response();obj['usage'].update(changes);cases.append(json.dumps(obj).encode())
        cases.extend([b'{}',b'not JSON',b'{"usage":{},"usage":{}}',object()])
        for body in cases:
            with self.subTest(body_type=type(body).__name__), tempfile.TemporaryDirectory() as tmp:
                path=self.ledger(tmp);calls=[]
                def completion(**kw):calls.append(1);return body
                with self.assertRaises(Exception):self.provider(path,completion)(messages=[])
                state=json.loads(path.read_text())
                self.assertTrue(state['halted']);self.assertEqual(state['reserved'],'2.101248')
                self.assertEqual(state['spent_cny'],'0')
                with self.assertRaises(RuntimeError):self.provider(path,completion)(messages=[])
                self.assertEqual(len(calls),1)

    def test_timeout_retains_full_reservation_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp);calls=[]
            def completion(**kw):calls.append(1);raise TimeoutError()
            with self.assertRaises(TimeoutError):self.provider(path,completion)(messages=[])
            with self.assertRaises(RuntimeError):self.provider(path,completion)(messages=[])
            state=json.loads(path.read_text())
            self.assertEqual(len(calls),1);self.assertEqual(state['reserved'],'2.101248')

    def test_reservation_write_failure_prevents_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            with patch.object(old,'save',side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    self.provider(path,lambda **kw:self.fail('transport called'))(messages=[])
            self.assertEqual(json.loads(path.read_text())['calls'],[])

    def test_raw_or_settlement_write_failure_retains_reservation_and_guard(self):
        for phase in ['raw_received','settled']:
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as tmp:
                path=self.ledger(tmp);real=old.save;failed=[]
                def save(where,state):
                    if Path(where)==path and state['calls'] and state['calls'][-1]['status']==phase and not failed:
                        failed.append(1);raise OSError('injected persistence fault')
                    return real(where,state)
                with patch.object(old,'save',save):
                    with self.assertRaises(OSError):self.provider(path)(messages=[])
                state=json.loads(path.read_text())
                self.assertEqual(state['reserved'],'2.101248');self.assertTrue(state['halted'])
                self.assertTrue(path.with_name('budget.json.inflight').exists())
                with self.assertRaises(RuntimeError):self.provider(path)(messages=[])

    def test_settlement_visible_but_fsync_failed_guard_still_blocks_new_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp);real=old.save;failed=[]
            def save(where,state):
                if failed: raise OSError('all subsequent writes fail')
                real(where,state)
                if Path(where)==path and state['calls'] and state['calls'][-1]['status']=='settled':
                    failed.append(1);raise OSError('post-rename fsync failure')
            with patch.object(old,'save',save):
                with self.assertRaises(OSError):self.provider(path)(messages=[])
            self.assertEqual(json.loads(path.read_text())['calls'][0]['status'],'settled')
            self.assertTrue(path.with_name('budget.json.inflight').exists())
            with self.assertRaises(RuntimeError):self.provider(path)(messages=[])

    def test_real_process_death_after_reservation_never_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            child=subprocess.run([sys.executable,'-B','-c',CHILD,str(path),'die',raw().hex()],
                                 capture_output=True,timeout=20)
            self.assertEqual(child.returncode,17)
            state=json.loads(path.read_text())
            self.assertEqual(state['calls'][0]['status'],'reserved')
            self.assertEqual(state['reserved'],'2.101248')
            with self.assertRaises(RuntimeError):self.provider(path)(messages=[])

    def test_eight_processes_share_durable_quota(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            children=[subprocess.Popen([sys.executable,'-B','-c',CHILD,str(path),'return',raw().hex()],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(8)]
            codes=[]
            for child in children:
                child.communicate(timeout=30);codes.append(child.returncode)
            self.assertEqual(codes.count(0),3);self.assertEqual(codes.count(2),5)
            self.assertEqual(len(json.loads(path.read_text())['calls']),3)

    def test_path_aliases_share_one_ledger_and_copied_ledger_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp);alias=Path(tmp)/'alias.json';alias.symlink_to(path)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda x:self.provider(x)(messages=[]),[path,alias,path]))
            self.assertEqual(len(json.loads(path.read_text())['calls']),3);self.assertTrue(alias.is_symlink())
            copy=Path(tmp)/'copy.json';copy.write_bytes(path.read_bytes())
            with self.assertRaises(RuntimeError):self.provider(copy)(messages=[])

    def test_tampered_settled_usage_or_totals_is_rejected(self):
        for kind in ['cost','raw','total']:
            with tempfile.TemporaryDirectory() as tmp:
                path=self.ledger(tmp);self.provider(path)(messages=[])
                state=json.loads(path.read_text())
                if kind=='cost':state['calls'][0]['cost_upper_cny']='0'
                elif kind=='raw':state['calls'][0]['raw_body_utf8']='{}'
                else:state['spent_cny']='0'
                path.write_text(json.dumps(state))
                with self.assertRaises(Exception):self.provider(path)(messages=[])

    def test_raw_transport_filters_overrides_and_uses_no_retry_or_redirects(self):
        with patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'synthetic-only'},clear=True):
            with patch('httpx.Client') as client,patch('httpx.HTTPTransport') as transport:
                reply=client.return_value.__enter__.return_value.post.return_value
                reply.status_code=200;reply.content=raw()
                body=f.request_raw(messages=[],model='bad',max_tokens=9999,stream=True,num_retries=8)
                self.assertEqual(body,raw())
                transport.assert_called_once_with(retries=0)
                self.assertFalse(client.call_args.kwargs['follow_redirects'])
                self.assertFalse(client.call_args.kwargs['trust_env'])
                post=client.return_value.__enter__.return_value.post
                self.assertEqual(post.call_count,1)
                self.assertEqual(post.call_args.args[0],'https://api.deepseek.com/chat/completions')
                payload=post.call_args.kwargs['json']
                self.assertEqual(payload['max_tokens'],512)
                self.assertEqual(payload['thinking'],{'type':'disabled'})
                self.assertEqual(payload['model'],'deepseek-v4-flash')
                self.assertFalse(payload['stream'])

    def test_raw_transport_http_error_never_retries(self):
        with patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'synthetic-only'},clear=True):
            for code in [302,429,500]:
                with patch('httpx.Client') as client:
                    post=client.return_value.__enter__.return_value.post
                    post.return_value.status_code=code
                    with self.assertRaises(RuntimeError):f.request_raw(messages=[])
                    self.assertEqual(post.call_count,1)

    def test_cli_followup_preflight_rejects_before_env_loading(self):
        from locagent_service.evaluate import load_live_pricing
        with self.assertRaises(ValueError):load_live_pricing(plan(),None)


    def test_real_httpx_serialization_validates_raw_body_before_sdk_normalization(self):
        import httpx
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            obj=response();obj.pop('usage')
            return httpx.Response(200,content=json.dumps(obj).encode(),request=request)
        with tempfile.TemporaryDirectory() as tmp:
            path=self.ledger(tmp)
            with patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'synthetic-only'},clear=True), \
                 patch('httpx.HTTPTransport',return_value=httpx.MockTransport(handler)):
                provider=f.SettlingBudgetProvider(path,'s0',CONFIG)
                with self.assertRaises(KeyError):
                    provider(messages=[{'role':'assistant','content':None,'function_call':None,
                                        'tool_calls':[{'id':'a','type':'function','function':{'name':'finish','arguments':'{}'}}]},
                                       {'role':'tool','name':'finish','tool_call_id':'a','content':'result'}])
            self.assertEqual(len(seen),1)
            self.assertNotIn('function_call',seen[0]['messages'][0])
            self.assertNotIn('name',seen[0]['messages'][1])
            self.assertEqual(json.loads(path.read_text())['reserved'],'2.101248')

    def test_evaluator_runs_exact_alternating_order_and_preserves_failed_sample_denominator(self):
        import io
        from contextlib import redirect_stdout
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json'
            labels.write_text(json.dumps({s:{'files':['f.py'],'entities':['f.py:f']} for s in plan()['sources']}))
            value=plan();value['labels_sha256']=digest(labels.read_bytes())
            p=root/'plan.json';p.write_text(json.dumps(value));observed=[]
            def child(cmd,**kwargs):
                source=cmd[cmd.index('--source')+1];arm=cmd[cmd.index('--suppress')+1]=='true'
                observed.append((source,arm))
                Path(cmd[cmd.index('--output')+1]).write_text(json.dumps({
                    'source_id':source,'suppress_repeats':arm,'mode':'offline',
                    'status':'failed','elapsed_seconds':0.01,'error_type':'SyntheticFailure'}))
                return subprocess.CompletedProcess(cmd,0)
            with patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child),redirect_stdout(io.StringIO()):
                result=run(p,labels,root/'out')
            self.assertEqual(observed,[(s,a) for i,s in enumerate(value['sources']) for a in f.arm_order(i)])
            self.assertEqual(result['denominator_per_arm'],5)
            self.assertTrue(all(a['failed_or_missing']==5 for a in result['arms'].values()))

    def test_live_failure_stops_five_sample_plan_and_keeps_billed_unknown_reserve(self):
        import io
        from contextlib import redirect_stdout
        from locagent_service.evaluate import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);labels=root/'labels.json'
            labels.write_text(json.dumps({s:{'files':['f.py'],'entities':['f.py:f']} for s in plan()['sources']}))
            value=plan();value['labels_sha256']=digest(labels.read_bytes())
            p=root/'plan.json';p.write_text(json.dumps(value))
            pricing=root/'pricing.json';pricing.write_text(json.dumps(confirmation(value)))
            def child(cmd,**kwargs):
                ledger=Path(kwargs['env']['LOCAGENT_BUDGET_LEDGER'])
                def broken(**kw):raise TimeoutError()
                with self.assertRaises(TimeoutError):
                    self.provider(ledger,broken)(messages=[])
                Path(cmd[cmd.index('--output')+1]).write_text('{')
                return subprocess.CompletedProcess(cmd,1)
            with patch.object(f,'AUTHORIZATION_PATH',root/'approval.json'), \
                 patch.object(f,'APPROVED_PLAN_HASH',digest(canonical(value))), \
                 patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'synthetic-only'},clear=True), \
                 patch('locagent_service.evaluate.load_manifest',return_value=({'config':CONFIG},None)), \
                 patch('locagent_service.evaluate.subprocess.run',side_effect=child) as launch,redirect_stdout(io.StringIO()):
                result=run(p,labels,root/'out',live=True,pricing_confirmation=pricing)
            self.assertEqual(launch.call_count,1)
            self.assertEqual(result['denominator_per_arm'],5)
            self.assertEqual(result['arms']['false']['cost_upper_cny'],'2.101248')
            self.assertEqual(result['arms']['false']['unknown_call_count'],1)
            self.assertTrue(all(a['failed_or_missing']==5 for a in result['arms'].values()))


if __name__=='__main__':
    unittest.main()
