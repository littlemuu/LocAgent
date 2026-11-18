"""New protocol only. Temporary authorities, local subprocesses, MockTransport, no credentials."""
from copy import deepcopy
from decimal import Decimal
import itertools,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from locagent_service import phased as p
from locagent_service.sources import canonical,digest
from locagent_service.evaluate import summarize
from util.localization_contract import LocalizationError,ErrorCode
import test_phased_http as http_fixtures
import test_quality_checkpoint as quality_fixtures

from phased_test_support import protocol_body, continuation_oracle

class SettledArmIsolationTests(unittest.TestCase):
    setUp=http_fixtures.HTTPAdmissionTests.setUp
    approve=http_fixtures.HTTPAdmissionTests.approve
    initialize=http_fixtures.HTTPAdmissionTests.initialize
    transport=http_fixtures.HTTPAdmissionTests.transport
    success=quality_fixtures.QualityCheckpointTests.execute

    def answers(self):
        return {s:{'files':['fixture.py'],'entities':['fixture.py:f']
            if s in self.plan['function_applicable_sources'] else []} for s in self.plan['sources']}

    def report(self):
        with patch.object(p,'check_labels',return_value=self.answers()):
            return p.summary(self.path,'synthetic')

    def publish_failure(self,path,index,token,fixture='replacement',*,raws=None):
        provider=p.Provider(path,index,token)
        raws=raws or [protocol_body(fixture,i) for i in range(2)]
        for ordinal,raw in enumerate(raws):
            with self.transport(lambda req,b=raw:httpx.Response(200,content=b,request=req)):
                provider(messages=[{'role':'user','content':str(ordinal)}])
        p.fail_localization(path,index,token,LocalizationError(ErrorCode.INVALID_RESPONSE,p.PROTOCOL_ERROR['message']))

    def fail_with_reaped_child(self,path,index,token,fixture='replacement',*,mutate=None):
        popen=subprocess.Popen
        def launch(*args,**kwargs):
            self.publish_failure(path,index,token,fixture)
            if mutate:mutate(path,index,token)
            return popen([sys.executable,'-c','raise SystemExit(1)'],**kwargs)
        with patch.object(p.subprocess,'Popen',side_effect=launch):
            p.child_executor(path,index,token)

    def executor(self,failures):
        def execute(path,index,token):
            if index in failures:return self.fail_with_reaped_child(path,index,token,failures[index])
            return self.success(path,index,token)
        return execute

    def test_synthetic_failures_both_continue_without_retry_and_full_paired_report(self):
        self.initialize();execute=self.executor({0:'old',38:'replacement'})
        p.run_phase(self.path,'initial-five',live=True,executor=execute)
        first=self.report()
        self.assertEqual(first['paired_outcomes']['terminal_pairs'],5)
        self.assertFalse(first['quality_claim_allowed'])
        s=p.load_state(self.path)[0];proof=deepcopy(s['arms'][0]['protocol_failure'])
        self.assertEqual(s['arms'][0]['status'],'failed');self.assertEqual(len(s['calls']),29)
        p.run_phase(self.path,'remaining-fifteen',live=True,executor=execute)
        s=p.load_state(self.path)[0];q=self.report()
        self.assertEqual(len(s['calls']),118);self.assertEqual(s['arms'][0]['protocol_failure'],proof)
        self.assertTrue(q['quality_claim_allowed']);self.assertTrue(q['experiment_complete'])
        self.assertEqual(q['paired_outcomes'],{'planned_pairs':20,'terminal_pairs':20,'both_completed_pairs':18})
        for a in q['arms'].values():
            self.assertEqual(a['metric_denominators'],{'files':20,'functions':18})
            self.assertEqual((a['completed'],a['failed'],a['terminal']),(19,1,20))
            self.assertEqual(a['failure_rate'],.05);self.assertEqual(a['completion_rate'],.95)
            self.assertEqual(a['not_started'],0);self.assertGreater(Decimal(a['cost_upper_cny']),0)
        self.assertEqual(Decimal(s['reserved_cny']),0)
        before=self.path.read_bytes()
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'remaining-fifteen',live=True,executor=execute)
        self.assertEqual(self.path.read_bytes(),before)

    def test_all_failed_is_complete_evaluation_not_success(self):
        self.initialize();execute=self.executor({i:'replacement' for i in range(40)})
        for phase in self.plan['phases']:p.run_phase(self.path,phase['name'],live=True,executor=execute)
        q=self.report();s=p.load_state(self.path)[0]
        self.assertEqual(len(s['calls']),80);self.assertTrue(q['quality_claim_allowed'])
        self.assertEqual(q['paired_outcomes']['terminal_pairs'],20)
        self.assertEqual(q['paired_outcomes']['both_completed_pairs'],0)
        for a in q['arms'].values():
            self.assertEqual((a['completed'],a['failed'],a['terminal']),(0,20,20))
            self.assertEqual(a['failure_rate'],1);self.assertEqual(a['completion_rate'],0)
            self.assertTrue(all(v==0 for v in a['metrics'].values()))
            self.assertEqual(a['valid_finish_rate'],0)
            self.assertGreater(a['prompt_tokens'],0);self.assertGreater(a['recorded_attempt_seconds'],0)
            self.assertEqual(a['completed_result_seconds'],0)

    def test_published_protocol_failure_but_generic_executor_exception_halts(self):
        self.initialize()
        def execute(path,index,token):
            self.publish_failure(path,index,token)
            raise RuntimeError('not a confirmed subprocess exit')
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=execute)
        s=p.load_state(self.path)[0]
        self.assertEqual(s['status'],'halted');self.assertNotIn('protocol_failure',s['arms'][0])
        self.assertEqual(len(s['calls']),2);self.assertFalse(self.report()['quality_claim_allowed'])

    def test_reaped_child_without_raw_protocol_evidence_halts(self):
        self.initialize();popen=subprocess.Popen
        def launch(*args,**kwargs):
            self.publish_failure(self.path,0,p.read_json(self.path)['active_run']['token'],raws=[p.scripted_raw(0)])
            return popen([sys.executable,'-c','raise SystemExit(1)'],**kwargs)
        with patch.object(p.subprocess,'Popen',side_effect=launch),self.assertRaises(RuntimeError):
            p.run_phase(self.path,'initial-five',live=True)
        self.assertEqual(len(p.load_state(self.path)[0]['calls']),1)

    def test_process_group_uncertain_never_continues(self):
        self.initialize()
        with patch.object(p.os,'killpg',return_value=None):
            with self.assertRaises(p.ExecutorExitUnknown):
                p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}))
        s=p.load_state(self.path)[0]
        self.assertEqual(s['arms'][0]['status'],'blocked');self.assertEqual(len(s['calls']),2)

    def test_safe_failure_commit_faults_do_not_start_next_arm(self):
        for boundary in ['before','ledger','owner','after']:
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                self.path=Path(tmp)/'ledger.json';self.plan=p.expected_plan('new20','commit-'+boundary,'live')
                self.approval=self.approve('commit-'+boundary);self.initialize()
                original=p.budget.save
                def write(path,value):
                    is_protocol=(value.get('arms') or [{}])[0].get('protocol_failure')
                    if boundary=='ledger' and Path(path)==self.path and is_protocol:raise OSError('ledger write')
                    if boundary=='owner' and Path(path)==p.owner_path(self.plan,'live') and p.read_json(self.path)['arms'][0].get('protocol_failure'):
                        raise OSError('owner write')
                    return original(path,value)
                def hook(point):
                    if (boundary=='before' and point=='before_protocol_failure_commit') or (
                        boundary=='after' and point=='protocol_failure_committed'):raise OSError('commit hook')
                with patch.object(p.budget,'save',side_effect=write),self.assertRaises(OSError):
                    p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}),hook=hook)
                raw=p.read_json(self.path);self.assertEqual(len(raw['calls']),2)
                self.assertTrue(all(a['status']=='pending' for a in raw['arms'][1:]))
                self.assertFalse(p.audit_recovery(self.path)['recoverable'])
                with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}))

    def test_body_corruption_after_failure_commit_prevents_next_claim(self):
        self.initialize()
        def hook(point):
            if point=='protocol_failure_committed':
                s=p.read_json(self.path);c=s['calls'][-1]
                (p.response_store.directory(self.path)/c['raw_body_ref']['file']).write_bytes(b'corrupt')
        with self.assertRaises(RuntimeError):
            p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}),hook=hook)
        self.assertEqual(len(p.read_json(self.path)['calls']),2)
        self.assertTrue(all(a['status']=='pending' for a in p.read_json(self.path)['arms'][1:]))

    def test_second_runner_and_duplicate_failure_callback_are_rejected(self):
        self.initialize();attempts=[]
        def hook(point):
            if point=='protocol_failure_committed':
                with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)
                s=p.load_state(self.path)[0];proof=s['arms'][0]['protocol_failure']
                exc=p.ReapedProtocolError(0,s['active_run']['token'],proof['executor'])
                attempts.append((point,s['active_run']['token'],exc))
        p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}),hook=hook)
        self.assertEqual([a[0] for a in attempts],['protocol_failure_committed'])
        # Invoke the duplicate after leaving the original commit's non-reentrant ledger lock.
        with self.assertRaises(RuntimeError):
            p.complete_protocol_failure(self.path,0,attempts[0][1],attempts[0][2],.1)
        self.assertEqual(len(p.load_state(self.path)[0]['calls']),29)

    def test_unknown_cost_after_prior_safe_failure_halts_with_reserve(self):
        self.initialize()
        def execute(path,index,token):
            if index==0:return self.fail_with_reaped_child(path,index,token,'old')
            with self.transport(lambda req:(_ for _ in ()).throw(TimeoutError('fixture'))):
                p.Provider(path,index,token)(messages=[])
        with self.assertRaises(Exception):p.run_phase(self.path,'initial-five',live=True,executor=execute)
        s=p.load_state(self.path)[0]
        self.assertEqual(s['arms'][0]['status'],'failed');self.assertEqual(s['arms'][1]['status'],'blocked')
        self.assertEqual(Decimal(s['reserved_cny']),p.followup.RESERVE)
        self.assertEqual(len(s['calls']),3);self.assertFalse(self.report()['quality_claim_allowed'])

    def test_last_safe_failure_before_checkpoint_fault_remains_progress(self):
        self.initialize()
        p.run_phase(self.path,'initial-five',live=True,executor=self.success)
        def hook(point):
            if point=='before_checkpoint':raise OSError('checkpoint absent')
        with self.assertRaises(OSError):
            p.run_phase(self.path,'remaining-fifteen',live=True,executor=self.executor({39:'old'}),hook=hook)
        q=self.report()
        self.assertEqual(q['paired_outcomes']['terminal_pairs'],20)
        self.assertFalse(q['quality_claim_allowed']);self.assertFalse(q['experiment_complete'])
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_checkpoint_cannot_accept_nonterminal_or_unverified_failed(self):
        for status in ['pending','running','blocked','failed']:
            state={'arms':[{'status':'completed','result_sha256':'0'*64},{'status':status}]}
            with self.subTest(status=status),self.assertRaises(RuntimeError):
                p.checkpoint_for(state,{'name':'x','start':0,'end':2})

    def test_summary_requires_new_policy_and_verified_failures(self):
        labels=self.answers()
        rows=[{'source_id':s,'suppress_repeats':a,'mode':'live','status':'failed','terminal_failure_verified':True}
            for s in self.plan['sources'] for a in self.plan['arms']]
        self.assertTrue(summarize(self.plan,rows,labels,execution_mode='live',experiment_complete=True)['quality_claim_allowed'])
        for status in ['pending','running','blocked']:
            bad=deepcopy(rows);bad[-1]['status']=status
            self.assertFalse(summarize(self.plan,bad,labels,execution_mode='live',experiment_complete=True)['quality_claim_allowed'])
        old=deepcopy(self.plan);old['policy']='locagent-phased-v2'
        self.assertFalse(summarize(old,rows,labels,execution_mode='live',experiment_complete=True)['quality_claim_allowed'])
        bad=deepcopy(rows);bad[-1].pop('terminal_failure_verified')
        self.assertFalse(summarize(self.plan,bad,labels,execution_mode='live',experiment_complete=True)['quality_claim_allowed'])

    def test_synthetic_bad_json_not_truncated_and_parser_never_repairs(self):
        import networkx as nx
        from litellm import ModelResponse
        from util.localizer import GraphLocalizer
        from util.localization_contract import LocalizationOptions,LocalizationRequest
        graph=nx.MultiDiGraph();graph.add_node('.',type='directory');graph.add_node('demo.py',type='file',code='def f(): pass')
        graph.add_node('demo.py:f',type='function',code='def f(): pass',start_line=1,end_line=1)
        graph.add_edge('.','demo.py',type='contains');graph.add_edge('demo.py','demo.py:f',type='contains')
        for fixture in ['old','replacement']:
            raw=json.loads(protocol_body(fixture,1))
            self.assertEqual(raw['usage']['completion_tokens'],142)
            self.assertEqual(raw['choices'][0]['finish_reason'],'tool_calls')
            response=ModelResponse(**raw);calls=[]
            def provider(**kw):calls.append(kw);return response
            with patch('util.localizer._execute_tool',side_effect=AssertionError('no partial dispatch')) as dispatch:
                with self.assertRaises(LocalizationError) as exc:
                    GraphLocalizer.from_graph(graph,provider=provider,model_name='offline',
                        options=LocalizationOptions(3,False,'bounded-v1')).localize(
                            LocalizationRequest('demo__demo-1','demo/demo','a'*40,'Find f'))
                self.assertEqual(exc.exception.to_dict(),p.PROTOCOL_ERROR);dispatch.assert_not_called()
            self.assertEqual(len(calls),1)
            self.assertEqual(response.choices[0].message.tool_calls[-1].function.arguments,
                raw['choices'][0]['message']['tool_calls'][-1]['function']['arguments'])

    def test_json_example_preserves_schema_types_and_limits(self):
        from util.runtime.content_tools import SearchRepoTool
        spec=SearchRepoTool['function']
        examples=[json.loads(line) for line in spec['description'].splitlines() if line.startswith('{')]
        self.assertIn({'line_nums':[10,15],'file_path_or_pattern':'src/example.py'},examples)
        prop=spec['parameters']['properties']
        self.assertEqual(prop['line_nums']['type'],'array');self.assertEqual(prop['line_nums']['items'],{'type':'integer'})
        self.assertEqual(self.plan['config']['max_output_tokens'],512)
        self.assertEqual(self.plan['config']['max_calls'],3)
        self.assertEqual(self.plan['transport']['retries'],0)

    def test_v2_historical_shaped_plan_cannot_initialize_or_validate(self):
        old=deepcopy(self.plan);old['version']=2;old['policy']='locagent-phased-v2';old.pop('arm_failure_policy')
        with self.assertRaises(ValueError):p.validate_plan(old)
        old_approval=self.approve('old-shape',old)
        with self.assertRaises(ValueError):p.initialize(self.path,old,live=True,approval_id=old_approval)
        self.assertFalse(self.path.exists())

    def test_256_independent_safety_combinations_fail_closed(self):
        oracle=continuation_oracle()
        self.initialize()
        with p.budget.ledger_lock(self.path):
            state=p.load_state(self.path)[0]
            state.update(status='running',active_run={'token':'matrix','parent_pid':os.getpid(),'phase':'initial-five','arm_index':0})
            state['arms'][0]['status']='running';p.commit(self.path,state)
        self.publish_failure(self.path,0,'matrix')
        popen=subprocess.Popen
        with patch.object(p.subprocess,'Popen',side_effect=lambda *args,**kw:popen([sys.executable,'-c','raise SystemExit(1)'],**kw)):
            with self.assertRaises(p.ReapedProtocolError) as caught:p.child_executor(self.path,0,'matrix')
        proof=deepcopy(caught.exception.exit_proof)
        baseline=p.read_json(self.path);owner=p.read_json(p.owner_path(self.plan,'live'))
        bodypath=p.response_store.directory(self.path)/baseline['calls'][-1]['raw_body_ref']['file'];body=bodypath.read_bytes()
        allowed=0
        for row in oracle:
            c=row['conditions'];state=deepcopy(baseline);exit_proof=deepcopy(proof)
            bodypath.write_bytes(body)
            if not c['allowlisted_protocol_error']:state['arms'][0]['localization_error']={'code':'model_error','message':'other'}
            if not c['all_arm_calls_settled']:state['calls'][0]['status']='raw_received'
            if not c['raw_evidence_valid_and_durable']:bodypath.write_bytes(b'corrupt fixture')
            if not c['failure_evidence_valid_and_durable']:state['arms'][0].pop('localization_error',None)
            if not c['child_exit_confirmed']:exit_proof['process_group_empty']=False
            if not c['ownership_fence_current']:state['active_run']['token']='stale'
            if not c['no_concurrent_executor']:state['arms'][1]['status']='running'
            if not c['no_unsettled_calls_global']:
                identity=p.arms_for(self.plan)[1];state['arms'][1]['status']='running'
                state['calls'].append({'index':2,'arm_index':1,'ordinal':0,'source_id':identity['source_id'],'arm':identity['arm'],
                    'status':'reserved','reservation_cny':str(p.followup.RESERVE),'request_sha256':'0'*64})
            state['spent_cny'],state['reserved_cny']=map(str,p.totals(state))
            p.budget.save(self.path,state)
            marker=deepcopy(owner);marker.update(state_sha256=digest(canonical(state)))
            p.budget.save(p.owner_path(self.plan,'live'),marker)
            exc=p.ReapedProtocolError(0,'matrix',exit_proof)
            with self.subTest(conditions=c),p.phase_lock(self.path):
                if row['may_continue']:
                    p.complete_protocol_failure(self.path,0,'matrix',exc,.01)
                    self.assertEqual(p.load_state(self.path)[0]['arms'][0]['status'],'failed');allowed+=1
                else:
                    with self.assertRaises((RuntimeError,ValueError)):
                        p.complete_protocol_failure(self.path,0,'matrix',exc,.01)
                self.assertEqual(len(p.read_json(self.path)['calls']),len(state['calls']))
        self.assertEqual(len(oracle),256);self.assertEqual(allowed,1)

    def test_actual_parent_crash_after_safe_failure_never_replays(self):
        import multiprocessing as mp
        for point in ['protocol_failure_committed','next_arm_claimed']:
            with self.subTest(point=point),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                self.path=Path(tmp)/'ledger.json';self.plan=p.expected_plan('new20','crash-'+point,'live')
                self.approval=self.approve('crash-'+point);self.initialize()
                def run():
                    def hook(name):
                        if name==point or (point=='next_arm_claimed' and name=='arm_claimed'
                                and p.read_json(self.path)['active_run']['arm_index']==1):os._exit(91)
                    p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}),hook=hook)
                child=mp.get_context('fork').Process(target=run);child.start();child.join(30)
                if child.is_alive():child.kill();child.join();self.fail('Fixture parent did not exit')
                self.assertEqual(child.exitcode,91)
                self.assertEqual(len(p.read_json(self.path)['calls']),2)
                self.assertFalse(p.audit_recovery(self.path)['recoverable'])
                self.assertEqual(p.load_state(self.path)[0]['arms'][0]['status'],'failed')
                with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)

    def test_checkpoint_owner_partial_write_with_failure_needs_explicit_audit(self):
        self.initialize();original=p.budget.save
        def write(path,value):
            if Path(path)==p.owner_path(self.plan,'live') and p.read_json(self.path)['next_phase']==1:
                raise OSError('checkpoint owner write')
            return original(path,value)
        with patch.object(p.budget,'save',side_effect=write),self.assertRaises(OSError):
            p.run_phase(self.path,'initial-five',live=True,executor=self.executor({0:'old'}))
        with self.assertRaises(RuntimeError):self.report()
        self.assertTrue(p.audit_recovery(self.path)['recoverable'])
        q=self.report();self.assertFalse(q['quality_claim_allowed'])
        self.assertEqual(q['paired_outcomes']['terminal_pairs'],5)
        self.assertEqual(len(p.load_state(self.path)[0]['calls']),29)
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',live=True,executor=self.success)
