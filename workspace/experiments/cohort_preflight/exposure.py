"""Reconcile local ledgers by source snapshot, issue identity and source-only fixtures."""
import collections,json,sqlite3
from pathlib import Path
from readonly_agent.core import Snapshot,digest
from .entry import ROOT,read,sha,save
OUT=ROOT/'verification/cohort-preflight-v1'
def main():
    catalog=read(OUT/'runtime-catalog.json')['cases'];entries={r['id']:read(r['entry']) for r in catalog}
    synthetic={}
    paths=list((ROOT/'development_suite/v1/cases').glob('*/case.json'))+[ROOT/'examples/case.json',ROOT/'examples/crossfile/case.json']
    for p in paths:
        case=read(p);snapshot=Snapshot(p.parent/case['root'],case['source_files'])
        synthetic[snapshot.identity]=str(p.relative_to(ROOT))
    rows=[]
    for directory in sorted(ROOT.glob('authority*')):
        if not directory.is_dir():continue
        for p in sorted(directory.rglob('ledger.sqlite')):
            with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
                tables={r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
                if not {'run','calls'}<=tables:continue
                columns={r[1] for r in db.execute('PRAGMA table_info(calls)')}
                if 'transport_started' not in columns:
                    rows.append({'path':str(p),'status':'unresolved_missing_start_column'});continue
                count=db.execute('SELECT COUNT(*) FROM calls WHERE transport_started=1').fetchone()[0]
                plan=json.loads(db.execute('SELECT plan FROM run').fetchone()[0])
                issue_matches=[id for id,v in entries.items() if v['issue_hash']==plan.get('issue_hash')]
                snapshot_matches=[id for id,v in entries.items() if v['source_snapshot']==plan.get('snapshot')]
                method='issue_hash' if issue_matches else 'source_snapshot'
                ids=issue_matches or snapshot_matches
                if not ids and count and plan.get('snapshot') not in synthetic:
                    # Only inspect already-sent text bodies, never headers or credentials.
                    request_messages=[]
                    for request, in db.execute('SELECT request FROM calls WHERE transport_started=1'):
                        request_messages.extend(m.get('content','') for m in json.loads(request).get('messages',[]) if isinstance(m.get('content'),str))
                    ids=[id for id,v in entries.items() if any(v['issue'] in text for text in request_messages)]
                    method='exact_issue_in_saved_request'
                fixture=synthetic.get(plan.get('snapshot'))
                status='mapped_cohort' if ids else ('mapped_authored_fixture' if fixture else ('no_transport' if not count else 'unresolved'))
                rows.append({'path':str(p),'sha256':sha(p),'status':status,'transport_started':count,
                    'case_ids':ids,'mapping':method if ids else None,'fixture':fixture})
    old=read(ROOT/'verification/eval-fair-review-v1/exposure-eligibility.json')
    known_ids={i for row in rows if row.get('transport_started') for i in row.get('case_ids',[])}
    known_repos={row['repo'].lower() for row in catalog if row['id'] in known_ids}
    new=[]
    for row in old['rows']:
        new.append({**row,'known_repository_exposure_now':row['known_repository_exposure_now'] or row['repo'].lower() in known_repos})
    summary={'local_ledger_files_checked':len(rows),'status_counts':dict(collections.Counter(r['status'] for r in rows)),
        'cohort_transport_lower_bound':{id:sum(r.get('transport_started',0) for r in rows if id in r.get('case_ids',[])) for id in sorted(known_ids)},
        'known_repository_exposure':sum(r['known_repository_exposure_now'] for r in new),
        'not_confirmed_unexposed':sum(not r['known_repository_exposure_now'] for r in new),
        'external_historical_workspaces_not_exhaustively_scanned':True,'external_unchecked_run_count':None,
        'external_unchecked_count_reason':'No complete cross-workspace run inventory; do not invent a denominator.',
        'no_new_semantic_reviews':True,'rows':new,'ledger_evidence':rows}
    save(OUT/'exposure-reconciliation.json',summary)
    print({k:summary[k] for k in ['local_ledger_files_checked','status_counts','cohort_transport_lower_bound','known_repository_exposure','not_confirmed_unexposed']})
if __name__=='__main__':main()
