"""Single-lane, one-shot ABC holdout controller. Results stay sealed until completion."""
import argparse,fcntl,json,os,subprocess,sys,time
from pathlib import Path
from support import P,F,AB,C,IDS,MIN_FREE,load,sha,verify,durable,claim,sync_file,check_free,free_bytes
from locagent_e2e.driver import image_name,inspect_image

class SafetyStop(RuntimeError):pass

class Runner:
 def __init__(self,credential):
  verify();a=load(P/'authorization.json');assert a['approved'] and a['ids_sha256']==IDS and a['concurrency']==1 and a['repetitions']==1 and a['api_total_cap_cny'] is None
  assert load(P/'delivery/adapter-equivalence.json')['status']=='passed'
  pre=load(P/'remote-preflight.json');assert pre['status']=='passed' and pre['free_bytes']>=MIN_FREE
  self.lock=Path('/home/ubuntu/.locagent-paid-run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.out=P/'run';self.out.mkdir(exist_ok=False);self.credential=credential
  claim(P/'experiment-once.json',{'at':time.time(),'C':C,'AB':AB,'ids_sha256':IDS,'authorization_sha256':sha(P/'authorization.json'),'deployment_manifest_sha256':sha(P/'deployment-manifest.json')})
  self.tasks=load(P/'execution-order.json')['tasks'];self.state={'status':'running','started_at':time.time(),'steps':{},'rows':[],'completed_tasks':0,'completed_arms':0,'current_task_number':None,'current_arm':None,'current_stage':None,'ids_sha256':IDS,'C':C,'AB':AB,'stop_reason':None}
  self.retained={r['name']:r['id'] for r in load(P/'cache-before.json')['images']}
  self.save()
 def save(self):
  durable(self.out/'state.json',self.state)
  durable(P/'health.json',{k:self.state.get(k) for k in ['status','started_at','completed_tasks','completed_arms','current_task_number','current_arm','current_stage','finished_at','stop_reason']}|{'free_bytes':free_bytes(),'at':time.time(),'unblinded':False})
 def guard(self):
  try:check_free();verify()
  except Exception as e:raise SafetyStop(str(e))
  if (P/'RESOURCE_DEVIATION.json').exists():raise SafetyStop('runtime_resource_deviation')
  models=set()
  for p in self.out.glob('trial/*/*/ledger.json'):
   for r in load(p)['calls']:
    if r.get('actual_model'):models.add(r['actual_model'])
  if models-{'deepseek-flash'}:raise SafetyStop('actual_model_identifier_deviation')
 def once(self,key,fn):
  mark=self.out/'once'/key
  claim(mark,{'status':'started','at':time.time()})
  self.state['current_stage']=key.rsplit('--',1)[-1];step={'status':'running','started_at':time.time()};self.state['steps'][key]=step;self.save()
  try:r=fn()
  except SafetyStop:
   step.update(status='failed',ended_at=time.time(),result={'status':'failed','technical_failure':'safety_stop'});self.save();raise
  except Exception as e:r={'status':'failed','technical_failure':type(e).__name__+': '+str(e)[:700]}
  step.update(status=r.get('status','failed'),ended_at=time.time(),result=r);self.save();return r
 def image(self,identifier):
  self.guard();name=image_name(identifier);dest=self.out/'images'/identifier;dest.mkdir(parents=True,exist_ok=False)
  exists=subprocess.run(['docker','image','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
  before=time.time()
  if not exists:
   with (dest/'pull.log').open('w') as f:subprocess.run(['docker','pull','--platform','linux/amd64',name],stdout=f,stderr=f,check=True,timeout=1800)
  info=inspect_image('docker',name);info.update(status='completed',preexisting=exists,pull_elapsed_seconds=time.time()-before)
  durable(dest/'image.json',info);self.guard();return info
 def ensure_image(self,image):
  actual=inspect_image('docker',image['name'])
  if actual['id']!=image['id']:raise SafetyStop('image_digest_changed')
 def child(self,identifier,arm,stage,image):
  self.guard();self.ensure_image(image);episode=self.out/'trial'/identifier/arm;episode.mkdir(parents=True,exist_ok=True)
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',LOCAGENT_EVAL_SCOPE='holdout50')
  if stage=='evaluation':
   args=[sys.executable,str(P/'control/evaluation_adapter.py'),'--id',identifier,'--prediction',str(episode/'prediction.json'),'--output',str(episode/'harness'),'--formal-development-scope'];result_path=episode/'harness/evaluation.json';timeout=2100
  else:
   args=[sys.executable,str(P/'control/worker.py'),'--stage',stage,'--id',identifier,'--arm',arm,'--image-id',image['id'],'--credentials',str(self.credential),'--output',str(self.out)];result_path=episode/(stage+'-worker.json');timeout=3300 if stage=='coding' else 600
  with (episode/(stage+'-console.log')).open('w') as f:
   process=subprocess.run(args,env=env,stdout=f,stderr=f,timeout=timeout)
  if not result_path.exists():return {'status':'failed','technical_failure':'missing_stage_result','returncode':process.returncode}
  result=load(result_path)
  if process.returncode and result.get('status')=='completed':result={'status':'failed','technical_failure':'stage_process_nonzero','returncode':process.returncode}
  return result
 def cleanup_owned_containers(self):
  # Dedicated host had zero containers at preflight. Remove only task-owned names.
  ids=subprocess.check_output(['docker','ps','-aq'],text=True).split()
  if not ids:return
  rows=json.loads(subprocess.check_output(['docker','inspect',*ids]))
  for r in rows:
   if r['Name'].startswith(('/locagent-e2e-','/sweb.eval.')):
    subprocess.run(['docker','rm','-f',r['Id']],check=True,stdout=subprocess.DEVNULL)
   else:raise SafetyStop('unexpected_foreign_container')
 def arm(self,task,arm,image):
  identifier=task['instance_id'];self.state['current_arm']=arm;self.save();start=time.time()
  row={'number':task['number'],'instance_id':identifier,'arm':arm,'status':'not_run','resolved':None,'empty_patch':None,'errors':[],'image_id':image.get('id')}
  if image['status']!='completed':row['reason']='image_unavailable';return row
  episode=self.out/'trial'/identifier/arm;episode.mkdir(parents=True,exist_ok=True)
  try:
   if arm!='A':
    loc=self.once(identifier+'--'+arm+'--locator',lambda:self.child(identifier,arm,'locator',image))
    if loc['status']!='completed':row.update(status='failed',reason='localization_not_completed');row['errors'].append({'stage':'locator',**loc});return row
   code=self.once(identifier+'--'+arm+'--coding',lambda:self.child(identifier,arm,'coding',image))
   if code['status']!='completed':row['errors'].append({'stage':'coding',**code})
   if (episode/'coding.json').exists():
    c=load(episode/'coding.json');row.update(empty_patch=c.get('empty_patch'),coding_requests=c.get('requests'),first_source_edit_request=c.get('first_source_edit_request'),coding_status=c['status'])
   if (episode/'prediction.json').exists():
    ev=self.once(identifier+'--'+arm+'--evaluation',lambda:self.child(identifier,arm,'evaluation',image));row.update(resolved=ev.get('resolved'),evaluation_status=ev['status'])
    if ev['status']!='completed':row['errors'].append({'stage':'evaluation',**ev})
   else:row['errors'].append({'stage':'evaluation','status':'not_run','reason':'no_prediction'})
   row['status']='completed' if not row['errors'] else 'failed';return row
  except SafetyStop as e:
   row.update(status='failed',reason='safety_stop');row['errors'].append({'stage':self.state.get('current_stage'),'technical_failure':str(e)})
   self.state['rows'].append(row);self.state['completed_arms']+=1;self.save();raise
  finally:
   row['elapsed_seconds']=time.time()-start;durable(episode/'row.json',row);self.cleanup_owned_containers()
 def archive_and_cleanup(self,task,image):
  identifier=task['instance_id'];case=self.out/'trial'/identifier
  case.mkdir(parents=True,exist_ok=True)
  # Every available patch, trajectory, wire receipt and harness log is hashed before deletion.
  # Explicit missing products are included; failures are never repaired by re-execution.
  products={p.relative_to(self.out).as_posix():sha(p) for p in sorted(case.rglob('*')) if p.is_file()}
  image_path=self.out/'images'/identifier/'image.json'
  if image_path.exists():products[image_path.relative_to(self.out).as_posix()]=sha(image_path)
  missing={a:[n for n in ['patch.diff','agent/result.json','harness/evaluation.json'] if not (case/a/n).exists()] for a in ['A','B','C']}
  receipt=self.out/'evidence-manifests'/(identifier+'.json')
  durable(receipt,{'instance_id':identifier,'image':image,'products':products,'missing_due_to_failure_or_not_run':missing,'arms_recorded':[r['arm'] for r in self.state['rows'] if r['instance_id']==identifier],'at':time.time()})
  assert set(load(receipt)['arms_recorded'])=={'A','B','C'}
  for n,h in products.items():assert sha(self.out/n)==h
  if image['status']=='completed' and not image['preexisting']:
   assert image['name'] not in self.retained
   self.ensure_image(image)
   subprocess.run(['docker','image','rm',image['name']],check=True,stdout=subprocess.DEVNULL)
   return {'status':'completed','removed_new_image':image['name'],'image_id':image['id'],'evidence_manifest_sha256':sha(receipt)}
  return {'status':'completed','removed_new_image':None,'preserved_preexisting':True,'evidence_manifest_sha256':sha(receipt)}
 def run(self):
  try:
   for task in self.tasks:
    self.guard();identifier=task['instance_id'];self.state['current_task_number']=task['number'];self.save()
    image=self.once(identifier+'--image',lambda:self.image(identifier))
    for arm in task['arm_order']:
     try:row=self.arm(task,arm,image)
     except SafetyStop:raise
     except Exception as e:row={'number':task['number'],'instance_id':identifier,'arm':arm,'status':'failed','resolved':None,'empty_patch':None,'errors':[{'stage':'orchestration','technical_failure':type(e).__name__+': '+str(e)[:700]}]}
     self.state['rows'].append(row);self.state['completed_arms']+=1;self.save()
    cleanup=self.once(identifier+'--archive-and-image-cleanup',lambda:self.archive_and_cleanup(task,image))
    if cleanup['status']!='completed':raise SafetyStop('evidence_or_image_cleanup_failed')
    self.state['completed_tasks']+=1;self.save()
   self.state['status']='finished'
  except Exception as e:
   self.state.update(status='stopped',stop_reason=type(e).__name__+': '+str(e)[:700])
  finally:
   seen={(r['instance_id'],r['arm']) for r in self.state['rows']}
   for t in self.tasks:
    for a in t['arm_order']:
     if (t['instance_id'],a) not in seen:self.state['rows'].append({'number':t['number'],'instance_id':t['instance_id'],'arm':a,'status':'not_run','resolved':None,'empty_patch':None,'reason':self.state['stop_reason'] or 'not_attempted'})
   self.state.update(finished_at=time.time(),current_stage=None,current_arm=None);self.save()
   durable(self.out/'completed.json',self.state)
   self.cleanup_owned_containers()
  return self.state['status']

def main():
 p=argparse.ArgumentParser();p.add_argument('--credentials',type=Path,required=True);a=p.parse_args()
 try:status=Runner(a.credentials).run();print(json.dumps({'status':status,'results_sealed':True}))
 finally:
  a.credentials.unlink(missing_ok=True);durable(P/'credential-cleanup.json',{'at':time.time(),'credential_exists':a.credentials.exists()})
if __name__=='__main__':main()
