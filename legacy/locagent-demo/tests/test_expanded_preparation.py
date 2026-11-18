import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'scripts/prepare_expanded_subset.py'
spec=importlib.util.spec_from_file_location('expanded',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class PreparationTests(unittest.TestCase):
    def test_multigold_recall_differs_from_hit(self):
        self.assertEqual(m.score(['a','b'],['a','c'],1),{'hit':1,'recall':.5})
    def test_na_and_missing(self):
        self.assertIsNone(m.score([],['a'],5));self.assertEqual(m.score(['a'],[],5),{'hit':0,'recall':0})
    def test_duplicate_gold_not_double_counted(self):
        self.assertEqual(m.score(['a','a'],['a'],1)['recall'],1)
    def test_insertions_not_whole_hunk(self):
        self.assertEqual(m.changed_old_lines('@@ -10,3 +10,4 @@ f\n context\n+new\n unchanged\n tail'),[(10,'insertion_after')])
    def test_removal_and_insert(self):
        self.assertEqual(m.changed_old_lines('@@ -10,2 +10,2 @@ f\n-old\n+new\n context'),[(10,'insertion_after'),(10,'removed')])
    def test_invalid_hunk(self):
        with self.assertRaises(ValueError):m.changed_old_lines('@@ broken')
    def test_no_overwrite(self):
        with self.assertRaises(ValueError):m.prepare(Path('.'),{},Path('.'))

if __name__=='__main__':unittest.main()
