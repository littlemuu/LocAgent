"""Read-only experimental audit. No imports of experiment runtimes, network, or API calls.
Only this preflight directory is written. Sealed dataset is hashed, never decoded.
"""
import collections, hashlib, importlib.util, json, os, re, subprocess, tarfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / 'delivery'
def sha(raw): return hashlib.sha256(raw).hexdigest()
def digest(obj): return sha(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
def read(p): return json.loads((ROOT / p).read_text())
def save(name, obj): (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

freeze = read('locator-diagnostic-calibration-v8.2/FREEZE.json')
base = ROOT / 'locator-diagnostic-calibration-v8.2'
actual = {p: sha((base / p).read_bytes()) for p in freeze['files']}
copies = {}
for name in ['locator-diagnostic-calibration-v8.2', 'dev24-c-v82-20261117/frozen']:
    copies[name] = [p for p, h in freeze['files'].items() if sha((ROOT / name / p).read_bytes()) != h]
b = base / 'baseline'
paths = [*sorted((b/'locagent_e2e').glob('*.py')), *sorted((b/'config').glob('*')), *sorted((b/'runtime').rglob('*.py')), b/'data/dev24/manifest.json', b/'data/dev24/content/receipt.json']
bmap = {p.relative_to(b).as_posix(): sha(p.read_bytes()) for p in paths}
zip_path = ROOT/'dev24-completion-20261117-v5/delivery/unchanged-core-runtime-v4.zip'
with zipfile.ZipFile(zip_path) as z:
    historic = {}
    for p, h in bmap.items():
        names = [n for n in z.namelist() if n == p or n.endswith('/'+p)]
        historic[p] = {'matches': len(names), 'byte_identical': len(names)==1 and sha(z.read(names[0]))==h}
    shared = []
    for p, h in freeze['files'].items():
        if not p.startswith('baseline/'): continue
        rel = p[len('baseline/'):]
        names = [n for n in z.namelist() if n == rel or n.endswith('/'+rel)]
        assert len(names)==1 and sha(z.read(names[0]))==h, p
        shared.append(p)
save('freeze-verification.json', {'C_expected': '031e6a4265add240659f2900d33b75659e13f0b356b35b764fd9df618c835db7', 'C_actual': digest(actual), 'C_files': len(actual), 'C_mismatches': [p for p in actual if actual[p]!=freeze['files'][p]], 'deployment_copy_mismatches': copies, 'AB_expected': 'a02c0341ebddeba3718d9d4a00e8485e35a62944f088cac982f6c817b7160036', 'AB_actual': digest(bmap), 'AB_files': len(bmap), 'AB_original_v5_zip_comparison': historic, 'all_42_shared_baseline_files_byte_identical_to_v5_zip':shared, 'coding_agent_sha256': bmap['locagent_e2e/agent.py'], 'coding_system_sha256': bmap['config/coding-system.txt'], 'config': read('locator-diagnostic-calibration-v8.2/baseline/config/experiment.json'), 'current_remote_verification': 'not_run_instance_off'})

m = read('freezes/holdout-v1/manifest.json')
ids = (ROOT/'freezes/holdout-v1/ids.txt').read_bytes()
lock = read('freezes/stage1-lock.json')
selected = {r['instance_id'].lower(): r for r in m['instances']}
commits = {r['base_commit']: r['instance_id'].lower() for r in m['instances']}
check_paths = [p for p in lock['files'] if p.startswith(('freezes/holdout-v1/', 'data/selection/')) or p=='scripts/sample_holdout.py']
checks = {p: {'expected': lock['files'][p], 'actual': sha((ROOT/p).read_bytes())} for p in check_paths}
spec=importlib.util.spec_from_file_location('metadata_sampler', ROOT/'scripts/sample_holdout.py')
sampler=importlib.util.module_from_spec(spec);spec.loader.exec_module(sampler)
rows, eligible = sampler.select(read('data/selection/verified-metadata.json'), read('data/selection/exposure-audit.json'))
dev24=read('e2e-preparation-v1/data/dev24/manifest.json')['instances']
dev37=read('data/dev37/registry.json')['cases']
exposure=read('data/selection/exposure-audit.json')
save('holdout-integrity.json', {'count':len(selected), 'ids_sha256':sha(ids), 'original_lock_sha256':lock['holdout_ids_sha256'], 'original_frozen_files':checks, 'all_original_hashes_match':all(v['actual']==v['expected'] for v in checks.values()), 'metadata_reproduction_byte_identical':ids==''.join(r['instance_id']+'\n' for r in rows).encode(), 'manifest_order_byte_identical':ids==''.join(r['instance_id']+'\n' for r in m['instances']).encode(), 'previous_reproduction_byte_identical':ids==(ROOT/'verification/holdout-reproduction/ids.txt').read_bytes(), 'eligible':eligible, 'dev24_overlap':sorted(set(selected)&{r['instance_id'].lower() for r in dev24}), 'dev37_overlap':sorted(set(selected)&{r['id'].lower() for r in dev37}), 'original_exposure_overlap':sorted(set(selected)&set(exposure['excluded_verified_ids'])), 'dev24_repo_commit_overlap':[r['instance_id'] for r in m['instances'] if (r['repo'],r['base_commit']) in {(r['repo'],r['base_commit']) for r in dev24}], 'dev37_repo_commit_overlap':[r['instance_id'] for r in m['instances'] if (r['repo'],r['base_commit']) in {(r['repo'],r['base_commit']) for r in dev37}], 'sealed_content_decoded':False})

# Report identifiers and hashes only; never expose any matched source text.
id_re=re.compile(r'(?:'+'|'.join(re.escape(k) for k in selected)+r')(?!\d)')
commit_re=re.compile('|'.join(commits))
url_re=re.compile(r'github\.com/([^/\s"<>]+/[^/\s"<>]+)/(?:issues|pull)/(\d+)')
suffixes={'.json','.jsonl','.md','.log','.txt','.yaml','.yml','.csv','.py','.sh','.html','.toml','.diff','.patch'}
excluded_dirs={'.git','__pycache__','node_modules','holdout50-final-preflight-20261117'}
hits=[]; counts=collections.Counter(); archives=[]; errors=[]; symlinks=[]
patterns = {k:k for k in selected} | commits
for k,r in selected.items():
    for kind in ('issues','pull'):
        patterns['github.com/'+r['repo'].lower()+'/'+kind+'/'+k.rsplit('-',1)[1]]=k
pattern_file=OUT/'exposure-patterns.txt'
pattern_file.write_text('\n'.join(patterns)+'\n')
args=['rg','-l','-F','-i','--hidden','--no-ignore','-f',str(pattern_file)]
for d in excluded_dirs | {'.venv','.venv-openhands'}:args+=['-g','!**/'+d+'/**']
args+=['-g','!**/.venv*/**','-g','!freezes/holdout-v1/sealed/**','-g','!**/.env*','-g','!**/*.pem','-g','!**/*.key']
for ext in suffixes:args+=['-g','*'+ext]
r=subprocess.run(args+['.'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
if r.returncode not in (0,1):raise RuntimeError('rg_scan_failed: '+r.stderr.decode()[:300])
candidate_paths={v.removeprefix('./') for v in r.stdout.decode().splitlines()}
print(json.dumps({'rg_matching_paths':len(candidate_paths)}),flush=True)
def examine(name, raw=None):
    s=(name+'\n'+(raw.decode('utf-8','replace') if raw is not None else '')).lower()
    found={value for pattern,value in patterns.items() if pattern in s}
    if found: hits.append({'path':name, 'matched_ids':sorted(found),'sha256':sha(raw) if raw is not None else None})
for root, dirs, files in os.walk(ROOT, followlinks=False):
    dirs[:]=[d for d in dirs if d not in excluded_dirs and not d.startswith('.venv') and not (Path(root)/d).is_symlink()]
    for name in files:
        p=Path(root)/name; rel=p.relative_to(ROOT).as_posix()
        if p.is_symlink(): symlinks.append(rel);continue
        if rel.startswith('freezes/holdout-v1/sealed/'): counts['sealed_files_excluded_from_content_scan']+=1;continue
        if name.startswith('.env') or p.suffix in {'.pem','.key'}: counts['credential_files_excluded']+=1;continue
        try:
            counts['file_paths_scanned']+=1
            if counts['file_paths_scanned']%20000==0: print(json.dumps({'progress':dict(counts)}),flush=True)
            if p.suffix in suffixes:
                if rel in candidate_paths:examine(rel,p.read_bytes())
                counts['text_files_scanned_by_rg']+=1
            else: examine(rel)
            if name.endswith(('.tar.gz','.tgz','.tar','.zip')):
                archives.append({'path':rel,'sha256':sha(p.read_bytes())})
                print(json.dumps({'archive':rel,'progress':dict(counts)}),flush=True)
                if name.endswith('.zip'):
                    with zipfile.ZipFile(p) as z:
                        for item in z.infolist():
                            if item.is_dir():continue
                            counts['archive_members_scanned']+=1
                            if Path(item.filename).suffix in suffixes:
                                examine(rel+'::'+item.filename,z.read(item));counts['archive_text_members_scanned']+=1
                            else:examine(rel+'::'+item.filename)
                else:
                    with tarfile.open(p) as t:
                        for item in t:
                            if not item.isfile():continue
                            counts['archive_members_scanned']+=1
                            if Path(item.name).suffix in suffixes:
                                examine(rel+'::'+item.name,t.extractfile(item).read());counts['archive_text_members_scanned']+=1
                            else:examine(rel+'::'+item.name)
        except Exception as e: errors.append({'path':rel,'error':type(e).__name__+': '+str(e)})
save('historical-exposure-scan.json', {'method':'All project file paths and text plus tar/zip members; exact IDs, GitHub issue/PR URLs, base commits; no sealed parquet decoding. Hidden/ignored files included, virtualenv/git/node_modules/own output excluded. Archive binary bodies and nested archives are not decoded.', 'counts':dict(counts), 'hits':hits, 'archives':archives, 'errors':errors, 'symlinks_not_followed':symlinks, 'scope_limit':'Local project evidence only; absence does not establish external history or model pretraining non-exposure.'})
print(json.dumps({'C_binding':digest(actual),'AB_binding':digest(bmap),'historical_zip_mismatches':[p for p,v in historic.items() if not v['byte_identical']],'holdout_sha256':sha(ids),'scan_counts':dict(counts),'matching_files':len(hits),'scan_errors':len(errors)}))
