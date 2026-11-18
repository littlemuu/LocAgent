import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from run_locator import LocatorOnly,verify,validate,PACKAGE
class ControlTests(unittest.TestCase):
 def test_binding_and_scope(self):
  self.assertEqual(verify()['status'],'passed');a=validate(PACKAGE/'authorization.json')
  for k,v in [('budget_cny',20),('coding_agent',True),('harness',True),('concurrency',2),('automatic_retries',1),('trial_ids',list(reversed(a['trial_ids'])))]:
   with self.subTest(k=k),tempfile.TemporaryDirectory() as td:
    bad=copy.deepcopy(a);bad[k]=v;p=Path(td)/'bad.json';p.write_text(json.dumps(bad))
    with self.assertRaises(PermissionError):validate(p)
 def test_failure_continues_once_in_same_order(self):
  with tempfile.TemporaryDirectory() as td,patch('run_locator.platform.system',return_value='Linux'),patch('run_locator.platform.machine',return_value='x86_64'):
   r=LocatorOnly(Path(td)/'out',Path(td)/'unused',PACKAGE/'authorization.json');seen=[]
   def one(i):seen.append(i);return dict(instance_id=i,delivery_success=len(seen)!=1,status='failed' if len(seen)==1 else 'delivered')
   r.one=one;done=r.run();r.lock.close()
   self.assertEqual(seen,r.auth['trial_ids']);self.assertEqual(done['attempted'],24);self.assertEqual(done['delivered'],23)
   self.assertFalse(hasattr(r,'coding'));self.assertFalse(hasattr(r,'evaluate'));self.assertEqual(r.ledger.read()['calls'],[])
if __name__=='__main__':unittest.main(verbosity=2)
