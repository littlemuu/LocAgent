import hashlib,json,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[2]; old=R/'locator-diagnostic-calibration-v8.1'; new=R/'locator-diagnostic-calibration-v8.2'; O=R/'dev24-v82-offline-replay-20261117'
assert not new.exists(),'Do not overwrite existing v8.2'
f=json.loads((old/'FREEZE.json').read_text()); inputs={}
for p,h in f['files'].items():
 assert hashlib.sha256((old/p).read_bytes()).hexdigest()==h
 dst=new/p;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/p,dst)
 inputs[str((old/p).relative_to(R))]=h
inputs[str((old/'FREEZE.json').relative_to(R))]=hashlib.sha256((old/'FREEZE.json').read_bytes()).hexdigest()
(new/'delivery').mkdir();shutil.copyfile(old/'delivery/B-C-COMPARISON.json',new/'delivery/B-C-COMPARISON.json')
cases=json.loads((R/'dev24-v81-fallback-audit-20261117/cases.json').read_text()); fixture=[]
for c in cases:
 a=Path(c['raw_audit_path']);result=a.parent/'result.json';raw=json.loads(a.read_text());r=json.loads(result.read_text())
 fixture.append({'instance_id':c['instance_id'],'audit':raw,'tool_audit':r['tool_audit'],'original_finish_paths':c['raw_finish_wire_paths']})
 for p in [a,result,*map(Path,c['raw_finish_wire_paths'])]:inputs[str(p.relative_to(R))]=hashlib.sha256(p.read_bytes()).hexdigest()
review=R/'dev24-v81-fallback-audit-20261117/violations-reviewed.json'
inputs[str(review.relative_to(R))]=hashlib.sha256(review.read_bytes()).hexdigest()
(new/'tests/fixtures/v81-recorded24.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
expected=[{k:v[k] for k in ['id','instance_id','recorded_violation','classification']} for v in json.loads(review.read_text())]
(new/'tests/fixtures/v81-reviewed55.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n')
(O/'input-sha256.json').write_text(json.dumps(inputs,indent=2)+'\n')
print('Created independent copy; 24 original answer/coverage fixtures and 55 review expectations.')
