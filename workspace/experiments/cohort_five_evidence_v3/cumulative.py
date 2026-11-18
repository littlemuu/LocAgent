"""Read-only binding to the stopped predecessor; never releases its historic holds."""
import sqlite3,json,hashlib
from pathlib import Path
from experiments.cohort_preflight.entry import ROOT,read,sha
PRIOR_REQUESTS=15
PRIOR_UPPER=172942
NEW_REQUESTS=40
TOTAL_REQUESTS=55
TOTAL_MICRO_CNY=85000000
NEW_MICRO_CNY=TOTAL_MICRO_CNY-PRIOR_UPPER
CASE_HOLD=8*2113536

def prior_binding():
    root=ROOT/'verification/five-batch-live-v2/authority/run'
    summary=read(root/'result.json')
    if summary['mode']!='live' or not summary['halted']:raise PermissionError('prior_batch_not_stopped')
    parent=root/'batch.sqlite'
    with sqlite3.connect(parent.as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('SELECT halted FROM state').fetchall()!=[(1,)]:raise PermissionError('prior_parent_active')
    files={str((root/'result.json').relative_to(ROOT)):sha(root/'result.json'),str(parent.relative_to(ROOT)):sha(parent)}
    requests=cost=0
    plan=read(ROOT/'verification/five-batch-v2/live.json')
    for c in plan['cases']:
        path=root/'children'/c['id']/c['hash']/'run/ledger.sqlite'
        if not path.exists():continue
        if path!=path.resolve():raise PermissionError('linked_prior_ledger')
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            states=db.execute('SELECT * FROM run').fetchall()
            if len(states)!=1 or states[0]['mode']!='live' or states[0]['hash']!=c['hash']:raise PermissionError('prior_ledger_binding')
            calls=db.execute('SELECT * FROM calls ORDER BY id').fetchall()
            for call in calls:
                if call['status']!='settled' or call['transport_started']!=1 or call['response'] is None:raise PermissionError('prior_unknown_usage')
                for name in ('request','response'):
                    if hashlib.sha256(bytes(call[name])).hexdigest()!=call[name+'_hash']:raise PermissionError('prior_receipt_changed')
                requests+=1;cost+=call['cost']
        files[str(path.relative_to(ROOT))]=sha(path)
    if (requests,cost)!=(PRIOR_REQUESTS,PRIOR_UPPER):raise PermissionError('prior_usage_changed')
    return {'requests':requests,'upper_micro_cny':cost,'unknown_micro_cny':0,'files':files}

def verify_prior(value):
    if value!=prior_binding():raise PermissionError('prior_usage_or_files_changed')

def check_totals(new_reserved_or_spent,new_requests):
    if not 0<=new_reserved_or_spent<=NEW_MICRO_CNY or not 0<=new_requests<=NEW_REQUESTS:
        raise PermissionError('cumulative_budget_exceeded')
    if PRIOR_UPPER+new_reserved_or_spent>TOTAL_MICRO_CNY or PRIOR_REQUESTS+new_requests>TOTAL_REQUESTS:
        raise PermissionError('cumulative_budget_exceeded')
