"""Freeze v4 and validate two BOM cases before carrying forward 128 v3 indexes."""
import hashlib,json,os,subprocess,tempfile,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'engine_adaptation/v4';OLD=ROOT/'engine_adaptation/v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def enc(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def save(p,v):
 with p.open('xb') as f:f.write(enc(v))
def main():
 eng={str(p.relative_to(OUT/'engine')):sha(p) for p in sorted((OUT/'engine').rglob('*')) if p.is_file()}
 harness={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'readonly_agent').glob('*.py')}
 lock={'files':eng,'hash':hashlib.sha256(enc(eng)).hexdigest()};save(OUT/'engine-lock.json',lock)
 worker=ROOT/'diagnostics/bom_adaptation_worker.py';wh=sha(worker)
 previous=json.loads((OLD/'full-validation-results.json').read_text());failed=set(previous['failed'])
 (OUT/'plans').mkdir();(OUT/'validation').mkdir();fixture=OUT/'fixture';fixture.mkdir()
 for n,s in {'bom_crlf.py':'\ufeffdef café():\r\n    return "中\ufeff"\r\n',
  'bom_import.py':'\ufefffrom target import called\n\ndef caller():\n    return called()\n',
  'target.py':'def called():\n    return 1\n'}.items():(fixture/n).write_bytes(s.encode())
 plans=[]
 for old in sorted((OLD/'plans').glob('*.json')):
  p=json.loads(old.read_text());parent=p.pop('plan_hash');assert hashlib.sha256(enc(p)).hexdigest()==parent
  p.update(parent_v3_plan_hash=parent,engine_hash=lock['hash'],harness_files=harness,status='planned_v4_validation')
  if p['id'] not in failed:p.update(reuse=str(OLD/'indexes'/p['id']),attestation=str(OLD/'indexes'/(p['id']+'.attestation.json')))
  p['plan_hash']=hashlib.sha256(enc(p)).hexdigest();save(OUT/'plans'/old.name,p);plans.append(p)
 save(OUT/'manifest.json',{'engine':lock,'harness_files':harness,'worker_hash':wh,'plans':[{'id':p['id'],'hash':p['plan_hash']} for p in plans],
  'model_calls':0,'live_authorization':False,'semantics':'two fresh builds, 128 separately revalidated inherited indexes; original build provenance retained'})
 def check():
  assert all(sha(OUT/'engine'/n)==h for n,h in eng.items())
  assert all(sha(ROOT/n)==h for n,h in harness.items()) and sha(worker)==wh
 def run(p):
  check();start=time.monotonic();req={**p,'output':str(OUT/'validation'/p['id'])}
  with tempfile.TemporaryDirectory() as tmp:
   env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
    'MPLCONFIGDIR':tmp,'XDG_CACHE_HOME':tmp,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','TOKENIZERS_PARALLELISM':'false'}
   r=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(worker)],
    input=enc(req),capture_output=True,cwd=tmp,env=env,timeout=120)
  (OUT/'validation'/(p['id']+'.stderr')).write_bytes(r.stderr)
  row={'id':p['id'],'exit_code':r.returncode,'seconds':time.monotonic()-start,
   'result':json.loads(r.stdout) if r.returncode==0 else None,'plan_hash':p.get('plan_hash')}
  row['artifacts']={str(f.relative_to(OUT/'validation'/p['id'])):sha(f) for f in (OUT/'validation'/p['id']).rglob('*') if f.is_file()}
  save(OUT/'validation'/(p['id']+'.attestation.json'),row);print(p['id'],r.returncode,flush=True)
  return row
 synthetic={'id':'synthetic','source_root':str(fixture),'sources':{p.name:sha(p) for p in fixture.glob('*.py')},'hidden_python_paths':[]}
 first=[run(synthetic)]+[run(p) for p in plans if p['id'] in failed]
 save(OUT/'small-sample-results.json',first)
 assert all(r['exit_code']==0 for r in first),'small_sample_gate_failed'
 rows=first[1:]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for f in as_completed([pool.submit(run,p) for p in plans if p['id'] not in failed]):rows.append(f.result())
 check();assert len(rows)==130
 save(OUT/'full-validation-results.json',{'rows':rows,'ready':sum(r['exit_code']==0 for r in rows),
  'failed':[r['id'] for r in rows if r['exit_code']!=0],'model_calls':0,'semantic_review':'pending','exposure_review':'pending','scoring_review':'pending','live_authorization':False})
if __name__=='__main__':main()
