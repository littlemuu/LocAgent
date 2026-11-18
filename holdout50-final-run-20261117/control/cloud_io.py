"""Explicit SSH I/O. Credentials only on stdin to a unique temporary remote file.
Status is intentionally blind: no task IDs, scores, patches or model outputs.
"""
import argparse,ipaddress,json,subprocess,sys,tarfile
from pathlib import Path
P=Path(__file__).resolve().parents[1]
REMOTE='/home/ubuntu/holdout50-final-run-20261117'
PY='/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python'
KEY='/home/ubuntu/.config/locagent/holdout50-final-20261117.env'

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['deploy','preflight','prepare-public','start','status','collect','cleanup','final-check']);p.add_argument('--host',required=True);a=p.parse_args();ipaddress.ip_address(a.host)
 ssh=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','UserKnownHostsFile='+str(P/'known_hosts'),'-o','StrictHostKeyChecking='+('accept-new' if a.action=='deploy' else 'yes'),'ubuntu@'+a.host]
 def remote(command,**kwargs):return subprocess.run(ssh+[command],check=True,**kwargs)
 if a.action=='deploy':
  remote('mkdir '+REMOTE)
  with (P/'deployment.tar.gz').open('rb') as f:remote('tar -xzf - -C '+REMOTE,stdin=f)
  print('Deployed frozen package; no API credential.')
 elif a.action=='preflight':
  result=subprocess.run(ssh+['cd '+REMOTE+' && PYTHONDONTWRITEBYTECODE=1 '+PY+' control/remote_preflight.py'],capture_output=True)
  (P/'delivery/remote-preflight-console.log').write_bytes(result.stdout+result.stderr)
  r=remote('cat '+REMOTE+'/remote-preflight.json',capture_output=True);(P/'delivery/remote-preflight.json').write_bytes(r.stdout)
  print(r.stdout.decode());raise SystemExit(result.returncode)
 elif a.action=='prepare-public':
  remote('cd '+REMOTE+' && PYTHONDONTWRITEBYTECODE=1 '+PY+' control/data_adapter.py --prepare-public')
 elif a.action=='start':
  code="""import sys,json,os
from pathlib import Path
p=Path('/home/ubuntu/holdout50-final-run-20261117');sys.path.insert(0,str(p/'control'))
from support import verify,check_free,load
verify();check_free();assert load(p/'remote-preflight.json')['status']=='passed';assert load(p/'public-data-receipt.json')['rows']==50
assert not (p/'run').exists() and not (p/'run.pid').exists() and not (p/'experiment-once.json').exists()
print('All start gates passed; no paid request sent yet.')
"""
  remote(PY+' -',input=code.encode())
  from dotenv import dotenv_values
  key=dotenv_values('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.env',interpolate=False).get('DEEPSEEK_API_KEY')
  if not key or any(c.isspace() for c in key):raise ValueError('invalid_local_credential')
  remote('umask 077; test ! -e '+KEY+' && cat > '+KEY,input=('DEEPSEEK_API_KEY='+key+'\n').encode());del key
  try:remote('cd '+REMOTE+' && (nohup bash control/launch.sh > launch-console.log 2>&1 < /dev/null & echo $! > run.pid)',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  except BaseException:remote('rm -f '+KEY);raise
  print('One-shot run started; all task outcomes remain sealed.')
 elif a.action=='status':
  code="""import json,os,subprocess,time
from pathlib import Path
p=Path('/home/ubuntu/holdout50-final-run-20261117')
x=json.loads((p/'health.json').read_text()) if (p/'health.json').exists() else {'status':'not_started'}
x['exit']=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None
x['credential_exists']=Path('/home/ubuntu/.config/locagent/holdout50-final-20261117.env').exists()
v=os.statvfs(p);x['free_bytes_now']=v.f_bavail*v.f_frsize
x['running_container_count']=len(subprocess.check_output(['docker','ps','-q'],text=True).split())
x['resource_deviation']=(p/'RESOURCE_DEVIATION.json').exists()
print(json.dumps(x))
"""
  r=remote(PY+' -',input=code.encode(),capture_output=True);(P/'delivery/blind-status.json').write_bytes(r.stdout);print(r.stdout.decode())
 elif a.action=='collect':
  remote('test -f '+REMOTE+'/run.exit && test ! -e '+KEY)
  with (P/'sealed-evidence.tar.gz').open('wb') as f:remote('cd '+REMOTE+' && tar -czf - run remote-preflight.json cache-before.json run.exit run-console.log credential-cleanup.json resource-observations.jsonl observer-console.log public-data-receipt.json experiment-once.json health.json',stdout=f)
  print('Collected sealed evidence archive; contents not displayed or extracted.')
 elif a.action=='cleanup':remote('rm -f '+KEY);print('Temporary credential deleted.')
 elif a.action=='final-check':
  code="""import json,subprocess,hashlib,sys,time
from pathlib import Path
p=Path('/home/ubuntu/holdout50-final-run-20261117');sys.path.insert(0,str(p/'control'));from support import verify,load
x={'at':time.time(),'bindings':verify(),'credential_exists':Path('/home/ubuntu/.config/locagent/holdout50-final-20261117.env').exists(),'containers':subprocess.check_output(['docker','ps','-aq'],text=True).split()}
from locagent_e2e.driver import inspect_image
before=load(p/'cache-before.json')['images'];after=[inspect_image('docker',r['name']) for r in before]
x['preserved_original_cache_count']=sum(a['id']==b['id'] for a,b in zip(after,before));x['preserved_original_cache_unchanged']=all(a['id']==b['id'] for a,b in zip(after,before))
x['exit']=(p/'run.exit').read_text().strip() if (p/'run.exit').exists() else None
print(json.dumps(x))
"""
  r=remote(PY+' -',input=code.encode(),capture_output=True);(P/'delivery/final-remote-verification.json').write_bytes(r.stdout);print(r.stdout.decode())
if __name__=='__main__':main()
