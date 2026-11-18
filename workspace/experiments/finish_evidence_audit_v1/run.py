"""Audit 12 saved finishes using final-request-visible tools. No gold reads."""
import json
import sys
from pathlib import Path
import sqlite3
from experiments.cohort_preflight.entry import ROOT,read,save,sha,load_entry
from .check import entity_metadata,observed_lines,audit_finish

OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'verification/finish-evidence-audit-v1'
OUT.mkdir(parents=True,exist_ok=True)
LIVE=ROOT/'verification/sdk-retrieval-compare-v6-live'
lock=read(LIVE/'result-lock.json')
for name,h in lock['files'].items():assert sha(ROOT/name)==h,name
plan=read(ROOT/'verification/sdk-retrieval-compare-v6-batch/live.json')
rows=[]
for case in plan['cases']:
    b=case['plan']['cohort_binding'];entry,snapshot=load_entry(b['entry'],b['entry_sha256'])
    graph_path=__import__('pathlib').Path(entry['entity_index']).parent/'graph.json'
    graph=dict(read(graph_path)['nodes']);meta=entity_metadata(graph)
    folder=LIVE/'authority/run/children'/case['id']/case['hash']/'run'
    with sqlite3.connect((folder/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        calls=[dict(c) for c in db.execute('SELECT * FROM calls ORDER BY id')]
    for arm in ('baseline','retrieval'):
        stream=[c for c in calls if c['arm']==arm];last=stream[-1]
        for call in stream:
            for field in ('request','response'):
                import hashlib
                assert hashlib.sha256(bytes(call[field])).hexdigest()==call[field+'_hash']
        request=json.loads(last['request']);response=json.loads(last['response'])
        terminal=response['choices'][0]['message']['tool_calls'];assert len(terminal)==1 and terminal[0]['function']['name']=='finish'
        raw=json.loads(terminal[0]['function']['arguments'])['message']
        if isinstance(raw,str):raw=json.loads(raw)
        answer=read(folder/('sdk-'+arm)/'result.json')['answer']
        unchanged={k:raw[k]==answer[k] for k in ('files','entities','answer')};assert all(unchanged.values())
        events=[json.loads(x) for x in (folder/('sdk-'+arm)/'trace.jsonl').read_text().splitlines()]
        audits=[t for e in events if e.get('event')=='tool_audit' for t in e['audit']]
        calls_by_id={};evidence=[]
        for message in request['messages']:
            if message['role']=='assistant':
                for call in message.get('tool_calls',[]):
                    fn=call['function'];calls_by_id[call['id']]={'name':fn['name'],'args':json.loads(fn['arguments'])}
            if message['role']=='tool':
                identifier=message['tool_call_id'];call=calls_by_id[identifier];result=json.loads(message['content'])
                evidence.append({'tool_call_id':identifier,'tool':call['name'],'arguments':call['args'],
                                 'result':result,'lines':observed_lines(call['name'],call['args'],result,snapshot.files)})
        assert len(evidence)==len(audits)
        for e,t in zip(evidence,audits):assert e['tool']==t['tool'] and e['result']==t['result'],'wire_trace_mismatch'
        row={'id':case['id'],'arm':arm,'final_request_hash':last['request_hash'],'raw_response_hash':last['response_hash'],
             'graph_sha256':sha(graph_path),'raw_finish_fields_unchanged':unchanged,
             'finish_reason':response['choices'][0]['finish_reason'],
             'final_response_completion_tokens':response['usage']['completion_tokens'],
             'model_visible_tool_results':len(evidence),'trace_equals_model_input':True,
             'answer':answer,'audit':audit_finish(answer,meta,evidence),'evidence':evidence}
        save(OUT/(case['id']+'-'+arm+'.json'),row);rows.append({k:v for k,v in row.items() if k!='evidence'})
save(OUT/'audit.json',{'rows':rows,'gold_read':False,'new_model_requests':0,'source_result_lock_sha256':sha(LIVE/'result-lock.json'),
                     'purpose':'review leads only; no output repair, ranking change, or metric modification'})
for r in rows:
    omitted=sorted({n for m in r['audit']['mentions'] for n in m['omitted_observed_candidates']})
    unknown=[p['id'] for p in r['audit']['predictions'] if not p['exists_as_definition_id']]
    print(r['id'],r['arm'],'slots',r['audit']['slot_count'],'omitted_seen_mentions',omitted,'nondefinition_ids',unknown)
