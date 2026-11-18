"""One locator or coding stage. Calls frozen components without behavioral changes."""
import argparse,json,subprocess,time
from pathlib import Path
from tempfile import TemporaryDirectory
from support import P,F,AB,C,load,sha,verify,durable,sync_file,check_free
from locagent_e2e.common import CONFIG
from locagent_e2e.ledger import Ledger
from locagent_e2e.transport import LiveTransport
from locagent_e2e.sandbox import DockerSandbox
from locagent_e2e.driver import source_snapshot

class DurableLedger(Ledger):
 def update(self,fn):
  result=super().update(fn);sync_file(self.path);return result

def resource(box,out):
 row=json.loads(subprocess.check_output(['docker','inspect',box.name]))[0];h=row['HostConfig']
 observed={'at':time.time(),'container':row['Id'],'image_id':row['Image'],'Memory':h['Memory'],'NanoCpus':h['NanoCpus'],'NetworkMode':h['NetworkMode']}
 durable(out/'resource.json',observed)
 if (h['Memory'],h['NanoCpus'],h['NetworkMode'])!=(6442450944,6000000000,'none'):raise RuntimeError('agent_container_resource_deviation')

def execute(stage,identifier,arm,image_id,credential,out):
 verify();check_free();receipt=load(P/'public-data-receipt.json');assert sha(P/'data/public.json')==receipt['public_sha256']
 rows=load(P/'data/public.json');task=next(r for r in rows if r['instance_id']==identifier)
 assert set(task)=={'instance_id','repo','base_commit','problem_statement'}
 episode=out/'trial'/identifier/arm;episode.mkdir(parents=True,exist_ok=True)
 # Maximum authorized calls cannot reach this per-arm arithmetic envelope.
 # No global financial threshold, and failed/uncertain requests stay recorded.
 ledger=DurableLedger(episode/'ledger.json',44*(1048576*2+4096*8)/1e6)
 box=DockerSandbox(image_id,task['base_commit']);started=time.time()
 try:
  box.start();resource(box,episode/(stage+'-resources'));check_free()
  if stage=='locator':
   assert arm in ('B','C')
   from locagent_e2e.baseline import CurrentRetriever
   with TemporaryDirectory(prefix='holdout-source-') as td:
    snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
    transport=LiveTransport(credential,ledger,episode/'locator-wire',identifier+':'+arm+':locator')
    if arm=='B':
     from locagent_e2e.agent import run
     result=run(issue=task['problem_statement'],output=episode/'locator',transport=transport,locator=retriever)
     if result['status']=='completed':
      packet={'version':1,'instance_id':identifier,'base_commit':task['base_commit'],'result':result['finished']}
      assert len(json.dumps(packet,ensure_ascii=False).encode())<=14336
      durable(episode/'localization.json',packet)
    else:
     from calibration.locator import run,build_packet
     result=run(issue=task['problem_statement'],output=episode/'locator',transport=transport,locator=retriever)
     if result['status']=='completed':durable(episode/'localization.json',build_packet(result,instance_id=identifier,base_commit=task['base_commit']))
   durable(episode/'locator-stage.json',result)
  elif stage=='coding':
   from locagent_e2e.agent import run
   packet=None if arm=='A' else load(episode/'localization.json')
   if packet is not None:assert packet['instance_id']==identifier and packet['base_commit']==task['base_commit']
   assert not box.patch(),'dirty_agent_base'
   transport=LiveTransport(credential,ledger,episode/'wire',identifier+':'+arm+':coding')
   result=run(issue=task['problem_statement'],output=episode/'agent',transport=transport,sandbox=box,packet=packet)
   patch=box.patch();(episode/'patch.diff').write_text(patch);sync_file(episode/'patch.diff')
   pred={'instance_id':identifier,'model_name_or_path':'locagent-deepseek-flash-'+arm,'model_patch':patch}
   durable(episode/'prediction.json',pred)
   result.update(empty_patch=not bool(patch.strip()),patch_bytes=len(patch.encode()),patch_sha256=sha(episode/'patch.diff'),execution_mode='live',new_model_requests=len(transport.records))
   durable(episode/'coding.json',result)
  else:raise ValueError('unknown_stage')
  return {'status':result['status'],'technical_failure':result.get('technical_failure'),'elapsed_seconds':time.time()-started}
 finally:box.close()

def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',choices=['locator','coding'],required=True);p.add_argument('--id',required=True);p.add_argument('--arm',choices=['A','B','C'],required=True);p.add_argument('--image-id',required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result_path=a.output/'trial'/a.id/a.arm/(a.stage+'-worker.json')
 try:result=execute(a.stage,a.id,a.arm,a.image_id,a.credentials,a.output)
 except Exception as e:result={'status':'failed','technical_failure':type(e).__name__+': '+str(e)[:700]}
 durable(result_path,result)
if __name__=='__main__':main()
