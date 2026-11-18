"""Summarize only this smoke's own logs; no dataset content is opened."""
from pathlib import Path
import json,hashlib,datetime,sys
root=Path(__file__).resolve().parents[1]; run=root/'verification/cloud-smoke-run-v2'
s=json.loads((run/'state.json').read_text()); ledger=json.loads((run/'ledger.json').read_text())
known=[r for r in ledger['calls'] if r['status']=='received']
steps=[]
for key,v in s['steps'].items():
 r=v.get('result',{});steps.append({'key':key,'status':v['status'],'wall_seconds':v.get('ended_at',v['started_at'])-v['started_at'] if v.get('ended_at') else None,'requests':r.get('requests'),'prompt_tokens':r.get('prompt_tokens'),'completion_tokens':r.get('completion_tokens'),'technical_failure':r.get('technical_failure',v.get('error'))})
patches=[]
for p in sorted(run.glob('*/*/patch.diff')):
 raw=p.read_bytes();patches.append({'id':p.parent.parent.name,'arm':p.parent.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
groups={}
for r in known:
 g=groups.setdefault(r['context'],{'requests':0,'prompt_tokens':0,'completion_tokens':0,'cache_hit_tokens':0,'cache_miss_tokens':0,'peak_cache_adjusted_cny':0,'upper_cny':0,'request_wall_seconds':0})
 u=r['usage'];g['requests']+=1
 for name in ['prompt_tokens','completion_tokens']:g[name]+=u[name]
 for name in ['cache_hit_tokens','cache_miss_tokens']:g[name]+=u.get('prompt_'+name,0)
 g['peak_cache_adjusted_cny']+=(r.get('peak_cache_adjusted_microcny') or r['charged_upper_microcny'])/1e6
 g['upper_cny']+=r['charged_upper_microcny']/1e6;g['request_wall_seconds']+=r['elapsed_seconds']
result={'steps':steps,'patches':patches,'groups':groups,'requests_started':len(ledger['calls']),'requests_received':len(known),'actual_models':sorted({r['actual_model'] for r in known}),'all_responses_peak_time':all(9<=datetime.datetime.fromtimestamp(r['started_at'],datetime.timezone(datetime.timedelta(hours=8))).hour<12 for r in known),'started_utc':datetime.datetime.fromtimestamp(min(v['started_at'] for v in s['steps'].values()),datetime.timezone.utc).isoformat(),'last_completed_utc':datetime.datetime.fromtimestamp(max(v.get('ended_at',v['started_at']) for v in s['steps'].values()),datetime.timezone.utc).isoformat(),'elapsed_completed_wall_seconds':max(v.get('ended_at',v['started_at']) for v in s['steps'].values())-min(v['started_at'] for v in s['steps'].values()),'credential_file_exists':Path('/home/ubuntu/.config/locagent/smoke.env').exists(),'formal_trial_run':False,'holdout_content_read':False}
(root/'verification/cloud-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
