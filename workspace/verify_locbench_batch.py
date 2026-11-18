"""Acceptance audit for offline verification of the LocBench live entry point."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,sqlite3
from experiments.locbench_batch.control import frozen,ROOT,PROJECT
from readonly_agent.core import digest
from experiments.locbench_dev.prepare import sha,read,save

plan=frozen();h=digest(plan)
assert not ROOT.exists(), 'production_authority_must_remain_absent'
history=read(PROJECT/'verification/LOCBENCH_BATCH_HISTORY_BEFORE.json')
assert all(sha(PROJECT/n)==wanted for n,wanted in history.items())
expected={
 'normal':('completed',16,None,0),
 'timeout_second_arm':('halted',5,'TimeoutError',2113536),
 'bad_closing_second_arm':('halted',8,'closing_tool_violation',0),
 'timeout_second_case':('halted',9,'TimeoutError',2113536),
 'truncation_first_arm':('halted',4,'model_output_truncated',0),
 'invalid_finish':('halted',4,'finish_source_validation_error',0),
 'missing_finish':('halted',4,'closing_finish_missing',0),
 'oversized_receipt':('halted',3,'RuntimeError',2113536)}
scenarios=[]
for name,wanted in expected.items():
 path=PROJECT/f'verification/locbench-live-v1-{name}/verification.json'
 record=read(path);state=record['result']
 assert record['suite_hash']==h and record['real_provider_requests']==0 and record['network_attempts']==0
 assert record['duplicate_claim_blocked'] and record['assertions_passed']
 assert (state['status'],state['requests'],state['reason'],state['request_pending_micro_cny'])==wanted
 assert state['limit_micro_cny']==34_000_000
 report=read(path.parent/'mock-authority'/h/'run/measurements.json')
 assert report['simulation'] and report['planned_arms']==4 and not report['claims_benefit']
 assert all(r['localization_score'] is None for r in report['rows'])
 assert all(not r['observability']['live_auto_selection_observed'] for r in report['rows'] if r['observability'])
 if name=='timeout_second_case':
  assert state['cases'][0]['status']=='completed' and state['cases'][0]['hold']==0
  assert state['cases'][1]['status']=='failed' and state['cases'][1]['hold']==17_000_000
 if name=='normal':
  assert report['completed_arms']==4 and state['case_budget_hold_micro_cny']==0
  for item in plan['base_manifest']['cases']:
   ledger=path.parent/'mock-authority'/h/'run/children'/item['plan_hash']/'run/ledger.sqlite'
   with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
    wire={arm:[json.loads(row[0]) for row in db.execute('SELECT request FROM calls WHERE arm=? ORDER BY turn',(arm,))] for arm in item['arm_order']}
   assert wire['baseline'][0]['messages']==wire['retrieval'][0]['messages']
   shared={t['function']['name']:t for t in wire['baseline'][0]['tools']}
   extra={t['function']['name']:t for t in wire['retrieval'][0]['tools']}
   assert set(extra)-set(shared)=={'locagent_retrieve'} and all(extra[k]==v for k,v in shared.items())
   for arm,requests in wire.items():
    assert len(requests)==4
    assert all(r['model']=='deepseek-flash' and r['max_tokens']==2048 and r['thinking']=={'type':'disabled'} for r in requests)
    assert all(r['tool_choice']=='auto' for r in requests[:3])
    assert [t['function']['name'] for t in requests[3]['tools']]==['finish']
    assert requests[3]['tool_choice']['function']['name']=='finish'
 scenarios.append({'name':name,'status':state['status'],'requests':state['requests'],'reason':state['reason'],
   'pending_micro_cny':state['request_pending_micro_cny'],'case_hold_micro_cny':state['case_budget_hold_micro_cny'],
   'verification_sha256':sha(path),'not_run_arms':sum(a['status']=='not_run' for a in state['arms'])})
logs=['locbench-batch-tests-final.log','locbench-batch-test_live.py.log',
      'locbench-batch-test_final_length.py.log','locbench-batch-test_preparation.py.log']
counts={}
for name in logs:
 text=(PROJECT/'verification'/name).read_text()
 assert '\nOK\n' in text
 counts[name]=int(re.search(r'Ran (\d+) tests',text).group(1))
assert sum(counts.values())==60
report={'status':'offline_live_entrypoint_accepted_no_production_grant',
 'checked_utc':datetime.now(timezone.utc).isoformat(),'suite_hash':h,
 'source_manifest_hash':plan['source_manifest_hash'],'history_files_unchanged':len(history),
 'production_authority_exists':False,'real_provider_requests':0,'real_cost_cny':0,
 'credential_loaded':False,'network_attempts':0,'test_counts':counts,'test_total':60,
 'scenarios':scenarios,'mock_transport_calls':sum(s['requests'] for s in scenarios),
 'max_live_requests':16,'budget_cap_cny':34,'full_reservations_cny':33.816576,
 'public_price_checked_utc_date':'2026-11-13','account_price_confirmed':False,
 'production_start_requires':['Explicit approval of this frozen two-case scope and transmitted data',
 'Account all-in CNY input/output prices within 2/8 per million and current alias/version recheck',
 'Fresh one-use grant; source/driver revalidation; local TTY and private existing .env'],
 'claims_autonomous_retrieval':False,'claims_benefit':False,'independent_test':False}
save(PROJECT/'verification/LOCBENCH_BATCH_READY_ACCEPTANCE.json',report)
print(json.dumps(report,indent=2,ensure_ascii=False))
