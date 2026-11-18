"""Post-run audit/metrics and blind grading packets. Never invokes a model."""
import hashlib
import json
from pathlib import Path
import sqlite3

from readonly_agent.authority import save_new
from readonly_agent.core import digest
from experiments.retrieval_choice.audit import audit
from experiments.dev_compare.suite import score_localization
from .control import read_status, PROJECT


def write_report(authority,h):
    grant=authority.read(h,fresh=False);root=Path(grant['run_dir'])
    summary=read_status(authority,h)
    simulated=summary.get('execution_mode')!='live'
    base=grant['plan']['base_manifest']
    rubric_path=PROJECT/'development_suite/v1/evaluation/rubrics.json'
    if hashlib.sha256(rubric_path.read_bytes()).hexdigest()!=base['source_and_rubric_hashes']['evaluation/rubrics.json']:
        raise PermissionError('rubric_changed_before_scoring')
    rubrics={r['id']:r for r in json.loads(rubric_path.read_text())}
    rows=[];blind=[];mapping=[]
    order=sorted((digest([h,c['id'],arm]),c['id'],arm) for c in base['cases'] for arm in c['arm_order'])
    labels={(c,a):f'review-{i+1:02}' for i,(_,c,a) in enumerate(order)}
    for item in base['cases']:
        pair=root/'children'/item['plan_hash']/'run'
        for arm in item['arm_order']:
            state=next(s for s in summary['arms'] if s['case_id']==item['id'] and s['arm']==arm)
            result=json.loads((pair/arm/'result.json').read_text()) if (pair/arm/'result.json').exists() else None
            calls=[]
            if (pair/'ledger.sqlite').exists():
                with sqlite3.connect((pair/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                    db.row_factory=sqlite3.Row
                    calls=[dict(r) for r in db.execute('SELECT * FROM calls WHERE arm=? ORDER BY id',(arm,))]
            usage=[json.loads(c['response']).get('usage',{}) for c in calls if c['status']=='settled']
            observation=audit(pair/'ledger.sqlite',pair/arm,arm) if result is not None else None
            if simulated and observation is not None:
                observation['simulation']=True;observation['live_auto_selection_observed']=False
                for invocation in observation['invocations']:invocation['selection_category']='scripted_fixture'
            score=None if simulated or result is None else score_localization(result,rubrics[item['id']])
            row={'case':item['id'],'arm':arm,'status':state['status'],'failure':state['failure'],
                 'elapsed_wall_seconds':state['elapsed'],'simulation':simulated,
                 'requests_reserved':len(calls),'transport_tickets_started':sum(c['transport_started'] for c in calls),
                 'spent_upper_micro_cny':sum(c['cost'] or 0 for c in calls if c['status']=='settled'),
                 'pending_micro_cny':sum(c['reservation'] for c in calls if c['status']!='settled'),
                 'usage_prompt_tokens':sum(u.get('prompt_tokens',0) for u in usage),
                 'usage_completion_tokens':sum(u.get('completion_tokens',0) for u in usage),
                 'usage_settled_calls':len(usage),'observability':observation,
                 'submitted_files':result['answer'].get('files',[]) if result and isinstance(result.get('answer'),dict) else None,
                 'submitted_entities':result['answer'].get('entities',[]) if result and isinstance(result.get('answer'),dict) else None,
                 'localization_score':score,'manual_answer_score':None,
                 'completion_adjusted_zero':not simulated and state['status']!='completed'}
            rows.append(row)
            if not simulated and state['status']=='completed':
                label=labels[(item['id'],arm)]
                blind.append({'review_id':label,'question':item['plan']['issue'],'answer':result['answer'],
                              'criteria':[{'criterion':c,'score':None,'answer_evidence':None,'source_evidence':None}
                                          for c in rubrics[item['id']]['answer_criteria']]})
                mapping.append({'review_id':label,'case':item['id'],'arm':arm})
    report={'suite_hash':h,'execution_mode':summary.get('execution_mode'),'simulation':simulated,
            'rows':rows,'planned_cases':6,'planned_arms':12,
            'completed_arms':sum(r['status']=='completed' for r in rows),
            'real_provider_requests':0 if simulated else None,
            'actual_provider_billing_reconciled':False,'claims_benefit':False}
    save_new(root/'measurements.json',report)
    if not simulated:
        save_new(root/'blind-review-packets.json',blind)
        save_new(root/'operator-review-map.json',mapping)
    return report
