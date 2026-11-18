import math
import unittest
from locagent_service.bailian_mapping_probe import compare


def unit(i):
 v=[0.]*1024;v[i]=1.;return v


class MappingComparisonTests(unittest.TestCase):
 def test_correct_mapping_passes(self):
  a,b=unit(0),unit(1)
  self.assertEqual(compare([a,b],[a,b])['result'],'this_pair_passed')
 def test_swapped_mapping_is_detected(self):
  a,b=unit(0),unit(1)
  self.assertEqual(compare([b,a],[a,b])['result'],'inconclusive')
 def test_indistinguishable_controls_are_inconclusive(self):
  a=unit(0)
  self.assertEqual(compare([a,a],[a,a])['result'],'inconclusive')
 def test_numerical_instability_is_not_accepted(self):
  a,b=unit(0),unit(1);unstable=[math.sqrt(1-0.01**2),0.,0.01]+[0.]*1021
  self.assertEqual(compare([unstable,b],[a,b])['result'],'inconclusive')
 def test_invalid_vectors_rejected(self):
  a,b=unit(0),unit(1)
  with self.assertRaises(ValueError):compare([[0.]*1024,b],[a,b])


if __name__=='__main__':unittest.main()
