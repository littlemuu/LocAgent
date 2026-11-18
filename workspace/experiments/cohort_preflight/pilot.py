"""Exclusive two-case batch, stop on first failure, never retry or authorize live."""
import os,subprocess,tempfile
from pathlib import Path
from .entry import ROOT,read,save,sha
from .batch import run_batch
OUT=ROOT/'verification/cohort-preflight-v1'
def main(run_name='pilot'):
    if run_name not in ('pilot','pilot-v2'):raise ValueError('invalid_run_name')
    run=OUT/run_name;run.mkdir(exist_ok=False);cat=OUT/'runtime-catalog.json';catalog=read(cat)
    code={str(p.relative_to(ROOT)):sha(p) for directory in ['experiments/cohort_preflight','experiments/eval_preflight','readonly_agent']
          for p in (ROOT/directory).glob('*.py')}
    archive=run/'source-archive';archive.mkdir()
    for name in code:
        target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
    save(run/'claim.json',{'case_ids':catalog['pilot_allowlist'],'mode':'simulation','max_requests':16,'retry':False,'code':code})
    def execute(number,id):
        bs=OUT/'body-status'/(id+'.json');jp=run/(f'job-{number}.json')
        save(jp,{'case_id':id,'catalog':str(cat),'catalog_sha256':sha(cat),'body_status':str(bs),
                 'body_status_sha256':sha(bs),'output':str(run/id),'code':code})
        with tempfile.TemporaryDirectory() as td,(run/f'worker-{number}.stderr').open('xb') as err:
            env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
                 'MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
            r=subprocess.run([str(ROOT/'.venv-openhands/bin/python'),'-I','-B',str(ROOT/'experiments/cohort_preflight/pilot_one.py'),str(jp)],
                cwd=td,env=env,stdout=subprocess.PIPE,stderr=err,timeout=360)
        if r.returncode:
            return {'case_id':id,'status':'failed','exit_code':r.returncode}
        return read(run/id/'result.json')
    summary=run_batch(catalog['pilot_allowlist'],execute)
    save(run/'summary.json',summary)
    print('Pilot summary:',[(r['case_id'],r['status']) for r in summary['results']])
if __name__=='__main__':main()
