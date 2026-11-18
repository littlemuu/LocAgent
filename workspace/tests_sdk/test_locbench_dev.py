import copy
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from experiments.dev_compare.suite import BatchGuard
from experiments.locbench_dev.prepare import ROOT, PROJECT, SELECTED, git_hash, read, validate, verify_tree
from experiments.locbench_dev.run_offline import replay
from experiments.locbench_dev.scoring import score, official_reference
from readonly_agent.locagent import source_entity_segments


class LocBenchDevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = read(ROOT/'manifest.json')

    def test_only_two_exposed_development_cases_and_equal_budgets(self):
        self.assertEqual(tuple(c['id'] for c in self.manifest['cases']), SELECTED)
        self.assertEqual(self.manifest['max_requests'],16)
        self.assertEqual(self.manifest['suite_budget_micro_cny'],34_000_000)
        for item in self.manifest['cases']:
            self.assertEqual(item['exposure']['original_local_split'],'development')
            self.assertTrue(item['exposure']['known_repository_exposure'])
            self.assertEqual(item['plan']['limits'],self.manifest['cases'][0]['plan']['limits'])
            self.assertEqual(item['plan']['max_requests_per_arm'],4)
        self.assertFalse(self.manifest['live_entrypoint_enabled'])

    def test_frozen_hashes_and_runtime_validate(self):
        self.assertEqual(validate(),self.manifest)

    def test_source_mutation_is_rejected(self):
        target=self.root/'mutated';shutil.copytree(ROOT,target)
        path=next((target/'cases'/SELECTED[0]/'source').rglob('*.py'))
        path.write_text(path.read_text()+'\n# mutation\n')
        with self.assertRaisesRegex(ValueError,'frozen_input_changed'):validate(target)

    def test_task_and_gold_mutation_are_rejected(self):
        for relative in (f'cases/{SELECTED[0]}/task.json',f'scoring-only/{SELECTED[0]}.json'):
            with self.subTest(relative=relative):
                target=self.root/str(len(list(self.root.iterdir())));shutil.copytree(ROOT,target)
                (target/relative).write_text('{}')
                with self.assertRaisesRegex(ValueError,'frozen_input_changed'):validate(target)

    def test_runtime_payload_has_no_scoring_fields_or_oracle_finish(self):
        for item in self.manifest['cases']:
            path=PROJECT/item['case_file'];case=read(path);task=read(path.with_name('task.json'))
            self.assertEqual(set(task),{'instance_id','repo','base_commit','problem_statement'})
            self.assertEqual(case['issue'],task['problem_statement'])
            self.assertEqual(set(case),{'root','source_files','issue','scripts'})
            for script in case['scripts'].values():
                end=script[-1]['content'][0]['input']
                self.assertEqual(end['files'],[]);self.assertEqual(end['entities'],[])
                self.assertIn(script[1]['content'][0]['input']['query'],case['issue'])
            serialized=json.dumps(item['plan'])
            self.assertNotIn('gold_entities',serialized)
            self.assertNotIn('edit_functions',serialized)

    def test_git_tree_content_and_completeness(self):
        blob=git_hash('blob',b'x=1\n')
        tree={'sha':git_hash('tree',b'100644 a.py\0'+bytes.fromhex(blob)),
              'truncated':False,'tree':[{'path':'a.py','type':'blob','mode':'100644','sha':blob,'size':4}]}
        self.assertEqual(set(verify_tree(tree)),{'a.py'})
        for altered in (dict(tree,truncated=True),dict(tree,tree=[]),dict(tree,sha='0'*40)):
            with self.assertRaises(ValueError):verify_tree(altered)

    def test_ast_exact_segment_preserves_string_whitespace(self):
        source='class C:\n    def f(self):\n        return """a\n  b\n""" # trailing\n'
        segments=source_entity_segments(source)
        text=segments[('function','C.f',2,5)]
        self.assertNotIn('# trailing',text)
        self.assertIn('\n  b\n',text)
        self.assertNotEqual(text,text.replace('\n  b\n','\nb\n'))

    def test_two_pairs_34_cny_cap_and_duplicate_start(self):
        guard=BatchGuard.create(self.root/'suite.sqlite',self.manifest)
        summary={'simulation':True,'halted':False,'reserved_micro_cny':0,
                 'spent_upper_micro_cny':17_000_000,'calls':[{'status':'settled'}]*8}
        for item in self.manifest['cases']:
            guard.start(item['id'])
            with self.assertRaises(RuntimeError):guard.start(item['id'])
            guard.finish(item['id'],summary)
        with sqlite3.connect(guard.path) as db:
            self.assertEqual(db.execute('SELECT SUM(cost),SUM(requests) FROM pairs').fetchone(),(34_000_000,16))
        with self.assertRaises(ValueError):guard.start('third')
        with self.assertRaises(FileExistsError):BatchGuard.create(guard.path,self.manifest)

    def test_worker_failure_stops_and_records_unrun_arms(self):
        with patch('experiments.locbench_dev.run_offline.validate',return_value=self.manifest), \
             patch('experiments.locbench_dev.run_offline.subprocess.run',side_effect=TimeoutError('fixture_timeout')) as worker:
            with self.assertRaises(TimeoutError):replay(self.root/'run')
            worker.assert_called_once()
        report=read(self.root/'run/interrupted.json')
        self.assertEqual(len(report['records']),1)
        self.assertEqual(len(report['not_run']),3)
        self.assertEqual(report['live_calls'],0)
        with self.assertRaises(RuntimeError):BatchGuard(self.root/'run/suite.sqlite',self.manifest).start(SELECTED[1])

    def test_partial_pair_unknown_cost_blocks_next_case(self):
        guard=BatchGuard.create(self.root/'suite.sqlite',self.manifest);guard.start(SELECTED[0])
        summary={'simulation':True,'halted':False,'reserved_micro_cny':2_113_536,
                 'spent_upper_micro_cny':100,'calls':[{'status':'unknown'}]}
        with self.assertRaises(RuntimeError):guard.finish(SELECTED[0],summary)
        with self.assertRaises(RuntimeError):guard.start(SELECTED[1])

    def test_scoring_oracle_empty_wrong_and_fixture_rejection(self):
        for identifier in SELECTED:
            gold=read(ROOT/'scoring-only'/f'{identifier}.json')
            result={'status':'completed','answer':{'files':gold['gold_files'],'entities':gold['gold_entities']}}
            self.assertEqual(score(result,gold)['strict_exact_top5']['entities']['f1'],1)
            result['status']='failed'
            self.assertEqual(score(result,gold)['strict_exact_top5']['entities']['f1'],0)
            result['status']='not_run'
            self.assertIsNone(score(result,gold)['raw_score'])
            result.update(status='completed',simulation=True)
            with self.assertRaises(ValueError):score(result,gold)
        self.assertEqual(official_reference(['a.py:C.__init__'],['a.py:C'])['Recall'],1)
        self.assertEqual(official_reference(['a.py:C.__init__'],['a.py:C.__init__'])['Recall'],0)
        self.assertEqual(official_reference(['a.py:f'],['a.py:f']*2)['Recall'],2)


if __name__=='__main__':
    unittest.main()
