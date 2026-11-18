"""Checkpoint handoff after explicit removal of the overall API money ceiling.
Only external orchestration changes; each locator/coding/evaluation runs once.
"""
import argparse,fcntl,json,time
from pathlib import Path
import run_c as base
from run_c import CRunner,PACKAGE,EXPECTED,BASE,MAX_RESERVATION,Ledger,write_json

def uncapped_aggregate(out):
 calls=[];models=set()
 for path in sorted((Path(out)/'trial').glob('*/ledger.json')):
  for item in json.loads(path.read_text())['calls']:
   c=dict(item,instance_id=path.parent.name,local_sequence=item['sequence']);calls.append(c)
   if c.get('actual_model'):models.add(c['actual_model'])
 calls.sort(key=lambda c:c['started_at'])
 held=sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in calls)
 # Frozen 4 locator + 40 coding requests cannot reach this per-case bound.
 # It merely satisfies the frozen Ledger interface; no total money gate.
 return {'limit_microcny':None,'budget_policy':'overall_API_ceiling_removed_by_user','calls':calls,'charged_or_reserved_microcny':held,'remaining_microcny':44*MAX_RESERVATION,'remaining_semantics':'theoretical_per_case_maximum_not_remaining_total_funds','models':sorted(models),'uncertain_requests':sum(c['status']=='reserved' for c in calls)}

def finalize_evaluation(state,out):
 key=state['current_stage'];assert key.endswith(':evaluation')
 ident=key.rsplit(':',1)[0];assert ident==state['current']
 assert ident not in {r['instance_id'] for r in state['rows']}
 steps=state['steps'];step=steps[key];assert step['status']=='running'
 case=out/'trial'/ident;evpath=case/'C/harness/evaluation.json';ev=json.loads(evpath.read_text())
 assert ev['status']=='completed' and type(ev['resolved']) is bool
 step.update(status=ev['status'],result=ev,ended_at=evpath.stat().st_mtime)
 code=steps[ident+':coding']['result'];im=steps[ident+':image']['result']
 row={'instance_id':ident,'arm':'C','status':'completed','resolved':ev['resolved'],'empty_patch':code.get('empty_patch'),'first_source_edit_request':code.get('first_source_edit_request'),'coding_requests':code.get('requests'),'finish_kind':code.get('finish_kind'),'coding_status':code['status'],'evaluation_status':ev['status'],'image_preexisting':im['preexisting'],'image_pull_seconds':im['pull_elapsed_seconds'],'elapsed_seconds':step['ended_at']-steps[ident+':image']['started_at'],'errors':[],'controller_handoff':'evaluation finished independently while parent controller paused; no stage repeated'}
 if code['status']!='completed':row['errors'].append({'stage':'coding','failure':code.get('technical_failure')});row['status']='failed'
 audit=json.loads((case/'locator/diagnostic-audit.json').read_text())
 if audit:row.update(full_fallback=audit['fallback'],disclosure_count=audit['disclosure_count'],rule_counts=audit['rule_counts'],validator_error=audit['validator_error'])
 loc=json.loads((case/'locator/result.json').read_text())
 errors=[{'index':i,'arguments':t['arguments'],'error':t['result']['error']} for i,t in enumerate(loc['tool_audit'],1) if t['tool']=='read_file' and isinstance(t['result'],dict) and 'error' in t['result']]
 row['read_file_error_count']=len(errors);write_json(case/'read-file-errors.json',errors);write_json(case/'task-summary.json',row);state['rows'].append(row)
 return ident

class Continuation(CRunner):
 def __init__(self,out,credential,authorization,amendment):
  self.auth=base.validate(authorization);base.verify_frozen();a=json.loads(amendment.read_text())
  assert a['user_instruction']=='取消API预算门槛，跑完再停' and a['api_budget_cny'] is None and a['v82_binding']==EXPECTED and a['repetitions']==1
  self.lock=(PACKAGE/'paid-run.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.global_lock=Path('/home/ubuntu/.locagent-paid-run.lock').open('a');fcntl.flock(self.global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  self.out=out.resolve();self.path=self.out/'state.json';self.state=json.loads(self.path.read_text());self.credential=credential;self.LiveTransport=base.LiveTransport;self.tasks={r['instance_id']:r for r in base.rows()}
  assert self.state['binding']==EXPECTED and self.state['baseline_binding']==BASE and self.state['status']=='running'
  assert self.state['trial_ids']==self.auth['trial_ids']
  assert not (PACKAGE/'continuation-started.json').exists(),'never start continuation twice'
  receipt=json.loads((PACKAGE/'budget-change-pause.json').read_text())
  assert not Path('/proc/'+str(receipt['controller_pid'])).exists(),'prior controller still exists'
  assert (PACKAGE/'handoff/phase1.exit').read_text().strip()=='137'
  assert not uncapped_aggregate(self.out)['uncertain_requests'],'do not continue with a pending/uncertain API request'
  base.aggregate=uncapped_aggregate
  finished=finalize_evaluation(self.state,self.out)
  self.state.update(api_budget_cny=None,budget_amendment=a,budget_handoff_completed_task=finished,budget_handoff_at=time.time())
  write_json(PACKAGE/'continuation-started.json',{'at':time.time(),'finalized_without_rerun':finished,'completed_ids':[r['instance_id'] for r in self.state['rows']],'remaining_ids':[i for i in self.auth['trial_ids'] if i not in {r['instance_id'] for r in self.state['rows']}]});self.save()
 def run(self):
  done={r['instance_id'] for r in self.state['rows']}
  for ident in self.auth['trial_ids']:
   if ident in done:continue
   try:row=self.one(ident)
   except Exception as e:row={'instance_id':ident,'arm':'C','status':'failed','resolved':None,'empty_patch':None,'first_source_edit_request':None,'errors':[{'stage':'orchestration','failure':type(e).__name__+': '+str(e)[:700]}]}
   self.state['rows'].append(row);self.save()
  self.state.update(current=None,current_stage=None,status='finished',finished_at=time.time(),further_runs_authorized=False);self.save();write_json(self.out/'completed.json',self.state)
  return {'status':'finished','rows':len(self.state['rows']),'completed':sum(r['status']=='completed' for r in self.state['rows'])}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--amendment',type=Path,required=True);a=p.parse_args()
 try:print(json.dumps(Continuation(a.output,a.credentials,a.authorization,a.amendment).run()))
 finally:a.credentials.unlink(missing_ok=True);write_json(PACKAGE/'credential-cleanup.json',{'credential_exists':a.credentials.exists(),'at':time.time()})
if __name__=='__main__':main()
