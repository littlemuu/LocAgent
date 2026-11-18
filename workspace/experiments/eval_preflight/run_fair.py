"""Paired whole-system offline check, one exposed SQLGlot development case."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch
from readonly_agent.core import Snapshot,Limits,encoded,digest
from readonly_agent.offline import no_network
from readonly_agent.preparation import make_plan,PreparationSession
from .sdk_adapter import run_sdk_case
from readonly_agent.journal import Ledger
from .common_contract import SharedWire,CONTRACT

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'verification/eval-fair-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('xb') as f:f.write(encoded(v))

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    case='tobymao__sqlglot-3417';mp=ROOT/'engine_adaptation/v4/adapted-manifest.json'
    m=json.loads(mp.read_text());item=next(r for r in m['cases'] if r['id']==case)
    p=json.loads((ROOT/'engine_adaptation/v4/plans'/(case+'.json')).read_text())
    snap=Snapshot(p['source_root'],list(p['sources']),hidden_python_paths=p['hidden_python_paths'])
    issue=json.loads((ROOT/'locbench_openhands/v5/cases'/case/'case.json').read_text())['issue']
    assert 'SET TAG' in issue and 'SetItem' in issue
    binding={'case':case,'snapshot':snap.identity,'adapted_manifest_sha256':sha(mp),
             'attestation_sha256':sha(Path(item['index_attestation'])),'body_root':str(OUT/'body')}
    sources={str(f.relative_to(ROOT)):sha(f) for f in sorted((ROOT/'experiments/eval_preflight').glob('*.py'))}
    archive=OUT/'adapter-source';archive.mkdir(exist_ok=False)
    for name,h in sources.items():
        data=(ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==h
        (archive/Path(name).name).write_bytes(data)
    def worker(args):
        assert all(sha(ROOT/n)==h for n,h in sources.items())
        with tempfile.TemporaryDirectory() as td:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1',
                 'HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,
                 'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            r=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',
                str(ROOT/'experiments/eval_preflight/fair_worker.py')],input=encoded({**binding,**args}),
                cwd=td,env=env,capture_output=True,timeout=120)
            if r.returncode:
                with (OUT/'worker-failure.stderr').open('xb') as f:f.write(r.stderr)
                raise RuntimeError('offline_worker_failed')
            return json.loads(r.stdout)
    with no_network(OUT/'profiles') as attempts:
        body=worker({'mode':'build_body'});save(OUT/'body-build.json',body)
        binding['body_attestation_hash']=sha(OUT/'body'/case/'attestation.json')
        plan=make_plan(snap,issue,ROOT/'engine_adaptation/v4/engine')
        plan.update(purpose='Whole-system comparison adapter validation; exposed development case, scripted responses only',
            public_pricing_checked_utc_date=None,pricing_status='historical_assumption_not_reverified',
            comparison_contract=CONTRACT,adapter_sources=sources,cache_binding=binding,
            arm_meaning={'baseline':'adapted-native-LocAgent','retrieval':'OpenHands-with-entity-LocAgent'})
        save(OUT/'proposal.json',plan);ledger=Ledger.create(OUT/'simulation.sqlite',plan)
        native=worker({'mode':'native','issue':issue,'ledger':str(ledger.path),'plan_hash':digest(plan)})
        save(OUT/'native.json',native)
        class Cache:
            snapshot_id=snap.identity
            def retrieve(self,query):return worker({'mode':'query','query':query})['text']
        def response(n,a):return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':'sdk-'+n,'name':n,'input':a}]}
        script=[response('search_text',{'query':'SET TAG','offset':0}),
            response('read_file',{'path':sorted(snap.files)[0],'start_line':1,'end_line':20}),
            response('locagent_retrieve',{'query':'SetItem','offset':0}),
            response('finish',{'files':[],'entities':[],'answer':'Scripted connectivity only; no quality claim.'})]
        with patch('readonly_agent.preparation.BudgetedWire',lambda led,arm:SharedWire(led,arm,snap)):
            session=PreparationSession(ledger,'retrieval')
        sdk=run_sdk_case(snapshot=snap,issue=issue,script=script,output_dir=OUT/'sdk',retriever=Cache(),
                         limits=Limits(max_requests=4),preparation=session)
        if sdk['status']!='completed':
            session.wire.fail('sdk_run_failed');raise RuntimeError('sdk_run_failed')
        save(OUT/'sdk-common-requests.json',session.wire.requests)
        assert not attempts
        assert len(native['requests'])==len(session.wire.requests)==4
        for requests in [native['requests'],session.wire.requests]:
            assert all(r['model']=='deepseek-flash' and r['max_tokens']==2048 and r['temperature']==0
                       and r['thinking']=={'type':'disabled'} and len(encoded(r))<=65536 for r in requests)
            assert [t['function']['name'] for t in requests[-1]['tools']]==['finish']
        assert native['requests'][-1]['tools']==session.wire.requests[-1]['tools']
        try:ledger.claim('baseline')
        except Exception:duplicate=True
        else:duplicate=False
        assert duplicate
        save(OUT/'acceptance.json',{'simulation':True,'real_model_requests':0,'network_attempts':0,
            'mock_requests':8,'native_finished':True,'sdk_finished':True,'body_backend_exercised':True,
            'native_tool_calls':native['tool_calls'],'sdk_tool_calls':sdk['tool_calls'],
            'native_source_bytes':native['native_result']['diagnostics']['source_content_utf8_bytes'],
            'sdk_source_bytes':sdk['source_bytes'],'identical_wire_model_limits_finish_schema':True,
            'duplicate_arm_rejected':duplicate,'contract':CONTRACT,'plan_hash':digest(plan),
            'quality_scored':False,'live_enabled':False,'ledger':ledger.summary(),
            'limitations':['Whole-system treatment includes different prompts/tools/rankers; no retrieval causal claim.',
                'Source-body backend uses fixed 80-line chunks, not upstream EpicSplitter.',
                'Single exposed development case; semantic/exposure eligibility remains separate.',
                'New comparison live authorization adapter remains locked; old grants are not reusable.']})
    print('Paired adapted systems finished: 8 mock requests, 0 real requests; live remains locked.')

if __name__=='__main__':main()
