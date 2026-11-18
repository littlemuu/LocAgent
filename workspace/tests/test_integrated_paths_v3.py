import json,unittest,sqlite3
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
from experiments.cohort_five_evidence_v3.finish_policy import validate_finish,audit_predictions,PATH_INSTRUCTION
from readonly_agent.core import validate_finish as old_validate
from experiments.cohort_five_evidence_v3.common_contract import validate_response,raw_payload,FINISH
from experiments.eval_preflight.scoring import ranked_metrics
class Tests(unittest.TestCase):
 def setUp(self):self.snapshot=SimpleNamespace(files={'a_l.py':'','a_1.py':''});self.answer={'files':['a_l.py'],'entities':['a_l.py:f'],'answer':'evidence'}
 def test_existing_unchanged(self):self.assertEqual(validate_finish(self.answer,self.snapshot),self.answer)
 def test_unknown_safe_retained_without_correction(self):
  a={'files':['a_I.py'],'entities':['a_I.py:f'],'answer':''};self.assertEqual(validate_finish(a,self.snapshot),a)
  self.assertEqual(audit_predictions(a,self.snapshot)['unknown_paths'],['a_I.py']);self.assertEqual(ranked_metrics(['a_l.py:f'],a['entities'],1)['Hit'],0)
 def test_ambiguous_real_paths_stay_distinct(self):
  a=deepcopy(self.answer);a['entities']=['a_1.py:f'];self.assertEqual(validate_finish(a,self.snapshot),a);self.assertEqual(ranked_metrics(['a_l.py:f'],a['entities'],1)['Hit'],0)
 def test_unsafe_paths_rejected(self):
  for path in ('../outside.py','/etc/passwd','x/../a.py','a\\b.py','https://x/a.py','.env','x/.env.local','x/.ssh/id_rsa','a\x00.py','a//b.py','./a.py',''):
   a=deepcopy(self.answer);a['files']=[path]
   with self.subTest(path=path),self.assertRaises(ValueError):validate_finish(a,self.snapshot)
 def test_protocol_errors_rejected(self):
  for a in ({**self.answer,'extra':None},{**self.answer,'files':['a_l.py']*2},{**self.answer,'entities':['a_l.py:bad-name']},{**self.answer,'files':['a_l.py:f']},{**self.answer,'answer':None},{**self.answer,'entities':['a.py:f'+str(i) for i in range(6)]}):
   with self.assertRaises(ValueError):validate_finish(a,self.snapshot)
 def test_no_filesystem_reads_and_unknown_unicode(self):
  a={'files':['不存在.py'],'entities':['不存在.py:方法'],'answer':''};self.assertEqual(validate_finish(a,self.snapshot),a)
 def test_instructions_apply_to_both_wire_surfaces(self):
  q=json.loads(raw_payload([{'role':'system','content':'base'},{'role':'user','content':'issue'}],[FINISH],closing=True))
  self.assertIn(PATH_INSTRUCTION,q['messages'][0]['content']);self.assertEqual([t['function']['name'] for t in q['tools']],['finish'])
 def test_real_failed_response_replayed_without_gold(self):
  p=json.loads(Path('verification/five-batch-v2/live.json').read_text())['cases'][1]
  snapshot=SimpleNamespace(files=p['plan']['source_hashes'])
  ledger=Path('verification/five-batch-live-v2/authority/run/children')/p['id']/p['hash']/'run/ledger.sqlite'
  with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:raw=db.execute("SELECT response FROM calls WHERE arm='baseline' AND turn=3").fetchone()[0]
  z=json.loads(raw);a=json.loads(z['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['message']
  with self.assertRaisesRegex(ValueError,'prediction_outside_snapshot'):old_validate(a,snapshot)
  self.assertEqual(validate_response(z,{'finish'},True,0,snapshot),0)
  self.assertEqual(validate_finish(a,snapshot),a);self.assertEqual(audit_predictions(a,snapshot)['unknown_paths'],['examples/by_feature/megatron_1m_gpt_pretraining.py'])
 def test_prediction_acceptance_never_grants_file_access(self):
  from readonly_agent.core import FileTools
  a={'files':['not_in_source.py'],'entities':[],'answer':''}
  self.assertEqual(validate_finish(a,self.snapshot),a)
  with self.assertRaisesRegex(ValueError,'path_not_allowlisted'):
   FileTools(self.snapshot).respond('read_file',{'path':'not_in_source.py'},4096)
if __name__=='__main__':unittest.main()

