import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_c
from locagent_e2e.ledger import Ledger,BudgetStop
from locagent_e2e.common import write_json
class Tests(unittest.TestCase):
 def test_current_authorization_and_hashes(self):
  self.assertEqual(run_c.verify_frozen(),run_c.EXPECTED);self.assertEqual(run_c.validate(run_c.PACKAGE/'authorization.json')['budget_cny'],15)
 def test_no_extra_arm_or_repetition(self):
  a=json.loads((run_c.PACKAGE/'authorization.json').read_text())
  for k,v in [('arm_order',['A','C']),('repetitions',2),('budget_cny',16),('v82_binding','bad')]:
   bad=copy.deepcopy(a);bad[k]=v
   with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'a.json';p.write_text(json.dumps(bad))
    with self.assertRaises(PermissionError):run_c.validate(p)
 def test_uncertain_request_stays_reserved_across_tasks(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);a=Ledger(root/'trial/one/ledger.json',15);a.reserve(100,4096,'one');a.stop('provider_failed')
   g=run_c.aggregate(root);self.assertEqual(g['uncertain_requests'],1);self.assertEqual(g['charged_or_reserved_microcny'],run_c.MAX_RESERVATION)
   b=Ledger(root/'trial/two/ledger.json',g['remaining_microcny']/1e6);b.reserve(100,4096,'two')
   self.assertEqual(run_c.aggregate(root)['charged_or_reserved_microcny'],2*run_c.MAX_RESERVATION)
   with self.assertRaises(BudgetStop):a.reserve(100,4096,'retry')
 def test_global_cap_cannot_be_reset(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for i in range(7):
    g=run_c.aggregate(root);l=Ledger(root/'trial'/str(i)/'ledger.json',g['remaining_microcny']/1e6)
    l.reserve(1,4096,str(i));l.stop('uncertain')
   g=run_c.aggregate(root);self.assertLess(g['remaining_microcny'],run_c.MAX_RESERVATION);self.assertLessEqual(g['charged_or_reserved_microcny'],15000000)
   l=Ledger(root/'trial/eight/ledger.json',g['remaining_microcny']/1e6)
   with self.assertRaises(BudgetStop):l.reserve(1,4096,'eight')
 def test_failed_case_does_not_abort_following_case(self):
  with tempfile.TemporaryDirectory() as td:
   r=run_c.CRunner.__new__(run_c.CRunner);r.out=Path(td);r.path=r.out/'state.json';r.auth={'trial_ids':['first','second']};r.state={'rows':[]}
   def one(identifier):
    if identifier=='first':raise ValueError('single case failed')
    return {'instance_id':identifier,'status':'completed'}
   r.one=one;r.run();self.assertEqual([x['status'] for x in r.state['rows']],['failed','completed'])
 def test_stage_never_retried(self):
  with tempfile.TemporaryDirectory() as td:
   r=run_c.CRunner.__new__(run_c.CRunner);r.out=Path(td);r.path=r.out/'state.json';r.state={'steps':{}}
   r.once('x',lambda:(_ for _ in ()).throw(ValueError('fail')))
   with self.assertRaises(RuntimeError):r.once('x',lambda:{'status':'completed'})
if __name__=='__main__':unittest.main(verbosity=2)
