import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from diagnostics.probe_natural_gaps import BoundedRoute
from readonly_agent.core import Snapshot
from readonly_agent.offline import no_network
class RoundBudgetTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  (self.root/'a.py').write_text('def f():\n    return 1\n')
  (self.root/'b.py').write_text('def g():\n    return 2\n')
  (self.root/'long.py').write_text('x = 1\n'*2000)
  self.s=Snapshot(self.root,['a.py','b.py','long.py']);self.guard=no_network(self.root/'profiles');self.guard.__enter__();self.addCleanup(self.guard.__exit__,None,None,None)
 def test_dependent_read_blocked_last_round(self):
  r=BoundedRoute(self.s,{},[16,14336],1);r.call('search_text',{'query':'def f(','offset':0});r.round=2
  self.assertIsNone(r.call('read_file',{'path':'a.py'}));self.assertEqual(len(r.steps),1);self.assertEqual(r.stop,'investigation_rounds_exhausted')
 def test_dependent_read_allowed_two_rounds(self):
  r=BoundedRoute(self.s,{},[16,14336],2);r.call('search_text',{'query':'def f(','offset':0});r.round=2;r.call('read_file',{'path':'a.py'})
  self.assertEqual(r.result()['rounds_used'],2);self.assertEqual(len(r.steps),2);self.assertEqual(r.result()['complete_functions'][0]['name'],'f')
 def test_independent_reads_share_round(self):
  r=BoundedRoute(self.s,{},[16,14336],1);r.call('read_file',{'path':'a.py'});r.call('read_file',{'path':'b.py'})
  self.assertEqual(r.result()['rounds_used'],1);self.assertEqual(len(r.result()['complete_functions']),2)
 def test_continuation_needs_another_round(self):
  r=BoundedRoute(self.s,{},[16,14336],1);r.pages('read_file',{'path':'long.py'})
  self.assertEqual(len(r.steps),1);self.assertLessEqual(r.used,4096);self.assertEqual(r.stop,'investigation_rounds_exhausted');self.assertTrue(r.blocked)
 def test_tool_budget_still_enforced(self):
  r=BoundedRoute(self.s,{},[1,1000],2);r.call('read_file',{'path':'a.py'});r.call('read_file',{'path':'b.py'})
  self.assertEqual(len(r.steps),1);self.assertEqual(r.stop,'budget');self.assertLessEqual(r.used,1000)
if __name__=='__main__':unittest.main()
