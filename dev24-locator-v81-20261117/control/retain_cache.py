"""User-authorized cache retention sidecar; no experiment/API/frozen code changes.
Pin exact task image IDs under extra tags before unchanged per-case tag cleanup.
Restore their canonical tags only after the locator-only run has exited.
"""
import hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path('/home/ubuntu/dev24-locator-v81-20261117');RUN=ROOT/'run';seen={};missing=set()
def docker(args):return subprocess.run(['docker',*args],capture_output=True,text=True)
def save():
 p=ROOT/'cache-retention.json';tmp=p.with_suffix('.tmp')
 tmp.write_text(json.dumps(dict(at=time.time(),user_instruction='如果镜像可以复用就保留缓存',images=list(seen.values()),already_removed=sorted(missing),scope='extra tags only; no pulls, no API, no frozen changes'),ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
while True:
 for path in (RUN/'images').glob('*/image.json'):
  info=json.loads(path.read_text());key=path.parent.name
  if key in seen:continue
  identifier=info['id'];original=info['name'];tag='locagent-dev24-cache:'+hashlib.sha256(key.encode()).hexdigest()[:20]
  result=docker(['image','tag',identifier,tag])
  if result.returncode:
   missing.add(key);continue
  seen[key]=dict(instance_id=key,image_id=identifier,canonical_tag=original,cache_tag=tag,preserved_at=time.time(),canonical_restored=False)
  missing.discard(key);save()
 if (ROOT/'run.exit').exists():break
 time.sleep(1)
for row in seen.values():
 result=docker(['image','tag',row['image_id'],row['canonical_tag']]);row['canonical_restored']=result.returncode==0
 if result.returncode:row['restore_error']=result.stderr[:300]
save()
print(json.dumps(dict(preserved=len(seen),canonical_restored=sum(x['canonical_restored'] for x in seen.values()),already_removed=len(missing))))
