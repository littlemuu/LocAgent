"""Fixed-denominator sequential simulation controller, including partial failure."""
def run_batch(case_ids,executor):
    if not case_ids or len(set(case_ids))!=len(case_ids):raise ValueError('invalid_case_scope')
    results=[]
    for index,id in enumerate(case_ids):
        try:
            result=executor(index,id)
            if result.get('case_id')!=id or result.get('status') not in ('completed','failed'):
                raise ValueError('foreign_or_invalid_case_result')
            if result['status']=='completed' and (result.get('mode')!='simulation'
                or type(result.get('mock_requests')) is not int or not 0<=result['mock_requests']<=8
                or result.get('real_model_requests')!=0):
                raise ValueError('simulation_budget_or_mode_mismatch')
        except Exception as error:
            result={'case_id':id,'status':'failed','error_type':type(error).__name__}
        results.append(result)
        if result['status']!='completed':break
    return {'planned_cases':len(case_ids),'completed':sum(r['status']=='completed' for r in results),
        'failed':sum(r['status']=='failed' for r in results),'not_started':len(case_ids)-len(results),
        'results':results,'real_model_requests':0,'quality_scored':False,'retry':False,
        'isolation':'fresh process, ledger, conversation and caches per case'}
