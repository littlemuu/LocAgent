"""Offline reconciliation of completed artifacts, not another model/test run."""
import hashlib,json,math
from pathlib import Path
P=Path(__file__).resolve().parents[1];D=P/'delivery';R=P/'evidence/run'
read=lambda p:json.loads(p.read_text())
s=read(R/'state.json');rows=read(D/'C-per-task.json');summary=read(D/'summary.json')
assert s['status']=='finished' and (P/'evidence/run.exit').read_text().strip()=='0'
assert s['api_budget_cny'] is None and s['budget_amendment']['user_instruction']=='取消API预算门槛，跑完再停'
assert [r['instance_id'] for r in rows]==s['trial_ids']==[r['instance_id'] for r in s['rows']]
assert len(rows)==len({r['instance_id'] for r in rows})==24
for r in rows:
 i=r['instance_id'];c=R/'trial'/i
 assert r['status']=='completed' and type(r['resolved']) is bool
 assert {k.rsplit(':',1)[-1] for k in s['steps'] if k.startswith(i+':')}=={'image','locator','coding','evaluation'}
 code=read(c/'C/coding.json');loc=read(c/'locator/result.json');calls=read(c/'ledger.json')['calls']
 assert code['requests']<=40 and loc['requests']<=4
 assert len(calls)==code['requests']+loc['requests'] and all(x['status']=='received' for x in calls)
 assert r['resolved']==read(c/'C/harness/evaluation.json')['resolved']
 assert r['empty_patch']==(not (c/'C/patch.diff').read_text().strip())
 assert r['total_cost']['input_tokens']==sum(x['usage']['prompt_tokens'] for x in calls)
 assert r['total_cost']['output_tokens']==sum(x['usage']['completion_tokens'] for x in calls)
g=read(R/'ledger.json');assert g['limit_microcny'] is None
assert len(g['calls'])==summary['arms']['C']['totals']['requests']
assert math.isclose(sum(x['charged_upper_microcny'] for x in g['calls'])/1e6,summary['arms']['C']['totals']['upper_cny'])
assert len({x['actual_model'] for x in g['calls']})==1
f=read(P/'frozen/FREEZE.json')
assert all(hashlib.sha256((P/'frozen'/k).read_bytes()).hexdigest()==v for k,v in f['files'].items())
assert set(x['instance_id'] for x in read(D/'failure-judgments.json'))==set(r['instance_id'] for r in rows if not r['resolved'])
receipt={'status':'passed','tasks':24,'original_order':True,'each_stage_once':True,'calls_match_per_case_counts':True,'all_calls_received':True,'frozen_files_verified':len(f['files']),'harness_scores_preserved':True,'all_unresolved_cases_reviewed':True,'overall_API_ceiling_removed_by_explicit_user_amendment':True}
(D/'result-validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt))
