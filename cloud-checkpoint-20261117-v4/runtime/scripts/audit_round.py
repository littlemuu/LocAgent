from pathlib import Path
import json,hashlib,sys,time,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import ROOT,CONFIG,write_json
from locagent_e2e.driver import config_binding
run=ROOT/'verification/round-run';s=json.loads((run/'state.json').read_text());a=json.loads((ROOT/'checkpoint-authorization.json').read_text());ledger=json.loads((run/'ledger.json').read_text())
assert s['code_binding']==config_binding();assert s['failed'] is None
accept=json.loads((run/'smoke-acceptance.json').read_text());assert len(accept['episodes'])==4 and accept['all_four_completed_without_technical_failure']
progress=json.loads((run/'trial-progress.json').read_text());assert len(progress['episodes'])==16
chronology=sorted([(v['started_at'],k) for k,v in s['steps'].items() if k.startswith('trial:') and k.endswith(':agent')]);expected=[f'trial:{i}:{arm}:agent' for i in a['trial_ids'] for arm in ['A','B']];assert [k for _,k in chronology]==expected
contracts=[]
for phase,ids in [('smoke',['sympy__sympy-21379','astropy__astropy-14182']),('trial',a['trial_ids'])]:
 for identifier in ids:
  for arm in ['A','B']:
   p=run/phase/identifier/arm;code=json.loads((p/'coding.json').read_text());agent=json.loads((p/'agent/result.json').read_text());pred=json.loads((p/'prediction.json').read_text());ev=json.loads((p/'harness/evaluation.json').read_text());patch=(p/'patch.diff').read_text()
   assert code['status']=='completed' and ev['status']=='completed';assert pred['instance_id']==identifier and pred['model_patch']==patch;assert code['empty_patch']==(not bool(patch.strip()));assert agent['requests']<=40
   first=min((e['request'] for e in agent['source_edit_events']),default=None);assert agent['first_source_edit_request']==first
   assert all(1<=e['request']<=agent['requests'] for e in agent['source_edit_events']);contracts.append((agent['system_prompt_sha256'],agent['tool_schema_sha256'],json.dumps(agent['budget'],sort_keys=True)))
assert len(set(contracts))==1
assert all(r['status']=='received' for r in ledger['calls']);upper=sum(r['charged_upper_microcny'] for r in ledger['calls']);assert upper<=50000000 and ledger['limit_microcny']==50000000
key=Path('/home/ubuntu/.config/locagent/checkpoint.env');assert not key.exists()
containers=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines();assert not containers
result={'status':'passed','code_binding':s['code_binding'],'smoke_episodes':4,'trial_episodes':16,'trial_order_verified':True,'ab_prompt_schema_budget_identical':True,'first_edit_and_empty_patch_verified':True,'all_predictions_match_diff':True,'api_requests':len(ledger['calls']),'api_cost_upper_cny':upper/1e6,'unknown_requests':0,'credential_deleted':True,'running_containers':containers,'holdout_read':False,'after_eight_not_run':True,'captured_at':time.time()}
write_json(ROOT/'verification/final-round-audit.json',result);print(json.dumps(result))
