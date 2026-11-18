"""Sequential one-use batch; CLI only rehearses; live requires explicit parent grant."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
from readonly_agent.authority import Admission
from readonly_agent.core import encoded
from readonly_agent.journal import Ledger
from experiments.cohort_preflight.entry import ROOT,read,save
from .guard import CohortAuthority,RehearsalAuthority,RehearsalAdmission
from .parent import Parent,BatchLedger,validate

def execute(parent,token,key=None):
    record=parent.check(token);rehearsal=record['plan']['mode']=='rehearsal'
    if rehearsal and key is not None:raise PermissionError('rehearsal_no_key')
    batch=BatchLedger.create(parent,token);run=parent.root/'run'
    for item in record['plan']['cases']:
        try:
            batch.begin(item['id']);root=run/'children'/item['id']
            if rehearsal:
                auth=RehearsalAuthority(root);auth.prepare_fixture(item['plan']);ticket=auth.claim(item['hash'])
            else:
                auth=CohortAuthority(root);auth.approve(item['plan'],item['hash'],currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True,consent=f"APPROVE {item['hash']} CNY 17");ticket=auth.claim(item['hash'])
            path=run/(item['id']+'.plan.json');save(path,item['plan'])
            message={'path':str(path),'root':str(root),'hash':item['hash'],'token':ticket.token,'parent_pid':os.getpid()}
            if not rehearsal:message['key']=key
            env={'PATH':os.defpath,'DO_NOT_TRACK':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1'}
            proc=subprocess.Popen([str(ROOT/'.venv-openhands/bin/python'),'-B','-m','experiments.cohort_five_evidence_v3.batch','_case'],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            start=time.monotonic()
            try:
                _,_=proc.communicate(encoded(message),timeout=720)
                if proc.returncode:raise RuntimeError('isolated_case_failed')
            finally:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
            childrun=Path(ticket.validate()['run_dir']);result=read(childrun/'result.json')
            if result['status']!='completed':raise RuntimeError(result.get('failure','case_failed'))
            batch.finish(item['id'],Ledger(childrun/'ledger.sqlite',item['hash']))
            save(run/(item['id']+'.timing.json'),{'seconds':time.monotonic()-start})
            print(item['id'],'completed',flush=True)
        except BaseException as error:
            batch.halt(type(error).__name__);break
    summary=batch.audit_summary();summary.update(mode='simulation' if rehearsal else 'live',real_requests=0 if rehearsal else None)
    # Include failed-child reservations and starts, not merely completed pairs.
    child=[]
    for item in record['plan']['cases']:
        base=run/'children'/item['id'];base=base if rehearsal else base/item['hash']
        path=base/'run/ledger.sqlite'
        if path.exists():child.append({'id':item['id'],'budget':Ledger(path,item['hash']).summary()})
    summary['children']=child;summary['all_child_requests']=sum(len(c['budget']['calls']) for c in child)
    summary['request_pending_micro_cny']=sum(c['budget']['reserved_micro_cny'] for c in child)
    summary['all_child_settled_micro_cny']=sum(c['budget']['spent_upper_micro_cny'] for c in child)
    from .cumulative import PRIOR_REQUESTS,PRIOR_UPPER,check_totals
    check_totals(summary['all_child_settled_micro_cny']+summary['request_pending_micro_cny'],summary['all_child_requests'])
    summary['combined_requests']=PRIOR_REQUESTS+summary['all_child_requests']
    summary['combined_upper_micro_cny']=PRIOR_UPPER+summary['all_child_settled_micro_cny']
    summary['cumulative_note']='Rehearsal values are synthetic; prior real usage is a fixed accounting fixture, not new actual spend.' if rehearsal else 'Prior plus current actual response-based upper bound.'
    save(run/'result.json',summary);return summary

def main():
    if sys.argv[1]=='_case':
        from .run import run_pair
        m=json.load(sys.stdin);p=read(m['path']);rehearsal=p['cohort_execution']=='rehearsal'
        auth=(RehearsalAuthority if rehearsal else CohortAuthority)(m['root'])
        ticket=(RehearsalAdmission if rehearsal else Admission)(auth,m['hash'],m['token'])
        def alive():
            if os.getppid()!=m['parent_pid']:raise RuntimeError('batch_parent_lost')
        alive();result=run_pair(m['path'],ticket,key=m.get('key'),parent_alive=alive)
        if result['status']!='completed':raise SystemExit(1)
    elif sys.argv[1]=='--rehearse' and len(sys.argv)==3:
        path=Path(sys.argv[2]).resolve();plan=read(path);validate(plan)
        if plan['mode']!='rehearsal':raise PermissionError('rehearsal_only_cli')
        parent=Parent(path.parent/'rehearsal-authority');parent.prepare(plan)
        result=execute(parent,parent.claim());print('batch',result['halted'],result['all_child_requests'])
    else:raise PermissionError('no_live_cli')
if __name__=='__main__':main()
