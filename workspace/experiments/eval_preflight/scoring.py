"""Explicit metric dialects. Historical results and scorers remain untouched."""
VERSION='localization-metrics-v1'

def ranked_metrics(gold,predicted,k,*,dialect='strict'):
    if type(k) is not int or k not in (1,3,5):raise ValueError('unsupported_k')
    if dialect not in ('strict','upstream_reference'):raise ValueError('unsupported_dialect')
    if any(not isinstance(v,list) or any(not isinstance(x,str) or not x for x in v) for v in (gold,predicted)):
        raise ValueError('invalid_ids')
    if len(predicted)>5 or len(set(predicted))!=len(predicted):raise ValueError('invalid_submission')
    if dialect=='upstream_reference':
        normalize=lambda x:x[:-9] if x.endswith('.__init__') else x
        gold=list(dict.fromkeys(map(normalize,gold)))
        predicted=list(dict.fromkeys(map(normalize,predicted)))
    targets=set(gold)
    if not targets:return {'eligible':False,'reason':'empty_gold_requires_review','Acc':None,'Recall':None,'Hit':None}
    # Strict retains every unique gold. Reference mode mirrors max_k=10 ideal vector.
    denominator=min(len(targets),10) if dialect=='upstream_reference' else len(targets)
    hits=len(set(predicted[:k])&targets)
    return {'eligible':True,'Acc':int(hits==min(k,denominator)),
            'Recall':hits/denominator,'Hit':int(hits>0),'hits':hits,'gold':len(targets),
            'recall_denominator':denominator,'k':k,'dialect':dialect}

def evaluate_completed(result,gold,k,*,dialect='strict'):
    if result.get('simulation'):raise ValueError('simulation_is_not_quality')
    if result.get('status')!='completed':
        return {'quality':None,'technical_failure':result.get('status')!='not_run',
                'not_run':result.get('status')=='not_run','planned_denominator_adjusted_zero':0}
    return {'quality':ranked_metrics(gold,result['entities'],k,dialect=dialect),'technical_failure':False}
