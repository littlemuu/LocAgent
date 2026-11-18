"""Predeclared offline analysis. Requires one-time unblinding receipt, never sends API calls."""
import collections,csv,json,math,re,statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from support import P,load,durable

def exact(b,c):
 n=b+c
 return min(1.,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.
def holm(values):
 out={};running=0.
 for i,(key,p) in enumerate(sorted(values.items(),key=lambda x:x[1])):
  running=max(running,(len(values)-i)*p);out[key]=min(1.,running)
 return out
def costs(calls):
 got=[x for x in calls if x['status']=='received'];actual=[];peak=[]
 for x in got:
  p=x.get('peak_cache_adjusted_microcny');peak.append(p)
  t=datetime.fromtimestamp(x['started_at'],ZoneInfo('Asia/Shanghai'));factor=1 if t.weekday()<5 and (9<=t.hour<12 or 14<=t.hour<18) else .5
  actual.append(None if p is None else p*factor/1e6)
 return {'requests':len(calls),'received_requests':len(got),'uncertain_requests':len(calls)-len(got),'input_tokens':sum(x['usage']['prompt_tokens'] for x in got),'output_tokens':sum(x['usage']['completion_tokens'] for x in got),'total_tokens':sum(x['usage']['total_tokens'] for x in got),'cache_hit_tokens':sum(x['usage'].get('prompt_cache_hit_tokens',0) for x in got),'cache_miss_tokens':sum(x['usage'].get('prompt_cache_miss_tokens',0) for x in got),'cache_usage_complete':all('prompt_cache_hit_tokens' in x['usage'] and 'prompt_cache_miss_tokens' in x['usage'] for x in got),'metered_cny':sum(actual) if all(x is not None for x in actual) else None,'peak_cache_adjusted_cny':sum(peak)/1e6 if all(x is not None for x in peak) else None,'upper_cny':sum(x['charged_upper_microcny'] for x in got)/1e6,'uncertain_reservation_cny':sum(x['reserved_microcny'] for x in calls if x['status']!='received')/1e6}
def arms(rows):
 out={}
 for a in ['A','B','C']:
  rr=[r for r in rows if r['arm']==a];edits=[r['first_source_edit_request'] for r in rr if r.get('first_source_edit_request') is not None];empty=[r['empty_patch'] for r in rr if type(r.get('empty_patch')) is bool]
  keys=['requests','input_tokens','output_tokens','total_tokens','metered_cny','upper_cny']
  totals={k:sum(r['total_cost'][k] for r in rr) if all(r.get('total_cost',{}).get(k) is not None for r in rr) else None for k in keys}
  out[a]={'tasks':len(rr),'resolved':sum(r.get('resolved') is True for r in rr),'resolved_rate_fixed_denominator':sum(r.get('resolved') is True for r in rr)/len(rr),'scored':sum(type(r.get('resolved')) is bool for r in rr),'not_run':sum(r['status']=='not_run' for r in rr),'technical_or_budget_failure':sum(r['status']=='failed' for r in rr),'empty_patch_count':sum(empty),'empty_patch_observed':len(empty),'empty_patch_rate':sum(empty)/len(empty) if empty else None,'edited_count':len(edits),'first_edit_median_among_edited':statistics.median(edits) if edits else None,'totals':totals,'stage_seconds':sum(r.get('total_seconds',0) for r in rr)}
 return out
def pairs(rows,ids,complete_only=False):
 by={(r['instance_id'],r['arm']):r for r in rows};out={}
 for first,second in [('C','A'),('C','B'),('B','A')]:
  win=[];lose=[];same_yes=[];same_no=[];excluded=[]
  for i in ids:
   x=by[i,first].get('resolved');y=by[i,second].get('resolved')
   if complete_only and (type(x)is not bool or type(y)is not bool):excluded.append(i);continue
   xx=x is True;yy=y is True
   (same_yes if xx and yy else win if xx else lose if yy else same_no).append(i)
  out[first+'_vs_'+second]={'first_resolved_other_not':win,'first_not_other_resolved':lose,'both_resolved':same_yes,'neither_observed_resolved':same_no,'excluded_unscored':excluded,'paired_count':len(ids)-len(excluded),'McNemar_exact_two_sided_p':exact(len(win),len(lose))}
 adjusted=holm({k:v['McNemar_exact_two_sided_p'] for k,v in out.items()})
 for k,v in out.items():v['Holm_p_three_predeclared_comparisons']=adjusted[k]
 return out
def maybe(p):return load(p) if p.exists() else {}
def main():
 assert (P/'unblinding-receipt.json').exists(),'results_remain_sealed'
 run=P/'evidence/run';state=load(run/'completed.json');ids=[t['instance_id'] for t in load(P/'execution-order.json')['tasks']];rows=[];fail=[]
 for raw in state['rows']:
  r=dict(raw);i=r['instance_id'];a=r['arm'];d=run/'trial'/i/a
  ledger=maybe(d/'ledger.json').get('calls',[]);code=maybe(d/'coding.json');loc=maybe(d/'locator/result.json');audit=maybe(d/'locator/diagnostic-audit.json')
  r.update(total_cost=costs(ledger),coding_cost=costs([x for x in ledger if x['context'].endswith(':coding')]),localization_cost=costs([x for x in ledger if x['context'].endswith(':locator')]),first_source_edit_request=code.get('first_source_edit_request'),coding_requests=code.get('requests'),locator_requests=loc.get('requests'),used_all_40=code.get('requests')==40 if code else None,empty_patch=code.get('empty_patch'),finish_kind=code.get('finish_kind'))
  stages={k.rsplit('--',1)[1]:v for k,v in state['steps'].items() if k.startswith(i+'--'+a+'--')}
  r['stage_seconds']={k:v.get('ended_at',v['started_at'])-v['started_at'] for k,v in stages.items()};r['total_seconds']=sum(r['stage_seconds'].values())
  if a=='C':r.update(disclosure_count=audit.get('disclosure_count') if audit else None,rule_counts=audit.get('rule_counts') if audit else None,full_fallback=audit.get('fallback') if audit else None,validator_error=audit.get('validator_error') if audit else None)
  errs=[{'index':n,'arguments':t['arguments'],**t['result']} for n,t in enumerate(loc.get('tool_audit',[]),1) if t['tool']=='read_file' and isinstance(t['result'],dict) and 'error' in t['result']]
  r.update(read_file_error_count=len(errs) if loc else None,read_file_errors=errs);rows.append(r)
  if r.get('resolved') is not True:
   tools=code.get('tool_audit',[]);commands=[]
   for t in tools:
    if t['tool']=='terminal':commands.append((t.get('request'),t.get('arguments',{}).get('command','')))
   clusters=[]
   for cmd,count in collections.Counter(c for _,c in commands).most_common():
    if count>1:clusters.append({'command':cmd,'count':count,'requests':[n for n,c in commands if c==cmd]})
   f={'number':r['number'],'instance_id':i,'arm':a,'status':r['status'],'resolved':r.get('resolved'),'coding_requests':r['coding_requests'],'used_all_40':r['used_all_40'],'no_progress_loop':'未运行' if not code else '待离线证据审阅','wrong_localization_adoption':'未运行' if not code else '待离线证据审阅' if a=='C' else '不适用','repeated_commands':clusters,'source_edit_events':code.get('source_edit_events',[]),'finished':code.get('finished'),'localization':maybe(d/'localization.json').get('result'),'tool_calls':tools}
   durable(P/'delivery/failure-audit'/i/(a+'.json'),f);fail.append({k:f[k] for k in ['number','instance_id','arm','status','coding_requests','used_all_40','no_progress_loop','wrong_localization_adoption']})
 hist=load(P/'history/dev24-ABC-per-task.json')
 for r in hist:
  if 'total_tokens' not in r['total_cost']:r['total_cost']['total_tokens']=r['total_cost']['input_tokens']+r['total_cost']['output_tokens']
 summary={'status':state['status'],'holdout_only_inference':True,'holdout_arms':arms(rows),'primary_fixed_50_pairs':pairs(rows,ids),'complete_scored_pair_sensitivity':pairs(rows,ids,True),'dev24_descriptive_arms':arms(hist),'combined_74_descriptive_arms':arms(hist+rows),'run_wall_seconds':state['finished_at']-state['started_at'],'image_seconds':sum(v.get('ended_at',v['started_at'])-v['started_at'] for k,v in state['steps'].items() if k.endswith('--image')),'stop_reason':state.get('stop_reason'),'actual_account_bill_observed':False,'C_full_fallback':sum(r.get('full_fallback') is True for r in rows if r['arm']=='C'),'C_validator_errors':sum(bool(r.get('validator_error')) for r in rows if r['arm']=='C'),'C_rule_counts':{k:sum((r.get('rule_counts') or {}).get(k,0) for r in rows if r['arm']=='C') for k in ['R1','R2','R3','R4']}}
 durable(P/'delivery/ABC-per-task.json',rows);durable(P/'delivery/failure-judgments-pending.json',fail);durable(P/'delivery/summary.json',summary)
 fields=['number','instance_id','arm','status','resolved','empty_patch','first_source_edit_request','coding_requests','locator_requests','used_all_40','disclosure_count','rule_counts','full_fallback','validator_error','read_file_error_count','total_cost','total_seconds','image_id','errors','reason']
 with (P/'delivery/ABC-per-task.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(r[k],ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in fields})
 print(json.dumps({'holdout_arms':summary['holdout_arms'],'pairs':summary['primary_fixed_50_pairs'],'failure_rows_for_review':len(fail)},ensure_ascii=False))
if __name__=='__main__':main()
