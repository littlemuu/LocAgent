"""Stage 130 metadata-only plans; validate a fixture, two exposed cases, then hidden cases."""
import hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'engine_adaptation/v1'
BATCH=Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113')
PYTHON='/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def save(p,x):
    with p.open('xb') as f:f.write(enc(x))
def main():
    lock=json.loads((OUT/'engine-lock.json').read_text())
    assert all(sha(OUT/'engine'/n)==h for n,h in lock['files'].items())
    harness={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'readonly_agent').glob('*.py')}
    (OUT/'plans').mkdir(exist_ok=False);(OUT/'indexes').mkdir(exist_ok=False)
    plans=[]
    for row in json.loads((BATCH/'technical-ready-current-engine.json').read_text()):
        mp=Path(row['registry'])/(row['source_id']+'.json');assert sha(mp)==row['source_id'][9:]
        m=json.loads(mp.read_text());bundle=mp.parent/m['bundle']
        sources={p[5:]:h for p,h in m['artifacts'].items() if p.startswith('repo/') and p.endswith('.py')}
        hidden=[n for n in sources if any(p.startswith('.') for p in n.split('/'))]
        plan={'id':row['instance_id'],'parent_source_id':row['source_id'],'parent_manifest':str(mp),
            'commit':m['task']['base_commit'],'engine_hash':lock['hash'],'harness_files':harness,
            'source_root':str(bundle/'repo'),'sources':sources,'hidden_python_paths':hidden,
            'projection':'all manifest-bound Python including explicit hidden Python; no labels or patches',
            'semantic_review':'pending','exposure_review':'pending','scoring_review':'pending',
            'authorization':'none','model_calls':0,'status':'planned_not_validated'}
        plan['plan_hash']=hashlib.sha256(enc(plan)).hexdigest()
        save(OUT/'plans'/(row['instance_id']+'.json'),plan);plans.append(plan)
    save(OUT/'manifest.json',{'version':1,'engine':lock,'harness_files':harness,'plans':[{'id':p['id'],'hash':p['plan_hash']} for p in plans],
        'status':'offline_preparation_not_live_authorization','python_executable':PYTHON})
    fixture=OUT/'fixture';fs={str(p.relative_to(fixture)):sha(p) for p in fixture.rglob('*.py')}
    selected=[{'id':'synthetic','source_root':str(fixture),'sources':fs,'hidden_python_paths':['.ci/helper.py'],
        'query':'.ci/helper.py:Box.__init__'}]
    selected += [next(p for p in plans if p['id']==n) for n in ['tobymao__sqlglot-3417','Delgan__loguru-1239']]
    selected += [p for p in plans if p['hidden_python_paths']]
    statuses=[]
    for i,p in enumerate(selected):
        assert all(sha(OUT/'engine'/n)==h for n,h in lock['files'].items())
        assert all(sha(ROOT/n)==h for n,h in harness.items())
        req={**p,'output':str(OUT/'indexes'/p['id'])};started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='adaptation-worker-') as tmp:
            env={'PATH':os.defpath,'MPLCONFIGDIR':tmp,'XDG_CACHE_HOME':tmp,'HF_HUB_OFFLINE':'1',
                'HF_DATASETS_OFFLINE':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True','TOKENIZERS_PARALLELISM':'false',
                'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            try:
                run=subprocess.run([PYTHON,'-I','-B',str(ROOT/'diagnostics/adaptation_index_worker.py')],input=enc(req),
                    cwd=tmp,env=env,capture_output=True,timeout=120)
                (OUT/'indexes'/(p['id']+'.stderr')).write_bytes(run.stderr)
                status={'id':p['id'],'exit_code':run.returncode,'seconds':time.monotonic()-started,
                    'result':json.loads(run.stdout) if run.returncode==0 else None}
            except subprocess.TimeoutExpired:
                status={'id':p['id'],'exit_code':'timeout','seconds':time.monotonic()-started,'result':None}
        artifacts={str(f.relative_to(OUT/'indexes'/p['id'])):sha(f) for f in (OUT/'indexes'/p['id']).rglob('*') if f.is_file()}
        status['artifacts']=artifacts;statuses.append(status)
        save(OUT/'indexes'/(p['id']+'.attestation.json'),status)
        print(p['id'],status['exit_code'],flush=True)
        if status['exit_code']!=0 and i<3:
            break  # Small-sample gate: never expand after a core failure.
    save(OUT/'validation-results.json',{'rows':statuses,'model_calls':0,
        'untested_ids':[p['id'] for p in plans if p['id'] not in {s['id'] for s in statuses}],
        'full_130_ready':False})
if __name__=='__main__':main()
