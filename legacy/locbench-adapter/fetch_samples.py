"""Fetch three fixed-commit real repositories; does not execute their code."""
from pathlib import Path,PurePosixPath
import urllib.request,tarfile,io,json,hashlib
from adapter import ROOT,save
wanted=['Delgan/loguru','py-pdf/pypdf','networkx/networkx']
tasks=[json.loads(p.read_text()) for p in (ROOT/'inputs').glob('*/task.json')]
out=[]
for repo in wanted:
 t=sorted((x for x in tasks if x['repo']==repo),key=lambda x:x['instance_id'])[0]
 i=t['instance_id'];commit=t['base_commit'];url=f'https://codeload.github.com/{repo}/tar.gz/{commit}'
 data=urllib.request.urlopen(url,timeout=120).read();dest=ROOT/'samples'/i/'repo';dest.mkdir(parents=True,exist_ok=False)
 (dest.parent/'source.tar.gz').write_bytes(data);inventory={}
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
  for m in tar:
   parts=PurePosixPath(m.name).parts[1:]
   if not parts or '..' in parts or m.name.startswith('/'):continue
   if not m.isfile() or not parts[-1].endswith('.py'):continue
   path=Path(*parts);b=tar.extractfile(m).read();p=dest/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);inventory[str(path)]=hashlib.sha256(b).hexdigest()
 info={**{k:t[k] for k in ('instance_id','repo','base_commit')},'source_url':url,'archive_sha256':hashlib.sha256(data).hexdigest(),'python_files':inventory,'verification':'fixed-commit codeload archive, not independent Git tree verification'}
 save(dest.parent/'source.json',info);out.append({'instance_id':i,'python_files':len(inventory)})
save(ROOT/'sample-selection.json',{'rule':'lexicographically first instance in three preselected manageable repos; convenience sample, not accuracy estimate','cases':out});print(out)
