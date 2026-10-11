
"""Quality conclusions require a finished experiment, not just complete result files."""
from pathlib import Path
import unittest
from unittest.mock import patch
import httpx
import test_phased_http as fixtures
from locagent_service import phased as p
from locagent_service.evaluate import summarize
from util.localization_contract import LocalizationResult,ResultStatus

class QualityCheckpointTests(unittest.TestCase):
    setUp=fixtures.HTTPAdmissionTests.setUp
    approve=fixtures.HTTPAdmissionTests.approve
    initialize=fixtures.HTTPAdmissionTests.initialize
    transport=fixtures.HTTPAdmissionTests.transport

    def setup_old5(self):
        self.plan=p.expected_plan('regression5','quality-checkpoint','live')
        self.approval=self.approve('quality-checkpoint-approval')
        self.initialize()

    def execute(self,path,index,token):
        provider=p.Provider(path,index,token)
        for ordinal in range(3):
            with self.transport(lambda request:httpx.Response(
                    200,content=p.scripted_raw(ordinal),request=request)):
                provider(messages=[{'role':'user','content':str(ordinal)}])
        result=LocalizationResult(p.arms_for(self.plan)[index]['instance_id'],
            ResultStatus.SUCCESS,found_files=['fixture.py'],found_entities=['fixture.py:f'],
            iterations=3,diagnostics={'termination_reason':'finished'}).to_dict()
        p.finish_arm(path,index,token,result,.01)

    def report(self):
        answers={s:{'files':['fixture.py'],'entities':['fixture.py:f']} for s in self.plan['sources']}
        with patch.object(p,'check_labels',return_value=answers):
            return p.summary(self.path,'synthetic')

    def assert_progress(self):
        state=p.load_state(self.path)[0];report=self.report()
        self.assertEqual(state['status'],'halted')
        self.assertEqual(state['next_phase'],0);self.assertEqual(state['checkpoints'],[])
        self.assertEqual(len(state['calls']),30)
        self.assertTrue(all(a['status']=='completed' for a in state['arms']))
        self.assertFalse(report['quality_claim_allowed'])
        self.assertEqual(report['metrics_scope'],'progress')
        for arm in report['arms'].values():
            self.assertEqual(arm['completed'],5)
            self.assertTrue(all(score==1 for score in arm['metrics'].values()))
            self.assertEqual(arm['valid_finish_count'],5)
        self.assertFalse(p.audit_recovery(self.path)['recoverable'])
        self.assertFalse(self.report()['quality_claim_allowed'])

    def test_last_result_before_checkpoint_failure_only_reports_progress(self):
        self.setup_old5()
        def hook(point):
            if point=='before_checkpoint':raise OSError('checkpoint not begun')
        with self.assertRaises(OSError):
            p.run_phase(self.path,'regression-five',live=True,executor=self.execute,hook=hook)
        self.assert_progress()

    def test_checkpoint_ledger_write_failure_only_reports_progress(self):
        self.setup_old5();save=p.budget.save
        def fail(path,value):
            if Path(path)==self.path and value.get('status')=='complete':
                raise OSError('checkpoint ledger write')
            return save(path,value)
        with patch.object(p.budget,'save',side_effect=fail):
            with self.assertRaises(OSError):
                p.run_phase(self.path,'regression-five',live=True,executor=self.execute)
        self.assert_progress()

    def test_normal_complete_checkpoint_allows_quality(self):
        self.setup_old5()
        p.run_phase(self.path,'regression-five',live=True,executor=self.execute)
        report=self.report()
        self.assertTrue(report['quality_claim_allowed'])
        self.assertEqual(report['metrics_scope'],'completed_experiment')
        self.assertEqual(report['stage_status'],'complete')
        with p.budget.ledger_lock(self.path):
            state=p.load_state(self.path)[0]
            state['terminal_failure']={'code':'executor_error','error_type':'RuntimeError'}
            p.commit(self.path,state)
        self.assertFalse(self.report()['quality_claim_allowed'])
        self.assertEqual(self.report()['metrics_scope'],'progress')

    def test_checkpoint_owner_write_fault_refuses_summary_until_explicit_audit(self):
        self.setup_old5();save=p.budget.save
        def fail(path,value):
            if Path(path)==p.owner_path(self.plan,'live') and p.read_json(self.path)['status']=='complete':
                raise OSError('checkpoint owner write')
            return save(path,value)
        with patch.object(p.budget,'save',side_effect=fail):
            with self.assertRaises(OSError):
                p.run_phase(self.path,'regression-five',live=True,executor=self.execute)
        with self.assertRaises(RuntimeError):self.report()
        self.assertTrue(p.audit_recovery(self.path)['recoverable'])
        self.assertTrue(self.report()['quality_claim_allowed'])

    def test_generic_summary_requires_explicit_completion_evidence(self):
        plan={'sources':['s'],'arms':[False,True]}
        labels={'s':{'files':['f.py'],'entities':['f.py:f']}}
        rows=[{'source_id':'s','suppress_repeats':arm,'mode':'live','status':'completed',
               'elapsed_seconds':1,'result':{'found_files':['f.py'],'found_entities':['f.py:f']}}
              for arm in plan['arms']]
        report=summarize(plan,rows,labels,execution_mode='live')
        self.assertFalse(report['quality_claim_allowed']);self.assertEqual(report['metrics_scope'],'progress')
        self.assertTrue(summarize(plan,rows,labels,execution_mode='live',experiment_complete=True)['quality_claim_allowed'])
        with self.assertRaises(ValueError):
            summarize(plan,rows,labels,execution_mode='live',experiment_complete='complete')
