import json,unittest
from experiments.eval_preflight.outcomes import outcome,score_outcome
from experiments.eval_preflight.scoring import ranked_metrics

class OutcomeTests(unittest.TestCase):
    def test_empty_completion_is_miss_not_failure(self):
        r=outcome('native',{'status':'empty','diagnostics':{'termination_reason':'finished'},
            'raw_output':json.dumps({'message':{'files':[],'entities':[],'answer':'unknown'}})})
        self.assertEqual(score_outcome(r,['a.py:f'],5)['quality']['Recall'],0)
        self.assertEqual(r['category'],'completed')
    def test_class_prediction_kept_exact(self):
        r=outcome('native',{'status':'success','found_entities':[],
            'diagnostics':{'termination_reason':'finished'},
            'raw_output':json.dumps({'message':{'files':['a.py'],'entities':['a.py:C'],'answer':'class'}})})
        self.assertEqual(score_outcome(r,['a.py:C'],1)['quality']['Acc'],1)
    def test_unknown_symbol_not_infrastructure_error(self):
        r=outcome('sdk',{'status':'completed','answer':{'files':['a.py'],'entities':['a.py:Wrong'],'answer':'x'}})
        self.assertEqual(score_outcome(r,['a.py:f'],1)['quality']['Hit'],0)
    def test_failure_categories(self):
        for reason,category in [('ReadTimeout','transport_failure'),('output_truncated','protocol_failure'),
            ('tool_budget_exhausted','budget_or_termination_failure'),('index_unavailable','tool_or_index_failure'),
            ('unrecognized','unclassified_failure')]:
            r=outcome('sdk',{'status':'failed','failure':reason})
            self.assertEqual(r['category'],category)
            self.assertIsNone(score_outcome(r,['a'],1)['quality'])
    def test_not_run_and_simulated_no_quality(self):
        self.assertEqual(outcome('sdk',{'status':'not_run'})['category'],'not_run')
        r=outcome('native',{'simulation':True,'status':'success'})
        self.assertIsNone(score_outcome(r,['a'],1)['planned_denominator_adjusted_zero'])
    def test_inconsistent_native_status_not_completed(self):
        self.assertFalse(outcome('native',{'status':'success','diagnostics':{'termination_reason':'invalid_finish'}})['quality_eligible'])
    def test_malformed_finished_result_is_protocol_failure(self):
        self.assertEqual(outcome('sdk',{'status':'completed','answer':{'entities':[]}})['category'],'protocol_failure')
        self.assertEqual(outcome('native',{'status':'empty','diagnostics':{'termination_reason':'finished'},'raw_output':'{}'})['category'],'protocol_failure')
    def test_constructor_exact_and_reference_ranking(self):
        gold=['m.py:C.__init__','m.py:f']
        prediction=['m.py:C','m.py:C.__init__','m.py:f']
        self.assertEqual(ranked_metrics(gold,prediction,1)['Recall'],0)
        self.assertEqual(ranked_metrics(gold,prediction,1,dialect='upstream_reference')['Recall'],.5)
        self.assertEqual(ranked_metrics(gold,prediction,3,dialect='upstream_reference')['hits'],2)
    def test_duplicates_empty_nonfinite_and_bool_k(self):
        for args in [(['a'],['a','a'],1),(['a'],[''],1),(['a'],[float('nan')],1),(['a'],['a'],True)]:
            with self.assertRaises(ValueError):ranked_metrics(*args)
    def test_gold_duplicates_do_not_inflate_recall(self):
        self.assertEqual(ranked_metrics(['a','a'],['a'],1)['Recall'],1)
