import importlib.util,unittest
from pathlib import Path

def load(name):
    p=Path(__file__).resolve().parents[1]/'scripts'/f'{name}.py';spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class DesignTests(unittest.TestCase):
    def test_sampler_deterministic_balanced_excludes_exposure(self):
        sample=load('sample_holdout')
        rows=[{'instance_id':f'{repo}__r-{i}','repo':repo+'/r','base_commit':str(i).zfill(40),'created_at':'2000-01-01'} for repo in ['a','b','c'] for i in range(30)]
        e={'excluded_verified_ids':['a__r-0'],'development_ids':['b__r-1'],'development_repo_commits':[['c/r',str(2).zfill(40)]]}
        a,n=sample.select(rows,e);b,_=sample.select(list(reversed(rows)),e)
        self.assertEqual(a,b);self.assertEqual(n,87);self.assertEqual(len(a),50)
        self.assertTrue({'a__r-0','b__r-1','c__r-2'}.isdisjoint(r['instance_id'] for r in a))
        counts=[sum(x['repo']==repo+'/r' for x in a) for repo in ['a','b','c']];self.assertLessEqual(max(counts)-min(counts),1)
        with self.assertRaises(ValueError):sample.select([{**rows[0],'resolved':True}],e,n=1)
    def test_paired_statistics_null_extreme_and_multiplicity(self):
        s=load('paired_statistics')
        self.assertEqual(s.paired_signflip([0]*50,draws=1000),1.)
        self.assertLess(s.paired_signflip([1]*50,draws=1000),.01)
        self.assertEqual(s.holm([.01,.04,.03]),[.03,.06,.06])
        self.assertEqual(s.exact_mcnemar(0,0),1.);self.assertEqual(s.exact_mcnemar(0,5),.0625)
        self.assertEqual(s.stratified_paired_interval([.2]*6,['a']*3+['b']*3,draws=100),[.19999999999999998,.19999999999999998])
