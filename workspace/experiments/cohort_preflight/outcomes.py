"""Scoring-only aggregation: explicit provenance, fixed denominator, no silent drops."""
from experiments.eval_preflight.scoring import ranked_metrics

def aggregate(expected_ids,records,gold,k=5,*,mode):
    if mode not in ('simulation','live'):raise ValueError('explicit_run_mode_required')
    if not isinstance(expected_ids,list) or len(set(expected_ids))!=len(expected_ids) or not expected_ids:
        raise ValueError('invalid_frozen_denominator')
    byid={}
    for row in records:
        if set(row)!={'case_id','mode','status','answer','failure'} or row['case_id'] not in expected_ids or row['case_id'] in byid:
            raise ValueError('duplicate_or_foreign_result')
        if row['mode']!=mode or row['status'] not in ('completed','failed','not_run'):
            raise ValueError('result_provenance_or_status_mismatch')
        byid[row['case_id']]=row
    counts={s:0 for s in ('completed','failed','not_run')};scores=[]
    for id in expected_ids:
        row=byid.get(id,{'status':'not_run'})
        counts[row['status']]+=1
        if row['status']=='completed' and mode=='live':
            if id not in gold:raise ValueError('missing_gold_not_silently_dropped')
            result=ranked_metrics(gold[id],row['answer']['entities'],k)
            if not result['eligible']:raise ValueError('ineligible_gold_requires_new_denominator')
            scores.append(result)
    planned=len(expected_ids)
    return {'mode':mode,'planned':planned,**counts,'completion_rate':counts['completed']/planned,
        'quality_scored':mode=='live',
        'completed_only_mean':{m:sum(r[m] for r in scores)/len(scores) if scores else None for m in ('Acc','Recall','Hit')},
        'planned_denominator_adjusted':{m:sum(r[m] for r in scores)/planned if mode=='live' else None for m in ('Acc','Recall','Hit')},
        'technical_failures_not_localization_misses':True}

def require_run_provenance(result,run_mode):
    # Prior SDK inner results lack simulation=True; they must never be treated
    # as live scored answers merely because status says completed.
    if run_mode not in ('simulation','live'):raise ValueError('explicit_run_mode_required')
    if run_mode=='live':
        budget=result.get('budget',{})
        if (result.get('simulation') or result.get('budget_simulation') is not None
                or budget.get('simulation') is not False or budget.get('mode')!='live'
                or budget.get('authorization')!='one_use_claimed'
                or not budget.get('calls')):
            raise ValueError('verified_live_provenance_required')
    return run_mode
