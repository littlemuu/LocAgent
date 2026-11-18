"""Audit all prior linked usage, including successful v5 pilot; no reused admission."""
import hashlib,sqlite3
from experiments.cohort_preflight.entry import ROOT,read,sha
from experiments.cohort_finish_v5.cumulative import prior_binding as earlier_binding
PRIOR_REQUESTS=208
PRIOR_UPPER=2354774
NEW_REQUESTS=136
TOTAL_REQUESTS=344
NEW_MICRO_CNY=289000000
TOTAL_MICRO_CNY=630000000
CASE_HOLD=8*2113536

def prior_binding():
    earlier=earlier_binding();files=dict(earlier['files'])
    root=ROOT/'verification/finish-v5-live-v1/authority/run'
    lockpath=ROOT/'verification/finish-v5-live-v1/result-lock.json';lock=read(lockpath)
    files[str(lockpath.relative_to(ROOT))]=sha(lockpath)
    def bind(path):
        if path!=path.resolve():raise PermissionError('linked_prior_file')
        name=str(path.relative_to(ROOT));actual=sha(path)
        if lock['files'].get(name)!=actual:raise PermissionError('prior_receipt_changed')
        files[name]=actual
    bind(root/'result.json');bind(root/'batch.sqlite')
    result=read(root/'result.json')
    if result['mode']!='live' or result['halted'] or result['request_pending_micro_cny'] or result['all_child_requests']!=7 or result['all_child_settled_micro_cny']!=88386:
        raise PermissionError('prior_pilot_not_completed')
    with sqlite3.connect((root/'batch.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('SELECT halted FROM state').fetchall()!=[(0,)] or db.execute('SELECT id,status FROM cases').fetchall()!=[('rwth-i6__sisyphus-191','completed')]:raise PermissionError('prior_case_state_changed')
    requests,cost=earlier['requests'],earlier['upper_micro_cny']
    for item in read(ROOT/'verification/finish-v5-batch-v2/live.json')['cases']:
        path=root/'children'/item['id']/item['hash']/'run/ledger.sqlite';bind(path)
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row;state=db.execute('SELECT * FROM run').fetchall()
            if len(state)!=1 or state[0]['hash']!=item['hash'] or state[0]['mode']!='live' or state[0]['halted']:raise PermissionError('prior_ledger_binding')
            if sorted(tuple(x) for x in db.execute('SELECT name,finished FROM arms'))!=[('baseline',1),('retrieval',1)]:raise PermissionError('prior_arm_unfinished')
            for c in db.execute('SELECT * FROM calls ORDER BY id'):
                if c['status']!='settled' or c['transport_started']!=1:raise PermissionError('prior_unknown_usage')
                for f in ('request','response'):
                    if hashlib.sha256(bytes(c[f])).hexdigest()!=c[f+'_hash']:raise PermissionError('prior_receipt_changed')
                requests+=1;cost+=c['cost']
    if (requests,cost)!=(PRIOR_REQUESTS,PRIOR_UPPER):raise PermissionError('prior_usage_changed')
    return {'requests':requests,'upper_micro_cny':cost,'unknown_micro_cny':0,'files':files}

def verify_prior(value):
    if value!=prior_binding():raise PermissionError('prior_usage_or_files_changed')

def check_totals(new_reserved_or_spent,new_requests):
    if not 0<=new_reserved_or_spent<=NEW_MICRO_CNY or not 0<=new_requests<=NEW_REQUESTS:raise PermissionError('new_budget_exceeded')
    if PRIOR_UPPER+new_reserved_or_spent>TOTAL_MICRO_CNY or PRIOR_REQUESTS+new_requests>TOTAL_REQUESTS:raise PermissionError('cumulative_budget_exceeded')
