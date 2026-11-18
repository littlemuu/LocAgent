"""Summarize this round's evidence; reading evaluator labels or holdout is unnecessary."""
import argparse,json,datetime
from pathlib import Path

def cost(records):
 out={'requests':len(records),'input_tokens':0,'output_tokens':0,'metered_cny':0.,'upper_cny':0.,'uncertain_requests':0}
 for r in records:
  if r['status']!='received':out['uncertain_requests']+=1;continue
  u=r['usage'];out['input_tokens']+=u['prompt_tokens'];out['output_tokens']+=u['completion_tokens'];out['upper_cny']+=r['charged_upper_microcny']/1e6
  bj=datetime.datetime.fromtimestamp(r['started_at'],datetime.timezone(datetime.timedelta(hours=8)))
  # This run is on Tue 2026-11-17, a normal workday; prices verified for this date.
  peak=bj.weekday()<5 and (9<=bj.hour<12 or 14<=bj.hour<18)
  out['metered_cny']+=r['peak_cache_adjusted_microcny']/1e6*(1 if peak else .5)
 return out

def summarize(root):
 root=Path(root);state=json.loads((root/'state.json').read_text());ledger=json.loads((root/'ledger.json').read_text());calls=ledger['calls']
 acceptance=json.loads((root/'smoke-acceptance.json').read_text()) if (root/'smoke-acceptance.json').exists() else None
 table=[]
 for index,identifier in enumerate(state['trial_ids'],1):
  loc_calls=[r for r in calls if r['context']=='trial:'+identifier+':locator'];loc_cost=cost(loc_calls)
  loc_step=state['steps'].get('trial:'+identifier+':locator',{});loc_time=loc_step.get('ended_at',loc_step.get('started_at',0))-loc_step.get('started_at',0)
  for arm in ['A','B']:
   p=root/'trial'/identifier/arm;f=p/'episode.json';agent=p/'agent/result.json'
   row={'number':index,'instance_id':identifier,'arm':arm,'status':'未运行','empty_patch':None,'first_source_edit_request':None,'resolved':None}
   if f.exists():row.update(json.loads(f.read_text()))
   elif agent.exists():
    a=json.loads(agent.read_text());row.update(status=a['status'],empty_patch=a.get('empty_patch'),first_source_edit_request=a.get('first_source_edit_request'),technical_failure=a.get('technical_failure'))
   cc=[r for r in calls if r['context']=='trial:'+identifier+':'+arm]
   row['coding_cost']=cost(cc);row['localization_cost']=loc_cost if arm=='B' else cost([])
   total_calls=cc+(loc_calls if arm=='B' else []);row['total_cost']=cost(total_calls)
   row['localization_seconds']=loc_time if arm=='B' else 0
   if row.get('wall_seconds') is not None:row['total_seconds']=row['wall_seconds']+row['localization_seconds']
   table.append(row)
 decision=json.loads((root/'checkpoint.json').read_text()) if (root/'checkpoint.json').exists() else {'status':'not_reached','reason':state.get('failed') or 'still_running','continue_allowed':False}
 return {'smoke_acceptance':acceptance,'trial_rows':table,'checkpoint':decision,'round_cost':cost(calls),'trial_cost':cost([r for r in calls if r['context'].startswith('trial:')]),'smoke_live_cost':cost([r for r in calls if r['context'].startswith('smoke:')]),'models':sorted({r.get('actual_model') for r in calls if r.get('actual_model')}),'failed_step':state.get('failed'),'started_at':state['started_at'],'last_completed_at':max(v.get('ended_at',v['started_at']) for v in state['steps'].values()),'code_binding':state['code_binding'],'price_account_bill_observed':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();value=summarize(a.run);a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k not in ['smoke_acceptance','trial_rows']},ensure_ascii=False))
