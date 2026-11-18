import os,subprocess,tempfile
from experiments.cohort_preflight.entry import ROOT,read,sha,save
out=ROOT/'verification/replay-queries-v1'
for c in read(out/'manifest.json')['cases']:
 assert sha(c['spec'])==c['sha256']
 with tempfile.TemporaryDirectory() as td:
  env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1','MPLCONFIGDIR':td,'XDG_CACHE_HOME':td,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
  p=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(ROOT/'experiments/replay_queries_v1/worker.py'),c['spec'],str(out/c['id'])],cwd=td,env=env,capture_output=True,timeout=300)
  (out/(c['id']+'.execution.txt')).write_bytes(p.stdout+p.stderr)
  if p.returncode:raise RuntimeError('offline_replay_failed:'+c['id'])
  print(c['id'],'replayed',flush=True)
rows=[read(out/c['id']/'result.json') for c in read(out/'manifest.json')['cases']]
save(out/'results.json',{'cases':rows,'real_requests':0,'gold_read':False,'historical_page_exact':all(q['original_page_exact'] for r in rows for q in r['queries'])})
