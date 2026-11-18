"""Explicit current-round runner: one live smoke, three offline replays, 8 paired dev tasks, stop."""
import argparse,copy,fcntl,hashlib,json,os,platform,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from .common import ROOT,CONFIG,allow,manifest,rows,write_json,digest
from .driver import image_name,inspect_image,config_binding,source_snapshot
from .ledger import Ledger
from .sandbox import DockerSandbox

class ReplayTransport:
 """Replays historical provider responses; never sends a request or feeds history to live API."""
 def __init__(self,wire,out):
  self.files=sorted(Path(wire).glob('response-*.json'),key=lambda p:int(p.stem.split('-')[-1]));self.index=0;self.records=[];self.out=Path(out);self.out.mkdir(parents=True)
 def exchange(self,payload):
  if self.index>=len(self.files):raise RuntimeError('replay_exhausted')
  f=self.files[self.index];raw=json.loads(f.read_text());self.index+=1
  self.records.append({'usage':raw['usage'],'actual_model':raw['model'],'charged_upper_microcny':0,'replayed':True})
  write_json(self.out/f'replay-{self.index}.json',{'original_response_path':str(f),'original_response_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'current_request_sha256':digest(payload),'mode':'recorded response replay; no network; not fresh model performance'})
  return raw

def validate_authorization(path):
 a=json.loads(Path(path).read_text());m=manifest()
 if (a.get('approved') is not True or a.get('budget_cny')!=50 or a.get('ids_sha256')!=m['ids_sha256']
     or a.get('trial_ids')!=m['selection_order'][:8] or a.get('smoke_live')!=[['astropy__astropy-14182','A']]
     or a.get('max_trial_episodes')!=16 or a.get('arm_order')!=['A','B'] or a.get('pause_after')!=8):
  raise PermissionError('invalid_checkpoint_authorization')
 return a

def stop_decision(episodes):
 if len(episodes)!=16 or any(e.get('status')!='completed' for e in episodes):
  return {'status':'stopped_incomplete','continue_allowed':False,'empty_patch_rate':None,'reason':'incomplete or technical failure'}
 empty=sum(e['empty_patch'] for e in episodes);rate=empty/16
 return {'status':'stopped_loss_threshold' if rate>.5 else 'paused_checkpoint','empty_patch_count':empty,'empty_patch_rate':rate,'resolved_count':sum(e['resolved'] is True for e in episodes),'continue_condition_met':rate<=.5,'continue_allowed':False,'reason':'empty patch rate >50%' if rate>.5 else 'mandatory user checkpoint; no automatic continuation'}

class Runner:
 def __init__(self,out,credential,authorization,old_v2,old_v3):
  from .transport import LiveTransport
  self.LiveTransport=LiveTransport;self.out=Path(out).resolve();self.out.mkdir(parents=True,exist_ok=True);self.credential=credential;self.auth=validate_authorization(authorization)
  if platform.system()!='Linux' or platform.machine()!='x86_64':raise PermissionError('cloud_x86_required')
  self.lock=(self.out/'run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.path=self.out/'state.json';self.binding=config_binding();self.old_v2=Path(old_v2);self.old_v3=Path(old_v3)
  self.tasks={r['instance_id']:r for r in rows()};self.ledger=Ledger(self.out/'ledger.json',50)
  if self.path.exists():
   self.state=json.loads(self.path.read_text())
   if self.state['code_binding']!=self.binding or self.state['authorization_sha256']!=digest(self.auth):raise RuntimeError('resume_binding_changed')
   if self.state.get('failed') or any(s['status']=='running' for s in self.state['steps'].values()):raise RuntimeError('no_automatic_retry_after_failed_or_uncertain_step')
  else:self.state={'code_binding':self.binding,'authorization_sha256':digest(self.auth),'started_at':time.time(),'steps':{},'failed':None,'trial_ids':self.auth['trial_ids']};write_json(self.path,self.state)
 def step(self,key,fn):
  if key in self.state['steps']:
   v=self.state['steps'][key]
   if v['status']=='completed':return v['result']
   raise RuntimeError('step_not_retryable')
  v={'status':'running','started_at':time.time()};self.state['steps'][key]=v;write_json(self.path,self.state)
  try:
   result=fn()
   if result.get('status')!='completed':raise RuntimeError('step_not_completed: '+str(result.get('technical_failure') or result.get('status')))
   v.update(status='completed',result=result,ended_at=time.time());write_json(self.path,self.state);return result
  except Exception as e:
   v.update(status='failed',error=type(e).__name__+': '+str(e)[:1000],ended_at=time.time());self.state['failed']=key;write_json(self.path,self.state);raise
 def image(self,identifier):
  allow(identifier);name=image_name(identifier);log=self.out/'images'/identifier;log.mkdir(parents=True,exist_ok=True)
  exists=subprocess.run(['docker','image','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
  start=time.time()
  if not exists:
   free=os.statvfs(ROOT);available=free.f_bavail*free.f_frsize
   if available<25*1024**3:raise RuntimeError('insufficient_free_disk_before_pull')
   with (log/'pull.log').open('w') as f:subprocess.run(['docker','pull','--platform','linux/amd64',name],stdout=f,stderr=f,check=True,timeout=1800)
  value=inspect_image('docker',name);value.update(status='completed',preexisting=exists,pull_elapsed_seconds=time.time()-start)
  write_json(log/'image.json',value);return value
 def locator(self,identifier,image):
  from .agent import run
  from .baseline import CurrentRetriever
  task=self.tasks[identifier];case=self.out/'trial'/identifier;case.mkdir(parents=True,exist_ok=True);box=DockerSandbox(image['id'],task['base_commit'])
  try:
   box.start()
   with TemporaryDirectory(prefix='checkpoint-source-') as td:
    snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
    result=run(issue=task['problem_statement'],output=case/'locator',transport=self.LiveTransport(self.credential,self.ledger,case/'locator-wire','trial:'+identifier+':locator'),locator=retriever)
    if result['status']=='completed':
     packet={'version':1,'instance_id':identifier,'base_commit':task['base_commit'],'result':result['finished']}
     if len(json.dumps(packet,ensure_ascii=False).encode())>14336:raise RuntimeError('localization_packet_byte_limit')
     write_json(case/'localization.json',packet)
    return result
  finally:box.close()
 def coding(self,phase,identifier,arm,image,*,replay=None):
  from .agent import run
  task=self.tasks[identifier];episode=self.out/phase/identifier/arm;episode.mkdir(parents=True,exist_ok=True);box=DockerSandbox(image['id'],task['base_commit'])
  packet=None
  if arm=='B':
   packet_source=(replay.parent/'localization.json') if replay else self.out/phase/identifier/'localization.json'
   packet=json.loads(packet_source.read_text());assert packet['instance_id']==identifier and packet['base_commit']==task['base_commit']
  try:
   box.start()
   if box.patch():raise RuntimeError('dirty_agent_base')
   transport=ReplayTransport(replay/'wire',episode/'replay-receipts') if replay else self.LiveTransport(self.credential,self.ledger,episode/'wire',phase+':'+identifier+':'+arm)
   result=run(issue=task['problem_statement'],output=episode/'agent',transport=transport,sandbox=box,packet=packet,scripted=bool(replay))
   patch=box.patch();(episode/'patch.diff').write_text(patch)
   pred={'instance_id':identifier,'model_name_or_path':'locagent-deepseek-flash-'+arm,'model_patch':patch};write_json(episode/'prediction.json',pred);(episode/'prediction.jsonl').write_text(json.dumps(pred)+'\n')
   result.update(empty_patch=not bool(patch.strip()),patch_bytes=len(patch.encode()),patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),execution_mode='historical_response_replay' if replay else 'live',new_model_requests=0 if replay else len(transport.records))
   if replay:
    result['historical_patch_matches']=patch==(replay/'patch.diff').read_text();result['all_recorded_responses_consumed']=transport.index==len(transport.files)
    if not result['historical_patch_matches'] or not result['all_recorded_responses_consumed']:raise RuntimeError('replay_patch_or_sequence_mismatch')
   write_json(episode/'coding.json',result);return result
  finally:box.close()
 def evaluate(self,phase,identifier,arm):
  episode=self.out/phase/identifier/arm;env=dict(os.environ,PYTHONPATH=str(ROOT),HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1')
  args=[sys.executable,'-m','locagent_e2e.evaluation','--id',identifier,'--prediction',str(episode/'prediction.json'),'--output',str(episode/'harness')]
  if phase=='trial':args+=['--formal-development-scope']
  with (episode/'harness-console.log').open('w') as f:p=subprocess.run(args,env=env,stdout=f,stderr=f,timeout=2000)
  result=json.loads((episode/'harness/evaluation.json').read_text())
  if p.returncode:raise RuntimeError('harness_process_failed: '+str(result.get('technical_failure')))
  return result
 def episode(self,phase,identifier,arm,image,*,replay=None):
  start=time.time();code=self.step(f'{phase}:{identifier}:{arm}:agent',lambda:self.coding(phase,identifier,arm,image,replay=replay))
  ev=self.step(f'{phase}:{identifier}:{arm}:evaluation',lambda:self.evaluate(phase,identifier,arm))
  states=[self.state['steps'][f'{phase}:{identifier}:{arm}:{name}'] for name in ['agent','evaluation']]
  row={'status':'completed','instance_id':identifier,'arm':arm,'empty_patch':code['empty_patch'],'first_source_edit_request':code['first_source_edit_request'],'resolved':ev['resolved'],'coding_requests':code['requests'],'prompt_tokens':code['prompt_tokens'],'completion_tokens':code['completion_tokens'],'wall_seconds':sum(s['ended_at']-s['started_at'] for s in states),'execution_mode':code['execution_mode'],'finish_kind':code['finish_kind'],'patch_bytes':code['patch_bytes']}
  cc=[r for r in self.ledger.read()['calls'] if r['context']==phase+':'+identifier+':'+arm and r['status']=='received']
  row.update(new_model_requests=len(cc),cost_upper_cny=sum(r['charged_upper_microcny'] for r in cc)/1e6,peak_cache_adjusted_cny=sum(r['peak_cache_adjusted_microcny'] for r in cc)/1e6)
  write_json(self.out/phase/identifier/arm/'episode.json',row);return row
 def run(self):
  # First requested paid run is the missing Astropy A. No locator input/call for A.
  astro='astropy__astropy-14182';sympy='sympy__sympy-21379'
  images={i:self.step('smoke:image:'+i,lambda i=i:self.image(i)) for i in [astro,sympy]}
  accepted=[self.episode('smoke',astro,'A',images[astro])]
  for i,arm,old in [(sympy,'A',self.old_v2/sympy/'A'),(sympy,'B',self.old_v2/sympy/'B'),(astro,'B',self.old_v3/astro/'B')]:
   accepted.append(self.episode('smoke',i,arm,images[i],replay=old))
  write_json(self.out/'smoke-acceptance.json',{'status':'completed','live_episodes':1,'offline_replay_episodes':3,'episodes':accepted,'all_four_completed_without_technical_failure':True,'historical_failures_unchanged':True})
  episodes=[]
  for index,identifier in enumerate(self.auth['trial_ids'],1):
   image=self.step('trial:image:'+identifier,lambda i=identifier:self.image(i))
   self.step('trial:'+identifier+':locator',lambda:self.locator(identifier,image))
   for arm in ['A','B']:
    episodes.append(self.episode('trial',identifier,arm,image))
    write_json(self.out/'trial-progress.json',{'completed_episodes':len(episodes),'episodes':episodes,'checkpoint_at_episodes':16})
   # Exact trial image cleanup after each repo's current singleton batch, preserve existing smoke images.
   if not image['preexisting']:
    def cleanup():
     subprocess.run(['docker','image','rm',image['name']],check=True);return {'status':'completed','image':image['name']}
    self.step('trial:cleanup:'+identifier,cleanup)
  decision=stop_decision(episodes);write_json(self.out/'checkpoint.json',decision);return decision

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--old-v2',type=Path,required=True);p.add_argument('--old-v3',type=Path,required=True);a=p.parse_args()
 try:
  runner=Runner(a.output,a.credentials,a.authorization,a.old_v2,a.old_v3);print(json.dumps(runner.run(),ensure_ascii=False))
 finally:a.credentials.unlink(missing_ok=True)
if __name__=='__main__':main()
