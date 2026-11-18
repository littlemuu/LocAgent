"""Select only previously exposed metadata; never open holdout content."""
import argparse,collections,hashlib,json,random
from pathlib import Path
SEED=20261117

def select(metadata,exposure,holdout_ids,n=24):
    exposed={x.lower() for x in exposure['excluded_verified_ids']}
    assert len(exposed)==93
    holdout={x.lower() for x in holdout_ids};groups=collections.defaultdict(list)
    for row in sorted(metadata,key=lambda x:x['instance_id']):
        assert set(row)=={'instance_id','repo','base_commit','created_at'}
        if row['instance_id'].lower() in exposed:
            assert row['instance_id'].lower() not in holdout
            groups[row['repo']].append(row)
    assert sum(map(len,groups.values()))==93
    rng=random.Random(SEED)
    for repo in sorted(groups):rng.shuffle(groups[repo])
    result=[]
    while len(result)<n:
        repos=sorted(k for k,v in groups.items() if v);rng.shuffle(repos)
        if not repos:raise ValueError('not_enough_exposed_candidates')
        for repo in repos:
            result.append(groups[repo].pop())
            if len(result)==n:break
    assert len({x['repo'] for x in result})>=6
    assert {x['instance_id'].lower() for x in result}.isdisjoint(holdout)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    metadata=a.project/'data/selection/verified-metadata.json';exposure=a.project/'data/selection/exposure-audit.json';ids=a.project/'freezes/holdout-v1/ids.txt'
    chosen=select(json.loads(metadata.read_text()),json.loads(exposure.read_text()),ids.read_text().splitlines());a.output.mkdir(parents=True,exist_ok=False)
    text=''.join(x['instance_id']+'\n' for x in sorted(chosen,key=lambda x:x['instance_id']));(a.output/'ids.txt').write_text(text)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    manifest={'version':'e2e-dev24-v1','seed':SEED,'source':'stage1 exposed Verified 93 metadata only','algorithm':'sorted repo pools shuffled with seed; round-robin over shuffled nonempty repositories; no difficulty or outcomes used','instances':sorted(chosen,key=lambda x:x['instance_id']),'selection_order':[x['instance_id'] for x in chosen],'smoke_ids':[x['instance_id'] for x in chosen[:2]],'repository_counts':dict(sorted(collections.Counter(x['repo'] for x in chosen).items())),'ids_sha256':sha(text.encode()),'source_metadata_sha256':sha(metadata.read_bytes()),'exposure_sha256':sha(exposure.read_bytes()),'holdout_ids_sha256':sha(ids.read_bytes()),'holdout_overlap_count':0,'locbench37_role':'localization_development_only_no_e2e_runs','sampler_sha256':sha(Path(__file__).read_bytes())}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({k:manifest[k] for k in ('repository_counts','smoke_ids','ids_sha256','holdout_overlap_count')}))
if __name__=='__main__':main()
