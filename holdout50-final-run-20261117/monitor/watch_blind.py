"""Read-only monitor outside the frozen experiment package; never reads outcomes."""
import json,subprocess,time
from pathlib import Path
P=Path(__file__).resolve().parents[1]
code='''import json,os,time,subprocess
from pathlib import Path
p=Path('/home/ubuntu/holdout50-final-run-20261117')
previous=None
while True:
 x=json.loads((p/'health.json').read_text()) if (p/'health.json').exists() else {'status':'not_started'}
 x['exit']=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None
 x['credential_exists']=Path('/home/ubuntu/.config/locagent/holdout50-final-20261117.env').exists()
 v=os.statvfs(p);x['free_bytes_now']=v.f_bavail*v.f_frsize
 x['running_container_count']=len(subprocess.check_output(['docker','ps','-q'],text=True).split())
 x['resource_deviation']=(p/'RESOURCE_DEVIATION.json').exists()
 x['observed_at']=time.time()
 print(json.dumps(x),flush=True)
 if x['exit'] is not None:break
 time.sleep(50)
'''
ssh=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-o','UserKnownHostsFile='+str(P/'known_hosts'),'-o','StrictHostKeyChecking=yes','ubuntu@101.32.181.180','/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -']
p=subprocess.Popen(ssh,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);p.stdin.write(code);p.stdin.close()
with (P/'delivery/blind-progress.jsonl').open('a') as f:
 for line in p.stdout:
  x=json.loads(line);f.write(line);f.flush();(P/'delivery/blind-status.json').write_text(json.dumps(x)+'\n');print(line.strip(),flush=True)
raise SystemExit(p.wait())
