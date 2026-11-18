"""Offline factual summaries from original v5 and this run's collected evidence."""
import collections,csv,json,math,statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
P=Path(__file__).resolve().parents[1];RUN=P/'evidence/run';D=P/'delivery'
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def metered(c):
 peak=c.get('peak_cache_adjusted_microcny')
 if peak is None:return None
 t=datetime.fromtimestamp(c['started_at'],ZoneInfo('Asia/Shanghai'))
 factor=1 if t.weekday()<5 and (9<=t.hour<12 or 14<=t.hour<18) else .5
 return peak*factor/1e6

def costs(calls):
 settled=[c for c in calls if c['status']=='received'];values=[metered(c) for c in settled]
 return {'requests':len(calls),'received_requests':len(settled),'input_tokens':sum(c['usage']['prompt_tokens'] for c in settled),'output_tokens':sum(c['usage']['completion_tokens'] for c in settled),'metered_cny':sum(values) if all(v is not None for v in values) else None,'peak_cache_adjusted_cny':sum(c['peak_cache_adjusted_microcny'] for c in settled)/1e6 if all(c.get('peak_cache_adjusted_microcny') is not None for c in settled) else None,'upper_cny':sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in calls)/1e6,'uncertain_requests':len(calls)-len(settled)}

def p_exact(wins,losses):
 n=wins+losses
 return min(1.,2*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/(2**n)) if n else 1.

def main():
 state=read(RUN/'state.json');hist=read(P/'history/v5-summary.json');ids=state['trial_ids'];C=[]
 for n,ident in enumerate(ids,1):
  row=next((dict(r) for r in state['rows'] if r['instance_id']==ident),{'instance_id':ident,'status':'not_run','resolved':None,'empty_patch':None});case=RUN/'trial'/ident
  calls=read(case/'ledger.json')['calls'] if (case/'ledger.json').exists() else []
  code=read(case/'C/coding.json') if (case/'C/coding.json').exists() else {}
  loc=read(case/'locator/result.json') if (case/'locator/result.json').exists() else {}
  audit=read(case/'locator/diagnostic-audit.json') if (case/'locator/diagnostic-audit.json').exists() else None
  stages={key.rsplit(':',1)[-1]:v for key,v in state['steps'].items() if key.startswith(ident+':')}
  sec=lambda v:v.get('ended_at',v['started_at'])-v['started_at']
  row.update(number=n,arm='C',coding_cost=costs([c for c in calls if c['context'].endswith(':C')]),localization_cost=costs([c for c in calls if c['context'].endswith(':locator')]),total_cost=costs(calls),total_seconds=sum(sec(v) for k,v in stages.items() if k in ['locator','coding','evaluation']),localization_seconds=sec(stages['locator']) if 'locator' in stages else None,coding_elapsed_seconds=code.get('elapsed_seconds'),first_source_edit_request=code.get('first_source_edit_request'),coding_requests=code.get('requests'),locator_requests=loc.get('requests'),used_all_40=code.get('requests')==40 if code else None,empty_patch=code.get('empty_patch'),finish_kind=code.get('finish_kind'))
  if audit:row.update(full_fallback=audit['fallback'],disclosure_count=audit['disclosure_count'],rule_counts=audit['rule_counts'],validator_error=audit['validator_error'])
  errors=[{'index':i,'arguments':t['arguments'],**t['result']} for i,t in enumerate(loc.get('tool_audit',[]),1) if t['tool']=='read_file' and isinstance(t['result'],dict) and 'error' in t['result']]
  row['read_file_errors']=errors;row['read_file_error_count']=len(errors) if loc else None
  C.append(row)
 allrows=hist['trial_rows']+C;arms={}
 for arm in ['A','B','C']:
  rr=[r for r in allrows if r['arm']==arm];edits=[r['first_source_edit_request'] for r in rr if r.get('first_source_edit_request') is not None];empty=[r['empty_patch'] for r in rr if type(r.get('empty_patch')) is bool]
  sums={k:sum(r['total_cost'][k] for r in rr) if all(r['total_cost'].get(k) is not None for r in rr) else None for k in ['requests','input_tokens','output_tokens','metered_cny','upper_cny']}
  sums['total_tokens']=sums['input_tokens']+sums['output_tokens']
  arms[arm]={'tasks':len(rr),'completed':sum(r['status']=='completed' for r in rr),'resolved':sum(r.get('resolved') is True for r in rr),'unresolved':sum(r.get('resolved') is False for r in rr),'unscored':sum(type(r.get('resolved')) is not bool for r in rr),'empty_patch_count':sum(empty),'empty_patch_observed':len(empty),'empty_patch_rate':sum(empty)/len(empty) if empty else None,'first_edit_median_among_edited':statistics.median(edits) if edits else None,'edited_count':len(edits),'totals':sums,'wall_seconds_excluding_images_including_locator_harness':sum(r['total_seconds'] for r in rr)}
 pairs={}
 for other in ['B','A']:
  wins=[];losses=[];same_true=[];same_false=[];unknown=[]
  for ident in ids:
   c=next(r for r in C if r['instance_id']==ident);b=next(r for r in hist['trial_rows'] if r['arm']==other and r['instance_id']==ident)
   if type(c.get('resolved')) is not bool:unknown.append(ident);continue
   (same_true if c['resolved'] and b['resolved'] else wins if c['resolved'] else losses if b['resolved'] else same_false).append(ident)
  pairs['C_vs_'+other]={'C_resolved_other_not':wins,'C_not_other_resolved':losses,'both_resolved':same_true,'both_unresolved':same_false,'unscored_excluded':unknown,'complete_pairs':len(ids)-len(unknown),'McNemar_exact_two_sided_p':p_exact(len(wins),len(losses))}
 groups={}
 for label,cond in [('有披露',lambda r:r.get('disclosure_count',0)>0),('无披露',lambda r:r.get('disclosure_count')==0),('定位未交付',lambda r:r.get('disclosure_count') is None)]:
  rr=[r for r in C if cond(r)];scored=[r for r in rr if type(r.get('resolved')) is bool];resolved=sum(r.get('resolved') is True for r in rr)
  groups[label]={'tasks':len(rr),'scored':len(scored),'resolved':resolved,'resolved_rate_among_scored':resolved/len(scored) if scored else None,'instance_ids':[r['instance_id'] for r in rr]}
 bh=read(P/'history/B-read-file-errors.json');bmap={r['instance_id']:r for r in bh}
 readerrors=[{'instance_id':r['instance_id'],'C_count':r['read_file_error_count'],'C_errors':r['read_file_errors'],'B_count':bmap[r['instance_id']]['read_file_error_count'],'B_errors':bmap[r['instance_id']]['errors']} for r in C]
 focus=['astropy__astropy-12907','django__django-13964','django__django-13033','sympy__sympy-18698','django__django-13925']
 summary={'binding':state['binding'],'baseline_binding':state['baseline_binding'],'arms':arms,'pairs':pairs,'disclosure_groups':groups,'C_full_fallback':sum(r.get('full_fallback') is True for r in C),'C_validator_errors':sum(bool(r.get('validator_error')) for r in C),'C_rule_counts':{rule:sum(r.get('rule_counts',{}).get(rule,0) for r in C) for rule in ['R1','R2','R3','R4']},'C_read_file_error_count':sum(r['C_count'] or 0 for r in readerrors),'B_read_file_error_count':sum(r['B_count'] for r in readerrors),'focus':{i:{arm:next(r for r in allrows if r['instance_id']==i and r['arm']==arm) for arm in ['A','B','C']} for i in focus},'C_run_wall_seconds':state.get('finished_at',state['started_at'])-state['started_at'],'C_start_epoch':state['started_at'],'C_finish_epoch':state.get('finished_at'),'C_image_cache_hits':sum(r.get('image_preexisting') is True for r in C),'C_image_pull_seconds':sum(r.get('image_pull_seconds',0) for r in C),'C_API_upper_cap_cny':state.get('api_budget_cny',15),'budget_amendment':state.get('budget_amendment'),'budget_handoff_at':state.get('budget_handoff_at'),'C_final_budget':read(RUN/'ledger.json'),'batch_caveat':'C(v8.2) and v5 A/B were run at different times; model/service/sampling/cache and price-window variation may contribute. dev24 development only, no final conclusion.','requests_2317':'Original harness scoring preserved; certificate issue separately annotated; not rescored.','account_bill_observed':False}
 write(D/'summary.json',summary);write(D/'C-per-task.json',C);write(D/'read-file-errors-BC.json',readerrors);write(D/'ABC-per-task.json',allrows)
 fields=['number','instance_id','status','resolved','empty_patch','first_source_edit_request','coding_requests','locator_requests','total_requests','input_tokens','output_tokens','total_tokens','metered_cny','upper_cny','used_all_40','full_fallback','disclosure_count','rule_counts','validator_error','read_file_error_count','total_cost','total_seconds','errors']
 with (D/'C-per-task.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in C:
   t=r['total_cost'];flat=dict(r,total_requests=t['requests'],input_tokens=t['input_tokens'],output_tokens=t['output_tokens'],total_tokens=t['input_tokens']+t['output_tokens'],metered_cny=t['metered_cny'],upper_cny=t['upper_cny'])
   w.writerow({k:json.dumps(flat[k],ensure_ascii=False) if isinstance(flat.get(k),(dict,list)) else flat.get(k) for k in fields})
 print(json.dumps({k:v for k,v in summary.items() if k in ['arms','pairs','disclosure_groups','C_read_file_error_count','B_read_file_error_count']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
