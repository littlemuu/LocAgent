"""C(v8.2) once; only external orchestration, no frozen runtime mutations."""
import argparse,fcntl,hashlib,json,platform,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
PACKAGE=Path(__file__).resolve().parents[1];FROZEN=PACKAGE/'frozen'
sys.path[:0]=[str(FROZEN),str(FROZEN/'baseline')]
from locagent_e2e.common import CONFIG,manifest,rows,write_json,digest
from locagent_e2e.checkpoint import Runner
from locagent_e2e.driver import config_binding,source_snapshot
from locagent_e2e.ledger import Ledger
from locagent_e2e.transport import LiveTransport
from locagent_e2e.sandbox import DockerSandbox
EXPECTED='031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7'
BASE='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'
LIMIT=15000000
MAX_RESERVATION=1048576*2+4096*8

def verify_frozen():
 f=json.loads((FROZEN/'FREEZE.json').read_text());actual={p:hashlib.sha256((FROZEN/p).read_bytes()).hexdigest() for p in f['files']}
 if actual!=f['files'] or digest(actual)!=EXPECTED or config_binding()!=BASE:raise RuntimeError('frozen_binding_changed')
 if CONFIG['coding']['max_requests']!=40:raise RuntimeError('coding_budget_changed')
 return EXPECTED

def validate(path):
 a=json.loads(Path(path).read_text());m=manifest()
 required={'approved':True,'budget_cny':15,'arm_order':['C'],'trial_ids':m['selection_order'],'repetitions':1,'max_trial_episodes':24,'automatic_retries':0,'concurrency':1,'v82_binding':EXPECTED,'baseline_binding':BASE,'ids_sha256':m['ids_sha256'],'holdout':False,'retain_image_cache':True,'A_B_rerun':False}
 if any(type(a.get(k)) is not type(v) or a.get(k)!=v for k,v in required.items()):raise PermissionError('invalid_C_authorization')
 return a

def aggregate(out):
 calls=[];models=set()
 for path in sorted((Path(out)/'trial').glob('*/ledger.json')):
  state=json.loads(path.read_text())
  for c in state['calls']:
   c=dict(c,instance_id=path.parent.name,local_sequence=c['sequence']);calls.append(c)
   if c.get('actual_model'):models.add(c['actual_model'])
 calls.sort(key=lambda c:c['started_at'])
 held=sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in calls)
 if held>LIMIT:raise RuntimeError('global_cap_exceeded')
 return {'limit_microcny':LIMIT,'calls':calls,'charged_or_reserved_microcny':held,'remaining_microcny':LIMIT-held,'models':sorted(models),'uncertain_requests':sum(c['status']=='reserved' for c in calls)}

class CRunner:
 image=Runner.image
 evaluate=Runner.evaluate
 def __init__(self,out,credential,authorization):
  self.auth=validate(authorization);verify_frozen()
  if platform.system()!='Linux' or platform.machine()!='x86_64':raise PermissionError('cloud_x86_required')
  self.lock=(PACKAGE/'paid-run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.global_lock=Path('/home/ubuntu/.locagent-paid-run.lock').open('a');fcntl.flock(self.global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.out=Path(out).resolve();self.out.mkdir(parents=True,exist_ok=False);self.credential=Path(credential);self.LiveTransport=LiveTransport
  self.tasks={r['instance_id']:r for r in rows()};self.path=self.out/'state.json'
  self.state={'binding':EXPECTED,'baseline_binding':BASE,'control_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'authorization_sha256':digest(self.auth),'started_at':time.time(),'trial_ids':self.auth['trial_ids'],'current':None,'steps':{},'rows':[],'status':'running'};self.save()
 def save(self):write_json(self.path,self.state);write_json(self.out/'ledger.json',aggregate(self.out))
 def once(self,key,fn):
  if key in self.state['steps']:raise RuntimeError('no_retry_of_attempted_stage')
  step={'status':'running','started_at':time.time()};self.state['steps'][key]=step;self.state['current_stage']=key;self.save()
  try:
   result=fn();step.update(status=result.get('status','failed'),result=result)
  except Exception as e:
   result={'status':'failed','technical_failure':type(e).__name__+': '+str(e)[:700]};step.update(status='failed',result=result)
  step['ended_at']=time.time();self.save();return result
 def locator(self,identifier,image):
  from calibration.locator import run,build_packet
  from locagent_e2e.baseline import CurrentRetriever
  task=self.tasks[identifier];case=self.out/'trial'/identifier;box=DockerSandbox(image['id'],task['base_commit'])
  try:
   box.start()
   with TemporaryDirectory(prefix='C-v82-source-') as td:
    snap=source_snapshot(box.source_archive(),Path(td)/'source');retriever=CurrentRetriever(snap)
    result=run(issue=task['problem_statement'],output=case/'locator',transport=self.LiveTransport(self.credential,self.ledger,case/'locator-wire','trial:'+identifier+':locator'),locator=retriever)
    if result['status']=='completed':
     packet=build_packet(result,instance_id=identifier,base_commit=task['base_commit']);write_json(case/'localization.json',packet)
    return result
  finally:box.close()
 def coding(self,identifier,image):
  from locagent_e2e.agent import run
  task=self.tasks[identifier];episode=self.out/'trial'/identifier/'C';episode.mkdir(parents=True,exist_ok=False);box=DockerSandbox(image['id'],task['base_commit'])
  packet=json.loads((episode.parent/'localization.json').read_text())
  assert packet['instance_id']==identifier and packet['base_commit']==task['base_commit']
  try:
   box.start()
   if box.patch():raise RuntimeError('dirty_agent_base')
   transport=self.LiveTransport(self.credential,self.ledger,episode/'wire','trial:'+identifier+':C')
   result=run(issue=task['problem_statement'],output=episode/'agent',transport=transport,sandbox=box,packet=packet)
   patch=box.patch();(episode/'patch.diff').write_text(patch)
   pred={'instance_id':identifier,'model_name_or_path':'locagent-deepseek-flash-C','model_patch':patch}
   write_json(episode/'prediction.json',pred);(episode/'prediction.jsonl').write_text(json.dumps(pred)+'\n')
   result.update(empty_patch=not bool(patch.strip()),patch_bytes=len(patch.encode()),patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),execution_mode='live',new_model_requests=len(transport.records))
   write_json(episode/'coding.json',result);return result
  finally:box.close()
 def one(self,identifier):
  verify_frozen();self.state['current']=identifier;self.save();start=time.time()
  global_budget=aggregate(self.out)
  row={'instance_id':identifier,'arm':'C','status':'not_run','resolved':None,'empty_patch':None,'first_source_edit_request':None,'errors':[]}
  if len(global_budget['models'])>1 or global_budget['remaining_microcny']<MAX_RESERVATION:
   row['reason']='model_identifier_drift' if len(global_budget['models'])>1 else '15_cny_cap_cannot_reserve_next_request';return row
  case=self.out/'trial'/identifier;case.mkdir(parents=True,exist_ok=False)
  # Per-task frozen Ledger instances isolate a failed request. The next task
  # receives only GLOBAL remaining funds; uncertain full reservations stay held.
  # Never clear a ledger stop, reuse/retry a failed stage, or reset spent money.
  self.ledger=Ledger(case/'ledger.json',global_budget['remaining_microcny']/1e6)
  image=self.once(identifier+':image',lambda:self.image(identifier))
  if image['status']!='completed':row['errors'].append({'stage':'image',**image});row['status']='failed'
  else:
   row['image_preexisting']=image['preexisting'];row['image_pull_seconds']=image['pull_elapsed_seconds']
   loc=self.once(identifier+':locator',lambda:self.locator(identifier,image))
   if loc['status']!='completed':row['errors'].append({'stage':'locator','failure':loc.get('technical_failure')});row['status']='failed'
   else:
    code=self.once(identifier+':coding',lambda:self.coding(identifier,image));row['coding_status']=code['status']
    row.update(empty_patch=code.get('empty_patch'),first_source_edit_request=code.get('first_source_edit_request'),coding_requests=code.get('requests'),finish_kind=code.get('finish_kind'))
    if code['status']!='completed':row['errors'].append({'stage':'coding','failure':code.get('technical_failure')})
    if (case/'C/prediction.json').exists():
     ev=self.once(identifier+':evaluation',lambda:self.evaluate('trial',identifier,'C'));row['resolved']=ev.get('resolved');row['evaluation_status']=ev['status']
     if ev['status']!='completed':row['errors'].append({'stage':'evaluation','failure':ev.get('technical_failure')})
    row['status']='completed' if not row['errors'] else 'failed'
  row['elapsed_seconds']=time.time()-start
  audit=case/'locator/diagnostic-audit.json';result=case/'locator/result.json'
  if audit.exists() and json.loads(audit.read_text()) is not None:
   a=json.loads(audit.read_text());row.update(full_fallback=a['fallback'],disclosure_count=a['disclosure_count'],rule_counts=a['rule_counts'],validator_error=a['validator_error'])
  if result.exists():
   r=json.loads(result.read_text());errors=[{'index':i,'arguments':t['arguments'],'error':t['result']['error']} for i,t in enumerate(r['tool_audit'],1) if t['tool']=='read_file' and isinstance(t['result'],dict) and 'error' in t['result']]
   row['read_file_error_count']=len(errors);write_json(case/'read-file-errors.json',errors)
  write_json(case/'task-summary.json',row);return row
 def run(self):
  for identifier in self.auth['trial_ids']:
   try:row=self.one(identifier)
   except Exception as e:
    row={'instance_id':identifier,'arm':'C','status':'failed','resolved':None,'empty_patch':None,'first_source_edit_request':None,'errors':[{'stage':'orchestration','failure':type(e).__name__+': '+str(e)[:700]}]}
   self.state['rows'].append(row);self.save()
  self.state.update(current=None,current_stage=None,status='finished',finished_at=time.time(),further_runs_authorized=False);self.save();write_json(self.out/'completed.json',self.state)
  return {'status':'finished','rows':len(self.state['rows']),'completed':sum(r['status']=='completed' for r in self.state['rows'])}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);a=p.parse_args()
 try:print(json.dumps(CRunner(a.output,a.credentials,a.authorization).run()))
 finally:
  a.credentials.unlink(missing_ok=True);write_json(PACKAGE/'credential-cleanup.json',{'credential_exists':a.credentials.exists(),'at':time.time()})
if __name__=='__main__':main()
