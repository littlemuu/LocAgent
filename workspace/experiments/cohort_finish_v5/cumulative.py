"""Bind the stopped v4 batch and earlier usage; never resume or release its grant."""
import hashlib
import sqlite3
from experiments.cohort_preflight.entry import ROOT, read, sha
from experiments.cohort_dev37_v4.cumulative import prior_binding as earlier_binding
PRIOR_REQUESTS = 201
PRIOR_UPPER = 2266388
NEW_REQUESTS = 8
TOTAL_REQUESTS = 209
NEW_MICRO_CNY = 17000000
TOTAL_MICRO_CNY = 20000000
CASE_HOLD = 8 * 2113536


def prior_binding():
    earlier = earlier_binding()
    root = ROOT/'verification/dev37-live-v4b/authority/run'
    lockpath = ROOT/'verification/dev37-live-v4b/result-lock.json'
    lock = read(lockpath)
    files = dict(earlier['files'])
    files[str(lockpath.relative_to(ROOT))] = sha(lockpath)
    def bind(path):
        if path != path.resolve():
            raise PermissionError('linked_prior_file')
        name = str(path.relative_to(ROOT)); actual = sha(path)
        if lock['files'].get(name) != actual:
            raise PermissionError('stopped_v4_receipt_changed')
        files[name] = actual
    bind(root/'result.json'); bind(root/'batch.sqlite')
    result = read(root/'result.json')
    if (result['mode'] != 'live' or result['halted'] is not True
            or result['request_pending_micro_cny'] != 0
            or result['all_child_requests'] != 148
            or result['all_child_settled_micro_cny'] != 1645960):
        raise PermissionError('prior_batch_not_terminal')
    with sqlite3.connect((root/'batch.sqlite').as_uri()+'?mode=ro', uri=True) as db:
        states = db.execute('SELECT halted FROM state').fetchall()
        statuses = db.execute('SELECT id,status FROM cases ORDER BY seq').fetchall()
        if states != [(1,)] or [s for _,s in statuses] != ['completed']*19+['failed']+['not_started']*17:
            raise PermissionError('prior_batch_status_changed')
    expected = dict(statuses)
    requests, cost = earlier['requests'], earlier['upper_micro_cny']
    for item in read(ROOT/'verification/dev37-batch-v4b/live.json')['cases']:
        path = root/'children'/item['id']/item['hash']/'run/ledger.sqlite'
        if expected[item['id']] == 'not_started':
            if (root/'children'/item['id']).exists():
                raise PermissionError('unexpected_prior_started_case')
            continue
        bind(path)
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            state = db.execute('SELECT * FROM run').fetchall()
            if len(state)!=1 or state[0]['hash']!=item['hash'] or state[0]['mode']!='live':
                raise PermissionError('prior_ledger_binding')
            arms=sorted(tuple(x) for x in db.execute('SELECT name,finished FROM arms'))
            wanted=[('baseline',1),('retrieval',1)] if expected[item['id']]=='completed' else [('baseline',0),('retrieval',1)]
            if arms!=wanted or bool(state[0]['halted']) != (expected[item['id']]=='failed'):
                raise PermissionError('prior_arm_status_changed')
            for call in db.execute('SELECT * FROM calls ORDER BY id'):
                if call['status']!='settled' or call['transport_started']!=1:
                    raise PermissionError('prior_unknown_usage')
                for field in ('request','response'):
                    if hashlib.sha256(bytes(call[field])).hexdigest()!=call[field+'_hash']:
                        raise PermissionError('prior_receipt_changed')
                requests += 1; cost += call['cost']
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
