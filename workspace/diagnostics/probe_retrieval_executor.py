"""Free native executor checks; explicitly commanded by the analyst, not the model."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,Limits,digest
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.offline import no_network
from experiments.locbench_batch.control import frozen
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'verification/retrieval-choice-hypotheses-v1'
plan=frozen();results=[]
with no_network(OUT/'profiles') as attempts:
 from readonly_agent.openhands_tools import ToolSession,register_readonly_tools,QueryAction
 from openhands.sdk.tool import resolve_tool
 for c in plan['base_manifest']['cases']:
  p=ROOT/c['case_file'];case=json.loads(p.read_text());snapshot=Snapshot(p.parent/'source',case['source_files']);engine=Path(c['plan']['locagent_engine']['root'])
  retriever=LocAgentProcessRetriever(snapshot,python=engine/'.venv/bin/python',engine_root=engine)
  session=ToolSession(snapshot,retriever=retriever,limits=Limits(source_bytes=7434))
  tool=next(t for spec in register_readonly_tools(session) for t in resolve_tool(spec,None) if t.name=='locagent_retrieve')
  query='traceback' if 'loguru' in c['id'] else '_parse_set_item_assignment'
  response=tool(QueryAction(query=query));body=json.loads(response.text)
  assert not response.is_error and session.calls==1 and session.used<=7434
  if 'sqlglot' in c['id']:assert '5977 |' in body['text'] and 'left = self._parse_primary() or self._parse_id_var()' in body['text']
  else:assert body['text']=='No locations found.'
  try:QueryAction(query=case['issue'])
  except ValueError:long_query_rejected=True
  else:raise AssertionError('query_limit_not_enforced')
  schema=tool.to_openai_tool()['function']['parameters']['properties']['query']
  assert schema=={'type':'string'}
  results.append({'case':c['id'],'query':query,'observation':body,'tool_succeeded':True,
   'executor_calls':session.calls,'source_bytes':session.used,'full_issue_rejected_by_action':long_query_rejected,
   'wire_query_schema':schema,'selection':'analyst_requested_connectivity_only_not_autonomous'})
 assert not attempts
record={'native_sdk_tool_checks':results,'new_model_calls':0,'new_cost_cny':0,'network_attempts':len(attempts),
 'target_code_executed':False,'credentials_read':False,'current_plan_hash':digest(plan),'retrieval_strategy_changed':False}
with (OUT/'executor-checks.json').open('x') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k!='observation'} for r in results],ensure_ascii=False))
