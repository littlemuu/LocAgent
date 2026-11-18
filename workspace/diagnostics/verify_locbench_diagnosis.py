"""Validate saved offline diagnostic evidence without model or target execution."""
from pathlib import Path
import hashlib,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import encoded,digest
from experiments.locbench_batch.control import frozen
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/locbench-offline-diagnosis-v1'
before=json.loads((OUT/'before.json').read_text())
assert digest(frozen())==before['suite_hash']
assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in before['files'].items())
assert hashlib.sha256((ROOT/'diagnostics/locbench_offline_probe.py').read_bytes()).hexdigest()==before['probe_script_sha256']
assert len(list((ROOT/'authority-locbench').iterdir()))==2
reports=[];queries=0
for path in sorted(OUT.glob('*/results.json')):
 r=json.loads(path.read_text());assert r['network_attempts']==r['paid_calls']==0
 assert not r['credential_read'] and not r['target_code_executed']
 assert all(v=='invalid_query' for v in r['full_issue_query_rejected'].values())
 for q in r['queries']:
  assert 1<=len(q['query'])<=256;queries+=1
  for tool in ('search_text','locagent_retrieve'):
   v=q[tool];raw=(path.parent/v['raw_file']).read_text()
   assert hashlib.sha256(raw.encode()).hexdigest()==v['raw_sha256']
   first=v['first_page'];assert len(encoded(first))<=4096 and raw.startswith(first['text'])
   if first['next_offset'] is None:assert raw==first['text']
   else:assert first['next_offset']==len(first['text'])
   ids=re.findall(r'^##Searching for entity `([^`]+)`',raw,re.M)
   assert ids==v['ranked_entity_ids'] and len(ids)<=5
   assert v['gold_entity_rank']==(ids.index(r['gold'])+1 if r['gold'] in ids else None)
 reports.append(r)
assert queries==17 and len(reports)==2
trace=json.loads((OUT/'trace-and-reference-analysis.json').read_text());checks=json.loads((OUT/'followup-static-checks.json').read_text())
assert all(x['mapping_verified'] and x['old_patch_hunks_exact'] for x in trace)
assert all(a['score_recomputed_exact'] and a['retrieval_call_count']==0 for x in trace for a in x['arms'])
assert all(x['exact_entity_source_matches_ast_byte_for_byte'] for x in checks)
report={'passed':True,'historical_frozen_files_unchanged':len(before['files']),'suite_hash_unchanged':before['suite_hash'],
 'cases':2,'actual_arms_analyzed':4,'paired_offline_queries':queries,'retrieval_processes':17,
 'actual_live_retrieval_calls':0,'new_paid_requests':0,'new_cost_cny':0,'credential_read':False,'target_code_executed':False,
 'mapping_and_patch_hunks_verified':2,'scores_recomputed':4,'exact_entity_ast_text_matches':2,
 'query_limit_full_issue_rejections':4,'new_production_authorizations':0,
 'interpretation':'Post-hoc exposed development diagnosis; oracle queries explicitly labelled; no autonomous-choice or benefit claim.',
 'artifacts':{str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and p.name!='before.json'}}
with (OUT/'acceptance.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='artifacts'},ensure_ascii=False))
