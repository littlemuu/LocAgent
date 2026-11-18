import os
import subprocess
import tempfile
from experiments.cohort_preflight.entry import ROOT,read,save,sha

out=ROOT/'verification/retrieval-evidence-v6'
for c in read(out/'manifest.json')['cases']:
    assert sha(c['spec'])==c['sha256']
    with tempfile.TemporaryDirectory() as td:
        env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        p=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(ROOT/'experiments/retrieval_evidence_v6/worker.py'),c['spec'],str(out/c['id'])],cwd=td,env=env,capture_output=True,timeout=300)
        (out/(c['id']+'.execution.txt')).write_bytes(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('offline_check_failed:'+c['id'])
        print(c['id'],'passed',flush=True)
save(out/'results.json',{'cases':[read(out/c['id']/'result.json') for c in read(out/'manifest.json')['cases']],
                        'real_requests':0,'gold_read':False,'network_guard_completed':True})
