"""One exposed SQLGlot case. Freeze, simulate SDK pair and native connectivity."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'verification/eval-preflight-v2'
from readonly_agent.core import Snapshot,Limits,digest,encoded
from readonly_agent.offline import no_network
from readonly_agent.preparation import make_plan,PreparationSession
from readonly_agent.journal import Ledger
from readonly_agent.openhands_replay import run_sdk_case
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('xb') as f:f.write(encoded(v))
def main():
 OUT.mkdir(exist_ok=False,parents=True)
 case='tobymao__sqlglot-3417';mp=ROOT/'engine_adaptation/v4/adapted-manifest.json'
 m=json.loads(mp.read_text());item=next(x for x in m['cases'] if x['id']==case)
 p=json.loads((ROOT/'engine_adaptation/v4/plans'/(case+'.json')).read_text())
 snap=Snapshot(p['source_root'],list(p['sources']),hidden_python_paths=p['hidden_python_paths'])
 oldcase=json.loads((ROOT/'locbench_openhands/v5/cases'/case/'case.json').read_text())
 issue=oldcase['issue'];assert 'SetItem' in issue
 worker=Path(__file__).with_name('cache_worker_v2.py');worker_hash=sha(worker)
 request={'case':case,'snapshot':snap.identity,'adapted_manifest_sha256':sha(mp),'attestation_sha256':sha(Path(item['index_attestation']))}
 def cached(data):
  assert sha(worker)==worker_hash
  with tempfile.TemporaryDirectory() as tmp:
   env={'PATH':os.defpath,'LITELLM_LOCAL_MODEL_COST_MAP':'True','HF_HUB_OFFLINE':'1','HF_DATASETS_OFFLINE':'1',
    'MPLCONFIGDIR':tmp,'XDG_CACHE_HOME':tmp,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
   r=subprocess.run(['/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.venv/bin/python','-I','-B',str(worker)],
    input=encoded({**request,**data}),env=env,cwd=tmp,capture_output=True,timeout=90)
   if r.returncode:
    (OUT/'worker-failure.stderr').write_bytes(r.stderr);raise RuntimeError('cache_worker_failed')
   return json.loads(r.stdout)
 class Cache:
  snapshot_id=snap.identity
  def retrieve(self,query):
   value=cached({'mode':'query','query':query});assert value['snapshot']==self.snapshot_id and value['cache_loaded'];return value['text']
 plan=make_plan(snap,issue,ROOT/'engine_adaptation/v4/engine')
 plan.update(purpose='Exposed SQLGlot development-only offline cache integration; no performance claim',
  public_pricing_checked_utc_date=None,pricing_status='historical_assumption_not_reverified_no_network',
  cached_index_binding=request,preflight_worker_sha256=worker_hash)
 save(OUT/'proposal.json',plan);ledger=Ledger.create(OUT/'simulation.sqlite',plan)
 def response(name,args):return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':'scripted-'+name,'name':name,'input':args}]}
 path=sorted(snap.files)[0];results={}
 with no_network(OUT/'profiles') as attempts:
  for arm in ('baseline','retrieval'):
   script=[response('list_files',{'offset':0}),response('read_file',{'path':path,'start_line':1,'end_line':20}),
    response('locagent_retrieve' if arm=='retrieval' else 'search_text',{'query':'SetItem','offset':0}),
    response('finish',{'files':[],'entities':[],'answer':'Scripted connectivity only; no quality judgment.'})]
   session=PreparationSession(ledger,arm)
   results[arm]=run_sdk_case(snapshot=snap,issue=issue,script=script,output_dir=OUT/arm,
    retriever=Cache() if arm=='retrieval' else None,limits=Limits(max_requests=4),preparation=session)
   save(OUT/(arm+'-requests.json'),session.requests)
   assert results[arm]['status']=='completed'
  native=cached({'mode':'native','issue':issue});save(OUT/'native-connectivity.json',native)
  assert len(native['requests'])==4 and native['native_result']['diagnostics']['termination_reason']=='finished'
  # Preserve frozen plans: a normal current-plan check rejects the previous live manifest.
  from readonly_agent.authority import current_plan
  previous=json.loads((ROOT/'locbench_live/v3/manifest.json').read_text())['base_manifest']['cases'][0]['plan']
  try:current_plan(previous)
  except Exception as e:old_gate={'rejected':True,'type':type(e).__name__,'reason':str(e)}
  else:raise AssertionError('old_plan_not_rejected')
  try:cached({'mode':'query','query':'SetItem','adapted_manifest_sha256':'0'*64})
  except RuntimeError:cache_tamper_blocked=True
  else:raise AssertionError('cache_hash_tamper_accepted')
  summary=ledger.summary()
  try:ledger.claim('baseline')
  except Exception:duplicate=True
  else:duplicate=False
  assert duplicate and not attempts
 save(OUT/'acceptance.json',{'sdk_pair_completed':True,'native_connectivity_finished':True,'native_fair_pair_ready':False,
  'real_model_requests':0,'sdk_mock_requests':8,'native_mock_requests':4,'network_attempts':0,
  'old_plan_gate':old_gate,'duplicate_arm_blocked':duplicate,'ledger':summary,'quality_scored':False,'cache_hash_tamper_blocked':cache_tamper_blocked,
  'plan_hash':digest(plan),'sdk_pair':'same OpenHands, retrieval availability only',
  'native':'locally modified bounded-v1 GraphLocalizer, not pristine upstream LocAgent'})
 print('SDK pair: 8 mocks; native: 4 mocks; real requests: 0; no quality score.')
if __name__=='__main__':main()
