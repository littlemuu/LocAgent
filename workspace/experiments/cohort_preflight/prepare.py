"""130-case hash verification and source-only runtime projection. No model calls."""
import collections,json,re
from pathlib import Path
from .entry import ROOT,sha,read,save,load_entry,checked_file
from readonly_agent.core import digest
OUT=ROOT/'verification/cohort-preflight-v1'
BATCH=Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113')

def changed_old_lines(patch):
    result={};file=None;old=None
    for line in patch.splitlines():
        if line.startswith('diff --git '):file=None;old=None
        elif line.startswith('--- a/'):
            file=line[6:];result.setdefault(file,{'removed':[],'insertions':[]})
        elif line.startswith('@@ '):
            match=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',line)
            old=int(match[1]) if match else None
        elif file is not None and old is not None:
            if line.startswith('-') and not line.startswith('---'):
                result[file]['removed'].append(old);old+=1
            elif line.startswith('+') and not line.startswith('+++'):
                result[file]['insertions'].append(old)
            elif line.startswith(' '):old+=1
    return result

def label_risks(labels,graph,sources):
    nodes=dict(graph['nodes']);gold=labels['edit_functions']
    missing=[e for e in gold if e not in nodes or nodes[e].get('type') not in ('function','class')]
    touched=changed_old_lines(labels['patch']);functions={}
    for name,data in nodes.items():
        if data.get('type')=='function':functions.setdefault(name.partition(':')[0],[]).append((name,data['start_line'],data['end_line']))
    def owner(file,line):
        matches=[r for r in functions.get(file,[]) if r[1]<=line<=r[2]]
        return min(matches,key=lambda r:r[2]-r[1])[0] if matches else None
    changed=set()
    for file,lines in touched.items():
        for n in lines['removed']:
            candidate=owner(file,n)
            if candidate:changed.add(candidate)
        for n in lines['insertions']:
            before,after=owner(file,n-1),owner(file,n)
            if before and before==after:changed.add(before)
    return {'gold_missing_from_base_graph':missing,'potential_edited_functions_omitted':sorted(changed-set(gold)),
        'patch_paths_outside_python_snapshot':sorted(f for f in touched if f not in sources),
        'added_function_count':len(labels['added_functions']),'gold_count':len(set(gold)),
        'not_semantic_adjudication':True,'gold_unchanged':True}

def main():
    OUT.mkdir(parents=True,exist_ok=False);(OUT/'runtime').mkdir();(OUT/'scoring-only').mkdir()
    mp=ROOT/'engine_adaptation/v4/adapted-manifest.json';manifest=read(mp)
    for n,h in manifest['engine']['files'].items():checked_file(ROOT/'engine_adaptation/v4/engine'/n,h)
    for n,h in manifest['harness_files'].items():checked_file(ROOT/n,h)
    exposure=read(ROOT/'verification/eval-fair-review-v1/exposure-eligibility.json')
    byid={r['id']:r for r in exposure['rows']};catalog=[];technical=[];risks=[];revisions=collections.Counter()
    for i,item in enumerate(manifest['cases'],1):
        id=item['id'];pp=ROOT/'engine_adaptation/v4/plans'/(id+'.json');plan=read(pp)
        parent=read(plan['parent_manifest']);task=parent['task']
        if task['instance_id']!=id or task['base_commit']!=plan['commit']:raise ValueError('task_source_commit_mismatch')
        revisions[parent['dataset']['dataset_revision']]+=1
        value={'version':1,'case_id':id,'repo':task['repo'],'base_commit':plan['commit'],
            'issue':task['problem_statement'],'issue_hash':digest(task['problem_statement']),
            'source_plan':str(pp),'source_plan_sha256':sha(pp),'source_snapshot':item['source_snapshot'],
            'parent_manifest_sha256':sha(plan['parent_manifest']),'entity_index':item['index_directory'],
            'entity_attestation':item['index_attestation'],'entity_attestation_sha256':sha(item['index_attestation']),
            'validation_attestation':item['validation_attestation'],'validation_attestation_sha256':sha(item['validation_attestation']),
            'v4_manifest_sha256':sha(mp)}
        ep=OUT/'runtime'/(id+'.json');save(ep,value)
        _,snapshot=load_entry(ep,sha(ep),check_engine=False)
        unicode_files=sum(any(c in text for c in '\v\f\x1c\x1d\x1e\x85\u2028\u2029') for text in snapshot.files.values())
        technical.append({'id':id,'source_files':len(snapshot.files),'source_bytes':sum(len(x.encode()) for x in snapshot.files.values()),
            'status':'hash_verified','unicode_splitlines_risk_files':unicode_files,'entity_index_verified':True,
            'body_index_status':'not_built','runtime_entry_sha256':sha(ep)})
        row=byid[id]
        catalog.append({'id':id,'entry':str(ep),'entry_sha256':sha(ep),'snapshot':snapshot.identity,
            'split':row['local_split'],'repo':row['repo'],'exposure':row['known_repository_exposure_now'],
            'eligibility':row['eligibility'],'live_allowed':False})
        # This side stays in scoring-only; never imported by source runtime.
        lp=BATCH/'scoring-only/labels'/(id+'.json');labels=read(lp)
        if labels['base_commit']!=plan['commit'] or labels['instance_id']!=id:raise ValueError('label_commit_mismatch')
        graph=read(Path(item['index_directory']).parent/'graph.json')
        risks.append({'id':id,'label_sha256':sha(lp),**label_risks(labels,graph,plan['sources'])})
        if i%10==0:print(f'Hash/source/runtime projection checked: {i}/130',flush=True)
    snapshots=collections.Counter(r['snapshot'] for r in catalog)
    repos={s:{r['repo'].lower() for r in catalog if r['split']==s} for s in ['development','test']}
    summary={'planned_cases':len(catalog),'hash_verified':len(technical),'hash_failed':0,'hash_unchecked':0,
      'source_files':sum(r['source_files'] for r in technical),'source_bytes':sum(r['source_bytes'] for r in technical),
      'unicode_splitlines_risk_cases':sum(r['unicode_splitlines_risk_files']>0 for r in technical),
      'unicode_splitlines_risk_files':sum(r['unicode_splitlines_risk_files'] for r in technical),
      'split_counts':dict(collections.Counter(r['split'] for r in catalog)),
      'cross_split_repository_overlap':sorted(repos['development']&repos['test']),
      'duplicate_source_snapshots':sum(c-1 for c in snapshots.values() if c>1),'dataset_revisions':dict(revisions),
      'automated_label_structural_checked':len(risks),'automated_label_unchecked':0,
      'missing_gold_entity_cases':sum(bool(r['gold_missing_from_base_graph']) for r in risks),
      'potential_omitted_label_cases':sum(bool(r['potential_edited_functions_omitted']) for r in risks),
      'outside_snapshot_patch_cases':sum(bool(r['patch_paths_outside_python_snapshot']) for r in risks),
      'manual_semantic_preliminary':6,'manual_semantic_unreviewed':124,'independent_second_reviews_completed':0,
      'formal_eligible_confirmed':0,'formal_eligibility_unresolved':130,'real_model_requests':0,
      'projection_contains_gold':False,'body_backend':'physical-line80-v2; not upstream EpicSplitter'}
    save(OUT/'runtime-catalog.json',{'version':1,'live_enabled':False,'pilot_allowlist':['Delgan__loguru-1239','tobymao__sqlglot-3417'],'cases':catalog})
    save(OUT/'technical-checks.json',technical);save(OUT/'scoring-only/structural-label-audit.json',risks)
    save(OUT/'preparation-summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
