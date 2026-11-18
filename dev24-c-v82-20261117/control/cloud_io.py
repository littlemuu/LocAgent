"""Explicit SSH deployment/observation for the authorized full C(v8.2) run.
Credential is passed on stdin only; never logged or included in deployment archive.
"""
import argparse,ipaddress,json,subprocess,sys,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REMOTE='/home/ubuntu/dev24-c-v82-20261117'
p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','preflight','start','status','collect','cleanup']);p.add_argument('--host',required=True);a=p.parse_args();ipaddress.ip_address(a.host)
ssh=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','UserKnownHostsFile='+str(ROOT/'known_hosts'),'-o','StrictHostKeyChecking='+('accept-new' if a.action=='deploy' else 'yes'),'ubuntu@'+a.host]
def remote(command,**kwargs):return subprocess.run(ssh+[command],check=True,**kwargs)
if a.action=='deploy':
 remote('mkdir '+REMOTE)
 with (ROOT/'deployment.tar.gz').open('rb') as f:remote('tar -xzf - -C '+REMOTE,stdin=f)
 print('deployed explicit frozen whitelist; no credentials')
elif a.action=='preflight':
 remote('cd '+REMOTE+' && PYTHONDONTWRITEBYTECODE=1 /home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python control/remote_preflight.py')
elif a.action=='start':
 from dotenv import dotenv_values
 # Enforce successful remote preflight before any credential transmission.
 remote('test -f '+REMOTE+'/remote-preflight.json && test ! -e '+REMOTE+'/run && test ! -e '+REMOTE+'/run.pid')
 key=dotenv_values('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.env',interpolate=False).get('DEEPSEEK_API_KEY')
 if not key or any(c.isspace() for c in key):raise ValueError('invalid_local_credential')
 remote('umask 077; mkdir -p /home/ubuntu/.config/locagent; cat > /home/ubuntu/.config/locagent/C-v82.env',input=('DEEPSEEK_API_KEY='+key+'\n').encode())
 del key
 try:remote('cd '+REMOTE+' && (nohup bash control/launch.sh > launch-console.log 2>&1 < /dev/null & echo $! > run.pid)',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 except BaseException:
  remote('rm -f /home/ubuntu/.config/locagent/C-v82.env');raise
 print('started one full C(v8.2) process; remote credential cleanup is in finally and EXIT trap')
elif a.action=='status':
 code="""import sys,json
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v82-20261117');sys.path.insert(0,str(p/'control'));from run_c import aggregate
if (p/'continuation-started.json').exists():
 from continue_uncapped import uncapped_aggregate as aggregate
s=json.loads((p/'run/state.json').read_text()) if (p/'run/state.json').exists() else {};g=aggregate(p/'run');rows=s.get('rows',[])
print(json.dumps(dict(status=s.get('status','starting'),current=s.get('current'),stage=s.get('current_stage'),rows=len(rows),resolved=sum(r.get('resolved') is True for r in rows),failed=sum(r['status']=='failed' for r in rows),last=rows[-1] if rows else None,requests=len(g['calls']),upper_cny=g['charged_or_reserved_microcny']/1e6,uncertain_requests=g['uncertain_requests'],exit=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None,credential_exists=Path('/home/ubuntu/.config/locagent/C-v82.env').exists()),ensure_ascii=False))
"""
 remote('/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -',input=code.encode())
elif a.action=='collect':
 command='cd '+REMOTE+' && tar -czf - run remote-preflight.json run.exit run-console.log credential-cleanup.json resource-observations.jsonl observer-console.log handoff budget-change-pause.json authorization-amendment.json continuation-started.json'
 with (ROOT/'evidence.tar.gz').open('wb') as out:remote(command,stdout=out)
 target=ROOT/'evidence';target.mkdir(exist_ok=True)
 with tarfile.open(ROOT/'evidence.tar.gz') as tar:
  for member in tar.getmembers():
   if member.issym() or member.islnk() or not (target/member.name).resolve().is_relative_to(target.resolve()):raise ValueError('unsafe_archive')
  tar.extractall(target,filter='data')
 print('collected complete C evidence, resource observations, exit and credential cleanup')
elif a.action=='cleanup':
 remote('rm -f /home/ubuntu/.config/locagent/C-v82.env')
 code="""import json,subprocess,time
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v82-20261117');r=dict(at=time.time(),credential_exists=Path('/home/ubuntu/.config/locagent/C-v82.env').exists(),running_containers=subprocess.check_output(['docker','ps','-q'],text=True).split(),all_containers=subprocess.check_output(['docker','ps','-aq'],text=True).split(),exit=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None);print(json.dumps(r))
"""
 result=remote('/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -',input=code.encode(),capture_output=True)
 (ROOT/'delivery/final-cloud-audit.json').write_bytes(result.stdout);print(result.stdout.decode())
