"""External orchestration ONLY: sequential dev24 locator, no coding or evaluator calls."""
import argparse,fcntl,hashlib,json,platform,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from zoneinfo import ZoneInfo
PACKAGE=Path(__file__).resolve().parents[1];FROZEN=PACKAGE/'frozen'
sys.path[:0]=[str(FROZEN),str(FROZEN/'baseline')]
from locagent_e2e.common import manifest,rows,write_json,digest
from locagent_e2e.checkpoint import Runner as FrozenImageHelpers
from locagent_e2e.driver import config_binding,source_snapshot
from locagent_e2e.ledger import Ledger
from locagent_e2e.transport import LiveTransport
from locagent_e2e.sandbox import DockerSandbox
EXPECTED='9def7a0000b202dc8f7127ef6424b596c1155015bc7d248e74203512b02f7cee'
BASE='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'
def verify():
 f=json.loads((FROZEN/'FREEZE.json').read_text());actual={p:hashlib.sha256((FROZEN/p).read_bytes()).hexdigest() for p in f['files']}
 if actual!=f['files'] or digest(actual)!=EXPECTED or config_binding()!=BASE:raise RuntimeError('frozen_binding_changed')
 return dict(status='passed',binding=EXPECTED,baseline_binding=BASE,files=len(actual))
def validate(path):
 a=json.loads(Path(path).read_text());m=manifest()
 required=dict(approved=True,budget_cny=5,trial_ids=m['selection_order'],ids_sha256=m['ids_sha256'],v81_binding=EXPECTED,baseline_binding=BASE,concurrency=1,repetitions=1,automatic_retries=0,holdout=False,coding_agent=False,harness=False,stop_after='locator_precheck',delete_remote_credential=True,shutdown_mode='STOP_CHARGING')
 if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in required.items()):raise PermissionError('invalid_locator_only_authorization')
 return a

def metered_cost(call):
 peak=call.get('peak_cache_adjusted_microcny')
 if peak is None:return None
 d=datetime.fromtimestamp(call['started_at'],ZoneInfo('Asia/Shanghai'))
 multiplier=1 if d.weekday()<5 and (9<=d.hour<12 or 14<=d.hour<18) else .5
 return peak*multiplier/1e6

class LocatorOnly:
 # Reuse only unchanged image acquisition, not Runner.run/step/episode.
 image=FrozenImageHelpers.image
 def __init__(self,out,credential,authorization):
  verify();self.auth=validate(authorization)
  if platform.system()!='Linux' or platform.machine()!='x86_64':raise PermissionError('cloud_x86_required')
  self.lock=(PACKAGE/'paid-run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False);self.credential=Path(credential)
  self.ledger=Ledger(self.out/'ledger.json',5);self.tasks={r['instance_id']:r for r in rows()}
  self.state=dict(scope='dev24_C_v8.1_locator_only_once',binding=EXPECTED,started_at=time.time(),current=None,rows=[],coding_agent='未运行',harness='未运行')
  self.save()
 def save(self):write_json(self.out/'state.json',self.state)
 def locate(self,identifier,image):
  from calibration.locator import run,build_packet
  from locagent_e2e.baseline import CurrentRetriever
  task=self.tasks[identifier];case=self.out/'trial'/identifier;case.mkdir(parents=True,exist_ok=True)
  box=DockerSandbox(image['id'],task['base_commit'])
  try:
   box.start()
   inspected=json.loads(subprocess.check_output(['docker','inspect',box.name],text=True))[0];h=inspected['HostConfig']
   write_json(case/'source-container.json',dict(name=box.name,purpose='base-source export only; no coding/evaluation',memory=h['Memory'],cpus=h['NanoCpus'],network=h['NetworkMode']))
   with TemporaryDirectory(prefix='locator-v81-source-') as td:
    snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
    result=run(issue=task['problem_statement'],output=case/'locator',transport=LiveTransport(self.credential,self.ledger,case/'locator-wire','locator:'+identifier),locator=retriever)
    if result['status']=='completed':
     packet=build_packet(result,instance_id=identifier,base_commit=task['base_commit']);write_json(case/'localization.json',packet)
    return result
  finally:box.close()
 def one(self,identifier):
  start=time.time();self.state['current']=identifier;self.save();image=None;result={};error=None;cleanup_error=None
  try:
   verify();image=self.image(identifier);result=self.locate(identifier,image)
  except Exception as exc:error=type(exc).__name__+': '+str(exc)[:500]
  finally:
   if image and not image['preexisting']:
    try:subprocess.run(['docker','image','rm',image['name']],check=True,capture_output=True,timeout=120)
    except Exception as exc:cleanup_error=type(exc).__name__
  case=self.out/'trial'/identifier;case.mkdir(parents=True,exist_ok=True)
  a=case/'locator/diagnostic-audit.json';audit=json.loads(a.read_text()) if a.exists() else None
  calls=[c for c in self.ledger.read()['calls'] if c['context']=='locator:'+identifier]
  received=[c for c in calls if c['status']=='received'];costs=[metered_cost(c) for c in received]
  delivered=(case/'localization.json').is_file()
  row=dict(instance_id=identifier,attempted=True,delivery_success=delivered,status='delivered' if delivered else 'failed',
   raw_compliant=(not audit['violations'] and not audit.get('validator_error')) if audit else None,
   fallback=audit['fallback'] if audit else None,validator_error=audit.get('validator_error') if audit else None,
   violation_details=audit['violations'] if audit else [],violation_rules=sorted({v.split('_')[0] for v in audit['violations']}) if audit else [],
   raw_marks_unread='未读完' in audit['raw_packet']['answer'] if audit else None,
   delivered_marks_unread='未读完' in result.get('finished',{}).get('answer','') if delivered else None,
   delivery_policy='fixed_conservative_fallback' if audit and audit['fallback'] else ('validated_answer' if delivered else None),
   requests=len(calls),received_requests=len(received),runner_request_attempts=result.get('requests'),
   prompt_tokens=sum(c['usage']['prompt_tokens'] for c in received),completion_tokens=sum(c['usage']['completion_tokens'] for c in received),
   metered_cny=sum(costs) if len(received)==len(calls) and all(c is not None for c in costs) else None,
   cost_upper_cny=sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in calls)/1e6,
   locator_seconds=result.get('elapsed_seconds'),wall_seconds=time.time()-start,
   error=error or result.get('technical_failure'),image_cleanup_error=cleanup_error,coding_agent='未运行',harness='未运行')
  write_json(case/'metrics.json',row);return row
 def run(self):
  for identifier in self.auth['trial_ids']:
   state=self.ledger.read()
   if state['stopped'] or any(c['status']=='reserved' for c in state['calls']):
    self.state['global_stop_reason']=state['stopped'] or 'unsettled_request';break
   row=self.one(identifier);self.state['rows'].append(row);self.save()
  self.state.update(current=None,finished_at=time.time(),status='completed' if len(self.state['rows'])==24 else 'stopped',further_runs_authorized=False)
  self.save();write_json(self.out/'completed.json',self.state)
  return dict(status=self.state['status'],attempted=len(self.state['rows']),delivered=sum(r['delivery_success'] for r in self.state['rows']))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);a=p.parse_args()
 try:print(json.dumps(LocatorOnly(a.output,a.credentials,a.authorization).run()))
 finally:
  a.credentials.unlink(missing_ok=True);write_json(PACKAGE/'credential-cleanup.json',dict(credential_exists=a.credentials.exists(),at=time.time()))
if __name__=='__main__':main()
