"""Join current C records with immutable v5 A/B summaries; no task/reference patches."""
import argparse,csv,datetime,json,math,statistics
from pathlib import Path

def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default

def cost(records):
 out=dict(requests=len(records),input_tokens=0,output_tokens=0,metered_cny=0.,upper_cny=0.,uncertain_requests=0)
 for r in records:
  if r['status']!='received':out['uncertain_requests']+=1;continue
  u=r['usage'];out['input_tokens']+=u['prompt_tokens'];out['output_tokens']+=u['completion_tokens'];out['upper_cny']+=r['charged_upper_microcny']/1e6
  d=datetime.datetime.fromtimestamp(r['started_at'],datetime.timezone(datetime.timedelta(hours=8)))
  peak=d.weekday()<5 and (9<=d.hour<12 or 14<=d.hour<18)
  value=r.get('peak_cache_adjusted_microcny')
  out['metered_cny']+=(r['charged_upper_microcny'] if value is None else value)/1e6*(1 if peak else .5)
 return out

def exact(b,c):
 n=b+c
 return min(1.,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.

def compare(C,other):
 shared=[i for i in C if i in other];wins=[i for i in shared if C[i]['resolved'] and not other[i]['resolved']];losses=[i for i in shared if other[i]['resolved'] and not C[i]['resolved']]
 return dict(complete_pairs=len(shared),C_correct_other_wrong=wins,C_wrong_other_correct=losses,exact_mcnemar_two_sided_p=exact(len(wins),len(losses)) if shared else None)

def summarize(root,old):
 run=root/'run';s=read(run/'state.json',{});l=read(run/'ledger.json',{'calls':[]});calls=l['calls'];ids=s.get('trial_ids',[])
 rows=[]
 for index,i in enumerate(ids,1):
  case=run/'trial'/i;episode=read(case/'C/episode.json');m=read(case/'localization-metrics.json',{})
  row=episode or dict(instance_id=i,arm='C',status='未运行',resolved=None,empty_patch=None,first_source_edit_request=None)
  row=dict(row);row['number']=index
  row['coding_cost']=cost([r for r in calls if r['context']=='trial:'+i+':C'])
  row['localization_cost']=cost([r for r in calls if r['context']=='trial:'+i+':locator'])
  row['total_cost']=cost([r for r in calls if r['context'] in ['trial:'+i+':C','trial:'+i+':locator']])
  loc=s.get('steps',{}).get('trial:'+i+':locator',{})
  row['localization_seconds']=loc['ended_at']-loc['started_at'] if loc.get('ended_at') is not None else None
  row['localization_status']=loc.get('status','未运行')
  if loc.get('status')=='failed' and not episode:row['status']='定位技术失败；编码/评测未运行'
  row['total_seconds']=row['wall_seconds']+row['localization_seconds'] if episode and row['localization_seconds'] is not None else None
  row['localization_metrics']=m or None
  code=read(case/'C/agent/result.json')
  if not episode and code:row['status']='未完成';row['coding_status']=code['status'];row['technical_failure']=code.get('technical_failure')
  rows.append(row)
 complete=[r for r in rows if r['status']=='completed'];c={r['instance_id']:r for r in complete}
 first=[r['first_source_edit_request'] for r in complete if r['first_source_edit_request'] is not None]
 arms=dict(old['arms']);arms['C']=dict(completed=len(complete),resolved=sum(r['resolved'] is True for r in complete) if complete else None,
   empty_patch_count=sum(r['empty_patch'] for r in complete) if complete else None,empty_patch_rate=sum(r['empty_patch'] for r in complete)/len(complete) if complete else None,
   first_source_edit_median=statistics.median(first) if first else None,ever_edited_count=len(first),never_edited_count=len(complete)-len(first),
   totals=cost(calls),wall_seconds_including_locator=sum(r['total_seconds'] for r in complete) if complete else None)
 metrics=[r['localization_metrics'] for r in rows if r['localization_metrics']]
 groups={}
 for fallback in [True,False]:
  group=[r for r in complete if r['localization_metrics']['fallback']==fallback]
  groups['fallback' if fallback else 'non_fallback']=dict(completed=len(group),resolved=sum(r['resolved'] for r in group) if group else None,resolved_rate=sum(r['resolved'] for r in group)/len(group) if group else None,instance_ids=[r['instance_id'] for r in group])
 pairs={}
 for arm in ['A','B']:pairs['C_vs_'+arm]=compare(c,{r['instance_id']:r for r in old['trial_rows'] if r['arm']==arm and r['status']=='completed'})
 done=read(run/'completed.json')
 return dict(arms=arms,trial_rows=old['trial_rows']+rows,C_rows=rows,pairwise=pairs,
   locator_completed=len(metrics),fallback_count=sum(m['fallback'] for m in metrics),fallback_rate=sum(m['fallback'] for m in metrics)/len(metrics) if metrics else None,
   raw_compliant_count=sum(m['raw_compliant'] for m in metrics),delivered_compliant_count=sum(m['delivered_compliant'] for m in metrics),
   marks_unread_count=sum(m['delivered_marks_unread'] for m in metrics),fallback_resolved_groups=groups,
   C_wall_seconds_including_images_cleanup=done['finished_at']-s['started_at'] if done else None,
   C_completed=bool(done),C_locator_attempts=sum(r['localization_status']!='未运行' for r in rows),C_attempted_locator_seconds=sum(r['localization_seconds'] or 0 for r in rows),failed_step=s.get('failed'),budget_limit_cny=l.get('limit_microcny',0)/1e6,
   actual_model_ids=sorted({r['actual_model'] for r in calls if r['status']=='received'}),
   baseline_binding=s.get('code_binding'),v8_binding=s.get('v8_binding'),AB_reused=True,AB_rerun=False,
   account_bill_observed=False,holdout_read=False,requests_2317_scoring_unchanged=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--AB-summary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 summary=summarize(a.root,read(a.AB_summary));(a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 fields=['number','instance_id','arm','status','resolved','empty_patch','first_source_edit_request','total_seconds','requests','input_tokens','output_tokens','metered_cny','upper_cny','raw_compliant','fallback','violation_rules','delivered_compliant','delivered_marks_unread']
 with (a.output/'ABC-per-task.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for row in summary['trial_rows']:
   flat={k:row.get(k) for k in fields};flat.update({k:row['total_cost'][k] for k in ['requests','input_tokens','output_tokens','metered_cny','upper_cny']})
   if row.get('localization_metrics'):
    for k in ['raw_compliant','fallback','violation_rules','delivered_compliant','delivered_marks_unread']:flat[k]=row['localization_metrics'][k]
   w.writerow(flat)
 print(json.dumps({k:v for k,v in summary.items() if k not in ['trial_rows','C_rows']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
