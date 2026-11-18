"""Read-only foreground progress stream for this task, not a scheduled automation."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
code="""import json,time
from pathlib import Path
p=Path('/home/ubuntu/dev24-locator-v81-20261117')
while True:
 s=json.loads((p/'run/state.json').read_text());l=json.loads((p/'run/ledger.json').read_text());rows=s.get('rows',[]);last=rows[-1] if rows else {}
 print(json.dumps(dict(current=s.get('current'),attempted=len(rows),delivered=sum(r['delivery_success'] for r in rows),fallback=sum(r.get('fallback') is True for r in rows),validator_errors=sum(bool(r.get('validator_error')) for r in rows),requests=len(l['calls']),upper_cny=round(sum(c.get('charged_upper_microcny',c['reserved_microcny']) for c in l['calls'])/1e6,6),last={k:last.get(k) for k in ['instance_id','status','violation_rules','validator_error','error','locator_seconds']},status=s.get('status','running'),exit=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None),ensure_ascii=False),flush=True)
 if (p/'run.exit').exists():break
 time.sleep(30)
"""
args=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','UserKnownHostsFile='+str(ROOT/'known_hosts'),'-o','StrictHostKeyChecking=yes','ubuntu@43.155.16.91','/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -u -']
p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);p.stdin.write(code);p.stdin.close()
with (ROOT/'delivery/progress.jsonl').open('a') as log:
 for line in p.stdout:log.write(line);log.flush();print(line,end='',flush=True)
raise SystemExit(p.wait())
