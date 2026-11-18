import sys
from readonly_agent.preparation import make_plan
from readonly_agent.core import digest
from experiments.cohort_preflight.entry import ROOT,read,sha,save,load_entry
from .common_contract import CONTRACT
from .guard import IDS,NAMES,SENT,source_hashes
from .parent import validate
from .cumulative import prior_binding,NEW_MICRO_CNY

def candidate(mode):
    cases=[]
    for i,row in enumerate(read(ROOT/'verification/dev37-preparation-v4/runtime-cases.json')['cases']):
        if row['id'] not in IDS: continue
        v,s=load_entry(row['entry'],row['entry_sha256'])
        p=make_plan(s,v['issue'],ROOT/'engine_adaptation/v4/engine')
        p.update(cohort_admission_version=1,cohort_execution=mode,cohort_sources=source_hashes(),comparison_names=NAMES,comparison_contract=CONTRACT,send_categories=SENT,live_transport_enabled=mode=='live',arm_order=['baseline','retrieval'] if len(cases)%2==0 else ['retrieval','baseline'],purpose='6 exposed development cases selected by historical retrieval use; same OpenHands evidence-v6 retrieval original/selfcheck-v7 prompt comparison; no independent test claim',public_pricing_checked_utc_date=None,pricing_status='reconfirm before user approval',cohort_binding={k:row[k] for k in ('entry','entry_sha256','body_status','body_status_sha256')})
        p['cohort_binding']['case_id']=row['id']
        cases.append({'id':row['id'],'plan':p,'hash':digest(p)})
    batch={'version':1,'mode':mode,'cases':cases,'sources':source_hashes(),'max_requests':48,'budget_micro_cny':NEW_MICRO_CNY,'prior_usage':prior_binding(),'cumulative_request_limit':474,'cumulative_micro_cny_limit':107000000,'authorization':'not_granted','scoring_hash':sha(ROOT/'experiments/eval_preflight/scoring.py'),'design_hash':sha(ROOT/'verification/sdk-finish-selfcheck-v7-preparation/proposal.json')}
    validate(batch);return batch

def main():
    name=sys.argv[1]
    if not name.startswith('sdk-finish-selfcheck-v7-batch') or '/' in name:raise ValueError('output_name')
    out=ROOT/'verification'/name;out.mkdir(exist_ok=False)
    for mode in ('live','rehearsal'):save(out/(mode+'.json'),candidate(mode))
    print('Frozen unapproved batch; no grant or request')
if __name__=='__main__':main()
