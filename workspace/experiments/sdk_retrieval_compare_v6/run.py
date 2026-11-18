"""Same OpenHands runner for both arms; only retriever implementation changes."""
import json,os,subprocess,tempfile
from pathlib import Path
from readonly_agent.authority import Admission
from readonly_agent.core import Limits,digest,encoded
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from experiments.cohort_preflight.entry import ROOT,read,save
from .guard import CohortAuthority,RehearsalAdmission,CohortWire,verify
from .fixtures import mock_transport
from .sdk_adapter import run_sdk_case

def run_pair(plan_path,admission,*,key=None,parent_alive=lambda:None):
    plan_path=Path(plan_path).resolve();p=read(plan_path);rehearsal=p['cohort_execution']=='rehearsal'
    if type(admission) is not (RehearsalAdmission if rehearsal else Admission) or (rehearsal and key is not None):raise PermissionError('explicit_matching_admission_required')
    if not rehearsal and type(admission.authority) is not CohortAuthority:raise PermissionError('ablation_authority_required')
    record=admission.validate()
    if record['plan_hash']!=digest(p):raise PermissionError('changed_plan')
    v,s,_=verify(p,p['cohort_execution']);out=Path(record['run_dir']);out.mkdir(exist_ok=False)
    ledger=Ledger.create(out/'ledger.sqlite',p,admission=None if rehearsal else admission);admission.validate(ledger.path)
    class Retrieval:
        snapshot_id=s.identity
        def __init__(self, arm): self.arm=arm
        def retrieve(self,query):
            parent_alive();admission.validate(ledger.path)
            message={'plan':str(plan_path),'query':query,'arm':self.arm,'parent_pid':os.getpid(),'batch_parent_pid':os.getppid()}
            with tempfile.TemporaryDirectory() as td:
                env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
                result=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(ROOT/'experiments/sdk_retrieval_compare_v6/worker.py')],input=encoded(message),cwd=td,env=env,capture_output=True,timeout=300)
                if result.returncode:raise RuntimeError('isolated_retrieval_worker_failed')
                data=json.loads(result.stdout)
                if data['snapshot']!=s.identity:raise RuntimeError('retrieval_snapshot_changed')
                return data['text']
    results=[];started=[]
    try:
        with no_network(out/'profiles') as attempts:
            for arm in p['arm_order']:
                parent_alive();started.append(arm)
                wire=CohortWire(ledger,arm,admission,key,snapshot=s,transport=mock_transport(arm,s,v['issue']) if rehearsal else None,parent_alive=parent_alive)
                result=run_sdk_case(snapshot=s,issue=v['issue'],script=None,output_dir=out/('sdk-'+arm),limits=Limits(max_requests=4),retriever=Retrieval(arm),live=wire)
                results.append({'arm':arm,'status':result['status']})
                if result['status']!='completed':raise RuntimeError('sdk_arm_failed')
            if attempts:raise RuntimeError('unexpected_parent_network')
        outcome={'status':'completed','results':results}
    except BaseException as error:
        with ledger.transaction() as db:db.execute('UPDATE run SET halted=1,reason=COALESCE(reason,?)',(type(error).__name__,))
        outcome={'status':'failed','failure':type(error).__name__,'results':results}
    finally:key=None
    with ledger.transaction() as db:starts=db.execute('SELECT COUNT(*) FROM calls WHERE transport_started=1').fetchone()[0]
    outcome.update(mode='simulation' if rehearsal else 'live',case_id=v['case_id'],plan_hash=digest(p),budget=ledger.summary(),quality_scored=False,real_transport_starts=0 if rehearsal else starts,real_model_requests=0 if rehearsal else None,mock_requests=starts if rehearsal else 0,started_arms=started,second_arm_not_started=len(started)<2)
    save(out/'result.json',outcome);return outcome
