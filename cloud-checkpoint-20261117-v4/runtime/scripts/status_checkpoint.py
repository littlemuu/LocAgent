"""Print compact run metadata only, never prompts, source, credentials or evaluator labels."""
from pathlib import Path
import json,time
root=Path(__file__).resolve().parents[1];run=root/'verification/round-run'
if not (run/'state.json').exists():print('Not started');raise SystemExit
s=json.loads((run/'state.json').read_text());l=json.loads((run/'ledger.json').read_text());rr=l['calls'];received=[r for r in rr if r['status']=='received']
active=[k for k,v in s['steps'].items() if v['status']=='running'];failed=s.get('failed')
progress=json.loads((run/'trial-progress.json').read_text()) if (run/'trial-progress.json').exists() else {'episodes':[]}
print(json.dumps({'elapsed_seconds':round(time.time()-s['started_at']),'active':active,'failed':failed,'smoke_accepted':(run/'smoke-acceptance.json').exists(),'trial_completed':len(progress['episodes']),'trial_empty':sum(e['empty_patch'] for e in progress['episodes']),'trial_resolved':sum(e['resolved'] is True for e in progress['episodes']),'requests_started':len(rr),'requests_received':len(received),'input_tokens':sum(r['usage']['prompt_tokens'] for r in received),'output_tokens':sum(r['usage']['completion_tokens'] for r in received),'api_cost_upper_cny':sum(r['charged_upper_microcny'] for r in received)/1e6,'reserved_cny':sum(r['reserved_microcny'] for r in rr if r['status']!='received')/1e6,'ledger_stopped':l['stopped'],'checkpoint':json.loads((run/'checkpoint.json').read_text()) if (run/'checkpoint.json').exists() else None,'cloud_key_present':Path('/home/ubuntu/.config/locagent/checkpoint.env').exists()},ensure_ascii=False))
