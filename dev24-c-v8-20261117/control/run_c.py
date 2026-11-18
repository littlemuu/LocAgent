"""Authorized C-only orchestration; frozen locator/coding/evaluator code untouched."""
import argparse,fcntl,hashlib,json,os,platform,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
PACKAGE=Path(__file__).resolve().parents[1]
FROZEN=PACKAGE/'frozen'
sys.path[:0]=[str(FROZEN),str(FROZEN/'baseline')]
from locagent_e2e.common import ROOT,CONFIG,manifest,rows,write_json,digest
from locagent_e2e.checkpoint import Runner
from locagent_e2e.driver import config_binding,source_snapshot
from locagent_e2e.ledger import Ledger
from locagent_e2e.transport import LiveTransport
from locagent_e2e.sandbox import DockerSandbox
EXPECTED='c072f4f8c9764f0311fabb7f52dfabbcdc04ba0369473296cba75547d54edf3a'
BASE='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'

def verify_frozen():
 f=json.loads((FROZEN/'FREEZE.json').read_text())
 actual={p:hashlib.sha256((FROZEN/p).read_bytes()).hexdigest() for p in f['files']}
 if actual!=f['files'] or digest(actual)!=EXPECTED or config_binding()!=BASE:raise RuntimeError('frozen_binding_changed')
 return EXPECTED

def validate(path):
 a=json.loads(Path(path).read_text());m=manifest()
 if (a.get('approved') is not True or a.get('budget_cny')!=20 or a.get('arm_order')!=['C'] or a.get('trial_ids')!=m['selection_order']
     or a.get('repetitions')!=1 or a.get('max_trial_episodes')!=24 or a.get('automatic_retries')!=0 or a.get('concurrency')!=1
     or a.get('v8_binding')!=EXPECTED or a.get('baseline_binding')!=BASE or a.get('ids_sha256')!=m['ids_sha256'] or a.get('holdout') is not False):
  raise PermissionError('invalid_C_authorization')
 return a

class CRunner(Runner):
 def __init__(self,out,credential,authorization):
  self.auth=validate(authorization);verify_frozen()
  if platform.system()!='Linux' or platform.machine()!='x86_64':raise PermissionError('cloud_x86_required')
  self.out=Path(out).resolve();self.out.mkdir(parents=True,exist_ok=False)
  self.credential=Path(credential);self.LiveTransport=LiveTransport
  self.lock=(PACKAGE/'paid-run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.path=self.out/'state.json';self.tasks={r['instance_id']:r for r in rows()};self.ledger=Ledger(self.out/'ledger.json',20)
  self.state=dict(code_binding=BASE,v8_binding=EXPECTED,control_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    authorization_sha256=digest(self.auth),started_at=time.time(),steps={},failed=None,trial_ids=self.auth['trial_ids'],scope='dev24_C_v8_once')
  write_json(self.path,self.state)
 def locator(self,identifier,image):
  from calibration.locator import run,build_packet
  from calibration.policy import EvidenceLedger,violations
  from locagent_e2e.baseline import CurrentRetriever
  task=self.tasks[identifier];case=self.out/'trial'/identifier;case.mkdir(parents=True,exist_ok=True);box=DockerSandbox(image['id'],task['base_commit'])
  try:
   box.start()
   with TemporaryDirectory(prefix='C-source-') as td:
    snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
    result=run(issue=task['problem_statement'],output=case/'locator',transport=self.LiveTransport(self.credential,self.ledger,case/'locator-wire','trial:'+identifier+':locator'),locator=retriever)
    if result['status']=='completed':
     packet=build_packet(result,instance_id=identifier,base_commit=task['base_commit']);write_json(case/'localization.json',packet)
     audit=json.loads((case/'locator/diagnostic-audit.json').read_text())
     evidence=EvidenceLedger(snap)
     for item in result['tool_audit']:evidence.observe(item)
     post=violations(packet['result'],evidence)
     write_json(case/'localization-metrics.json',dict(instance_id=identifier,raw_compliant=not audit['violations'],fallback=audit['fallback'],
       violation_details=audit['violations'],violation_rules=sorted({x.split('_')[0] for x in audit['violations']}),
       delivered_compliant=not post,delivered_violations=post,raw_marks_unread='未读完' in audit['raw_packet']['answer'],
       delivered_marks_unread='未读完' in packet['result']['answer'],requests=result['requests'],quality_measured=False))
     if post:raise RuntimeError('calibrated_packet_not_compliant')
    return result
  finally:box.close()
 def coding(self,phase,identifier,arm,image,*,replay=None):
  if arm!='C' or replay is not None:raise PermissionError('C_once_live_only')
  from locagent_e2e.agent import run
  task=self.tasks[identifier];episode=self.out/phase/identifier/arm;episode.mkdir(parents=True,exist_ok=True);box=DockerSandbox(image['id'],task['base_commit'])
  packet=json.loads((self.out/phase/identifier/'localization.json').read_text())
  assert packet['instance_id']==identifier and packet['base_commit']==task['base_commit']
  try:
   box.start()
   if box.patch():raise RuntimeError('dirty_agent_base')
   transport=self.LiveTransport(self.credential,self.ledger,episode/'wire',phase+':'+identifier+':'+arm)
   result=run(issue=task['problem_statement'],output=episode/'agent',transport=transport,sandbox=box,packet=packet)
   patch=box.patch();(episode/'patch.diff').write_text(patch)
   pred={'instance_id':identifier,'model_name_or_path':'locagent-deepseek-flash-C','model_patch':patch}
   write_json(episode/'prediction.json',pred);(episode/'prediction.jsonl').write_text(json.dumps(pred)+'\n')
   result.update(empty_patch=not bool(patch.strip()),patch_bytes=len(patch.encode()),patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),execution_mode='live',new_model_requests=len(transport.records))
   write_json(episode/'coding.json',result);return result
  finally:box.close()
 def run(self):
  episodes=[]
  for identifier in self.auth['trial_ids']:
   verify_frozen()
   image=self.step('trial:image:'+identifier,lambda i=identifier:self.image(i))
   self.step('trial:'+identifier+':locator',lambda:self.locator(identifier,image))
   episodes.append(self.episode('trial',identifier,'C',image))
   write_json(self.out/'trial-progress.json',dict(completed_episodes=len(episodes),episodes=episodes,total_episodes=24))
   if not image['preexisting']:
    def cleanup():
     subprocess.run(['docker','image','rm',image['name']],check=True);return dict(status='completed',image=image['name'])
    self.step('trial:cleanup:'+identifier,cleanup)
  result=dict(status='completed',episodes=24,tasks=24,repetitions=1,finished_at=time.time(),further_runs_authorized=False)
  write_json(self.out/'completed.json',result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);a=p.parse_args()
 try:
  runner=CRunner(a.output,a.credentials,a.authorization);print(json.dumps(runner.run()))
 finally:
  a.credentials.unlink(missing_ok=True)
  write_json(PACKAGE/'credential-cleanup.json',dict(credential_exists=a.credentials.exists(),at=time.time()))
if __name__=='__main__':main()
