"""Audit the approved SQLGlot single-case run; no transport or key loading."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,sqlite3
from experiments.sqlglot_validation.control import SuiteAuthority,read_status,frozen
from readonly_agent.core import digest
from readonly_agent.deepseek_wire import usage,structured_finish
from readonly_agent.authority import save_new

h='df07e7a25bad76c053d3f372b8b0b9fd0a883b03577aef53676781553f5c3277'
a=SuiteAuthority();g=a.read(h,fresh=False);root=Path(g['run_dir']);s=read_status(a,h)
assert digest(frozen())==h and s['status'] in ('completed','halted') and s['execution_mode']=='live'
assert s['requests']<=8 and s['limit_micro_cny']==17_000_000
pre=json.loads(Path('verification/SQLGLOT_READ_APPROVED_PREFLIGHT.json').read_text())
for item in pre['old_ledgers']:assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
before=json.loads(Path('verification/sqlglot-validation-v1/before.json').read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in before['files'].items())
measurement=json.loads((root/'measurements.json').read_text());calls=[];arms=[]
for case in g['plan']['base_manifest']['cases']:
 pair=root/'children'/case['plan_hash']/'run';ledger=pair/'ledger.sqlite'
 if not ledger.exists():continue
 with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row;rows=db.execute('SELECT * FROM calls ORDER BY id').fetchall()
 for c in rows:
  assert hashlib.sha256(c['request']).hexdigest()==c['request_hash']
  q=json.loads(c['request']);assert q['model']=='deepseek-flash' and q['max_tokens']==2048
  assert q['thinking']=={'type':'disabled'} and q['temperature']==0
  names=[t['function']['name'] for t in q['tools']]
  assert ('locagent_retrieve' not in names) if c['arm']=='baseline' else True
  if c['turn']==4:assert names==['finish']
  else:assert q['tool_choice']=='auto'
  info={'case':case['id'],'arm':c['arm'],'turn':c['turn'],'status':c['status'],'request_sha256':c['request_hash'],
   'response_sha256':c['response_hash'],'cost_upper_micro_cny':c['cost'],'transport_started':c['transport_started']}
  if c['response'] is not None:assert hashlib.sha256(c['response']).hexdigest()==c['response_hash']
  if c['status']=='settled':
   assert c['complete']==1 and c['http_status']==200 and c['transport_started']==1
   raw,cost=usage(bytes(c['response']));assert cost==c['cost'];choice=raw['choices'][0]
   info.update(usage=raw['usage'],finish_reason=choice['finish_reason'],tools=[t['function']['name'] for t in choice['message'].get('tool_calls',[])])
   if info['tools']==['finish']:
    message=json.loads(choice['message']['tool_calls'][0]['function']['arguments'])['message']
    info['finish_fields']=sorted(message);info['known_null_compatibility_used']='entities_note' in message
  calls.append(info)
for row in measurement['rows']:
 counts=Counter(name for c in calls if c['case']==row['case'] and c['arm']==row['arm'] for name in c.get('tools',[]))
 obs=row['observability'];arm=dict(case=row['case'],arm=row['arm'],status=row['status'],failure=row['failure'],
  requests=row['requests_reserved'],tools=dict(counts),elapsed_wall_seconds=row['elapsed_wall_seconds'],
  cost_upper_cny=row['spent_upper_micro_cny']/1e6,pending_cny=row['pending_micro_cny']/1e6,
  normalization_events=len(row['finish_normalizations']),score=row['localization_score'],observability=obs,read_protocol=row['read_protocol'])
 if row['status']=='completed':assert obs['normal_finish']
 arms.append(arm)
settled=[c for c in calls if c['status']=='settled'];input_tokens=sum(c['usage']['prompt_tokens'] for c in settled);output_tokens=sum(c['usage']['completion_tokens'] for c in settled)
assert len(calls)==s['requests'];assert input_tokens*2+output_tokens*8==s['spent_upper_micro_cny']
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'suite_hash':h,'status':s['status'],'reason':s['reason'],
 'provider_requests':len(calls),'settled_receipts':len(settled),'unknown_requests':len(calls)-len(settled),
 'cost_upper_cny':s['spent_upper_micro_cny']/1e6,'pending_cny':s['request_pending_micro_cny']/1e6,
 'case_budget_hold_cny':s['case_budget_hold_micro_cny']/1e6,'actual_provider_billing_reconciled':False,
 'input_tokens':input_tokens,'output_tokens':output_tokens,
 'cache_hit_tokens':sum(c['usage'].get('prompt_cache_hit_tokens',0) for c in settled),
 'cache_miss_tokens':sum(c['usage'].get('prompt_cache_miss_tokens',0) for c in settled),
 'completed_arms':sum(x['status']=='completed' for x in arms),'historical_artifacts_unchanged':len(before['files']),
 'old_ledgers_unchanged':len(pre['old_ledgers']),'frozen_plan_unchanged':True,'retry':False,
 'claims_retrieval_benefit':False,'independent_test':False,'arms':arms,'calls':calls,
 'measurements_sha256':hashlib.sha256((root/'measurements.json').read_bytes()).hexdigest()}
save_new(Path('verification/SQLGLOT_READ_LIVE_ACCEPTANCE.json'),report)
print(json.dumps({k:v for k,v in report.items() if k not in ('arms','calls')},ensure_ascii=False,indent=2))
for arm in arms:print(json.dumps({k:v for k,v in arm.items() if k!='observability'},ensure_ascii=False))
