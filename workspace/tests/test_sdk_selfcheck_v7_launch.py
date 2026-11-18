import unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone,timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch
from experiments.sdk_finish_selfcheck_v7.freeze import candidate
from experiments.sdk_finish_selfcheck_v7.launch import validate_confirmation,matching_batch,launch
from readonly_agent.core import digest
from readonly_agent.authority import save_new

class LaunchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.plan=candidate('live')
 def confirmation(self):
  p=self.plan;h=digest(p);now=datetime.now(timezone.utc).isoformat()
  return {'plan_hash':h,'consent':f'APPROVE SDKSELFCHECK7 {h} NEW48 NEWCNY102 TOTAL474 TOTALCNY107',
   'currency':'CNY','input_ceiling':'2','output_ceiling':'8','all_charges_included':True,
   'destination':'https://api.deepseek.com/chat/completions','model':'deepseek-flash',
   'send_categories':p['cases'][0]['plan']['send_categories'],'excluded':['gold','reference_patch'],
   'max_requests':48,'new_micro_cny_limit':102000000,'automatic_retry':False,
   'confirmed_at':now,'pricing_checked_at':now,'user_confirmation':'SYNTHETIC TEST ONLY; NOT USER CONSENT'}
 def test_exact_scope_and_freshness(self):
  a=self.confirmation();validate_confirmation(self.plan,a)
  for key,value in [('max_requests',9),('currency','USD'),('all_charges_included',False),
   ('automatic_retry',True),('plan_hash','old'),('user_confirmation',''),('pricing_checked_at',(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()),
   ('send_categories',a['send_categories']+['gold']),('new_micro_cny_limit',17000001)]:
   b=deepcopy(a);b[key]=value
   with self.assertRaises(PermissionError):validate_confirmation(self.plan,b)
 def test_missing_confirmation_fails_before_key_or_process(self):
  with TemporaryDirectory() as td:
   with patch('readonly_agent.local_env.load_selected_key') as key,patch('experiments.sdk_finish_selfcheck_v7.launch.subprocess.run') as proc:
    with self.assertRaises(FileNotFoundError):launch(Path(td).resolve()/'missing.json')
    key.assert_not_called();proc.assert_not_called()
 def test_invalid_confirmation_fails_before_key_or_process(self):
  with TemporaryDirectory() as td:
   p=Path(td).resolve()/'confirmation.json';a=self.confirmation();a['max_requests']=40;save_new(p,a)
   with patch('experiments.sdk_finish_selfcheck_v7.launch.PLAN',Path(td).resolve()/'plan.json'):
    save_new(Path(td).resolve()/'plan.json',self.plan)
    with patch('readonly_agent.local_env.load_selected_key') as key,patch('experiments.sdk_finish_selfcheck_v7.launch.subprocess.run') as proc:
     with self.assertRaises(PermissionError):launch(p)
     key.assert_not_called();proc.assert_not_called()
 def test_process_filter(self):
  self.assertTrue(matching_batch(b'python python -m experiments.cohort_dev37_v4.batch _case'))
  self.assertTrue(matching_batch(b'python python -m experiments.sdk_finish_selfcheck_v7.batch _case'))
  self.assertFalse(matching_batch(b'python python -m experiments.sdk_finish_selfcheck_v7.launch --execute-approved x'))
  self.assertFalse(matching_batch(b'rg rg experiments.sdk_finish_selfcheck_v7'))

if __name__=='__main__':unittest.main()

class OneUseLaunchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.plan=candidate('live')
 confirmation=LaunchTests.confirmation
 def test_existing_launch_or_grant_prevents_key_read(self):
  for old_grant in (False,True):
   with TemporaryDirectory() as td:
    root=Path(td).resolve();out=root/'out';plan=root/'plan.json';lock=root/'lock.json';approval=root/'confirmation.json'
    save_new(plan,self.plan);save_new(approval,self.confirmation());save_new(lock,{'live_plan_hash':digest(self.plan),'files':{}})
    if old_grant:
     folder=root/'verification'/'old';folder.mkdir(parents=True);save_new(folder/'grant.json',{'hash':digest(self.plan)})
    else:out.mkdir()
    with patch('experiments.sdk_finish_selfcheck_v7.launch.ROOT',root),patch('experiments.sdk_finish_selfcheck_v7.launch.PLAN',plan),patch('experiments.sdk_finish_selfcheck_v7.launch.LOCK',lock),patch('experiments.sdk_finish_selfcheck_v7.launch.OUT',out):
     with patch('readonly_agent.local_env.load_selected_key') as key,patch('experiments.sdk_finish_selfcheck_v7.launch.subprocess.run') as proc:
      proc.return_value.stdout=b''
      with self.assertRaises((FileExistsError,PermissionError)):launch(approval)
      key.assert_not_called()
