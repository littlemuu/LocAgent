import datetime,json,time
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v8-20261117');run=p/'run'
def read(f,default):return json.loads(f.read_text()) if f.exists() else default
state=read(run/'state.json',{});ledger=read(run/'ledger.json',{'calls':[]});progress=read(run/'trial-progress.json',{'episodes':[]})
received=[r for r in ledger['calls'] if r['status']=='received'];cost=0
for r in received:
 d=datetime.datetime.fromtimestamp(r['started_at'],datetime.timezone(datetime.timedelta(hours=8)))
 peak=d.weekday()<5 and (9<=d.hour<12 or 14<=d.hour<18)
 cost+=(r.get('peak_cache_adjusted_microcny') or r['charged_upper_microcny'])/1e6*(1 if peak else .5)
completed=progress['episodes'];ids=state.get('trial_ids',[])
metrics=[read(run/'trial'/i/'localization-metrics.json',{}) for i in ids];metrics=[x for x in metrics if x]
active={k:{'status':s['status'],'elapsed_seconds':round(time.time()-s['started_at'])} for k,s in state.get('steps',{}).items() if s['status']!='completed'}
x=dict(at=time.time(),completed=len(completed),resolved=sum(r['resolved'] is True for r in completed),last_episode=completed[-1] if completed else None,
       active=active,failed=state.get('failed'),requests=len(ledger['calls']),received=len(received),unsettled=len(ledger['calls'])-len(received),
       upper_cny=sum(r['charged_upper_microcny'] for r in received)/1e6,metered_cny=cost,locator_completed=len(metrics),fallbacks=sum(r['fallback'] for r in metrics),
       exit_code=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None,
       credential_present=Path('/home/ubuntu/.config/locagent/C-v8.env').exists(),elapsed_seconds=round(time.time()-state['started_at']) if state else None)
print(json.dumps(x,ensure_ascii=False))
