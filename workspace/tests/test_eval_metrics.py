import unittest
from experiments.eval_preflight.scoring import ranked_metrics as m,evaluate_completed

class MetricsTests(unittest.TestCase):
    def test_acc_is_coverage_not_any_hit(self):
        r=m(['a','b'],['a','x'],3);self.assertEqual((r['Acc'],r['Recall'],r['Hit']),(0,.5,1))
    def test_short_gold_and_rank(self):
        self.assertEqual(m(['a'],['x','a'],1)['Acc'],0)
        self.assertEqual(m(['a'],['x','a'],3)['Acc'],1)
    def test_more_than_k_gold(self):
        r=m(['a','b','c','d'],['a','b','c'],3);self.assertEqual((r['Acc'],r['Recall']),(1,.75))
    def test_constructor_both_sides_normalized(self):
        g=['m.py:C.__init__'];p=['m.py:C.__init__']
        self.assertEqual(m(g,p,1,dialect='upstream_reference')['Acc'],1)
        self.assertEqual(m(g,['m.py:C'],1)['Acc'],0)
    def test_normalized_duplicates_removed_before_k(self):
        r=m(['m:C','b'],['m:C.__init__','m:C','b'],3,dialect='upstream_reference')
        self.assertEqual((r['hits'],r['Recall']),(2,1))
    def test_duplicates_invalid(self):
        with self.assertRaises(ValueError):m(['a'],['a','a'],3)
    def test_empty_gold_not_vacuous_success(self):self.assertIsNone(m([],[],1)['Acc'])
    def test_zero_prediction_is_valid_miss(self):self.assertEqual(m(['a'],[],5)['Recall'],0)
    def test_reference_denominator_is_explicit(self):
        g=[str(i) for i in range(12)];p=g[:5]
        self.assertEqual(m(g,p,5)['Recall'],5/12)
        self.assertEqual(m(g,p,5,dialect='upstream_reference')['Recall'],.5)
    def test_failure_and_simulation_separate(self):
        self.assertIsNone(evaluate_completed({'status':'failed'},['a'],1)['quality'])
        self.assertTrue(evaluate_completed({'status':'not_run'},['a'],1)['not_run'])
        with self.assertRaises(ValueError):evaluate_completed({'simulation':True},['a'],1)
