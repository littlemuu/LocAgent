import unittest
from copy import deepcopy
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from experiments.cohort_five_evidence_v3.freeze import candidate
from experiments.cohort_five_evidence_v3.parent import Parent,validate
from experiments.cohort_five_evidence_v3.cumulative import prior_binding,verify_prior,check_totals,CASE_HOLD,NEW_MICRO_CNY
from readonly_agent.core import digest
class Tests(unittest.TestCase):
 def test_prior_readonly_verified(self):
  b=prior_binding();self.assertEqual((b['requests'],b['upper_micro_cny'],b['unknown_micro_cny']),(15,172942,0))
 def test_cumulative_boundaries(self):
  check_totals(NEW_MICRO_CNY,40)
  for cost,count in ((NEW_MICRO_CNY+1,40),(0,41),(-1,1),(0,-1)):
   with self.assertRaises(PermissionError):check_totals(cost,count)
  self.assertEqual(5*CASE_HOLD+172942,84714382)
 def test_prior_binding_changes_stop(self):
  b=prior_binding();b['upper_micro_cny']=0
  with self.assertRaises(PermissionError):verify_prior(b)
  b=prior_binding();b['files'].clear()
  with self.assertRaises(PermissionError):verify_prior(b)
 def test_old_40_total_is_not_silently_extended(self):
  p=candidate('rehearsal');p['cumulative_request_limit']=40
  with self.assertRaises(PermissionError):validate(p)
 def test_old_consent_cannot_create_new_grant(self):
  p=candidate('live');h=digest(p)
  with TemporaryDirectory() as td:
   parent=Parent(Path(td).resolve()/'test-only')
   with self.assertRaises(PermissionError):parent.prepare(p,consent=f'APPROVE FIVE {h} CNY 85',currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
   self.assertFalse(parent.root.exists())
 def test_rehearsal_refuses_new_actual_key(self):
  from experiments.cohort_five_evidence_v3.batch import execute
  p=candidate('rehearsal')
  with TemporaryDirectory() as td:
   parent=Parent(Path(td).resolve()/'test-only');parent.prepare(p)
   with self.assertRaises(PermissionError):execute(parent,parent.claim(),key='synthetic-do-not-use')
   self.assertFalse((parent.root/'run').exists())
if __name__=='__main__':unittest.main()
