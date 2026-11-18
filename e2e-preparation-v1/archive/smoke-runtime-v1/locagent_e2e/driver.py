import argparse,fcntl,hashlib,io,json,os,subprocess,sys,tarfile,time,random
from pathlib import Path
from tempfile import TemporaryDirectory
from .common import ROOT,CONFIG,allow,manifest,rows,write_json,digest
from .ledger import Ledger
from .sandbox import DockerSandbox

def image_name(identifier):return 'swebench/sweb.eval.x86_64.'+identifier.lower().replace('__','_1776_')+':latest'
def inspect_image(docker,image):
 p=subprocess.run([docker,'image','inspect',image],capture_output=True,check=True);data=json.loads(p.stdout)[0]
 if data['Architecture']!='amd64':raise RuntimeError('wrong_image_architecture')
 return {'name':image,'id':data['Id'],'repo_digests':data.get('RepoDigests',[]),'size_bytes':data['Size'],'architecture':data['Architecture']}
def source_snapshot(archive,target):
 from readonly_agent.core import Snapshot
 target.mkdir();names=[];excluded=[]
 with tarfile.open(fileobj=io.BytesIO(archive)) as t:
  for member in t.getmembers():
   p=Path(member.name)
   if member.isfile() and p.suffix=='.py' and not p.is_absolute() and '..' not in p.parts and not any(x.startswith('.') for x in p.parts):
    raw=t.extractfile(member).read()
    try:raw.decode('utf8')
    except UnicodeDecodeError:excluded.append(member.name);continue
    dest=target/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);names.append(member.name)
 snap=Snapshot(target,names);snap.e2e_source_root=target;return snap

def config_binding():
 files=[*sorted((ROOT/'locagent_e2e').glob('*.py')),*sorted((ROOT/'config').glob('*')),*sorted((ROOT/'runtime').rglob('*.py')),ROOT/'data/dev24/manifest.json',ROOT/'data/dev24/content/receipt.json']
 return digest({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

def prepare_images(docker,out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);m=manifest();ids=m['smoke_ids']
 # Hard local limit; no broad docker/system prune and no unselected image download.
 assert len(ids)<=CONFIG['local_image_pull_limit']
 receipts=[]
 for identifier in ids:
  allow(identifier,smoke=True);image=image_name(identifier)
  existing=subprocess.run([docker,'image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
  if not existing:
   with (out/(identifier+'.pull.log')).open('w') as log:
    subprocess.run([docker,'pull','--platform','linux/amd64',image],stdout=log,stderr=log,check=True)
  receipts.append(inspect_image(docker,image));write_json(out/'images.json',receipts)
 return receipts

def smoke(output,credential,docker,docker_host=None):
 from .agent import run
 from .baseline import CurrentRetriever
 from .transport import LiveTransport
 out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
 with (out/'driver.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  binding=config_binding();statefile=out/'state.json'
  if statefile.exists():
   state=json.loads(statefile.read_text())
   if state['code_binding']!=binding:raise RuntimeError('resume_code_binding_changed')
   if state.get('failed') or any(v['status'] in ('running','failed') for v in state['steps'].values()):raise RuntimeError('uncertain_or_failed_step_no_automatic_retry')
  else:
   state={'version':1,'scope':'2 task A/B smoke only','code_binding':binding,'manifest_sha256':hashlib.sha256((ROOT/'data/dev24/manifest.json').read_bytes()).hexdigest(),'steps':{},'failed':None};write_json(statefile,state)
  if state['manifest_sha256']!=hashlib.sha256((ROOT/'data/dev24/manifest.json').read_bytes()).hexdigest():raise RuntimeError('resume_manifest_changed')
  receipt=json.loads((ROOT/'data/dev24/content/receipt.json').read_text())
  if hashlib.sha256((ROOT/'data/dev24/content/public.json').read_bytes()).hexdigest()!=receipt['files']['public.json']:raise RuntimeError('public_task_content_changed')
  ledger=Ledger(out/'ledger.json',CONFIG['smoke_max_cny']);public={x['instance_id']:x for x in rows()}
  def step(key,fn):
   if key in state['steps']:
    value=state['steps'][key]
    if value['status']=='completed':return value['result']
    raise RuntimeError('step_cannot_retry')
   state['steps'][key]={'status':'running','started_at':time.time()};write_json(statefile,state)
   try:
    value=fn()
    if value.get('status')=='failed':raise RuntimeError(value.get('technical_failure') or 'step_failed')
    state['steps'][key].update(status='completed',result=value,ended_at=time.time());write_json(statefile,state);return value
   except Exception as e:
    state['steps'][key].update(status='failed',error=type(e).__name__+': '+str(e));state['failed']=key;write_json(statefile,state);raise
  for identifier in manifest()['smoke_ids']:
   allow(identifier,smoke=True);task=public[identifier];case=out/identifier;case.mkdir(exist_ok=True);img=inspect_image(docker,image_name(identifier))
   imagefile=case/'image.json'
   if imagefile.exists() and json.loads(imagefile.read_text())!=img:raise RuntimeError('resume_image_changed')
   write_json(imagefile,img)
   packetfile=case/'localization.json'
   def locate():
    box=DockerSandbox(img['id'],task['base_commit'],docker)
    try:
     box.start()
     with TemporaryDirectory(prefix='e2e-source-') as td:
      snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
      transport=LiveTransport(credential,ledger,case/'locator-wire',identifier+':locator')
      result=run(issue=task['problem_statement'],output=case/'locator',transport=transport,locator=retriever)
      if result['status']!='completed':return result
      # Pass existing terminal localization, unchanged. No new synthesis or improvement.
      packet={'version':1,'instance_id':identifier,'base_commit':task['base_commit'],'result':result['finished']}
      if len(json.dumps(packet,ensure_ascii=False).encode())>14336:raise RuntimeError('localization_packet_byte_limit')
      write_json(packetfile,packet);return result
    finally:box.close()
   step(identifier+':locator',locate)
   arms=['A','B'];random.Random(CONFIG['seed']+manifest()['smoke_ids'].index(identifier)).shuffle(arms)
   for arm in arms:
    episode=case/arm;episode.mkdir(exist_ok=True)
    def code():
     box=DockerSandbox(img['id'],task['base_commit'],docker)
     try:
      box.start();transport=LiveTransport(credential,ledger,episode/'wire',identifier+':'+arm)
      result=run(issue=task['problem_statement'],output=episode/'agent',transport=transport,sandbox=box,packet=json.loads(packetfile.read_text()) if arm=='B' else None)
      patch=box.patch();(episode/'patch.diff').write_text(patch)
      pred={'instance_id':identifier,'model_name_or_path':'locagent-deepseek-flash-'+arm,'model_patch':patch};write_json(episode/'prediction.json',pred)
      (episode/'prediction.jsonl').write_text(json.dumps(pred)+'\n');return result
     finally:box.close()
    step(identifier+':'+arm+':agent',code)
    def evaluate():
     env=dict(os.environ,PYTHONPATH=str(ROOT),HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1')
     args=[sys.executable,'-m','locagent_e2e.evaluation','--id',identifier,'--prediction',str(episode/'prediction.json'),'--output',str(episode/'harness')]
     if docker_host:args+=['--docker-host',docker_host]
     with (episode/'harness-console.log').open('w') as log:p=subprocess.run(args,env=env,stdout=log,stderr=log,timeout=2000)
     if p.returncode:raise RuntimeError('harness_process_failed')
     return json.loads((episode/'harness/evaluation.json').read_text())
    step(identifier+':'+arm+':evaluation',evaluate)
  write_json(out/'completed.json',{'status':'completed','episodes':4,'purpose':'pipeline smoke only; do not interpret resolve rate','formal_trial_run':False});return state

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['images','smoke','plan']);p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path);p.add_argument('--docker',default='docker');p.add_argument('--docker-host');a=p.parse_args()
 if a.action=='images':prepare_images(a.docker,a.output)
 elif a.action=='smoke':
  if not a.credentials:p.error('--credentials required')
  smoke(a.output,a.credentials,a.docker,a.docker_host)
 else:
  m=manifest();a.output.mkdir(parents=True,exist_ok=True);write_json(a.output/'formal-plan-not-authorized.json',{'instances':m['instances'],'episodes':48,'arms':['A','B'],'concurrency':1,'execution_authorized':False})
if __name__=='__main__':main()
