import hashlib,json,tarfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];f=json.loads((P/'frozen/FREEZE.json').read_text())
paths=['frozen/'+p for p in f['files']]+['frozen/FREEZE.json','frozen/baseline/data/dev24/content/evaluator.json','authorization.json','control/run_c.py','control/launch.sh','control/remote_preflight.py','control/observe.py']
manifest={p:hashlib.sha256((P/p).read_bytes()).hexdigest() for p in paths};(P/'deployment-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(P/'deployment.tar.gz','w:gz') as tar:
 for p in paths+['deployment-manifest.json']:tar.add(P/p,arcname=p,recursive=False)
 tar.add(P/'frozen/delivery',arcname='frozen/delivery',recursive=False)
print(json.dumps({'files':len(paths),'bytes':(P/'deployment.tar.gz').stat().st_size,'sha256':hashlib.sha256((P/'deployment.tar.gz').read_bytes()).hexdigest()}))
