"""Bind both predecessor batches without granting more calls."""
import hashlib
import sqlite3
from experiments.cohort_preflight.entry import ROOT, read, sha
from experiments.cohort_five_evidence_v3.cumulative import prior_binding as earlier_binding
PRIOR_REQUESTS = 53
PRIOR_UPPER = 620428
NEW_REQUESTS = 296
TOTAL_REQUESTS = 349
NEW_MICRO_CNY = 629000000
TOTAL_MICRO_CNY = 630000000
CASE_HOLD = 8 * 2113536

def prior_binding():
    earlier = earlier_binding()
    root = ROOT/'verification/five-integrated-live-v3/authority/run'
    result = read(root/'result.json')
    if result['mode'] != 'live' or result['halted']:
        raise PermissionError('prior_batch_not_completed')
    files = dict(earlier['files'])
    for p in (root/'result.json', root/'batch.sqlite'):
        files[str(p.relative_to(ROOT))] = sha(p)
    with sqlite3.connect((root/'batch.sqlite').as_uri()+'?mode=ro', uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM cases WHERE status!='completed'").fetchone()[0]:
            raise PermissionError('prior_batch_still_pending')
    requests, cost = earlier['requests'], earlier['upper_micro_cny']
    for item in read(ROOT/'verification/five-batch-integrated-v3/live.json')['cases']:
        path = root/'children'/item['id']/item['hash']/'run/ledger.sqlite'
        if path != path.resolve():
            raise PermissionError('linked_prior_ledger')
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            state = db.execute('SELECT * FROM run').fetchall()
            if len(state)!=1 or state[0]['hash']!=item['hash'] or state[0]['mode']!='live':
                raise PermissionError('prior_ledger_binding')
            if sorted(tuple(r) for r in db.execute('SELECT name,finished FROM arms')) != [('baseline',1),('retrieval',1)]:
                raise PermissionError('prior_arm_not_finished')
            for call in db.execute('SELECT * FROM calls ORDER BY id'):
                if call['status']!='settled' or call['transport_started']!=1:
                    raise PermissionError('prior_unknown_usage')
                for field in ('request','response'):
                    if hashlib.sha256(bytes(call[field])).hexdigest()!=call[field+'_hash']:
                        raise PermissionError('prior_receipt_changed')
                requests += 1
                cost += call['cost']
        files[str(path.relative_to(ROOT))] = sha(path)
    if (requests,cost)!=(PRIOR_REQUESTS,PRIOR_UPPER):
        raise PermissionError('prior_usage_changed')
    return {'requests':requests,'upper_micro_cny':cost,'unknown_micro_cny':0,'files':files}

def verify_prior(value):
    if value != prior_binding():
        raise PermissionError('prior_usage_or_files_changed')

def check_totals(new_reserved_or_spent, new_requests):
    if not 0 <= new_reserved_or_spent <= NEW_MICRO_CNY or not 0 <= new_requests <= NEW_REQUESTS:
        raise PermissionError('new_budget_exceeded')
    if PRIOR_UPPER+new_reserved_or_spent > TOTAL_MICRO_CNY or PRIOR_REQUESTS+new_requests > TOTAL_REQUESTS:
        raise PermissionError('cumulative_budget_exceeded')
