"""Continue the frozen offline technical build after the small-sample gate."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'engine_adaptation/v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def save(p,x):
 with p.open('xb') as f:f.write(enc(x))
def main():
 gate=json.loads((OUT/'validation-results.json').read_text())
 assert len(gate['rows'])==10 and all(r['exit_code']==0 and r['result']['status']=='ready' for r in gate['rows'])
 assert json.loads((OUT/'boundary-results.json').read_text())['status']=='passed'
 manifest=json.loads((OUT/'manifest.json').read_text())
 worker=ROOT/'diagnostics/adaptation_index_worker_v2.py';worker_hash=sha(worker)
 def check():
  assert all(sha(OUT/'engine'/n)==h for n,h in manifest['engine']['files'].items())
  assert all(sha(ROOT/n)==h for n,h in manifest['harness_files'].items())
  assert sha(worker)==worker_hash
 check()
 remaining=[]
 for ref in manifest['plans']:
  p=json.loads((OUT/'plans'/(ref['id']+'.json')).read_text());h=p.pop('plan_hash')
  assert h==ref['hash']==hashlib.sha256(enc(p)).hexdigest();p['plan_hash']=h
  if p['id'] in gate['untested_ids']:remaining.append(p)
 save(OUT/'expansion-plan.json',{'cases':[p['id'] for p in remaining],'worker_sha256':worker_hash,
  'max_concurrent_workers':2,'wall_seconds_per_case':120,'cpu_seconds_per_case':90,'model_calls':0,
  'scope':'Technical source/index validation only; no issue text or scoring labels used.'})
 def run(p):
  check();dest=OUT/'indexes'/p['id'];assert not dest.exists()
  started=time.monotonic();req={**p,'output':str(dest)}
  with tempfile.TemporaryDirectory(prefix='adaptation-expansion-') as tmp:
   env={'PATH':os.defpath,'HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True',
    'MPLCONFIGDIR':tmp,'XDG_CACHE_HOME':tmp,'TOKENIZERS_PARALLELISM':'false','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
   try:
    r=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(worker)],
     input=enc(req),env=env,cwd=tmp,capture_output=True,timeout=120)
    (OUT/'indexes'/(p['id']+'.stderr')).write_bytes(r.stderr)
    result={'id':p['id'],'exit_code':r.returncode,'result':json.loads(r.stdout) if r.returncode==0 else None}
   except subprocess.TimeoutExpired as exc:
    (OUT/'indexes'/(p['id']+'.stderr')).write_bytes(exc.stderr or b'')
    result={'id':p['id'],'exit_code':'timeout','result':None}
  result.update(seconds=time.monotonic()-started,plan_hash=p['plan_hash'],
   artifacts={str(f.relative_to(dest)):sha(f) for f in dest.rglob('*') if f.is_file()})
  save(OUT/'indexes'/(p['id']+'.attestation.json'),result)
  return result
 rows=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(run,p) for p in remaining]
  for f in as_completed(futures):
   r=f.result();rows.append(r);print(len(rows),len(remaining),r['id'],r['exit_code'],flush=True)
 allrows=[r for r in gate['rows'] if r['id']!='synthetic']+rows
 check()
 save(OUT/'full-validation-results.json',{'rows':allrows,'ready':sum(r['exit_code']==0 for r in allrows),
  'failed':[r['id'] for r in allrows if r['exit_code']!=0],'model_calls':0,
  'semantic_review':'pending','exposure_review':'pending','scoring_review':'pending','live_authorization':False})
if __name__=='__main__':main()
