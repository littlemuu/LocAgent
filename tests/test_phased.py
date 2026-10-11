from phased_test_support import install_synthetic_cohorts
"""Temporary offline ledgers only; no old authorization or external model calls."""
from copy import deepcopy
from decimal import Decimal
import json
import io
from contextlib import redirect_stdout
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import signal
import unittest
from unittest.mock import patch

from locagent_service import phased as p
from locagent_service.offline import offline_engine
from locagent_service.sources import canonical,digest
from util.localization_contract import LocalizationResult,ResultStatus

def setUpModule():
    global guard
    guard=offline_engine();guard.__enter__()
    from litellm import ModelResponse

def tearDownModule():
    guard.__exit__(None,None,None)

def raw_counter(counter,ordinal,**kwargs):
    with counter.get_lock():counter.value+=1
    return p.scripted_raw(ordinal,**kwargs)

def fake_result(path,index):
    state,_,_=p.load_state(path)
    return LocalizationResult(p.arms_for(state['plan'])[index]['instance_id'],ResultStatus.EMPTY,
        iterations=3,diagnostics={'termination_reason':'finished'}).to_dict()

def fake_executor(path,index,token, *, counter=None,crash=None):
    def hook(name):
        if name==crash:os._exit(91)
    raw=(lambda ordinal,**kw:raw_counter(counter,ordinal,**kw)) if counter is not None else None
    provider=p.Provider(path,index,token,raw_completion=raw,hook=hook)
    for i in range(3):provider(messages=[{'role':'user','content':'fixture step '+str(i)}])
    p.finish_arm(path,index,token,fake_result(path,index),0.01,hook=hook)

def start_crash(path,stage,point,counter):
    p.run_phase(path,stage,executor=lambda a,b,c:fake_executor(a,b,c,counter=counter,crash=point),
                hook=lambda name:os._exit(91) if name==point else None)

def concurrent_init(path,plan,start,results):
    start.wait()
    try:p.initialize(path,plan);results.put('won')
    except Exception:results.put('lost')

def concurrent_stage(path,start,entered,release,results):
    start.wait()
    def executor(path,index,token):
        if index==0:entered.set();release.wait(10)
        fake_executor(path,index,token)
    try:p.run_phase(path,'initial-five',executor=executor);results.put('won')
    except Exception:results.put('lost')


def parent_with_waiting_arm(path):
    code = """import os,time
from pathlib import Path
from locagent_service import phased as p
def wait(path):
    Path(path).write_text(str(os.getpid()))
    while True:time.sleep(1)
p.load_state=wait
p.execute_arm(__import__('sys').argv[1],0,'fixture',os.getppid())
"""
    child=subprocess.Popen([sys.executable,'-B','-c',code,str(path)])
    child.wait()

class PhasedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        install_synthetic_cohorts(self)
        patch.object(p,'OWNERSHIP_ROOT',self.root/'owners').start()
        patch.object(p,'verify_sources').start()
        patch.object(p,'check_labels').start()
        self.plan=p.expected_plan('new20','unit')
        self.path=self.root/'ledger.json'
        self.ctx=mp.get_context('fork')

    def initialize(self,plan=None,path=None):
        return p.initialize(path or self.path,plan or self.plan)

    def claim(self,index=0):
        self.initialize()
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path)
            state.update(status='running',active_run={'token':'run','arm_index':index,'parent_pid':os.getpid(),'phase':'initial-five'})
            state['arms'][index]['status']='running';p.commit(self.path,state)
        return p.Provider(self.path,index,'run')

    def test_live_gate_cannot_use_environment_or_old_approval(self):
        with patch.dict(os.environ,{'LOCAGENT_ALLOW_PAID':'1','DEEPSEEK_API_KEY':'fake'}),patch.object(p.followup,'request_raw',side_effect=AssertionError('no live')):
            with self.assertRaises(RuntimeError):p.initialize(self.path,self.plan,live=True)
            with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True)
        self.assertFalse(self.path.exists())
        self.assertFalse(p.OWNERSHIP_ROOT.exists())

    def test_concurrent_initialization_has_one_global_owner(self):
        start=self.ctx.Event();q=self.ctx.Queue()
        children=[self.ctx.Process(target=concurrent_init,args=(self.root/f'{i}.json',self.plan,start,q)) for i in range(4)]
        for c in children:c.start()
        start.set()
        for c in children:c.join(15);self.assertEqual(c.exitcode,0)
        self.assertEqual(sorted(q.get(timeout=2) for _ in children),['lost','lost','lost','won'])
        self.assertEqual(len(list(self.root.glob('[0-9].json'))),1)

    def test_partial_initialization_is_consumed(self):
        original=p.budget.save
        def fail(path,value):
            if Path(path)==self.path:raise OSError('disk')
            return original(path,value)
        with patch.object(p.budget,'save',side_effect=fail):
            with self.assertRaises(OSError):self.initialize()
        with self.assertRaises(FileExistsError):self.initialize(path=self.root/'another.json')
        self.assertTrue(p.owner_path(self.plan).exists())

    def test_concurrent_phase_start_only_one_runner(self):
        self.initialize();start=self.ctx.Event();entered=self.ctx.Event();release=self.ctx.Event();q=self.ctx.Queue()
        children=[self.ctx.Process(target=concurrent_stage,args=(self.path,start,entered,release,q)) for _ in range(2)]
        for c in children:c.start()
        start.set();self.assertTrue(entered.wait(10))
        self.assertEqual(q.get(timeout=10),'lost');release.set()
        for c in children:c.join(30);self.assertEqual(c.exitcode,0)
        self.assertEqual(q.get(timeout=3),'won')
        state,_,_=p.load_state(self.path);self.assertEqual(len(state['calls']),30)

    def test_fixed_order_duplicate_stage_and_shared_second_stage_quotas(self):
        self.initialize()
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'remaining-fifteen',executor=fake_executor)
        p.run_phase(self.path,'initial-five',executor=fake_executor)
        first=p.read_json(self.path)
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',executor=fake_executor)
        final=p.run_phase(self.path,'remaining-fifteen',executor=fake_executor)
        self.assertEqual(final['calls'][:30],first['calls'])
        self.assertEqual(len(final['calls']),120);self.assertEqual(final['status'],'complete')
        self.assertEqual([c['arm_index'] for c in final['calls']],[i for i in range(40) for _ in range(3)])
        self.assertEqual(final['reserved_cny'],'0.000000')
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'remaining-fifteen',executor=fake_executor)

    def test_independent_old5_and_new20_ledgers_and_limits(self):
        self.initialize()
        old=p.expected_plan('regression5','unit');other=self.root/'old.json';self.initialize(old,other)
        p.run_phase(other,'regression-five',executor=fake_executor)
        a,_,_=p.load_state(self.path);b,_,_=p.load_state(other)
        self.assertEqual(a['calls'],[]);self.assertEqual(len(b['calls']),30)
        self.assertEqual((a['plan']['limit_cny'],b['plan']['limit_cny']),('8','5'))
        self.assertNotEqual(a['token'],b['token'])

    def test_copied_ledger_symlink_alias_and_deleted_ledger_cannot_reset_owner(self):
        self.initialize()
        copy=self.root/'copy.json';copy.write_bytes(self.path.read_bytes())
        with self.assertRaises(RuntimeError):p.load_state(copy)
        alias=self.root/'alias.json';alias.symlink_to(self.path)
        self.assertEqual(p.load_state(alias)[0],p.load_state(self.path)[0])
        self.path.unlink()
        with self.assertRaises(FileExistsError):self.initialize()

    def test_plan_runtime_sample_label_config_changes_rejected(self):
        for field in ['config','samples','labels_sha256','metric_specification_sha256','runtime_hashes','limit_cny']:
            changed=deepcopy(self.plan)
            if field=='config':changed[field]['temperature']=1
            elif field=='samples':changed[field].reverse()
            elif field=='runtime_hashes':changed[field]['locagent_service/phased.py']='0'*64
            else:changed[field]='changed'
            with self.subTest(field=field),self.assertRaises(ValueError):p.validate_plan(changed)

    def test_corrupt_json_duplicate_fields_totals_and_rollback_rejected(self):
        self.initialize();first=self.path.read_bytes()
        with p.budget.ledger_lock(self.path):
            s,_,_=p.load_state(self.path);s['audits'].append({'test':'known state'});p.commit(self.path,s)
        latest=self.path.read_bytes()
        for raw in [b'{',b'{"a":1,"a":2}',first]:
            self.path.write_bytes(raw)
            with self.assertRaises((RuntimeError,ValueError,KeyError)):p.load_state(self.path)
        self.path.write_bytes(latest)
        state=p.read_json(self.path);state['spent_cny']='1';p.budget.save(self.path,state)
        with self.assertRaises(RuntimeError):p.load_state(self.path)

    def test_owner_head_partial_save_requires_explicit_audit(self):
        self.initialize();original=p.budget.save
        def fail(path,value):
            if Path(path)==p.owner_path(self.plan):raise OSError('owner head disk fault')
            return original(path,value)
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path);state.update(status='running',active_run={'token':'run','phase':'initial-five'})
            with patch.object(p.budget,'save',side_effect=fail):
                with self.assertRaises(OSError):p.commit(self.path,state)
        with self.assertRaises(RuntimeError):p.load_state(self.path)
        audit=p.audit_recovery(self.path);self.assertFalse(audit['recoverable'])
        self.assertEqual(p.load_state(self.path)[0]['status'],'halted')

    def test_real_process_crashes_at_all_persistence_boundaries(self):
        for point in ['reserved','sent','raw_saved','settled','result_saved','arm_committed','before_checkpoint','checkpoint_saved']:
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=self.root) as tmp:
                folder=Path(tmp);plan=p.expected_plan('new20',point);path=folder/'ledger.json'
                p.initialize(path,plan);counter=self.ctx.Value('i',0)
                child=self.ctx.Process(target=start_crash,args=(path,'initial-five',point,counter));child.start();child.join(40)
                self.assertEqual(child.exitcode,91)
                if point=='checkpoint_saved':
                    with self.assertRaises(RuntimeError):p.run_phase(path,'initial-five',executor=fake_executor)
                    self.assertEqual(counter.value,30);continue
                with self.assertRaises(RuntimeError):p.run_phase(path,'initial-five',executor=fake_executor)
                audit=p.audit_recovery(path)
                if point in ('reserved','sent'):
                    self.assertFalse(audit['recoverable'])
                    state,_,_=p.load_state(path);self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                    with self.assertRaises(RuntimeError):p.run_phase(path,'initial-five',executor=fake_executor)
                    self.assertEqual(counter.value,0 if point=='reserved' else 1)
                else:
                    self.assertFalse(audit['recoverable'])
                    before=counter.value
                    with self.assertRaises(RuntimeError):
                        p.run_phase(path,'initial-five',executor=lambda a,b,c:fake_executor(a,b,c,counter=counter))
                    self.assertEqual(counter.value,before,'Unverified executor exit must never resume or resend')
                    self.assertEqual(p.load_state(path)[0]['status'],'halted')

    def test_unknown_transport_and_invalid_usage_keep_full_reservation(self):
        for failure in ['timeout','missing_usage','duplicate_usage','wrong_total','non_bytes','invalid_utf8']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                path=Path(tmp)/'l.json';plan=p.expected_plan('new20',failure);p.initialize(path,plan)
                with p.budget.ledger_lock(path):
                    state,_,_=p.load_state(path);state.update(status='running',active_run={'token':'run','arm_index':0})
                    state['arms'][0]['status']='running';p.commit(path,state)
                calls=[]
                def raw(ordinal,**kw):
                    calls.append(1)
                    if failure=='timeout':raise TimeoutError()
                    if failure=='non_bytes':return {}
                    if failure=='invalid_utf8':return b'\xff\xfe'
                    value=json.loads(p.scripted_raw(ordinal))
                    if failure=='missing_usage':del value['usage']['prompt_tokens']
                    if failure=='wrong_total':value['usage']['total_tokens']=999
                    if failure=='duplicate_usage':return b'{"usage":{},"usage":{}}'
                    return canonical(value)
                provider=p.Provider(path,0,'run',raw_completion=raw)
                with self.assertRaises(Exception):provider(messages=[])
                self.assertFalse(p.audit_recovery(path)['recoverable'])
                state,_,_=p.load_state(path);self.assertEqual(Decimal(state['reserved_cny']),p.followup.RESERVE)
                with self.assertRaises(RuntimeError):provider(messages=[])
                self.assertEqual(len(calls),1)

    def test_per_arm_quota_does_not_reset_with_provider_restart(self):
        provider=self.claim()
        for i in range(3):provider(messages=[{'role':'user','content':str(i)}])
        again=p.Provider(self.path,0,'run',raw_completion=lambda *a,**k:self.fail('No new call permitted'))
        for i in range(3):again(messages=[{'role':'user','content':str(i)}])
        with self.assertRaises(RuntimeError):again(messages=[{'role':'user','content':'fourth'}])
        self.assertEqual(len(p.load_state(self.path)[0]['calls']),3)

    def test_cached_request_divergence_does_not_send(self):
        provider=self.claim();provider(messages=[{'role':'user','content':'original'}])
        again=p.Provider(self.path,0,'run',raw_completion=lambda *a,**k:self.fail('No divergent send'))
        with self.assertRaises(RuntimeError):again(messages=[{'role':'user','content':'changed'}])
        self.assertEqual(len(p.load_state(self.path)[0]['calls']),1)

    def test_budget_exhaustion_stops_before_next_full_reservation(self):
        self.initialize()
        def expensive(ordinal,**kw):
            raw=json.loads(p.scripted_raw(ordinal))
            raw['usage']={'prompt_tokens':1048576,'completion_tokens':512,'total_tokens':1049088,
                'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':1048576}
            return canonical(raw)
        def executor(path,index,token):
            provider=p.Provider(path,index,token,raw_completion=expensive)
            for i in range(3):provider(messages=[{'role':'user','content':str(i)}])
            p.finish_arm(path,index,token,fake_result(path,index),.01)
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',executor=executor)
        state,_,_=p.load_state(self.path)
        self.assertEqual(len(state['calls']),3);self.assertEqual(state['status'],'halted')
        self.assertEqual(state['stop_reason'],'budget_exhausted')
        self.assertEqual(len(state['arms']),40);self.assertEqual(state['plan']['denominator_per_arm'],20)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_stale_runner_fencing_and_results_cannot_be_changed(self):
        provider=self.claim()
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path);state['active_run']['token']='replacement';p.commit(self.path,state)
        with self.assertRaises(RuntimeError):provider(messages=[])
        with self.assertRaises(RuntimeError):p.finish_arm(self.path,0,'run',fake_result(self.path,0),.01)

    def test_complete_fixed25_simulation_keeps_denominators_and_no_quality_claim(self):
        self.initialize();p.run_phase(self.path,'initial-five',executor=fake_executor)
        p.run_phase(self.path,'remaining-fifteen',executor=fake_executor)
        answers={s:{'files':['fixture.py'],'entities':['fixture.py:f'] if s in self.plan['function_applicable_sources'] else []} for s in self.plan['sources']}
        with patch.object(p,'check_labels',return_value=answers):
            summary=p.summary(self.path,'unused')
        self.assertEqual(summary['denominator_per_arm'],20)
        self.assertEqual(summary['arms']['false']['metric_denominators'],{'files':20,'functions':18})
        self.assertFalse(summary['quality_claim_allowed']);self.assertEqual(summary['paid_calls'],0)
        self.assertTrue(all(v is None for v in summary['arms']['true']['metrics'].values()))
        old=p.expected_plan('regression5','full25');path=self.root/'old.json';p.initialize(path,old)
        p.run_phase(path,'regression-five',executor=fake_executor)
        self.assertEqual(len(p.load_state(path)[0]['calls'])+summary['simulated_calls'],150)

    def test_result_corruption_and_checkpoint_inconsistency_fail_closed(self):
        self.initialize();p.run_phase(self.path,'initial-five',executor=fake_executor)
        record=p.result_path(self.path,0);original=record.read_bytes();record.write_text('{}')
        with self.assertRaises(RuntimeError):p.load_state(self.path)
        record.write_bytes(original)
        state=p.read_json(self.path);state['checkpoints'][0]['results_sha256']='0'*64;p.budget.save(self.path,state)
        with self.assertRaises(RuntimeError):p.load_state(self.path)

    def test_label_fields_never_enter_provider_requests(self):
        provider=self.claim();seen=[]
        def raw(ordinal,**kw):
            seen.append(kw);return p.scripted_raw(ordinal)
        provider.raw=raw
        provider(messages=[{'role':'user','content':'issue only'}],labels='GOLD_SENTINEL',patch='GOLD_SENTINEL')
        self.assertNotIn('GOLD_SENTINEL',json.dumps(seen))
        self.assertEqual(set(seen[0]),{'messages'})

    def test_input_gate_rejects_before_reservation_or_transport(self):
        provider=self.claim()
        provider.raw=lambda *a,**k:self.fail('Input must be rejected before transport')
        with self.assertRaises(RuntimeError):provider(messages=[{'content':'x'*65536}])
        self.assertEqual(p.load_state(self.path)[0]['calls'],[])

    def test_partial_phase_and_changed_labels_keep_fixed_cohort(self):
        self.initialize()
        p.run_phase(self.path,'initial-five',executor=fake_executor)
        answers={s:{'files':['fixture.py'],'entities':['fixture.py:f'] if s in self.plan['function_applicable_sources'] else []} for s in self.plan['sources']}
        with patch.object(p,'check_labels',return_value=answers):
            summary=p.summary(self.path,'unused')
        for arm in summary['arms'].values():
            self.assertEqual(arm['completed'],5)
            self.assertEqual(arm['failed_or_missing'],15)
            self.assertEqual(arm['metric_denominators'],{'files':20,'functions':18})
        before=self.path.read_bytes()
        with patch.object(p,'check_labels',side_effect=ValueError('labels changed')):
            with self.assertRaises(ValueError):p.run_phase(self.path,'remaining-fifteen',executor=fake_executor)
        self.assertEqual(self.path.read_bytes(),before)

    def test_old_authorization_shape_cannot_initialize_new_ledger(self):
        marker=p.owner_path(self.plan);marker.parent.mkdir()
        p.budget.save(marker,{'policy':p.followup.POLICY,'limit':'5','plan_hash':p.followup.BOUNDED_PLAN_HASH,'token':'old-consumed'})
        with self.assertRaises(FileExistsError):self.initialize()
        self.assertFalse(self.path.exists())

    def test_actual_arm_parent_death_kills_isolated_child(self):
        pidfile=self.root/'child.pid'
        parent=self.ctx.Process(target=parent_with_waiting_arm,args=(pidfile,))
        parent.start()
        try:
            end=time.monotonic()+15
            while not pidfile.exists() and time.monotonic()<end:time.sleep(.05)
            self.assertTrue(pidfile.exists(),'Actual arm must enter after installing PDEATHSIG')
            pid=int(pidfile.read_text())
            parent.kill();parent.join(5)
            end=time.monotonic()+5
            while time.monotonic()<end:
                stat=Path('/proc')/str(pid)/'stat'
                if not stat.exists() or stat.read_text().split()[2]=='Z':break
                time.sleep(.05)
            else:
                os.kill(pid,signal.SIGKILL)
                self.fail('Orphan arm survived its parent')
        finally:
            if parent.is_alive():parent.kill()
            parent.join(5)

    def test_final_checkpoint_owner_head_fault_preserves_complete(self):
        plan=p.expected_plan('regression5','last-checkpoint')
        p.initialize(self.path,plan)
        original=p.budget.save
        def fail(path,value):
            if Path(path)==p.owner_path(plan) and p.read_json(self.path)['status']=='complete':
                raise OSError('final head persistence')
            return original(path,value)
        with patch.object(p.budget,'save',side_effect=fail):
            with self.assertRaises(OSError):p.run_phase(self.path,'regression-five',executor=fake_executor)
        with self.assertRaises(RuntimeError):p.load_state(self.path)
        audit=p.audit_recovery(self.path);self.assertTrue(audit['recoverable'])
        state,_,_=p.load_state(self.path)
        self.assertEqual(state['status'],'complete');self.assertEqual(len(state['calls']),30)
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'regression-five',executor=fake_executor)

    def test_cli_unknown_audit_explicitly_reports_blocked(self):
        provider=self.claim()
        provider.raw=lambda *a,**k:(_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(TimeoutError):provider(messages=[])
        output=io.StringIO()
        with patch.object(sys,'argv',['phased','audit-recovery','--ledger',str(self.path),'--labels','dummy']),redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:p.main()
        self.assertEqual(error.exception.code,2)
        self.assertEqual(json.loads(output.getvalue())['status'],'blocked')
        self.assertFalse(json.loads(output.getvalue())['recoverable'])
