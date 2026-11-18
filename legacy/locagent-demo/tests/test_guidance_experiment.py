"""Synthetic axis, subprocess, scoring and quota tests; never provider traffic."""
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from locagent_service import phased as p, guidance_experiment as g
from locagent_service.phased_admission import binding, proposal, validate_record
from locagent_service.sources import canonical, digest
from locagent_service.evaluate import summarize
from locagent_service.offline import offline_engine
from phased_test_support import synthetic_cohorts
from test_phased import fake_executor, fake_result


def setUpModule():
    global guard
    guard=offline_engine();guard.__enter__()


def tearDownModule():
    guard.__exit__(None,None,None)


def synthetic_spec():
    spec=synthetic_cohorts()['new20']
    spec['samples']=spec['samples'][:10]
    for i,s in enumerate(spec['samples']):
        s.update(instance_id=g.IDS[i],role='connectivity' if i<2 else 'primary',
                 arm_order=[True,False] if i==1 or i>=6 else [False,True])
    spec.update(comparison_axis='candidate_guidance',fixed_options={'suppress_repeats':False},
        limit_cny='5',phases=[{'name':'connectivity','start':0,'end':4},
                            {'name':'primary','start':4,'end':20}],
        function_applicable_sources=[s['source_id'] for s in spec['samples'][:9]])
    return spec


class GuidanceExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.spec=synthetic_spec()
        contexts=[
            patch.object(g,'load_spec',side_effect=lambda root:deepcopy(self.spec)),
            patch.object(p,'runtime_hashes',return_value={'synthetic':'0'*64}),
            patch.object(p,'verify_sources'),patch.object(p,'check_labels'),
            patch.object(p,'OWNERSHIP_ROOT',self.root/'owners')]
        for c in contexts:c.start();self.addCleanup(c.stop)
        self.plan=p.expected_plan(g.COHORT,'axis-unit')
        self.path=self.root/'ledger.json'
        self.answers={s['source_id']:{'files':['fixture.py'],
            'entities':['fixture.py:f'] if i<9 else []}
            for i,s in enumerate(self.spec['samples'])}

    def claim(self):
        p.initialize(self.path,self.plan)
        with p.budget.ledger_lock(self.path):
            state,_,_=p.load_state(self.path)
            state.update(status='running',active_run={'token':'run','arm_index':0,
                'parent_pid':os.getpid(),'phase':'connectivity'})
            state['arms'][0]['status']='running';p.commit(self.path,state)
        return p.Provider(self.path,0,'run')

    def test_plan_budget_order_and_binding_are_explicit(self):
        self.assertEqual(self.plan['max_calls'],60)
        self.assertEqual(self.plan['max_calls_per_arm'],3)
        self.assertEqual(self.plan['reservation_cny'],'2.101248')
        self.assertEqual(self.plan['config']['max_output_tokens'],512)
        self.assertEqual(sum(s['arm_order'][0] for s in self.plan['samples']),5)
        b=binding(self.plan)
        self.assertEqual(b['comparison_axis'],'candidate_guidance')
        self.assertEqual(b['fixed_options'],{'suppress_repeats':False})
        self.assertEqual(b['phase_roles'],['connectivity']*2+['primary']*8)

    def test_changed_axis_budget_order_or_fixed_option_rejected(self):
        for key,value in [('comparison_axis','suppress_repeats'),('limit_cny','8'),
                          ('fixed_options',{'suppress_repeats':True}),('max_calls',61)]:
            changed=deepcopy(self.plan);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):p.validate_plan(changed)

    def test_calls_results_and_two_phases_keep_axis(self):
        p.initialize(self.path,self.plan)
        p.run_phase(self.path,'connectivity',executor=fake_executor)
        first=p.read_json(self.path)
        final=p.run_phase(self.path,'primary',executor=fake_executor)
        self.assertEqual(final['calls'][:12],first['calls'])
        self.assertEqual(len(final['calls']),60)
        for c in final['calls']:
            self.assertIs(c['suppress_repeats'],False)
            self.assertIs(c['candidate_guidance'],c['arm'])
            self.assertEqual(c['comparison_axis'],'candidate_guidance')
        for i,identity in enumerate(p.arms_for(self.plan)):
            row=p.record_for(self.path,final,i)
            self.assertIs(row['suppress_repeats'],False)
            self.assertIs(row['candidate_guidance'],identity['arm'])

    def test_relabelled_call_or_returned_model_rejected(self):
        provider=self.claim();provider(messages=[])
        state=p.read_json(self.path)
        for key,value in [('candidate_guidance',True),('suppress_repeats',True),
                          ('comparison_axis','suppress_repeats'),('returned_model','forged')]:
            broken=deepcopy(state);broken['calls'][0][key]=value
            with self.subTest(key=key),self.assertRaises((RuntimeError,ValueError)):
                p.validate_state(self.path,broken)

    def test_unknown_call_keeps_full_reserve_and_cannot_replay(self):
        self.claim()
        transport=Mock(side_effect=OSError('synthetic unknown'))
        provider=p.Provider(self.path,0,'run',raw_completion=transport)
        with self.assertRaises(OSError):provider(messages=[])
        state=p.read_json(self.path)
        self.assertEqual(Decimal(state['reserved_cny']),Decimal('2.101248'))
        with self.assertRaises(RuntimeError):provider(messages=[])
        self.assertEqual(transport.call_count,1)

    def test_full_reserve_halts_before_exceeding_five(self):
        self.claim()
        def costly(ordinal,**kw):
            raw=json.loads(p.scripted_raw(ordinal))
            raw['usage']={'prompt_tokens':1048576,'completion_tokens':512,
                'total_tokens':1049088,'prompt_cache_hit_tokens':0,
                'prompt_cache_miss_tokens':1048576}
            return canonical(raw)
        transport=Mock(side_effect=costly)
        provider=p.Provider(self.path,0,'run',raw_completion=transport)
        provider(messages=[]);provider(messages=[])
        with self.assertRaises(RuntimeError):provider(messages=[])
        self.assertEqual(transport.call_count,2)
        self.assertEqual(p.read_json(self.path)['stop_reason'],'budget_exhausted')

    def test_scopes_and_na_denominators_are_separate(self):
        rows=[{'source_id':s,'candidate_guidance':a,'suppress_repeats':False,
               'comparison_axis':'candidate_guidance','mode':'live','status':'failed',
               'terminal_failure_verified':True,'elapsed_seconds':0}
              for s in self.plan['sources'] for a in [False,True]]
        report=summarize(self.plan,rows,self.answers,execution_mode='live',experiment_complete=True)
        self.assertFalse(report['quality_claim_allowed'])
        self.assertFalse(report['scoring_groups']['connectivity']['quality_claim_allowed'])
        self.assertTrue(report['scoring_groups']['primary']['quality_claim_allowed'])
        for arm in ['false','true']:
            self.assertIsNone(report['arms'][arm]['metrics']['files_recall_at_1'])
            self.assertEqual(report['scoring_groups']['connectivity']['arms'][arm]['metric_denominators'],{'files':2,'functions':2})
            self.assertEqual(report['scoring_groups']['primary']['arms'][arm]['metric_denominators'],{'files':8,'functions':7})
        rows[0]['suppress_repeats']=True
        with self.assertRaises(ValueError):summarize(self.plan,rows,self.answers)

    def test_offline_never_claims_quality(self):
        report=summarize(self.plan,[],self.answers,execution_mode='offline',experiment_complete=True)
        for group in report['scoring_groups'].values():
            self.assertFalse(group['quality_claim_allowed'])
            self.assertIsNone(group['arms']['true']['metrics']['files_recall_at_1'])

    def test_unapproved_proposal_and_old_binding_cannot_authorize(self):
        live=p.expected_plan(g.COHORT,'axis-unit','live')
        draft=proposal(live,'synthetic-only')
        self.assertFalse(draft['approved']);self.assertFalse(draft['independent_review_passed'])
        with self.assertRaises(ValueError):validate_record(live,draft)
        old={**live,'comparison_axis':'suppress_repeats'}
        self.assertNotEqual(binding(old),binding(live))

    def test_subprocess_passes_true_guidance_with_false_suppression(self):
        state={'plan':self.plan,'mode':'offline'}
        fake=Mock();fake.to_dict.return_value={}
        with patch.object(p.ctypes,'CDLL',return_value=Mock(prctl=Mock(return_value=0))), \
             patch.object(p,'load_state',return_value=(state,None,None)), \
             patch.object(p,'load_manifest',return_value=({'task':{'problem_statement':'demo'}},None)), \
             patch('locagent_service.sources.localize_prepared',return_value=fake) as localize, \
             patch.object(p,'finish_arm'):
            p.execute_arm(self.path,1,'run',os.getppid())
        request=localize.call_args.args[0]
        self.assertIs(request.options.suppress_repeats,False)
        self.assertIs(localize.call_args.kwargs['candidate_guidance'],True)
