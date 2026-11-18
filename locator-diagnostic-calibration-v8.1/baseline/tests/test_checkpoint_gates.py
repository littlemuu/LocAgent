import json,tempfile,unittest
from pathlib import Path
from locagent_e2e.common import ROOT
from locagent_e2e.checkpoint import stop_decision,validate_authorization
from locagent_e2e.ledger import Ledger,BudgetStop
class CheckpointTests(unittest.TestCase):
 def test_threshold_is_strictly_greater_and_every_complete_checkpoint_pauses(self):
  for count,expected in [(8,'paused_checkpoint'),(9,'stopped_loss_threshold')]:
   rows=[{'status':'completed','empty_patch':i<count,'resolved':False} for i in range(16)];r=stop_decision(rows)
   self.assertEqual(r['status'],expected);self.assertFalse(r['continue_allowed']);self.assertEqual(r['empty_patch_rate'],count/16)
  self.assertEqual(stop_decision([])['status'],'stopped_incomplete')
 def test_authorization_cannot_expand_or_reorder_first_eight(self):
  a=json.loads((ROOT/'checkpoint-authorization.json').read_text());self.assertEqual(len(validate_authorization(ROOT/'checkpoint-authorization.json')['trial_ids']),8)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'auth.json'
   for field,value in [('budget_cny',51),('max_trial_episodes',48),('trial_ids',list(reversed(a['trial_ids']))),('pause_after',24),('arm_order',['B','A'])]:
    b=dict(a);b[field]=value;p.write_text(json.dumps(b))
    with self.assertRaises(PermissionError):validate_authorization(p)
 def test_fifty_yuan_shared_reservation_stops_before_overrun(self):
  with tempfile.TemporaryDirectory() as td:
   l=Ledger(Path(td)/'ledger.json',50)
   l.update(lambda s:s['calls'].append({'status':'received','reserved_microcny':48000000,'charged_upper_microcny':48000000}))
   with self.assertRaises(BudgetStop):l.reserve(100,4096,'trial')
   self.assertEqual(len(l.read()['calls']),1)
