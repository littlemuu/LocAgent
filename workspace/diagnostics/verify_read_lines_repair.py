"""Final offline acceptance, no provider or credential access."""
from pathlib import Path
import hashlib,json,sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import FileTools,Snapshot,digest,encoded
from experiments.locbench_batch.control import frozen,SuiteAuthority,read_status
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/read-lines-repair-v1'
b=json.loads((OUT/'before.json').read_text())
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in b['files'].items())
plan=frozen();h=digest(plan);assert not (ROOT/'authority-locbench'/h).exists()
assert len(list((ROOT/'authority-locbench').iterdir()))==2
log=(OUT/'regression.log').read_text();assert 'Ran 153 tests' in log and log.rstrip().endswith('OK')
from experiments.locbench_batch.live import run
with patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('no_credential_read')) as key:
 for old in ('6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9','eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83'):
  try:run(old,live=True,env_api_key=True)
  except PermissionError:pass
  else:raise AssertionError('old_authorization_reused')
 key.assert_not_called()
checks=[]
for case,line,end,phrase in [(plan['base_manifest']['cases'][0],536,544,'result.append'),(plan['base_manifest']['cases'][1],5969,5987,'left = self._parse_primary() or self._parse_id_var()')]:
 p=ROOT/case['case_file'];cfg=json.loads(p.read_text());s=Snapshot(p.parent/'source',cfg['source_files'])
 file='loguru/_better_exceptions.py' if line==536 else 'sqlglot/parser.py'
 r=FileTools(s).respond('read_file',{'path':file,'start_line':line,'end_line':end},4096)
 assert r['start_line']==line and r['end_line']==end and phrase in r['text'] and r['next_cursor'] is None
 checks.append({'case':case['id'],'packet':r,'json_bytes':len(encoded(r))})
scenarios=[]
for name,expected,n,pending in [('normal','completed',16,0),('bad_closing_second_arm','halted',8,0),('timeout_second_arm','halted',5,2113536)]:
 x=json.loads((OUT/('batch-'+name)/'verification.json').read_text());r=x['result']
 assert x['real_provider_requests']==x['network_attempts']==0 and x['duplicate_claim_blocked']
 assert (r['status'],r['requests'],r['request_pending_micro_cny'])==(expected,n,pending)
 scenarios.append({'name':name,'status':expected,'mock_calls':n,'pending_mock_micro_cny':pending})
replay=json.loads((OUT/'sqlglot-replay.json').read_text());assert replay['model_requests']==0
for arm in replay['arms']:
 assert arm['result']['status']=='completed' and arm['result']['source_bytes']<=14336
 assert arm['result']['requests']==4 and arm['result']['network_attempts']==0
assert replay['arms'][0]['new_read_observations'][0]['text']==replay['arms'][1]['new_read_observations'][0]['text']
assert replay['arms'][0]['new_read_observations'][1]['text']==replay['arms'][1]['new_read_observations'][1]['text']
# The actual retrieval description and implementation were deliberately unchanged.
for file in ('readonly_agent/locagent.py','readonly_agent/bridge.py','readonly_agent/locagent_worker.py'):
 assert (ROOT/file).read_text()==b['code'][file]
old_retrieve=b['code']['readonly_agent/core.py'].split('RETRIEVE = schema(',1)[1].split('\nSYSTEM =',1)[0]
new_retrieve=(ROOT/'readonly_agent/core.py').read_text().split('RETRIEVE = schema(',1)[1].split('\nSYSTEM =',1)[0]
assert old_retrieve==new_retrieve
report={'passed':True,'unit_and_integration_tests':153,'sqlglot_scripted_arms_completed':2,'batch_scenarios':scenarios,
 'historical_files_unchanged':len(b['files']),'new_plan_hash':h,'new_source_manifest_hash':plan['source_manifest_hash'],
 'new_authorization':False,'new_paid_requests':0,'new_cost_cny':0,'credentials_read':False,'target_code_executed':False,
 'old_authorizations_blocked_before_key_loading':2,'retrieval_implementation_and_description_unchanged':True,
 'original_failure_reproduced':True,'new_model_behavior_measured':False,'real_source_checks':checks}
with (OUT/'acceptance.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='real_source_checks'},ensure_ascii=False))
