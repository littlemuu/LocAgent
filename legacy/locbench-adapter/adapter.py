"""Offline Loc-Bench adapter. Only four allowed fields become model input."""
from pathlib import Path
import json, hashlib, re, collections
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent/'locagent-demo-20261108'
FIELDS=('instance_id','repo','base_commit','problem_statement')
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f: json.dump(obj,f,indent=2,ensure_ascii=False);f.write('\n')
def normalize(s):
    return s[:-9] if s.endswith('.__init__') else s
def task(row):
    result={k:row[k] for k in FIELDS}
    assert all(isinstance(v,str) and v.strip() for v in result.values())
    assert re.fullmatch(r'[0-9a-f]{40}',result['base_commit'])
    return result

def main():
    import pyarrow.parquet as pq
    rows=pq.read_table(ROOT/'scoring-only/test-00000-of-00001.parquet').to_pylist()
    assert len(rows)==560 and len({r['instance_id'] for r in rows})==560
    # Actual task files, not candidate manifests; retain source paths as audit evidence.
    old={}; texts={}; old_targets={}; scanned=[]
    for folder in sorted(ROOT.parent.glob('locagent-*')):
        if not folder.is_dir() or folder==ROOT:continue
        for p in sorted(folder.glob('inputs/*/task.json')):
            d=json.loads(p.read_text());i=d.get('instance_id')
            if not i:continue
            scanned.append(str(p));old.setdefault(i,[]).append(str(p))
            texts.setdefault(' '.join(d.get('problem_statement','').split()).casefold(),[]).append(i)
        labels=folder/'scoring-only/frozen-labels.json'
        if labels.exists():
            for i,g in json.loads(labels.read_text()).items():
                if not isinstance(g,dict):continue
                for e in g.get('functions',[]):old_targets.setdefault((i.rsplit('-',1)[0].replace('__','/').lower(),normalize(e)),set()).add(i)
        for p in folder.glob('scoring-only/*-labels.json'):
            d=json.loads(p.read_text());i=p.name[:-12]
            for e in d.get('labels',[]):old_targets.setdefault((i.rsplit('-',1)[0].replace('__','/').lower(),normalize(e)),set()).add(i)
    audit=[];gold={};schema={}; init=0
    for row in rows:
        i=row['instance_id'];t=task(row)
        for k,v in row.items():schema.setdefault(k,set()).add(type(v).__name__)
        raw=row['edit_functions'];assert all(isinstance(e,str) and ':' in e for e in raw)
        functions=list(dict.fromkeys(map(normalize,raw)))
        init+=any(e.endswith('.__init__') for e in raw)
        gold[i]={'raw_edit_functions':raw,'official_function_labels':functions,'files':list(dict.fromkeys(e.split(':')[0] for e in raw)),'added_functions':row['added_functions'],'category':row['category']}
        targets=sorted({x for e in functions for (repo,prev),ids in old_targets.items() if repo==row['repo'].lower() and (e==prev or e.startswith(prev+'.') or prev.startswith(e+'.')) for x in ids})
        dup=old.get(i,[]);textdup=texts.get(' '.join(t['problem_statement'].split()).casefold(),[])
        audit.append({'instance_id':i,'repo':row['repo'],'category':row['category'],'prior_task_files':dup,'same_issue_text':textdup,'overlapping_prior_targets':targets,'candidate':not (dup or textdup or targets),'review_needed':'semantic novelty, question quality, graph coverage, license'})
        save(ROOT/'inputs'/i/'task.json',t)
    save(ROOT/'scoring-only/labels.json',gold)
    save(ROOT/'history-dedup.json',{'method':'actual inputs/*/task.json plus actual frozen-labels and per-case labels; no candidate-manifest mention exclusion; no live-call proof inferred','scanned_task_files':scanned,'prior_unique_ids':sorted(old),'cases':audit})
    summary={'rows':len(rows),'repositories':len({r['repo'] for r in rows}),'schema':{k:sorted(v) for k,v in schema.items()},'categories':dict(collections.Counter(r['category'] for r in rows)),'prior_task_files':len(scanned),'prior_unique_ids':len(old),'id_overlap':sum(bool(a['prior_task_files']) for a in audit),'text_overlap':sum(bool(a['same_issue_text']) for a in audit),'target_overlap':sum(bool(a['overlapping_prior_targets']) for a in audit),'remaining_candidates':sum(a['candidate'] for a in audit),'constructor_cases':init,'empty_function_labels':sum(not r['edit_functions'] for r in rows),'dataset_license':'Not declared in dataset card or repository files; code Apache-2.0 does not imply dataset license','model_calls':0}
    save(ROOT/'summary.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
