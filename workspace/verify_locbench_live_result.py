"""Read-only verification of the one authorized LocBench run; no model calls."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import json,sqlite3,hashlib
from experiments.locbench_batch.control import SuiteAuthority,read_status,frozen,PROJECT
from readonly_agent.core import digest
from readonly_agent.deepseek_wire import usage,structured_finish,FinishProtocolError
from readonly_agent.authority import save_new

h='6a84c4723546c2e9a9044f255915d39f31ccd40118ca92f795a1b6807c560eb9'
a=SuiteAuthority();grant=a.read(h,fresh=False);root=Path(grant['run_dir']);status=read_status(a,h)
assert digest(frozen())==h and status['status']=='halted' and status['reason']=='finish_message_contract_error'
assert status['requests']==12 and status['spent_upper_micro_cny']==106498 and status['request_pending_micro_cny']==0
assert status['execution_mode']=='live'
pre=json.loads((PROJECT/'verification/LOCBENCH_APPROVED_PREFLIGHT.json').read_text())
for old in pre['old_ledgers']:
 assert hashlib.sha256((PROJECT/old['path']).read_bytes()).hexdigest()==old['sha256']
measurements=json.loads((root/'measurements.json').read_text());records=[];input_tokens=output_tokens=cache_hit=cache_miss=0
incident=None
for case in grant['plan']['base_manifest']['cases']:
 pair=root/'children'/case['plan_hash']/'run';ledger=pair/'ledger.sqlite'
 with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;rows=db.execute('SELECT * FROM calls ORDER BY id').fetchall()
  assert len(rows)<=8
  for c in rows:
   assert c['status']=='settled' and c['complete']==1 and c['http_status']==200 and c['transport_started']==1
   assert hashlib.sha256(c['request']).hexdigest()==c['request_hash'] and hashlib.sha256(c['response']).hexdigest()==c['response_hash']
   raw,cost=usage(bytes(c['response']));assert cost==c['cost']
   request=json.loads(c['request']);choice=raw['choices'][0];u=raw['usage']
   input_tokens+=u['prompt_tokens'];output_tokens+=u['completion_tokens']
   cache_hit+=u.get('prompt_cache_hit_tokens',0);cache_miss+=u.get('prompt_cache_miss_tokens',0)
   names=[t['function']['name'] for t in choice['message'].get('tool_calls',[])]
   assert 'locagent_retrieve' not in names
   assert request['model']=='deepseek-flash' and request['max_tokens']==2048
   if c['turn']==4:
    assert [x['function']['name'] for x in request['tools']]==['finish']
   else:assert request['tool_choice']=='auto'
   records.append({'case':case['id'],'arm':c['arm'],'turn':c['turn'],'http_status':200,'complete':True,
    'finish_reason':choice['finish_reason'],'tools':names,'usage':u,'cost_upper_micro_cny':cost,
    'request_sha256':c['request_hash'],'response_sha256':c['response_hash']})
   if case['id']=='tobymao__sqlglot-3417' and c['turn']==4:
    args=json.loads(choice['message']['tool_calls'][0]['function']['arguments']);message=args['message']
    assert set(message)-{'files','entities','answer'}=={'entities_note'} and message['entities_note'] is None
    assert choice['finish_reason']=='tool_calls' and u['completion_tokens']==563
    schema=request['tools'][0]['function']['parameters']['properties']['message']
    assert schema['additionalProperties'] is False
    try:structured_finish(message)
    except FinishProtocolError as error:assert error.code=='finish_message_contract_error'
    else:raise AssertionError('must_reject_original_extra_field')
    # Diagnostic contract-only check on a copy, not a normalized accepted result.
    projected={k:message[k] for k in ('files','entities','answer')};structured_finish(projected)
    incident={'case':case['id'],'arm':c['arm'],'request_number':c['turn'],
      'cause':'Original message contains entities_note:null beyond the three required fields.',
      'response':raw,'offered_finish_schema':request['tools'][0],
      'request_sha256':c['request_hash'],'response_sha256':c['response_hash'],
      'original_ledger_modified':False,'original_result_accepted':False,'projection_used_for_contract_diagnosis_only':True}
for item in measurements['rows']:
 obs=item['observability']
 if obs:assert obs['retrieval_calls']==0 and not obs['live_auto_selection_observed']
assert [x['status'] for x in measurements['rows']]==['completed','completed','failed','not_run']
assert input_tokens==41977 and output_tokens==2818
assert input_tokens*2+output_tokens*8==106498
assert incident is not None
save_new(PROJECT/'verification/LOCBENCH_FINISH_EXTRA_FIELD_INCIDENT.json',incident)
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'suite_hash':h,'status':'halted_no_retry',
 'reason':status['reason'],'provider_requests':12,'settled_receipts':12,'unknown_requests':0,
 'cost_upper_micro_cny':106498,'cost_upper_cny':.106498,'actual_provider_billing_reconciled':False,
 'input_tokens':input_tokens,'output_tokens':output_tokens,'cache_hit_tokens':cache_hit,'cache_miss_tokens':cache_miss,
 'live_retrieval_calls':0,'completed_arms':2,'failed_arms':1,'not_run_arms':1,'complete_pairs':1,
 'old_ledgers_unchanged':len(pre['old_ledgers']),'frozen_plan_unchanged':True,
 'claims_retrieval_benefit':False,'independent_test':False,
 'unfinished_case_hold_cny':17,'hold_is_not_additional_spending':True,
 'source_files_exposure':'Both questions now exposed to model; Loguru baseline/retrieval and SQLGlot retrieval only.',
 'ledger_sha256':{c['id']:hashlib.sha256((root/'children'/c['plan_hash']/'run/ledger.sqlite').read_bytes()).hexdigest() for c in grant['plan']['base_manifest']['cases']},
 'measurements_sha256':hashlib.sha256((root/'measurements.json').read_bytes()).hexdigest(),'calls':records}
save_new(PROJECT/'verification/LOCBENCH_LIVE_ACCEPTANCE.json',report)
print(json.dumps({k:v for k,v in report.items() if k not in ('calls','ledger_sha256')},ensure_ascii=False,indent=2))
