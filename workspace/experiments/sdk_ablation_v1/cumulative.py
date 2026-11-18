"""Bind completed remaining17 batch; old authorities never authorize this ablation."""
import hashlib,sqlite3
from experiments.cohort_preflight.entry import ROOT,read,sha
from experiments.cohort_remaining17_v5.cumulative import prior_binding as earlier_binding
PRIOR_REQUESTS=332
PRIOR_UPPER=3946826
NEW_REQUESTS=48
TOTAL_REQUESTS=380
NEW_MICRO_CNY=102000000
TOTAL_MICRO_CNY=106000000
CASE_HOLD=8*2113536

def prior_binding():
    old=earlier_binding();files=dict(old['files']);requests,cost=old['requests'],old['upper_micro_cny']
    root=ROOT/'verification/remaining17-v5-live-v1/authority/run';lp=root.parents[1]/'result-lock.json';lock=read(lp);files[str(lp.relative_to(ROOT))]=sha(lp)
    def bind(path):
        if path!=path.resolve():raise PermissionError('linked_prior_file')
        name=str(path.relative_to(ROOT));actual=sha(path)
        if lock['files'].get(name)!=actual:raise PermissionError('prior_receipt_changed')
        files[name]=actual
    bind(root/'result.json');bind(root/'batch.sqlite');r=read(root/'result.json')
    if r['mode']!='live' or r['halted'] or r['request_pending_micro_cny'] or r['all_child_requests']!=124 or r['all_child_settled_micro_cny']!=1592052:raise PermissionError('prior_batch_not_complete')
    cases=read(ROOT/'verification/remaining17-v5-batch-v1/live.json')['cases']
    with sqlite3.connect((root/'batch.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('SELECT halted FROM state').fetchall()!=[(0,)] or db.execute('SELECT id,status FROM cases ORDER BY seq').fetchall()!=[(c['id'],'completed') for c in cases]:raise PermissionError('prior_case_status_changed')
    for c in cases:
        path=root/'children'/c['id']/c['hash']/'run/ledger.sqlite';bind(path)
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row;s=db.execute('SELECT * FROM run').fetchall()
            if len(s)!=1 or s[0]['hash']!=c['hash'] or s[0]['mode']!='live' or s[0]['halted']:raise PermissionError('prior_state_changed')
            if sorted(tuple(x) for x in db.execute('SELECT name,finished FROM arms'))!=[('baseline',1),('retrieval',1)]:raise PermissionError('prior_arm_incomplete')
            for x in db.execute('SELECT * FROM calls ORDER BY id'):
                if x['status']!='settled' or x['transport_started']!=1:raise PermissionError('prior_unknown_usage')
                for f in ('request','response'):
                    if hashlib.sha256(bytes(x[f])).hexdigest()!=x[f+'_hash']:raise PermissionError('prior_receipt_changed')
                requests+=1;cost+=x['cost']
    if (requests,cost)!=(PRIOR_REQUESTS,PRIOR_UPPER):raise PermissionError('prior_usage_changed')
    return {'requests':requests,'upper_micro_cny':cost,'unknown_micro_cny':0,'files':files}

def verify_prior(v):
    if v!=prior_binding():raise PermissionError('prior_usage_or_files_changed')

def check_totals(cost,count):
    if not 0<=cost<=NEW_MICRO_CNY or not 0<=count<=NEW_REQUESTS:raise PermissionError('new_budget_exceeded')
    if PRIOR_UPPER+cost>TOTAL_MICRO_CNY or PRIOR_REQUESTS+count>TOTAL_REQUESTS:raise PermissionError('cumulative_budget_exceeded')
