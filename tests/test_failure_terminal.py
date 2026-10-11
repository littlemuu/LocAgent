
"""Offline-only failures; never load keys or reuse real spending authorizations."""
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from locagent_service import phased as p
from locagent_service.evaluate import summarize
from locagent_service.offline import offline_engine
from locagent_service.sources import canonical
from util.localization_contract import LocalizationError,ErrorCode,LocalizationOptions,LocalizationRequest
from util.localizer import GraphLocalizer
import test_phased as fixtures
from test_phased import fake_executor

def setUpModule():
    global guard
    guard=offline_engine();guard.__enter__()

def tearDownModule():
    guard.__exit__(None,None,None)

class FailureRepairTests(unittest.TestCase):
    setUp=fixtures.PhasedTests.setUp
    initialize=fixtures.PhasedTests.initialize
    claim=fixtures.PhasedTests.claim

    def answers(self):
        return {s:{'files':['fixture.py'],'entities':['fixture.py:f']
            if s in self.plan['function_applicable_sources'] else []} for s in self.plan['sources']}

    def summary(self):
        with patch.object(p,'check_labels',return_value=self.answers()):
            return p.summary(self.path,'unused')

    def test_malformed_arguments_settled_failure_no_retry(self):
        self.initialize()
        sent=[]
        def executor(path,index,token):
            import networkx as nx
            graph=nx.MultiDiGraph();graph.add_node('.',type='directory')
            graph.add_node('demo.py',type='file',code='def f(): pass')
            graph.add_node('demo.py:f',type='function',code='def f(): pass',start_line=1,end_line=1)
            graph.add_edge('.','demo.py',type='contains');graph.add_edge('demo.py','demo.py:f',type='contains')
            def raw(ordinal,**kw):
                sent.append(ordinal)
                value=json.loads(p.scripted_raw(ordinal))
                value['choices'][0]['message']['tool_calls'][0]['function'].update(
                    name='search_code_snippets',arguments='{"line_nums": 1500, 1520}')
                return canonical(value)
            provider=p.Provider(path,index,token,raw_completion=raw)
            GraphLocalizer.from_graph(graph,provider=provider,model_name='offline',
                options=LocalizationOptions(3,False,'bounded-v1')).localize(
                LocalizationRequest('demo__demo-1','demo/demo','a'*40,'Find render'))
        with self.assertRaises(LocalizationError) as error:
            p.run_phase(self.path,'initial-five',executor=executor)
        self.assertEqual(error.exception.to_dict(),{
            'code':'invalid_response','message':'Tool arguments must be a valid JSON object'})
        s,_,_=p.load_state(self.path)
        self.assertEqual(sent,[0]);self.assertEqual(s['status'],'halted');self.assertIsNone(s['active_run'])
        self.assertEqual(s['arms'][0]['status'],'failed')
        self.assertEqual(s['arms'][0]['failure']['code'],'invalid_response')
        self.assertEqual(s['calls'][0]['status'],'settled');self.assertEqual(s['reserved_cny'],'0.000000')
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',executor=executor)
        self.assertEqual(sent,[0])
        q=self.summary()
        self.assertEqual(q['arms']['false']['failed'],1)
        self.assertEqual(q['arms']['false']['not_started'],19)
        self.assertEqual(q['arms']['false']['completed_result_seconds'],0)
        self.assertGreater(q['arms']['false']['recorded_attempt_seconds'],0)
        self.assertGreater(q['timing']['phase_wall_seconds'],0)

    def test_known_failure_after_two_calls_retains_cost_and_fixed_na(self):
        self.initialize()
        def executor(path,index,token):
            provider=p.Provider(path,index,token)
            provider(messages=[]);provider(messages=[{'role':'user','content':'step2'}])
            raise LocalizationError(ErrorCode.INVALID_RESPONSE,'Tool arguments must be a valid JSON object')
        with self.assertRaises(LocalizationError):p.run_phase(self.path,'initial-five',executor=executor)
        s,_,_=p.load_state(self.path)
        self.assertEqual(len(s['calls']),2);self.assertEqual(Decimal(s['spent_cny']),Decimal('0.000560'))
        self.assertEqual(self.summary()['arms']['false']['metric_denominators'],{'files':20,'functions':18})
        self.assertEqual(self.summary()['arms']['false']['function_not_applicable'],2)

    def test_transport_unknown_is_blocked_and_never_released(self):
        self.initialize()
        def executor(path,index,token):
            p.Provider(path,index,token,raw_completion=lambda *a,**k:(_ for _ in ()).throw(TimeoutError()))(messages=[])
        with self.assertRaises(TimeoutError):p.run_phase(self.path,'initial-five',executor=executor)
        s,_,_=p.load_state(self.path)
        self.assertEqual(s['arms'][0]['status'],'blocked')
        self.assertEqual(Decimal(s['reserved_cny']),p.followup.RESERVE)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(Decimal(p.load_state(self.path)[0]['reserved_cny']),p.followup.RESERVE)

    def test_launch_failure_terminal_without_call(self):
        self.initialize()
        with patch.object(p.subprocess,'Popen',side_effect=OSError('launch')):
            with self.assertRaises(OSError):p.run_phase(self.path,'initial-five')
        s,_,_=p.load_state(self.path)
        self.assertEqual(s['calls'],[]);self.assertEqual(s['arms'][0]['status'],'failed')
        self.assertEqual(s['arms'][0]['failure']['code'],'executor_error')

    def test_real_child_nonzero_exit_is_terminal(self):
        self.initialize()
        popen=subprocess.Popen
        def child(*a,**kw):
            return popen([sys.executable,'-c','import os; os._exit(23)'],**kw)
        with patch.object(p.subprocess,'Popen',side_effect=child):
            with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five')
        s,_,_=p.load_state(self.path)
        self.assertEqual(s['status'],'halted');self.assertIsNone(s['active_run'])
        self.assertEqual(s['arms'][0]['status'],'failed')

    def test_timeout_and_keyboard_interrupt_terminal(self):
        for n,exc in enumerate([subprocess.TimeoutExpired('child',300),KeyboardInterrupt()]):
            path=self.root/f'{n}.json';p.initialize(path,p.expected_plan('new20','interrupt'+str(n)))
            def executor(*a):raise exc
            with self.assertRaises(type(exc)):p.run_phase(path,'initial-five',executor=executor)
            s,_,_=p.load_state(path)
            self.assertEqual(s['status'],'halted');self.assertIsNone(s['active_run'])
            self.assertEqual(s['arms'][0]['failure']['code'],'child_timeout' if n==0 else 'interrupted')

    def test_child_localization_error_survives_parent_boundary(self):
        self.initialize();popen=subprocess.Popen
        def child(*args,**kw):
            path=args[0][args[0].index('--ledger')+1]
            token=args[0][args[0].index('--run-token')+1]
            p.fail_localization(Path(path),0,token,LocalizationError(ErrorCode.INVALID_RESPONSE,'Tool arguments must be a valid JSON object'))
            return popen([sys.executable,'-c','raise SystemExit(1)'],**kw)
        with patch.object(p.subprocess,'Popen',side_effect=child):
            with self.assertRaises(LocalizationError):p.run_phase(self.path,'initial-five')
        self.assertEqual(p.load_state(self.path)[0]['arms'][0]['failure']['code'],'invalid_response')

    def test_fenced_failure_writer_cannot_stop_replacement(self):
        self.claim()
        before=self.path.read_bytes()
        p.halt_failed_run(self.path,'stale',RuntimeError(),1,1)
        self.assertEqual(self.path.read_bytes(),before)
        with self.assertRaises(RuntimeError):
            p.fail_localization(self.path,0,'stale',LocalizationError(ErrorCode.INVALID_RESPONSE,'safe'))
        self.assertEqual(self.path.read_bytes(),before)

    def test_interrupted_duration_unknown_until_terminal_measurement(self):
        self.claim()
        q=self.summary()
        self.assertIsNone(q['timing']['phase_wall_seconds'])
        self.assertTrue(q['timing']['duration_unknown'])
        self.assertEqual(q['arms']['false']['running'],1)
        self.assertEqual(q['arms']['false']['attempt_duration_unknown_count'],1)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertIsNone(self.summary()['timing']['phase_wall_seconds'])

    def test_complete_and_failed_durations_separate(self):
        self.initialize()
        def executor(path,index,token):
            if index==0:return fake_executor(path,index,token)
            raise RuntimeError('fail next arm')
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',executor=executor)
        q=self.summary()
        self.assertEqual(q['arms']['false']['completed_result_seconds'],.01)
        self.assertEqual(q['arms']['true']['completed_result_seconds'],0)
        self.assertGreater(q['arms']['true']['recorded_attempt_seconds'],0)
        self.assertGreater(q['timing']['phase_wall_seconds'],0)

    def test_zero_record_explicit_live_mode_preserves_fixed_zero_and_na(self):
        q=summarize(self.plan,[],self.answers(),execution_mode='live')
        self.assertEqual(q['mode'],'live');self.assertFalse(q['quality_claim_allowed'])
        for a in q['arms'].values():
            self.assertEqual(a['metric_denominators'],{'files':20,'functions':18})
            self.assertEqual(a['valid_finish_count'],0)
            self.assertTrue(all(v==0 for v in a['metrics'].values()))
            self.assertEqual(a['not_started'],20)

    def test_simulation_never_live_and_mode_mismatch_rejected(self):
        q=summarize(self.plan,[],self.answers(),execution_mode='simulation')
        self.assertEqual(q['mode'],'simulation');self.assertFalse(q['quality_claim_allowed'])
        self.assertIsNone(q['arms']['false']['valid_finish_count'])
        row={'source_id':self.plan['sources'][0],'suppress_repeats':False,'status':'failed','mode':'offline'}
        with self.assertRaises(ValueError):summarize(self.plan,[row],self.answers(),execution_mode='live')

    def test_partial_live_failures_cannot_supply_forensic_success(self):
        source=self.plan['sources'][0]
        row={'source_id':source,'suppress_repeats':False,'status':'failed','mode':'live',
             'elapsed_seconds':2.5,'attempt_elapsed_seconds':2.5,'result':{'found_files':['fixture.py'],'found_entities':['fixture.py:f']}}
        q=summarize(self.plan,[row],self.answers(),execution_mode='live')
        a=q['arms']['false']
        self.assertEqual(a['failed'],1);self.assertEqual(a['not_started'],19)
        self.assertEqual(a['elapsed_seconds'],0);self.assertEqual(a['recorded_attempt_seconds'],2.5)
        self.assertTrue(all(v==0 for v in a['metrics'].values()))

    def test_all_nonobject_arguments_and_mixed_batch_have_no_tool_effects(self):
        import networkx as nx
        from litellm import ModelResponse
        graph=nx.MultiDiGraph()
        graph.add_node('.',type='directory');graph.add_node('demo.py',type='file',code='def f(): pass')
        graph.add_node('demo.py:f',type='function',code='def f(): pass',start_line=1,end_line=1)
        graph.add_edge('.','demo.py',type='contains');graph.add_edge('demo.py','demo.py:f',type='contains')
        for text in ['[]','null','"text"','3','true','{"line_nums": 1500, 1520}']:
            response=json.loads(p.scripted_raw(0))
            good=deepcopy(response['choices'][0]['message']['tool_calls'][0])
            bad=deepcopy(good);bad['id']='bad';bad['function'].update(name='search_code_snippets',arguments=text)
            response['choices'][0]['message']['tool_calls']=[good,bad]
            sent=[]
            def provider(**kw):sent.append(kw);return ModelResponse(**response)
            with patch('util.localizer._execute_tool',side_effect=AssertionError('No partial dispatch')) as dispatch:
                with self.subTest(text=text),self.assertRaises(LocalizationError):
                    GraphLocalizer.from_graph(graph,provider=provider,model_name='offline',
                        options=LocalizationOptions(3,False,'bounded-v1')).localize(
                            LocalizationRequest('demo__demo-1','demo/demo','a'*40,'Find f'))
                dispatch.assert_not_called()
                self.assertEqual(len(sent),1)

    def test_terminal_ledger_and_owner_write_faults_fail_closed(self):
        for boundary in ['ledger','owner']:
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                path=Path(tmp)/'l.json';plan=p.expected_plan('new20','failure-'+boundary)
                p.initialize(path,plan);original=p.budget.save
                def save(dest,value):
                    if boundary=='ledger' and Path(dest)==path and value.get('status')=='halted':
                        raise OSError('terminal ledger write')
                    if boundary=='owner' and Path(dest)==p.owner_path(plan) and p.read_json(path)['status']=='halted':
                        raise OSError('terminal owner write')
                    original(dest,value)
                def executor(path,index,token):
                    p.Provider(path,index,token)(messages=[])
                    raise LocalizationError(ErrorCode.INVALID_RESPONSE,'Tool arguments must be a valid JSON object')
                with patch.object(p.budget,'save',side_effect=save):
                    with self.assertRaises(LocalizationError) as exc:p.run_phase(path,'initial-five',executor=executor)
                self.assertTrue(any('could not be persisted' in n for n in exc.exception.__notes__))
                if boundary=='owner':
                    with self.assertRaises(RuntimeError):p.load_state(path)
                audit=p.audit_recovery(path)
                self.assertFalse(audit['recoverable'])
                state,_,_=p.load_state(path)
                self.assertEqual(state['status'],'halted');self.assertEqual(len(state['calls']),1)
                self.assertEqual(Decimal(state['spent_cny']),Decimal('.00028'))
                with self.assertRaises(RuntimeError):p.run_phase(path,'initial-five',executor=executor)

    def test_child_error_publication_partial_write_never_retries(self):
        for boundary in ['ledger','owner']:
            with self.subTest(boundary=boundary),tempfile.TemporaryDirectory(dir=self.root) as tmp:
                path=Path(tmp)/'l.json';plan=p.expected_plan('new20','child-error-'+boundary)
                p.initialize(path,plan);original=p.budget.save
                def save(dest,value):
                    if boundary=='ledger' and Path(dest)==path and value['arms'][0].get('localization_error'):
                        raise OSError('child failure ledger')
                    if boundary=='owner' and Path(dest)==p.owner_path(plan) and p.read_json(path)['arms'][0].get('localization_error'):
                        raise OSError('child failure owner')
                    original(dest,value)
                def executor(path,index,token):
                    p.Provider(path,index,token)(messages=[])
                    p.fail_localization(path,index,token,LocalizationError(ErrorCode.INVALID_RESPONSE,'safe'))
                    raise AssertionError('Should not reach')
                with patch.object(p.budget,'save',side_effect=save):
                    with self.assertRaises(OSError):p.run_phase(path,'initial-five',executor=executor)
                self.assertFalse(p.audit_recovery(path)['recoverable'])
                state,_,_=p.load_state(path)
                self.assertEqual(state['status'],'halted');self.assertEqual(len(state['calls']),1)

    def test_uncertain_child_exit_does_not_signal_or_resume(self):
        self.initialize()
        from unittest.mock import Mock
        child=Mock();child.pid=99999999
        child.wait.side_effect=subprocess.TimeoutExpired('child',300)
        child.poll.side_effect=PermissionError('cannot inspect')
        with patch.object(p.subprocess,'Popen',return_value=child),patch.object(p.os,'killpg') as kill:
            with self.assertRaises(p.ExecutorExitUnknown):p.run_phase(self.path,'initial-five')
            kill.assert_not_called()
        state,_,_=p.load_state(self.path)
        self.assertEqual(state['arms'][0]['status'],'blocked')
        self.assertEqual(state['arms'][0]['failure']['code'],'executor_exit_unverified')
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_actual_timeout_cleanup_reaps_owned_child(self):
        self.initialize();popen=subprocess.Popen;children=[]
        class TimedChild:
            def __init__(self,child):self.child=child;self.pid=child.pid;self.first=True
            def wait(self,timeout=None):
                if self.first:self.first=False;raise subprocess.TimeoutExpired('fixture',300)
                return self.child.wait(timeout=timeout)
            def poll(self):return self.child.poll()
        def launch(*a,**kw):
            child=popen([sys.executable,'-c','import time; time.sleep(60)'],**kw)
            children.append(child);return TimedChild(child)
        try:
            with patch.object(p.subprocess,'Popen',side_effect=launch):
                with self.assertRaises(subprocess.TimeoutExpired):p.run_phase(self.path,'initial-five')
            self.assertIsNotNone(children[0].poll())
            self.assertEqual(p.load_state(self.path)[0]['arms'][0]['failure']['code'],'child_timeout')
        finally:
            for child in children:
                if child.poll() is None:child.kill()
                child.wait()

    def test_stale_success_artifact_cannot_replace_known_failure(self):
        self.initialize()
        def executor(path,index,token):
            # Durable valid result then a later wrapper exception: completed result remains
            # a completed prefix, but phase is halted and cannot acquire a checkpoint.
            fake_executor(path,index,token)
            raise RuntimeError('post-result wrapper failed')
        with self.assertRaises(RuntimeError):p.run_phase(self.path,'initial-five',executor=executor)
        state,_,_=p.load_state(self.path)
        self.assertEqual(state['status'],'halted')
        self.assertEqual(state['arms'][0]['status'],'completed')
        self.assertEqual(state['checkpoints'],[])
        # Audit must not infer that a generic halted executor error is permission to resume.
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])

    def test_uncommitted_result_artifact_cannot_be_promoted_after_failure(self):
        self.initialize()
        def executor(path,index,token):
            def fault(point):
                if point=='result_saved':raise OSError('after result publication')
            p.finish_arm(path,index,token,fixtures.fake_result(path,index),.1,hook=fault)
        with self.assertRaises(OSError):p.run_phase(self.path,'initial-five',executor=executor)
        artifact=p.result_path(self.path,0).read_bytes()
        state,_,_=p.load_state(self.path)
        self.assertEqual(state['arms'][0]['status'],'failed')
        self.assertEqual(self.summary()['arms']['false']['completed'],0)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(p.result_path(self.path,0).read_bytes(),artifact)

    def test_missing_completed_duration_is_unknown_not_zero(self):
        row={'source_id':self.plan['sources'][0],'suppress_repeats':False,
             'status':'completed','mode':'live','result':{}}
        q=summarize(self.plan,[row],self.answers(),execution_mode='live')['arms']['false']
        self.assertIsNone(q['completed_result_seconds']);self.assertIsNone(q['elapsed_seconds'])
        self.assertEqual(q['recorded_attempt_seconds'],0) # Explicit known subtotal only.
        self.assertEqual(q['attempt_duration_unknown_count'],1)

    def test_missing_active_run_does_not_prove_executor_exit(self):
        self.claim()
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path);state['active_run']=None;p.commit(self.path,state)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertEqual(p.load_state(self.path)[0]['arms'][0]['status'],'blocked')

    def test_failure_writer_rejects_halted_legacy_active_run(self):
        self.claim()
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path);state['status']='halted';p.commit(self.path,state)
        before=self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            p.fail_localization(self.path,0,'run',LocalizationError(ErrorCode.INVALID_RESPONSE,'safe'))
        self.assertEqual(self.path.read_bytes(),before)
