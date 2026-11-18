"""One isolated source-only case pair, simulation-only and no inherited env."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.cohort_preflight.entry import read,sha,save,load_entry,checked_file
from experiments.eval_preflight.common_contract import SharedWire,CONTRACT
from experiments.cohort_preflight.sdk_adapter import run_sdk_case
from readonly_agent.core import Limits,encoded,digest
from readonly_agent.preparation import make_plan,PreparationSession
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network

def main():
    job=read(sys.argv[1]);out=Path(job['output']);out.mkdir(exist_ok=False)
    if any(sha(ROOT/n)!=h for n,h in job['code'].items()):raise ValueError('pilot_code_changed')
    cat=read(checked_file(job['catalog'],job['catalog_sha256']));row=next(r for r in cat['cases'] if r['id']==job['case_id'])
    if row['id'] not in cat['pilot_allowlist']:raise PermissionError('pilot_scope')
    value,snapshot=load_entry(row['entry'],row['entry_sha256'])
    status=read(checked_file(job['body_status'],job['body_status_sha256']))
    if status['status']!='ready' or status['snapshot']!=snapshot.identity:raise ValueError('body_not_ready')
    request={k:job[k] for k in ('catalog','catalog_sha256','case_id','body_status','body_status_sha256')}
    def worker(extra):
        if any(sha(ROOT/n)!=h for n,h in job['code'].items()):raise ValueError('pilot_code_changed')
        with tempfile.TemporaryDirectory() as td:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
                 'MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            result=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',
                str(ROOT/'experiments/cohort_preflight/pair_worker.py')],input=encoded({**request,**extra}),
                cwd=td,env=env,capture_output=True,timeout=120)
            if result.returncode:
                (out/'worker-error.stderr').write_bytes(result.stderr);raise RuntimeError('native_worker_failed')
            return json.loads(result.stdout)
    with no_network(out/'profiles') as attempts:
        plan=make_plan(snapshot,value['issue'],ROOT/'engine_adaptation/v4/engine')
        plan.update(purpose='Two exposed development cases; adapted systems entry/isolation validation, no quality claim',
            comparison_contract=CONTRACT,cohort_entry={'case_id':row['id'],'entry_sha256':row['entry_sha256']},
            comparison_names=['LocAgent-graph+physical-line80-BM25/adapted','OpenHands-basic+entity-BM25/adapted'],
            code=job['code'],body_status_sha256=job['body_status_sha256'],public_pricing_checked_utc_date=None,
            pricing_status='historical_assumption_not_current_quote')
        save(out/'plan.json',plan);ledger=Ledger.create(out/'simulation.sqlite',plan)
        native=worker({'mode':'native','ledger':str(ledger.path),'plan_hash':digest(plan)});save(out/'native.json',native)
        class Cache:
            snapshot_id=snapshot.identity
            def retrieve(self,query):return worker({'mode':'query','query':query})['text']
        def response(n,args,ident):return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':ident,'name':n,'input':args}]}
        query='SetItem' if row['id'].startswith('tobymao') else 'RecursionError'
        if query not in value['issue']:raise ValueError('query_not_in_issue')
        script=[response('list_files',{'offset':0},'list'),response('read_file',{'path':sorted(snapshot.files)[0],'start_line':1,'end_line':20},'read'),
            response('locagent_retrieve',{'query':query,'offset':0},'retrieve'),
            response('finish',{'files':[],'entities':[],'answer':'Offline fixture; no localization score.'},'end')]
        with patch('readonly_agent.preparation.BudgetedWire',lambda led,arm:SharedWire(led,arm,snapshot)):
            session=PreparationSession(ledger,'retrieval')
        sdk=run_sdk_case(snapshot=snapshot,issue=value['issue'],script=script,output_dir=out/'sdk',
            limits=Limits(max_requests=4),retriever=Cache(),preparation=session)
        if sdk['status']!='completed':session.wire.fail('sdk_failed');raise RuntimeError('sdk_failed')
        if attempts:raise RuntimeError('unexpected_network_attempt')
        save(out/'result.json',{'case_id':row['id'],'snapshot':snapshot.identity,'mode':'simulation',
            'status':'completed','mock_requests':len(ledger.summary()['calls']),'real_model_requests':0,'quality_scored':False,
            'native_body_queries':len(native['body_queries']),'native_requests':len(native['requests']),
            'sdk_requests':sdk['requests'],'ledger':ledger.summary(),'source_hashes':dict(snapshot.hashes)})
    print('Isolated case pair complete',flush=True)
if __name__=='__main__':main()
