"""Separate post-audit reference comparison; predictions and scorer stay unchanged."""
from experiments.cohort_preflight.entry import ROOT,read,save,sha
from experiments.eval_preflight.scoring import ranked_metrics

OUT=ROOT/'verification/finish-evidence-audit-v1'
audit_path=OUT/'checked/audit.json';audit=read(audit_path)
old=read(ROOT/'verification/sdk-retrieval-compare-v6-live/analysis.json')
plan=read(ROOT/'verification/sdk-retrieval-compare-v6-batch/live.json')
assert sha(ROOT/'experiments/eval_preflight/scoring.py')==plan['scoring_hash']
bindings={b['id']:b for b in read(ROOT/'verification/dev37-preparation-v4/scoring-only/gold-binding.json')}
rows=[]
for r in audit['rows']:
    b=bindings[r['id']];assert sha(b['original_label_path'])==b['original_label_hash']
    previous=next(x for x in old['rows'] if x['id']==r['id'] and x['arm']==r['arm'])
    current={str(k):ranked_metrics(b['gold'],r['answer']['entities'],k) for k in (1,3,5)}
    assert current==previous['strict']
    omitted={n for m in r['audit']['mentions'] for n in m['omitted_observed_candidates']}
    overlap=sorted(omitted & set(b['gold']))
    rows.append({'id':r['id'],'arm':r['arm'],'strict_metrics_identical':True,'gold_count':len(set(b['gold'])),
                 'max_recall_at5_given_submission_cap':min(5,len(set(b['gold'])))/len(set(b['gold'])),
                 'gold_members_among_review_leads':overlap,
                 'caution':'posthoc reference overlap, not proof the answer should automatically include this entity',
                 'original_metrics':current})
save(OUT/'score-check.json',{'rows':rows,'gold_free_audit_sha256':sha(audit_path),'predictions_modified':False,
                           'scorer_modified':False,'new_model_requests':0,'hypothetical_corrected_scores_not_computed':True})
print('Verified 12 original scores unchanged; reference overlap:',[(r['id'],r['arm'],r['gold_members_among_review_leads']) for r in rows if r['gold_members_among_review_leads']])
