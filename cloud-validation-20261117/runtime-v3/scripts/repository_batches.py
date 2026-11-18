"""Create repository batches and explicit image pull/cleanup commands; never run agents."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from locagent_e2e.common import manifest,write_json
from locagent_e2e.driver import image_name
p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','pull','cleanup']);p.add_argument('--repo');p.add_argument('--output',type=Path,required=True);p.add_argument('--docker',default='docker');p.add_argument('--execute',action='store_true');a=p.parse_args()
groups={}
for r in manifest()['instances']:groups.setdefault(r['repo'],[]).append(r['instance_id'])
a.output.mkdir(parents=True,exist_ok=True)
if a.action=='plan':
 write_json(a.output/'batches.json',[{'repo':r,'instances':ids,'images':[image_name(i) for i in ids],'concurrency':1,'cleanup':'only exact image refs in this batch; never system prune'} for r,ids in sorted(groups.items())])
else:
 if a.repo not in groups:p.error('select a frozen development repository')
 if a.execute and sys.platform!='linux':p.error('full repository batch execution is cloud Linux only; Mac uses smoke images command (max2)')
 names=[image_name(i) for i in groups[a.repo]]
 for name in names:
  cmd=[a.docker,'pull','--platform','linux/amd64',name] if a.action=='pull' else [a.docker,'image','rm',name]
  print(json.dumps(cmd))
  if a.execute:subprocess.run(cmd,check=True)
