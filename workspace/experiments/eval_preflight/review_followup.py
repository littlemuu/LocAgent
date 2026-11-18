"""Scoring-only review and metadata-only exposure reconciliation; no runner imports."""
import ast,collections,hashlib,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'verification/eval-fair-review-v1'
BATCH=Path('/Users/xiaomu/Documents/Codex/2026-11-10/task/locbench-remaining-batch134-20261113')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)

def main():
    initial=read(OUT/'scoring-only/initial-review.json');reviews=[]
    findings={
      'AzureAD__microsoft-authentication-library-for-python-454':(
        'hold_label_coverage_review',
        'Reference patch implements lazy imports in four Python files, but frozen edited-function labels cover only authority.py. Three directly modified existing functions are absent. Do not silently repair gold or count them as definitely wrong predictions.',
        ['msal/application.py:ClientApplication.__init__','msal/oauth2cli/assertion.py:JwtAssertionCreator.create_normal_assertion','msal/oauth2cli/oauth2.py:BaseClient.__init__']),
      'spotify__luigi-3308':('hinted_consistent_pending_second_review',
        'Patch changes the linked directory chmod in acquire_for; label consistent. Another permissive file chmod exists but is outside this reference patch. Issue provides file and exact line, so mark location-hinted.',[]),
      'matchms__matchms-backup-187':('hold_underspecified_and_source_scope',
        'Title and external license URL underspecify intended replacement. Patch replaces OpenBabel with RDKit, changes callers, a validation detail, adds functions and edits dependency YAML outside the Python snapshot. Edited labels exist in base, but reference scope is not uniquely recoverable from issue. No external link opened or legal judgment made.',[]),
      'huggingface__trl-2450':('answer_hinted_consistent_pending_second_review',
        'Issue supplies class, file, lines and exact proposed change. Base source and reference patch agree. Useful hinted development case, not an independent unguided localization task.',[])}
    for row in initial['rows']:
        id=row['id'];plan=read(ROOT/'engine_adaptation/v4/plans'/(id+'.json'))
        lp=BATCH/'scoring-only/labels'/(id+'.json');label=read(lp)
        assert row['commit']==plan['commit']==label['base_commit']
        targets={};node_ranges={}
        for entity in label['edit_functions']+findings[id][2]:
            file,_,qualified=entity.partition(':');data=(Path(plan['source_root'])/file).read_bytes()
            assert hashlib.sha256(data).hexdigest()==plan['sources'][file]
            tree=ast.parse(data.decode('utf-8-sig'))
            def visit(node,prefix=''):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                        name=prefix+child.name
                        node_ranges[file+':'+name]=(child.lineno,child.end_lineno)
                        visit(child,name+'.')
                    else:visit(child,prefix)
            visit(tree);assert entity in node_ranges,entity
            targets[entity]={'base_span':node_ranges[entity],'source_hash':plan['sources'][file]}
        status,reason,missing=findings[id]
        reviews.append({'id':id,'status':status,'reason':reason,'label_sha256':sha(lp),
          'initial_rationale_sha256':sha(OUT/'scoring-only/initial-review.json'),
          'base_entities_verified':targets,'potential_omitted_changed_entities':missing,
          'gold_changed':False,'independent_review':False,'second_reviewer':'pending',
          'used_for_runner_or_queries':False})
    save(OUT/'scoring-only/review-results.json',{'development_only':True,'reviews':reviews})
    old=read(ROOT/'verification/eval-preflight-v2/cohort-semantic-audit.json')
    manifest=read(ROOT/'engine_adaptation/v4/adapted-manifest.json')
    snapshot_ids=collections.defaultdict(list)
    for row in manifest['cases']:snapshot_ids[row['source_snapshot']].append(row['id'])
    scans=[];unmapped=[]
    for directory in sorted(ROOT.glob('authority*')):
        if not directory.is_dir():continue
        for p in sorted(directory.rglob('ledger.sqlite')):
            with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
                tables={r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
                if not {'run','calls'}<=tables:continue
                cols={r[1] for r in db.execute('PRAGMA table_info(calls)')}
                if 'transport_started' not in cols:
                    unmapped.append({'path':str(p),'reason':'no_transport_started_column'});continue
                count=db.execute('SELECT COUNT(*) FROM calls WHERE transport_started=1').fetchone()[0]
                snapshot=db.execute("SELECT json_extract(plan,'$.snapshot') FROM run").fetchone()[0]
                ids=snapshot_ids.get(snapshot,[])
                record={'path':str(p),'sha256':sha(p),'transport_started':count,'case_ids':ids}
                if ids:scans.append(record)
                elif count:unmapped.append(record)
    newly_reviewed={r['id'] for r in initial['rows']}
    reviewed_repos={r['repo'].lower() for r in old['rows'] if r['id'] in newly_reviewed}
    called_ids={i for s in scans if s['transport_started'] for i in s['case_ids']}
    called_repos={r['repo'].lower() for r in old['rows'] if r['id'] in called_ids}
    rows=[]
    decisions={r['id']:r['decision'] for r in old['verified_old_checklist_records']}
    for row in old['rows']:
        exposure=row['known_repository_exposure'] or row['repo'].lower() in reviewed_repos|called_repos
        decision='pending_semantic_and_exposure'
        if decisions.get(row['id'])=='excluded':decision='excluded_historical_not_overridden'
        elif decisions.get(row['id'])=='control_only':decision='development_control_only'
        elif row['local_split']=='test' and exposure:decision='not_independent_repository_exposed'
        elif row['id'] in newly_reviewed:decision=findings[row['id']][0]
        rows.append({**row,'known_repository_exposure_now':exposure,
            'reviewed_this_round':row['id'] in newly_reviewed,
            'repository_reviewed_this_round':row['repo'].lower() in reviewed_repos,
            'verified_live_ledger_present':row['id'] in called_ids,'eligibility':decision})
    summary={'rows':rows,'new_semantically_reviewed_development_cases':sorted(newly_reviewed),
      'counts':[{'split':s,'exposed':e,'count':sum(r['local_split']==s and r['known_repository_exposure_now']==e for r in rows)} for s in ['development','test'] for e in [True,False]],
      'historical_live_ledger_scan':scans,'unmapped_or_unverifiable':unmapped,
      'scan_scope':'All current workspace authority*/**/ledger.sqlite, read-only; external historical workspaces not exhaustively scanned.',
      'false_means':'not yet verified exposed; does not prove unexposed',
      'independent_test_claim':False,'old_records_overwritten':False}
    save(OUT/'exposure-eligibility.json',summary)
    print('Four preliminary development reviews saved; no gold changed. Exposure:',summary['counts'])
    print('Mapped historical requests:',{i:sum(s['transport_started'] for s in scans if i in s['case_ids']) for i in sorted(called_ids)})

if __name__=='__main__':main()
