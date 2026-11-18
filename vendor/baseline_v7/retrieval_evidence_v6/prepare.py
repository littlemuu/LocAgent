"""Freeze exposed historical queries and one existing path regression; no gold."""
import json
import sqlite3
from experiments.cohort_preflight.entry import ROOT, read, save, sha
from readonly_agent.core import page, runtime_identity

out = ROOT / 'verification/retrieval-evidence-v6'
prior = ROOT / 'verification/replay-queries-v1'
live = read(ROOT / 'verification/sdk-ablation-v1-batch/live.json')
cases = []
for old in read(prior / 'manifest.json')['cases']:
    assert sha(old['spec']) == old['sha256']
    spec = read(old['spec'])
    for q in spec['queries']:
        q['batch'] = 'remaining17-v5'
    case = next(c for c in live['cases'] if c['id'] == spec['id'])
    ledger = ROOT / 'verification/sdk-ablation-v1-live/authority/run/children' / case['id'] / case['hash'] / 'run/ledger.sqlite'
    with sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True) as db:
        calls = db.execute("SELECT turn,request,response,request_hash,response_hash FROM calls WHERE arm='retrieval' ORDER BY turn").fetchall()
    messages = json.loads(calls[-1][1])['messages']
    pages = {m['tool_call_id']: json.loads(m['content']) for m in messages if m['role'] == 'tool'}
    for turn, req, resp, rqh, rsh in calls:
        for c in json.loads(resp)['choices'][0]['message'].get('tool_calls', []):
            if c['function']['name'] != 'locagent_retrieve':
                continue
            args = json.loads(c['function']['arguments'])
            assert args.get('offset', 0) == 0
            spec['queries'].append({'query': args['query'], 'original_page': pages[c['id']],
                'original_turn': turn, 'original_call_id': c['id'], 'original_request_sha256': rqh,
                'original_response_sha256': rsh, 'batch': 'sdk-ablation-v1',
                'query_source': 'actual saved model call; no rewriting or gold',
                'has_prior_tool_evidence': any(m['role']=='tool' for m in json.loads(req)['messages'])})
    spec['additional_ledger'] = str(ledger); spec['additional_ledger_sha256'] = sha(ledger)
    spec['new_retriever_sha256'] = sha(ROOT / 'experiments/retrieval_evidence_v6/retriever.py')
    path = out / (spec['id'] + '.json'); save(path, spec)
    cases.append({'id': spec['id'], 'spec': str(path), 'sha256': sha(path), 'query_count': len(spec['queries'])})
template = spec
case_id = 'huggingface__accelerate-3261'
entry = ROOT / 'verification/cohort-preflight-v1/runtime' / (case_id + '.json')
regression = ROOT / 'verification/dev37-preparation-v4/checks' / (case_id + '.json')
r = read(regression)
spec = {'version':1, 'id':case_id, 'binding':{'entry':str(entry),'entry_sha256':sha(entry)},
        'snapshot':read(entry)['source_snapshot'], 'runtime_hash':runtime_identity(), 'engine':template['engine'],
        'retriever_sha256':template['retriever_sha256'], 'new_retriever_sha256':template['new_retriever_sha256'],
        'static_regression':str(regression), 'static_regression_sha256':sha(regression),
        'queries':[{'query':q['query'],'original_page':page(q['new_text'],0,4096), 'batch':'prior-offline-path-regression',
                    'query_source':'existing offline path regression, not a new model call'} for q in r['queries']]}
path=out/(case_id+'.json');save(path,spec);cases.append({'id':case_id,'spec':str(path),'sha256':sha(path),'query_count':len(spec['queries'])})
assert sum(c['query_count'] for c in cases)==13
save(out/'manifest.json',{'cases':cases,'real_query_occurrences':12,'path_regressions':1,'gold_read':False,
                          'retriever_sha256':template['new_retriever_sha256'],'queries_from_heldout_test':0})
print('Frozen 12 actual query occurrences (8 distinct case/query pairs) and 1 existing path regression.')
