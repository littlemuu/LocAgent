"""One controlled continuation launch, only after explicit user budget amendment."""
import hashlib,io,json,subprocess,tarfile
from pathlib import Path
from dotenv import dotenv_values
P=Path(__file__).resolve().parents[1];R='/home/ubuntu/dev24-c-v82-20261117'
ssh=['ssh','-i','/Users/xiaomu/.ssh/locagent_tencent_20261117','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','UserKnownHostsFile='+str(P/'known_hosts'),'-o','StrictHostKeyChecking=yes','ubuntu@43.154.206.220']
def remote(cmd,**kw):return subprocess.run(ssh+[cmd],check=True,**kw)
paths=['control/continue_uncapped.py','control/launch-continue.sh','authorization-amendment.json']
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as t:
 for name in paths:t.add(P/name,arcname=name)
remote('test -f '+R+'/handoff/receipt.json && test ! -e '+R+'/continuation-started.json && test ! -e /home/ubuntu/.config/locagent/C-v82.env && mkdir '+R+'/continuation-launch-once')
remote('tar -xzf - -C '+R,input=buf.getvalue())
checks={name:hashlib.sha256((P/name).read_bytes()).hexdigest() for name in paths}
code='''import hashlib,json,sys
from pathlib import Path
p=Path(%r);sys.path.insert(0,str(p/'control'));import run_c
checks=%r
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in checks.items())
assert run_c.verify_frozen()==run_c.EXPECTED
assert json.loads((p/'handoff/receipt.json').read_text())['pending_api_requests']==0
print('continuation hashes and unchanged frozen binding verified')
'''%(R,checks)
remote('/home/ubuntu/e2e-cloud-smoke-v2/.venv-cloud/bin/python -',input=code.encode())
key=dotenv_values('/Users/xiaomu/Documents/Codex/locagent-demo-20261108/.env',interpolate=False).get('DEEPSEEK_API_KEY')
assert key and not any(c.isspace() for c in key)
remote('umask 077; cat > /home/ubuntu/.config/locagent/C-v82.env',input=('DEEPSEEK_API_KEY='+key+'\n').encode());del key
try:remote('cd '+R+' && (nohup bash control/launch-continue.sh >> launch-console.log 2>&1 < /dev/null & echo $! > run.pid)',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
except BaseException:remote('rm -f /home/ubuntu/.config/locagent/C-v82.env');raise
(P/'delivery/continuation-deployment.json').write_text(json.dumps({'files':checks,'scope':'remaining cases only; original frozen files untouched; total API cap removed by user'},indent=2)+'\n')
print('started continuation once; original completed episodes will not run again')
