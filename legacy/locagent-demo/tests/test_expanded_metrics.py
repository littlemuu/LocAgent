import unittest
from evaluate_expanded_live import metrics

class ExpandedMetricsTests(unittest.TestCase):
    def test_multigold_hit_differs_from_recall(self):
        q={'id':'a','function_primary_eligible':True,'function_gold':['a','b'],'file_gold':['x','y']}
        actual=metrics([q],{'a':['a']},'function')
        self.assertEqual(actual['1'],{'hit':1.,'recall':.5,'denominator':1})

    def test_partial_excluded_from_function_but_file_included(self):
        qs=[{'id':'a','function_primary_eligible':True,'function_gold':['a'],'file_gold':['x']},
            {'id':'b','function_primary_eligible':False,'function_gold':['b'],'file_gold':['y']}]
        self.assertEqual(metrics(qs,{'a':['a'],'b':[]},'function')['1']['denominator'],1)
        self.assertEqual(metrics(qs,{'a':['x'],'b':[]},'file')['1'],{'hit':.5,'recall':.5,'denominator':2})

    def test_missing_result_counts_zero(self):
        q={'id':'a','function_primary_eligible':True,'function_gold':['a']}
        self.assertEqual(metrics([q],{'a':[]},'function')['5'],{'hit':0.,'recall':0.,'denominator':1})

    def test_no_eligible_stratum_is_na_not_zero(self):
        self.assertEqual(metrics([],{},'function')['1'],{'hit':None,'recall':None,'denominator':0})

if __name__=='__main__':unittest.main()
