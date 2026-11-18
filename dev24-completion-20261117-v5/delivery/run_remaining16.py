"""Remaining dev16 only. Reuses the exact core Runner methods from the first dev8."""
import argparse,fcntl,hashlib,json,platform,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.checkpoint import Runner
from locagent_e2e.common import ROOT,manifest,rows,write_json,digest
from locagent_e2e.driver import config_binding
from locagent_e2e.ledger import Ledger
from locagent_e2e.transport import LiveTransport
EXPECTED_BINDING='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'
def validate(path):
 a=json.loads(Path(path).read_text());m=manifest()
 if (a.get('approved') is not True or a.get('budget_cny')!=30 or a.get('ids_sha256')!=m['ids_sha256']
     or a.get('trial_ids')!=m['selection_order'][8:] or a.get('arm_order')!=['A','B']
     or a.get('max_trial_episodes')!=32 or a.get('core_binding')!=EXPECTED_BINDING
     or a.get('automatic_retries')!=0):raise PermissionError('invalid_remaining16_authorization')
 return a
class RemainingRunner(Runner):
 def __init__(self,out,credential,authorization,prior_run):
  self.LiveTransport=LiveTransport;self.out=Path(out).resolve();self.out.mkdir(parents=True,exist_ok=True);self.credential=credential;self.auth=validate(authorization)
  if platform.system()!='Linux' or platform.machine()!='x86_64':raise PermissionError('cloud_x86_required')
  self.binding=config_binding()
  if self.binding!=EXPECTED_BINDING:raise RuntimeError('core_changed_from_first_eight')
  prior=json.loads((Path(prior_run)/'state.json').read_text());checkpoint=json.loads((Path(prior_run)/'checkpoint.json').read_text())
  if prior['code_binding']!=self.binding or prior['trial_ids']!=manifest()['selection_order'][:8] or checkpoint.get('status')!='paused_checkpoint' or checkpoint.get('continue_condition_met') is not True:raise PermissionError('prior_checkpoint_not_qualified')
  self.global_lock=(ROOT/'verification/paid-run.lock').open('a');fcntl.flock(self.global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.lock=(self.out/'run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.path=self.out/'state.json';self.tasks={r['instance_id']:r for r in rows()};self.ledger=Ledger(self.out/'ledger.json',30)
  control=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  if self.path.exists():
   self.state=json.loads(self.path.read_text())
   if self.state['code_binding']!=self.binding or self.state['control_sha256']!=control or self.state['authorization_sha256']!=digest(self.auth):raise RuntimeError('resume_binding_changed')
   if self.state.get('failed') or any(s['status']=='running' for s in self.state['steps'].values()):raise RuntimeError('no_automatic_retry_after_failed_or_uncertain_step')
  else:
   self.state={'code_binding':self.binding,'control_sha256':control,'authorization_sha256':digest(self.auth),'started_at':time.time(),'steps':{},'failed':None,'trial_ids':self.auth['trial_ids'],'scope':'remaining16_once_A_then_B'};write_json(self.path,self.state)
 def run(self):
  episodes=[]
  for identifier in self.auth['trial_ids']:
   image=self.step('trial:image:'+identifier,lambda i=identifier:self.image(i))
   self.step('trial:'+identifier+':locator',lambda:self.locator(identifier,image))
   for arm in ['A','B']:
    episodes.append(self.episode('trial',identifier,arm,image))
    write_json(self.out/'trial-progress.json',{'completed_episodes':len(episodes),'episodes':episodes,'total_episodes':32})
   if not image['preexisting']:
    def cleanup():
     subprocess.run(['docker','image','rm',image['name']],check=True);return {'status':'completed','image':image['name']}
    self.step('trial:cleanup:'+identifier,cleanup)
  result={'status':'completed','episodes':32,'tasks':16,'repetitions':1,'further_runs_authorized':False,'extra_two_repeats_run':False}
  write_json(self.out/'completed.json',result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--prior-run',type=Path,required=True);a=p.parse_args()
 try:
  runner=RemainingRunner(a.output,a.credentials,a.authorization,a.prior_run);print(json.dumps(runner.run()))
 finally:a.credentials.unlink(missing_ok=True)
if __name__=='__main__':main()
