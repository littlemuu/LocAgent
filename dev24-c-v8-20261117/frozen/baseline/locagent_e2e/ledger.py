"""One durable budget for all paid calls; lock, reserve before send, never retry."""
import fcntl,json,os,time
from pathlib import Path
from .common import write_json,digest
class BudgetStop(RuntimeError):pass
class Ledger:
 def __init__(self,path,limit_cny=10):
  self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  if not self.path.exists():write_json(self.path,{'limit_microcny':round(limit_cny*1000000),'calls':[],'stopped':None})
  if self.read()['limit_microcny']!=round(limit_cny*1000000):raise BudgetStop('budget_binding_changed')
 def read(self):return json.loads(self.path.read_text())
 def update(self,fn):
  with self.path.with_suffix('.lock').open('a') as f:
   fcntl.flock(f,fcntl.LOCK_EX);state=self.read();value=fn(state);write_json(self.path,state);return value
 def reserve(self,request_bytes,max_tokens,context):
  # Reserve the full advertised context at peak rates; never rely on a tokenizer estimate for the money ceiling.
  reserved=1048576*2+max_tokens*8
  def action(s):
   if s['stopped'] or any(r['status']=='reserved' for r in s['calls']):raise BudgetStop('ledger_stopped_or_uncertain_request')
   if sum(r.get('charged_upper_microcny',r['reserved_microcny']) for r in s['calls'])+reserved>s['limit_microcny']:raise BudgetStop('ten_yuan_cap_would_be_exceeded')
   item={'sequence':len(s['calls'])+1,'context':context,'status':'reserved','reserved_microcny':reserved,'input_token_bound':request_bytes+4096,'max_output_tokens':max_tokens,'started_at':time.time()};s['calls'].append(item);return item.copy()
  return self.update(action)
 def settle(self,sequence,raw,elapsed):
  def action(s):
   r=s['calls'][sequence-1];u=raw['usage'];p,c,t=[u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')]
   if any(type(x)is not int for x in (p,c,t)) or min(p,c)<0 or p+c!=t or p>r['input_token_bound'] or c>r['max_output_tokens']:raise ValueError('invalid_usage')
   model=raw.get('model')
   if not isinstance(model,str) or not model:raise ValueError('missing_actual_model')
   hit=u.get('prompt_cache_hit_tokens');miss=u.get('prompt_cache_miss_tokens')
   if hit is not None and miss is not None and (type(hit)is not int or type(miss)is not int or min(hit,miss)<0 or hit+miss!=p):raise ValueError('invalid_cache_usage')
   r.update(status='received',usage=u,actual_model=model,system_fingerprint=raw.get('system_fingerprint'),response_id=raw.get('id'),elapsed_seconds=elapsed,charged_upper_microcny=p*2+c*8,peak_cache_adjusted_microcny=(miss*2+hit*.04+c*8) if hit is not None and miss is not None else None)
   models={x.get('actual_model') for x in s['calls'] if x.get('actual_model')}
   if len(models)>1:s['stopped']='actual_model_identifier_drift'
   return r.copy()
  return self.update(action)
 def stop(self,reason):return self.update(lambda s:s.update(stopped=reason))
