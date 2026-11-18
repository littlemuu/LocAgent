"""Metadata-only, deterministic repository-balanced sampling; never reads outcomes."""
import argparse,collections,hashlib,json,random
from pathlib import Path
FIELDS={'instance_id','repo','base_commit','created_at'}
SEED=20261116

def select(rows,exposure,n=50,seed=SEED):
    if any(set(row)!=FIELDS for row in rows):raise ValueError('metadata_columns_only')
    if len({r['instance_id'] for r in rows})!=len(rows):raise ValueError('duplicate_id')
    excluded={x.lower() for x in exposure['excluded_verified_ids']+exposure['development_ids']}
    snapshots={tuple(x) for x in exposure['development_repo_commits']}
    groups=collections.defaultdict(list)
    for r in sorted(rows,key=lambda x:x['instance_id']):
        if r['instance_id'].lower() not in excluded and (r['repo'],r['base_commit']) not in snapshots:groups[r['repo']].append(r)
    eligible=sum(map(len,groups.values()));rng=random.Random(seed)
    for repo in sorted(groups):rng.shuffle(groups[repo])
    chosen=[]
    while len(chosen)<n:
        repos=sorted(k for k,v in groups.items() if v);rng.shuffle(repos)
        if not repos:raise ValueError('insufficient_unexposed_candidates')
        for repo in repos:
            chosen.append(groups[repo].pop())
            if len(chosen)==n:break
    chosen.sort(key=lambda x:x['instance_id'])
    return chosen,eligible

def main():
    p=argparse.ArgumentParser();p.add_argument('--metadata',type=Path,required=True);p.add_argument('--exposure',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    rows,eligible=select(json.loads(args.metadata.read_text()),json.loads(args.exposure.read_text()))
    args.output.mkdir(parents=True,exist_ok=False)
    ids=''.join(r['instance_id']+'\n' for r in rows);(args.output/'ids.txt').write_text(ids)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest={'version':'holdout-v1','seed':SEED,'algorithm':'sorted metadata; Python Random(seed); shuffle each sorted repository pool; round-robin across shuffled available repositories; no replacement; sorted final IDs','dataset':'princeton-nlp/SWE-bench_Verified','split':'test','dataset_revision':'c104f840cc67f8b6eec6f759ebc8b2693d585d4a','parquet_sha256':'a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd','catalog_size':len(json.loads(args.metadata.read_text())),'eligible_count':eligible,'selected_count':len(rows),'repository_counts':dict(sorted(collections.Counter(r['repo'] for r in rows).items())),'instances':rows,'ids_sha256':hashlib.sha256(ids.encode()).hexdigest(),'metadata_sha256':sha(args.metadata),'exposure_sha256':sha(args.exposure),'sampler_sha256':sha(Path(__file__)),'exposure_scope':'not previously used by this project according to conservative local audit; model pretraining contamination unknown','outcomes':'not_run'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('selected_count','eligible_count','repository_counts','ids_sha256')},ensure_ascii=False))
if __name__=='__main__':main()
