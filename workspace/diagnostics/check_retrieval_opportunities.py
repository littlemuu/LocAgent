"""Read-only audit of observed opportunities and counterfactual byte capacity.

No model is called; candidate responses are cached results of previously verified
unchanged retrieval code. Feasibility is not evidence of autonomous selection.
"""
import hashlib,json,re,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import encoded,digest,page
from experiments.locbench_batch.control import frozen
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/retrieval-choice-hypotheses-v1'
run=ROOT/'authority-locbench/eeebe42c29508f99b293b48b194a401b8438226d8dff6d8ffe20d2362657ae83/run'
g=json.loads((run.parent/'grant.json').read_text());records=[]
for c in g['plan']['base_manifest']['cases']:
 p=run/'children'/c['plan_hash']/'run/ledger.sqlite'
 probe_root=ROOT/'verification/locbench-offline-diagnosis-v1'/c['id'];probes=json.loads((probe_root/'results.json').read_text())
 query='_parse_set_item_assignment' if 'sqlglot' in c['id'] else '_format_list'
 probe=next(x for x in probes['queries'] if x['query']==query)['locagent_retrieve']
 raw=(probe_root/probe['raw_file']).read_text();assert hashlib.sha256(raw.encode()).hexdigest()==probe['raw_sha256']
 evidence=page(raw,0,4096);packet_bytes=len(encoded(evidence))
 with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
  for arm,turn,request,response in db.execute('SELECT arm,turn,request,response FROM calls ORDER BY id'):
   req=json.loads(request);resp=json.loads(response);tools=req['tools'];names=[x['function']['name'] for x in tools]
   notice=next(m['content'] for m in req['messages'] if m['role']=='user' and isinstance(m['content'],str) and m['content'].startswith('CONTROLLER BUDGET'))
   m=re.search(r'available investigation calls: (\d+); available source-result bytes: (\d+)',notice);assert m
   left_calls,left_bytes=map(int,m.groups());texts=[m['content'] for m in req['messages'] if m['role']=='tool']
   symbol_already_delivered=any(query in t for t in texts)
   called=[x['function']['name'] for x in resp['choices'][0]['message'].get('tool_calls',[])]
   assert 'locagent_retrieve' not in called
   offered=next((t for t in tools if t['function']['name']=='locagent_retrieve'),None)
   if arm=='retrieval' and turn<4:
    assert offered and req['tool_choice']=='auto'
    qschema=offered['function']['parameters']['properties']['query'];assert qschema['type']=='string'
    assert 1<=len(query)<=256
   if turn==4:assert names==['finish'] and left_calls==left_bytes==0
   records.append({'case':c['id'],'arm':arm,'turn':turn,'tool_order':names,'tool_choice':req['tool_choice'],
    'remaining_tool_calls':left_calls,'remaining_source_bytes':left_bytes,'actual_tools':called,
    'candidate_query':query,'candidate_from_prior_tool_evidence':symbol_already_delivered,
    'candidate_origin':'observed_symbol' if symbol_already_delivered else 'oracle_only_not_yet_observed',
    'candidate_full_packet_bytes':packet_bytes,'candidate_fits_source_budget':packet_bytes<=left_bytes,
    'hypothetical_slot_available':offered is not None and req['tool_choice']=='auto' and left_calls>=1 and packet_bytes<=left_bytes,
    'retrieval_query_wire_schema':offered['function']['parameters']['properties']['query'] if offered else None,
    'retrieval_description':offered['function']['description'] if offered else None,
    'read_description':next((t['function']['description'] for t in tools if t['function']['name']=='read_file'),None)})
actual_opportunities=[r for r in records if r['arm']=='retrieval' and r['turn']<4]
assert len(actual_opportunities)==6 and all(r['hypothetical_slot_available'] for r in actual_opportunities)
sql=[r for r in actual_opportunities if 'sqlglot' in r['case'] and r['candidate_from_prior_tool_evidence']]
assert [r['turn'] for r in sql]==[2,3]
assert not any(r['candidate_from_prior_tool_evidence'] for r in actual_opportunities if 'loguru' in r['case'])
report={'model_calls':0,'cost_cny':0,'feasibility_not_model_choice':True,'existing_query_outputs_reused':True,
 'retrieval_opportunities':6,'known_sqlglot_symbol_feasible_at_turns':[2,3],
 'loguru_oracle_never_delivered':True,'records':records,'current_plan_hash':digest(frozen())}
with (OUT/'opportunities.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
for r in actual_opportunities:print(json.dumps({k:v for k,v in r.items() if k not in ('read_description','retrieval_description')},ensure_ascii=False))
