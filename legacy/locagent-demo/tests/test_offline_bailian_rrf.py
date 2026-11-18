from pathlib import Path
import importlib.util
import unittest
path=Path(__file__).resolve().parents[1]/'scripts/offline_bailian_rrf.py'
spec=importlib.util.spec_from_file_location('offline_rrf',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class OfflineRrfTests(unittest.TestCase):
 def test_max_entity_then_positive_filter_and_lexical_ties(self):
  docs=[{'entity':'b'},{'entity':'a'},{'entity':'b'},{'entity':'zero'}]
  rank,score=module.entity_ranking(docs,[.5,1,1,0],True)
  self.assertEqual(rank,['a','b']);self.assertEqual(score['b'],1)
 def test_equal_rrf_formula_and_tie(self):
  rank,s=module.rrf(['b','a'],['a','b'],60)
  self.assertEqual(rank,['a','b']);self.assertAlmostEqual(s['a'],1/62+1/61)
 def test_dense_weight_two(self):
  rank,s=module.rrf(['b','a'],['a','b'],60,1,2)
  self.assertEqual(rank[0],'a');self.assertAlmostEqual(s['a'],1/62+2/61)
 def test_k_ten(self):
  _,s=module.rrf(['a'],['a'],10);self.assertEqual(s['a'],2/11)
 def test_each_arm_truncates_before_union(self):
  a=[f'a{i}' for i in range(11)];b=[f'b{i}' for i in range(11)]
  rank,s=module.rrf(a,b,60,top_n_per_arm=10)
  self.assertEqual(len(rank),20);self.assertNotIn('a10',s);self.assertNotIn('b10',s);self.assertEqual(s['a0'],1/61)
 def test_duplicate_entity_rejected(self):
  with self.assertRaises(ValueError):module.rrf(['a','a'],['a'],60)
 def test_missing_gold_scores_zero_same_denominator(self):
  qs=[{'id':'q1','relevant_entities':['a']},{'id':'q2','relevant_entities':['z']}]
  result=module.measure(qs,{'q1':['a'],'q2':['b']})
  self.assertEqual(result['macro']['1'],{'hit':.5,'recall':.5});self.assertIsNone(result['per_query']['q2']['gold_rank'])


if __name__=='__main__':unittest.main()
