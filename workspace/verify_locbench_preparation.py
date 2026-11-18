"""Read-only acceptance; writes a new local report, never accesses credentials."""
from datetime import datetime,timezone
import hashlib,json,sqlite3
from pathlib import Path
from experiments.locbench_dev.prepare import ROOT,PROJECT,read,sha,validate,save
from readonly_agent.core import digest
from readonly_agent.deepseek_wire import RESERVATION

manifest=validate()
measurements=read(PROJECT/'locbench_openhands/offline-v3/measurements.json')
assert measurements['suite_hash']==digest(manifest)
assert measurements['mock_requests']==16 and measurements['live_calls']==0
assert len(measurements['records'])==4
history=read(PROJECT/'verification/LOCBENCH_PREPARATION_HISTORY_BEFORE.json')
assert all(sha(PROJECT/p)==h for p,h in history.items())
evidence=read(ROOT/'upstream-evidence.json')
assert all(sha(p)==h for p,h in evidence.items())
pairs=[]
for case in manifest['cases']:
 pair=PROJECT/'locbench_openhands/offline-v3'/case['id']
 summary=read(pair/'budget-summary.json')
 assert summary['simulation'] and not summary['halted'] and summary['reserved_micro_cny']==0
 assert len(summary['calls'])==8 and all(c['status']=='settled' for c in summary['calls'])
 with sqlite3.connect((pair/'simulation.sqlite').as_uri()+'?mode=ro',uri=True) as db:
  requests={arm:[json.loads(r[0]) for r in db.execute('SELECT request FROM calls WHERE arm=? ORDER BY turn',(arm,))] for arm in case['arm_order']}
 for arm, rows in requests.items():
  assert len(rows)==4 and [t['function']['name'] for t in rows[-1]['tools']]==['finish']
  assert all(r['model']=='deepseek-flash' and r['max_tokens']==2048 for r in rows)
  assert all(r['thinking']=={'type':'disabled'} and r['temperature']==0 for r in rows)
  assert all(r['tool_choice']=='auto' for r in rows[:-1])
 baseline=requests['baseline'][0];retrieval=requests['retrieval'][0]
 assert baseline['messages']==retrieval['messages']
 bt={x['function']['name']:x for x in baseline['tools']};rt={x['function']['name']:x for x in retrieval['tools']}
 assert set(rt)-set(bt)=={'locagent_retrieve'} and {k:rt[k] for k in bt}==bt
 for r in measurements['records']:
  if r['case']!=case['id']:continue
  assert r['status']=='completed' and r['network_attempts']==0 and r['live_calls']==0
  assert r['observability']['normal_finish'] and not r['observability']['live_auto_selection_observed']
  if r['arm']=='retrieval':
   assert r['all_retrieval_observations_delivered'] and r['source_evidence_chain_verified']
   assert all(c['selection_category']=='scripted_fixture' for c in r['observability']['invocations'])
 pairs.append({'id':case['id'],'commit':case['base_commit'],'snapshot':case['plan']['snapshot'],
   'files':case['source_file_count'],'bytes':case['source_bytes'],'same_initial_messages_and_shared_tools':True,
   'last_request_finish_only':True,'requests':8,'ledger_sha256':sha(pair/'simulation.sqlite')})
assert 16*RESERVATION==manifest['full_reservations_micro_cny']<=manifest['suite_budget_micro_cny']
logs=['locbench-adapter-tests-v3.log','locbench-locagent-tests.log','locbench-preparation-regression.log','locbench-closing-regression.log','locbench-core-regression.log']
for name in logs: assert '\nOK\n' in (PROJECT/'verification'/name).read_text()
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'status':'offline_accepted_live_not_enabled',
 'suite_hash':digest(manifest),'pairs':pairs,'historical_files_unchanged':len(history),'upstream_evidence_unchanged':len(evidence),
 'test_count':65,'test_logs':{n:sha(PROJECT/'verification'/n) for n in logs},'mock_requests':16,'paid_requests':0,
 'actual_cost_cny':0,'credentials_accessed':False,'proposal_max_requests':16,'proposal_cap_cny':34,
 'full_reservation_cny':16*RESERVATION/1_000_000,'account_pricing_confirmed':False,
 'live_start_blocker':'Two-case production admission/orchestration is not yet wired; no grant created. Offline BatchGuard refuses live.',
 'past_offline_attempts':['offline-v1: AST trailing-comment mismatch; halted, retained','offline-v2: empty lexical return rejected by overly strong acceptance predicate; halted, retained'],
 'claims_autonomous_retrieval':False,'claims_benefit':False,'independent_test':False}
save(PROJECT/'verification/LOCBENCH_PREPARATION_ACCEPTANCE.json',report)
print(json.dumps(report,ensure_ascii=False,indent=2))
