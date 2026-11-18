import hashlib,json,tarfile
from pathlib import Path
from support import P,F,verify,sha,durable
verify()
paths=['frozen/'+n for n in json.loads((F/'FREEZE.json').read_text())['files']]
paths+=['frozen/FREEZE.json','frozen/baseline/data/dev24/content/evaluator.json','authorization.json','execution-order.json','expected-cache.json','PREREGISTRATION_ZH.md','data/ids.txt','data/manifest.json','data/sealed-verified-test.parquet','delivery/adapter-equivalence.json','delivery/control-validation.json']
paths += [p.relative_to(P).as_posix() for p in sorted((P/'control').glob('*.py'))]+['control/launch.sh']
manifest={n:sha(P/n) for n in paths};durable(P/'deployment-manifest.json',manifest)
with tarfile.open(P/'deployment.tar.gz','w:gz') as tar:
 for n in paths+['deployment-manifest.json']:tar.add(P/n,arcname=n,recursive=False)
 tar.add(F/'delivery',arcname='frozen/delivery',recursive=False)
print(json.dumps({'files':len(paths),'package_bytes':(P/'deployment.tar.gz').stat().st_size,'sha256':sha(P/'deployment.tar.gz')}))
