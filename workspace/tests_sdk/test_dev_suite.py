import copy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from experiments.dev_compare.suite import BatchGuard, candidate, score_localization, main, replay


class DevSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest={'transport':'offline_only','authorization':'not_granted',
                       'suite_budget_micro_cny':102_000_000,
                       'cases':[{'id':'d'+str(i)} for i in range(6)]}

    def guard(self):return BatchGuard.create(self.root/'suite.sqlite',self.manifest)

    def settled(self,cost=100):
        return {'simulation':True,'halted':False,'reserved_micro_cny':0,
                'spent_upper_micro_cny':cost,'calls':[{'status':'settled'}]*8}

    def test_six_pairs_only_and_total_cap(self):
        guard=self.guard()
        for c in self.manifest['cases']:
            guard.start(c['id']);guard.finish(c['id'],self.settled(17_000_000))
        with sqlite3.connect(guard.path) as db:
            self.assertEqual(db.execute('SELECT SUM(cost),SUM(requests) FROM pairs').fetchone(),(102_000_000,48))
        with self.assertRaises(ValueError):guard.start('extra')
        with self.assertRaises(FileExistsError):self.guard()

    def test_pending_duplicate_restart_and_order_blocked(self):
        guard=self.guard()
        with self.assertRaises(ValueError):guard.start('d1')
        guard.start('d0')
        reopened=BatchGuard(guard.path,self.manifest)
        for identifier in ('d0','d1'):
            with self.assertRaises(RuntimeError):reopened.start(identifier)

    def test_unknown_settlement_halts_suite_no_next_pair(self):
        guard=self.guard();guard.start('d0')
        summary=self.settled();summary['reserved_micro_cny']=2_105_344
        with self.assertRaises(RuntimeError):guard.finish('d0',summary)
        with self.assertRaises(RuntimeError):guard.start('d1')

    def test_manifest_binding_and_global_budget_checked(self):
        guard=self.guard()
        changed=copy.deepcopy(self.manifest);changed['suite_budget_micro_cny']=1
        with self.assertRaises(ValueError):BatchGuard(guard.path,changed).start('d0')
        tiny=copy.deepcopy(self.manifest);tiny['suite_budget_micro_cny']=16_999_999
        other=BatchGuard.create(self.root/'tiny.sqlite',tiny)
        with self.assertRaises(RuntimeError):other.start('d0')

    def test_live_state_or_live_cli_cannot_load_transport(self):
        changed=dict(self.manifest,transport='live')
        with self.assertRaises(PermissionError):BatchGuard.create(self.root/'live.sqlite',changed)
        with patch('sys.argv',['suite','replay','--live']),patch('experiments.dev_compare.suite.replay') as runner:
            with self.assertRaises(PermissionError):main()
            runner.assert_not_called()

    def test_exact_scoring_penalizes_wrong_paths_and_no_finish(self):
        rubric={'gold_files':['a.py','b.py'],'gold_entities':['a.py:f']}
        result={'status':'completed','answer':{'files':['wrong.py','a.py'],'entities':['a.py:f_extra']}}
        score=score_localization(result,rubric)
        self.assertEqual(score['files']['precision'],.5)
        self.assertEqual(score['files']['recall'],.5)
        self.assertEqual(score['files']['reciprocal_rank'],.5)
        self.assertEqual(score['entities']['hits'],0)
        result['status']='failed'
        self.assertEqual(score_localization(result,rubric)['files']['recall'],0)
        result['answer']['files']=['a.py','a.py']
        with self.assertRaises(ValueError):score_localization(result,rubric)

    def test_rubric_membership_and_no_gold_in_scripted_finish(self):
        manifest=candidate()
        self.assertEqual(len(manifest['cases']),6)
        self.assertEqual(manifest['max_requests'],48)
        for row in manifest['cases']:
            case=json.loads((Path.cwd()/row['case_file']).read_text())
            self.assertEqual(row['source_file_count'],6)
            for script in case['scripts'].values():
                end=script[-1]['content'][0]['input']
                self.assertEqual(end['files'],[]);self.assertEqual(end['entities'],[])
        self.assertEqual([r['arm_order'][0] for r in manifest['cases']],['baseline','retrieval']*3)

    def test_worker_failure_records_not_run_and_never_retries(self):
        # Synthetic manifest, no real worker and no credential/authority access.
        from readonly_agent.preparation import make_plan
        from readonly_agent.core import Snapshot
        source=self.root/'src';source.mkdir();(source/'a.py').write_text('x=1\n')
        plan=make_plan(Snapshot(source,['a.py']),'Question.')
        manifest=copy.deepcopy(self.manifest)
        manifest['cases']=[{'id':'d0','plan':plan,'arm_order':['baseline','retrieval'],'case_file':'unused.json'}]
        with patch('experiments.dev_compare.suite.validate',return_value=manifest), \
             patch('experiments.dev_compare.suite.subprocess.run',side_effect=TimeoutError) as worker:
            with self.assertRaises(TimeoutError):replay(self.root/'run')
            worker.assert_called_once()
        report=json.loads((self.root/'run/interrupted.json').read_text())
        self.assertEqual(report['arm_records'][0]['status'],'failed')
        self.assertEqual(report['not_run'][0]['arm'],'retrieval')


if __name__=='__main__':unittest.main()
