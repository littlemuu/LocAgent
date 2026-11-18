"""Post-hoc scoring only; never imported by a model runner.

Official semantics are deliberately separate from source-ast-v2 strict metrics.
This small reference translation is not execution of upstream's torch scorer.
"""
import math,json,importlib.util
from adapter import ROOT,normalize
SCORER=ROOT.parent/'locagent-expanded-eval-prep-20261107/scoring/scorer.py'
spec=importlib.util.spec_from_file_location('existing_strict_scorer',SCORER)
strict=importlib.util.module_from_spec(spec);spec.loader.exec_module(strict)
def official_reference(gold,predictions,k=5,max_k=10):
    """found_entities branch: normalizes gold only, preserves duplicate pred slots.
    Upstream truncates ideal count to max_k; Acc uses min(k, ideal_count).
    MAP divides precision sum by k, NOT number of relevant labels.
    """
    if type(k) is not int or type(max_k) is not int or not 1<=k<=max_k:raise ValueError('require 1 <= k <= max_k')
    targets=list(dict.fromkeys(normalize(x) for x in gold))
    if not targets:return None
    count=min(len(targets),max_k); hits=[int(x in targets) for x in predictions[:k]]
    dcg=sum(v/math.log2(i+2) for i,v in enumerate(hits))
    ideal=sum(1/math.log2(i+2) for i in range(min(k,count)))
    return {'Acc':float(sum(hits)==min(k,count)),'Recall':sum(hits)/count,'P':sum(hits)/k,'NDCG':dcg/ideal,'MAP':sum(sum(hits[:i+1])/(i+1) for i,v in enumerate(hits) if v)/k}
def strict_gold(raw_labels,catalog):
    """Do not turn official class labels into exact-function truth."""
    functions=list(dict.fromkeys(raw_labels))
    gold={'files':list(dict.fromkeys(x.split(':')[0] for x in functions)),'functions':functions}
    strict.validate_gold(gold,catalog)
    return gold
if __name__=='__main__':
    import unittest
    class Tests(unittest.TestCase):
      def test_perfect(self):self.assertEqual(official_reference(['x.py:f'],['x.py:f'],1,1)['Recall'],1)
      def test_missing(self):self.assertEqual(official_reference(['x.py:f'],[],5)['Recall'],0)
      def test_init_gold_only(self):
        self.assertEqual(official_reference(['x.py:C.__init__'],['x.py:C'],1)['Recall'],1)
        self.assertEqual(official_reference(['x.py:C.__init__'],['x.py:C.__init__'],1)['Recall'],0)
      def test_duplicate_upstream_behavior(self):self.assertEqual(official_reference(['x.py:f'],['x.py:f']*2,2)['Recall'],2)
      def test_map_denominator(self):self.assertEqual(official_reference(['x.py:f'],['x.py:f'],5)['MAP'],.2)
      def test_strict_rejects_class(self):
        cat=strict.build_catalog({'x.py':b'class C:\n def __init__(self): pass\n'})
        with self.assertRaises(ValueError):strict_gold(['x.py:C'],cat)
        g=strict_gold(['x.py:C.__init__'],cat)
        result=strict.score_answer(json.dumps({'files':['x.py'],'entities':['x.py:C']}),cat,g)
        self.assertEqual(result['function']['recall_at_k'],0)
      def test_real_samples_strict(self):
        labels=json.loads((ROOT/'scoring-only/labels.json').read_text());checks=[]
        for p in sorted((ROOT/'samples').glob('*/source.json')):
          d=json.loads(p.read_text());i=d['instance_id']
          # Only gold files needed for this post-hoc AST resolvability check.
          src={f:(p.parent/'repo'/f).read_bytes() for f in labels[i]['files']}
          cat=strict.build_catalog(src)
          try:g=strict_gold(labels[i]['raw_edit_functions'],cat)
          except ValueError as e:checks.append({'instance_id':i,'strict_eligible':False,'reason':str(e)});continue
          res=strict.score_answer(json.dumps({'files':g['files'],'entities':g['functions']}),cat,g)
          self.assertEqual(res['function']['true_positive_unique'],min(5,len(g['functions'])))
          checks.append({'instance_id':i,'strict_eligible':True,'synthetic_gold_answer_check_only':res['function']})
        (ROOT/'strict-score-check.json').write_text(json.dumps(checks,indent=2))
    unittest.main(verbosity=2)
