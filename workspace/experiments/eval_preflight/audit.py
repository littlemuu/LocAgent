"""Metadata-only cohort audit plus two already-exposed static semantic reviews."""
import collections,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'verification/eval-preflight-v2'
BATCH=Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113')
PREVIOUS=BATCH.parent/'locbench-summary-independent-prep-20261111'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def main():
 ready=read(BATCH/'technical-ready-current-engine.json');ids={r['instance_id'] for r in ready}
 ledger=[r for r in read(BATCH/'scoring-only/stage-ledger-560.json') if r['instance_id'] in ids]
 oldreview=read(BATCH.parent/'locbench-review/scoring-only/review-checklist.json')
 overlap=[r for r in oldreview if r['instance_id'] in ids]
 exposures=read(PREVIOUS/'new-exposure-register.json')
 splitrepos={s:{r['repo'].lower() for r in ledger if r['original_local_split']==s} for s in ('development','test')}
 current_calls=[]
 for p in (ROOT/'authority-locbench').glob('*/grant.json'):
  g=read(p)
  for c in g['plan']['base_manifest']['cases']:
   db=Path(g['run_dir'])/'children'/c['plan_hash']/'run/ledger.sqlite'
   if db.is_file():
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
     count=conn.execute('SELECT COUNT(*) FROM calls WHERE transport_started=1').fetchone()[0]
    if count:current_calls.append({'id':c['id'],'transport_started':count,'ledger':str(db),'ledger_sha256':sha(db)})
 labelstats=collections.Counter()
 for id in ids:
  labels=read(BATCH/'scoring-only/labels'/(id+'.json'));gold=labels['edit_functions']
  labelstats['empty']+=not bool(gold);labelstats['more_than_5_unique']+=len(set(gold))>5
  labelstats['more_than_10_unique']+=len(set(gold))>10
  labelstats['constructor_cases']+=any(x.endswith('.__init__') for x in gold)
  labelstats['duplicate_labels']+=len(set(gold))!=len(gold)
 rows=[{'id':r['instance_id'],'repo':r['repo'],'local_split':r['original_local_split'],
   'known_repository_exposure':r['known_repository_exposure'],
   'has_historical_review_pointer':r['historical_review'] is not None,
   'current_semantic_status':'pending','review_register_mentions_case':r['instance_id'] in exposures['instance_ids'],
   'review_register_repository':r['repo'].lower() in exposures['repositories']} for r in ledger]
 selected={'Delgan__loguru-1239','tobymao__sqlglot-3417'}
 pool=[r for r in rows if r['local_split']=='development' and not r['known_repository_exposure'] and r['id'] not in selected]
 sample=sorted(pool,key=lambda r:hashlib.sha256(('semantic-preflight-v1|'+r['id']).encode()).hexdigest())[:4]
 reviews=[]
 for id in sorted(selected):
  frozen=read(ROOT/'locbench_openhands/v5/scoring-only'/(id+'.json'))
  labels=read(BATCH/'scoring-only/labels'/(id+'.json'));plan=read(ROOT/'engine_adaptation/v4/plans'/(id+'.json'))
  assert labels['base_commit']==plan['commit']==frozen['base_commit']
  assert set(labels['edit_functions'])==set(frozen['gold_entities'])
  reviews.append({'id':id,'status':'preliminary_static_review_not_independent','label_hash':sha(BATCH/'scoring-only/labels'/(id+'.json')),
   'issue_hash':hashlib.sha256(read(ROOT/'locbench_openhands/v5/cases'/id/'case.json')['issue'].encode()).hexdigest(),
   'finding':('Reference switches _parse_id_var to _parse_column for dotted SET assignment LHS; directly consistent with issue.'
     if 'sqlglot' in id else 'Expected repeated-frame abbreviation matches _format_list reference change; title requests unit tests while reference changes runtime. Preserve control-only status and review scope mismatch.'),
   'unique_root_cause_claim':False,'all_valid_alternatives_established':False,'fed_to_mock_provider':False})
 result={'count':130,'current_technical_ready':read(ROOT/'engine_adaptation/v4/acceptance.json')['technical_ready'],
  'local_splits':dict(collections.Counter(r['local_split'] for r in rows)),
  'split_repository_overlap':sorted(splitrepos['development']&splitrepos['test']),
  'exposure_by_split':[{'split':s,'known_repository_exposure':x,'count':sum(r['local_split']==s and r['known_repository_exposure']==x for r in rows)} for s in ['development','test'] for x in [True,False]],
  'historical_review_pointers':sum(r['has_historical_review_pointer'] for r in rows),
  'verified_old_checklist_records':[{'id':r['instance_id'],'decision':r['decision'],'old_split':r['split']} for r in overlap],
  'actual_live_call_lower_bound':current_calls,'live_scan_scope':'authority-locbench only; excludes other SQLGlot/choice and older external-run directories; never infer all others unexposed',
  'review_register_scope':{'path':str(PREVIOUS/'new-exposure-register.json'),'repositories':len(exposures['repositories']),'ready_case_overlap':sum(r['review_register_mentions_case'] for r in rows),'instruction':exposures['purpose']},
  'label_statistics_only':dict(labelstats),'rows':rows,'static_reviews':reviews,
  'next_review_sample':{'seed':'semantic-preflight-v1','ids':sorted(selected)+[r['id'] for r in sample],
    'additional_four_not_opened':True,'development_only':True,'selection_before_semantic_read':True},
  'independent_test_claim':False,'formal_evaluation_ready':False}
 save(OUT/'cohort-semantic-audit.json',result)
 print({k:result[k] for k in ['local_splits','split_repository_overlap','historical_review_pointers','label_statistics_only']})
 print('verified live lower bound',dict(collections.Counter({i:sum(r['transport_started'] for r in current_calls if r['id']==i) for i in selected})))
if __name__=='__main__':main()
