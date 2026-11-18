import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
f=json.loads((ROOT/'frozen/FREEZE.json').read_text())
paths=['frozen/'+p for p in f['files']]+['frozen/FREEZE.json','authorization.json','control/run_locator.py','control/launch.sh','control/preflight.py']
with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as tar:
 for p in paths:tar.add(ROOT/p,arcname=p,recursive=False)
 (ROOT/'frozen/delivery').mkdir(exist_ok=True)
 tar.add(ROOT/'frozen/delivery',arcname='frozen/delivery',recursive=False)
manifest={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
(ROOT/'delivery/deployment-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(files=len(paths),bytes=(ROOT/'deployment.tar.gz').stat().st_size,sha256=hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest())))
