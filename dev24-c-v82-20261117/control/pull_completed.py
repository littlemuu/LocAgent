"""Read selected logs of completed cases only, without touching the running case."""
import argparse,ipaddress,subprocess,tarfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('--host',required=True);a=p.parse_args();ipaddress.ip_address(a.host)
code='''import io,json,sys,tarfile
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v82-20261117');state=json.loads((p/'run/state.json').read_text())
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for row in state['rows']:
  case=p/'run/trial'/row['instance_id']
  if not case.exists():continue
  for pattern in ['task-summary.json','read-file-errors.json','ledger.json','localization.json','locator/result.json','locator/diagnostic-audit.json','C/coding.json','C/patch.diff','C/harness/evaluation.json','C/harness-console.log','C/harness/**/report.json','C/harness/**/test_output.txt','C/wire/response-*.json']:
   for f in case.glob(pattern):
    if f.is_file():tar.add(f,arcname=str(f.relative_to(p/'run/trial')),recursive=False)
  reqs=sorted((case/'C/wire').glob('request-*.json'),key=lambda f:int(f.stem.split('-')[-1]))
  for f in reqs[-1:]:tar.add(f,arcname=str(f.relative_to(p/'run/trial')),recursive=False)
'''
ssh=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','UserKnownHostsFile='+str(P/'known_hosts'),'-o','StrictHostKeyChecking=yes','ubuntu@'+a.host,'/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -']
archive=P/'completed-snapshot.tar.gz'
with archive.open('wb') as f:subprocess.run(ssh,input=code.encode(),stdout=f,check=True,timeout=60)
target=P/'completed-snapshot';target.mkdir(exist_ok=True)
with tarfile.open(archive) as t:t.extractall(target,filter='data')
print('Completed-case evidence snapshots:',len(list(target.glob('*/task-summary.json'))))
