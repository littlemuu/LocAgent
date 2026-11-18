import unittest
from types import SimpleNamespace as N
from experiments.cohort_five_evidence_v3.body_backend import positive_nodes
class Tests(unittest.TestCase):
 def test_positive_preserves_original_objects_and_rank(self):
  a,b=N(score=.2),N(score=4);self.assertEqual(positive_nodes([a,N(score=0),b]),[a,b])
 def test_zero_negative_nan_infinite_excluded(self):
  self.assertEqual(positive_nodes([N(score=x) for x in (0,-1,float('nan'),float('inf'),-float('inf'))]),[])
 def test_no_fallback_for_no_match(self):self.assertEqual(positive_nodes([]),[])
 def test_invalid_score_not_silently_ignored(self):
  with self.assertRaises(ValueError):positive_nodes([N(score='broken')])
if __name__=='__main__':unittest.main()
