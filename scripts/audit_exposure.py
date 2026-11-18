import json,re,os,hashlib
from pathlib import Path
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
S=Path(__file__).resolve().parents[1];root=S
catalog=json.loads((S/'data/selection/verified-metadata.json').read_text())
if isinstance(catalog,dict):print(catalog.keys());raise SystemExit(1)
ids={r['instance_id'].lower():r for r in catalog};commits={r['base_commit'] for r in catalog}
rx=re.compile('(?:'+'|'.join(re.escape(x) for x in sorted({r['repo'].replace('/','__') for r in catalog}))+')-[0-9]+',re.I);crx=re.compile(r'\b[a-f0-9]{40}\b')
exposed={};sources=[];scanned=0
for folder in ('workspace','legacy','benchmarks','assets/embedding-evidence/20261016-recovered-20261116/restored/outputs','docs','reviews'):
 for base,dirs,files in os.walk(root/folder,followlinks=False):
  dirs[:]=[d for d in dirs if d not in ('.git','.venv','.venv-openhands','__pycache__','node_modules') and not (Path(base)/d).is_symlink()]
  for name in files:
   p=Path(base)/name;rel=p.relative_to(root).as_posix();matches=set(m.group().lower() for m in rx.finditer(rel)) & ids.keys();foundcommits=set()
   if p.suffix in ('.json','.jsonl','.md','.log','.txt','.yaml','.yml') and not p.is_symlink():
    raw=p.read_bytes();text=raw.decode('utf-8','replace');scanned+=1
    matches.update(set(m.group().lower() for m in rx.finditer(text)) & ids.keys());foundcommits.update(set(crx.findall(text)) & commits)
    # Historical issue/PR URLs can identify tasks even when another instance ID was used.
    for m in re.finditer(r'github\.com/([^/\s"<>]+/[^/\s"<>]+)/(?:issues|pull)/(\d+)',text):
     candidate=m[1].replace('/','__').lower()+'-'+m[2]
     if candidate in ids:matches.add(candidate)
   else:raw=b''
   matches.update(k for k,r in ids.items() if r['base_commit'] in foundcommits)
   if matches:
    source={'path':rel,'sha256':hashlib.sha256(raw if raw else p.read_bytes()).hexdigest(),'matched_ids':sorted(matches)};sources.append(source)
    for i in matches:exposed.setdefault(i,[]).append(rel)
dev=json.loads((S/'data/dev37/registry.json').read_text())['cases']
output={'method':'Conservative metadata/text/path audit: exact Verified instance ID, historical issue/PR URL, or base_commit overlap. All historical preparation counts as exposure even without model run. No holdout outcomes used. Not a claim about model training contamination.','scanned_text_files':scanned,'excluded_verified_ids':sorted(exposed),'development_ids':[x['id'] for x in dev],'development_repo_commits':[[x['repo'],x['base_commit']] for x in dev],'evidence':sources}
p=args.output;p.mkdir(parents=True,exist_ok=False)
(p/'exposure-audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
(p/'verified-metadata.json').write_text(json.dumps(catalog,sort_keys=True,indent=2)+'\n')
print(json.dumps({'scanned_files':scanned,'excluded_verified':len(exposed),'evidence_files':len(sources)}))
