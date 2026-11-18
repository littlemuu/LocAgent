import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
CONFIG=json.loads((ROOT/'config/experiment.json').read_text())
def encoded(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(x):return hashlib.sha256(encoded(x)).hexdigest()
def write_json(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix(p.suffix+'.tmp');temp.write_bytes(encoded(x)+b'\n');os.replace(temp,p)
def rows():return json.loads((ROOT/'data/dev24/content/public.json').read_text())
def manifest():return json.loads((ROOT/'data/dev24/manifest.json').read_text())
def allow(identifier,smoke=False):
 m=manifest();allowed=m['smoke_ids'] if smoke else [r['instance_id'] for r in m['instances']]
 if identifier not in allowed:raise PermissionError('outside_frozen_development_scope')
def guard_holdout():
 def audit(event,args):
  if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes,os.PathLike)):
   s=os.fsdecode(args[0])
   if 'holdout-v1' in s and not s.endswith('/ids.txt'):raise PermissionError('holdout_content_forbidden')
 sys.addaudithook(audit)
guard_holdout()
