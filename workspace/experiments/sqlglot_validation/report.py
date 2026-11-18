"""Read-only post-run localization and evidence audit, separate from the worker."""
import json
from pathlib import Path
import sqlite3

from readonly_agent.authority import save_new
from experiments.retrieval_choice.audit import audit
from experiments.locbench_dev.prepare import sha, read
from experiments.locbench_dev.scoring import score
from .control import read_status
from .observability import check_reads


def write_report(authority,h):
    grant=authority.read(h,fresh=False);root=Path(grant['run_dir'])
    summary=read_status(authority,h)
    simulated=summary.get('execution_mode')!='live'
    base=grant['plan']['base_manifest']
    source=Path(grant['plan']['source_manifest']).parent
    rows=[]
    for item in base['cases']:
        label_file='scoring-only/'+item['id']+'.json'
        if sha(source/label_file)!=base['hashes'][label_file]:
            raise PermissionError('frozen_scoring_labels_changed')
        labels=read(source/label_file)
        pair=root/'children'/item['plan_hash']/'run'
        for arm in item['arm_order']:
            state=next(s for s in summary['arms'] if s['case_id']==item['id'] and s['arm']==arm)
            result=read(pair/arm/'result.json') if (pair/arm/'result.json').exists() else None
            calls=[]
            if (pair/'ledger.sqlite').exists():
                with sqlite3.connect((pair/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                    db.row_factory=sqlite3.Row
                    calls=[dict(r) for r in db.execute('SELECT * FROM calls WHERE arm=? ORDER BY id',(arm,))]
            usage=[json.loads(c['response']).get('usage',{}) for c in calls if c['status']=='settled']
            observation=audit(pair/'ledger.sqlite',pair/arm,arm) if result is not None else None
            trace_path=pair/arm/'trace.jsonl'
            events=[json.loads(line) for line in trace_path.read_text().splitlines()] if trace_path.exists() else []
            case_path=Path(__file__).resolve().parents[2]/item['case_file']
            case=read(case_path)
            sources={p:(case_path.parent/case['root']/p).read_text() for p in case['source_files']}
            read_protocol=check_reads(calls,events,sources,labels)
            normalizations=[]
            if result is not None:
                normalizations=[json.loads(line) for line in (pair/arm/'trace.jsonl').read_text().splitlines()
                                if json.loads(line).get('event')=='finish_normalization']
            if simulated and observation is not None:
                observation['simulation']=True;observation['live_auto_selection_observed']=False
                for invocation in observation['invocations']:
                    invocation['selection_category']='scripted_fixture'
            # SDK's quality_measured flag is a legacy fixture flag. Use the
            # outer execution mode and actual completion state, never that flag
            # to imply live quality or let a saved finish hide a worker failure.
            metrics=None if simulated else score({'status':state['status'],
                'answer':result.get('answer') if result else None},labels)
            rows.append({'case':item['id'],'arm':arm,'status':state['status'],'failure':state['failure'],
                'elapsed_wall_seconds':state['elapsed'],'simulation':simulated,
                'requests_reserved':len(calls),'transport_tickets_started':sum(c['transport_started'] for c in calls),
                'spent_upper_micro_cny':sum(c['cost'] or 0 for c in calls if c['status']=='settled'),
                'pending_micro_cny':sum(c['reservation'] for c in calls if c['status']!='settled'),
                'usage_prompt_tokens':sum(u.get('prompt_tokens',0) for u in usage),
                'usage_completion_tokens':sum(u.get('completion_tokens',0) for u in usage),
                'usage_settled_calls':len(usage),'observability':observation,
                'finish_normalizations':normalizations,'read_protocol':read_protocol,
                'answer':result.get('answer') if result else None,
                'localization_score':metrics,'manual_answer_score':None,
                'completion_adjusted_zero':not simulated and state['status']!='completed'})
    report={'suite_hash':h,'execution_mode':summary.get('execution_mode'),'simulation':simulated,
        'rows':rows,'planned_cases':1,'planned_arms':2,
        'completed_arms':sum(r['status']=='completed' for r in rows),
        'real_provider_requests':0 if simulated else None,
        'actual_provider_billing_reconciled':False,'claims_benefit':False,'independent_test':False}
    save_new(root/'measurements.json',report)
    return report
