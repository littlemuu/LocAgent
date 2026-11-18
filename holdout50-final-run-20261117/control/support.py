import hashlib,json,os,sys,time
from pathlib import Path
P=Path(__file__).resolve().parents[1]
F=P/'frozen'
sys.path[:0]=[str(F),str(F/'baseline')]
AB='a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036'
C='031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7'
IDS='5226d5870987a2f9d161b98077aa64788f6e3426d1cea326385694c47922acd6'
PARQUET='a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd'
MIN_FREE=30*1024**3
def encoded(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(encoded(x)).hexdigest()
def sync_file(p):
 with Path(p).open('rb') as f:os.fsync(f.fileno())
 fd=os.open(str(Path(p).parent),os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def durable(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
 with tmp.open('wb') as f:f.write(encoded(x)+b'\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);sync_file(p)
def claim(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(encoded(x)+b'\n');f.flush();os.fsync(f.fileno())
 sync_file(p)
def load(p):return json.loads(Path(p).read_text())
def verify():
 f=load(F/'FREEZE.json');actual={n:sha(F/n) for n in f['files']}
 assert actual==f['files'] and digest(actual)==C,'C_frozen_binding_mismatch'
 from locagent_e2e.driver import config_binding
 assert config_binding()==AB,'AB_frozen_binding_mismatch'
 assert sha(P/'data/ids.txt')==IDS,'holdout_ids_changed'
 if (P/'deployment-manifest.json').exists():
  for n,h in load(P/'deployment-manifest.json').items():assert sha(P/n)==h,'deployment_changed:'+n
 return {'C':C,'AB':AB,'ids_sha256':IDS}
def free_bytes():
 v=os.statvfs(P);return v.f_bavail*v.f_frsize
def check_free():
 v=free_bytes()
 if v<MIN_FREE:raise RuntimeError('disk_below_30GiB')
 return v
