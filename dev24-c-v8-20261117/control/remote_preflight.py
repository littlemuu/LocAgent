import hashlib,importlib.metadata,json,os,subprocess,sys
from pathlib import Path
p=Path('/home/ubuntu/dev24-c-v8-20261117')
sys.path.insert(0,str(p/'control'))
import run_c
assert run_c.verify_frozen()==run_c.EXPECTED
expected=json.loads((p/'deployment-manifest.json').read_text())
for path,h in expected.items():assert hashlib.sha256((p/path).read_bytes()).hexdigest()==h,path
from locagent_e2e.common import CONFIG
packages={k:importlib.metadata.version(k) for k in ['openhands-sdk','swebench','bm25s','PyStemmer']}
assert packages['openhands-sdk']=='1.62.0'
import swebench
swe_root=Path(swebench.__file__).resolve().parent.parent
direct_url=json.loads(importlib.metadata.distribution('swebench').read_text('direct_url.json'))
commit=direct_url['url'].rsplit('/',1)[-1]
assert direct_url['archive_info']['hashes']['sha256']=='c5be730adf22e403f3e350e1ea81810576a1443eda76ec98f39896d26c1cdcdf'
assert commit==CONFIG['harness_commit'],(commit,CONFIG['harness_commit'])
active=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).strip()
assert not active,'unexpected_active_containers'
record=dict(status='passed',v8_binding=run_c.EXPECTED,baseline_binding=run_c.BASE,packages=packages,harness_commit=commit,swebench_root=str(swe_root),python=sys.executable,active_containers=[],free_bytes=os.statvfs(p).f_bavail*os.statvfs(p).f_frsize,API_calls=0)
(p/'remote-preflight.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
