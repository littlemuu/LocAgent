"""Bounded two-process source-only indexing, no semantic/model execution."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .entry import ROOT,read,sha,save
OUT=ROOT/'verification/cohort-preflight-v1'
def main():
    catalog=read(OUT/'runtime-catalog.json')
    if shutil.disk_usage(OUT).free<5*1024**3:raise RuntimeError('insufficient_free_disk')
    (OUT/'body-status').mkdir(exist_ok=False);(OUT/'body').mkdir(exist_ok=False);(OUT/'build-jobs').mkdir(exist_ok=False)
    code={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'experiments/cohort_preflight').glob('*.py')}
    jobs=[]
    for number in range(2):
        p=OUT/'build-jobs'/f'shard-{number}.json'
        save(p,{'shard':number,'cases':catalog['cases'][number::2],'output':str(OUT),'code':code});jobs.append(p)
    def run(job):
        with tempfile.TemporaryDirectory() as td,(OUT/'build-jobs'/(job.stem+'.stderr')).open('xb') as err:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
                'MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            result=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',
                str(ROOT/'experiments/cohort_preflight/build_worker.py'),str(job)],env=env,cwd=td,
                stdout=subprocess.PIPE,stderr=err,timeout=7200)
            return {'shard':job.name,'exit_code':result.returncode}
    with ThreadPoolExecutor(max_workers=2) as pool:workers=list(pool.map(run,jobs))
    rows=[read(p) for p in sorted((OUT/'body-status').glob('*.json'))]
    summary={'planned':len(catalog['cases']),'ready':sum(r['status']=='ready' for r in rows),
        'failed':sum(r['status']=='failed' for r in rows),'unprocessed':len(catalog['cases'])-len(rows),
        'workers':workers,'real_model_requests':0,'semantic_queries':0,'retry':False}
    save(OUT/'body-summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
