"""Scripted offline wire/tool rehearsal. Never estimates autonomous choice rates."""
import hashlib,json,re,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readonly_agent.core import Snapshot,Limits,encoded,digest
from readonly_agent.authority import save_new
from readonly_agent.offline import no_network
from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.deepseek_wire import exchange_offline,normalize,usage,MODEL
from experiments.sqlglot_validation.control import frozen
ROOT=Path(__file__).resolve().parents[1]
DRAFT=ROOT/'verification/retrieval-choice-state-v1'
OUT=ROOT/'verification/retrieval-choice-pair-offline-v3'
SCENARIOS=['select_retrieval','select_read','finish_now','overlong_query','unknown_tool','truncated','timeout','closed_executor']
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def reply(name,args,finish_reason='tool_calls',identifier='fixture-call'):
 return {'id':'offline-scripted-only','model':MODEL,'choices':[{'index':0,'finish_reason':finish_reason,
  'message':{'role':'assistant','content':None,'tool_calls':[{'id':identifier,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
  'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 before={}
 for ns in ['authority','authority-batches','authority-locbench','authority-sqlglot-validation','readonly_agent','experiments','locbench_openhands','locbench_live','sqlglot_read_validation','verification/retrieval-choice-state-v1']:
  for p in (ROOT/ns).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:before[str(p.relative_to(ROOT))]=sha(p)
 save_new(OUT/'before.json',{'files':before})
 draft=read(DRAFT/'draft-experiment.json');inputs={v:read(DRAFT/f'diagnostic-{v}-request.json') for v in ('control','candidate')}
 for v in inputs:assert sha(DRAFT/f'diagnostic-{v}-request.json')==draft[v+'_sha256']
 stripped=json.loads(json.dumps(inputs['candidate']));stripped['tools'][3]['function']['description']=inputs['control']['tools'][3]['function']['description'];assert stripped==inputs['control']
 p=frozen();h=digest(p);case=p['base_manifest']['cases'][0];cfg=read(ROOT/case['case_file']);base=(ROOT/case['case_file']).parent
 snap=Snapshot(base/cfg['root'],cfg['source_files']);assert dict(snap.hashes)==case['plan']['source_hashes']
 engine=Path(case['plan']['locagent_engine']['root']);labels=read(ROOT/'locbench_openhands/v5/scoring-only/tobymao__sqlglot-3417.json');span=labels['mapping']['gold_mappings'][0]['strict_ast'];lo,hi=span['start_line'],span['end_line']
 results=[];retrieval_processes=[]
 with no_network(OUT/'profiles') as attempts,patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('no_credentials_allowed')):
  import httpx
  from readonly_agent.openhands_tools import ToolSession,register_readonly_tools
  from openhands.sdk.tool import resolve_tool
  for variant,request in inputs.items():
   assert request['tool_choice']=='auto' and request['model']==MODEL and request['max_tokens']==2048 and len(encoded(request))<=65536
   notice=next(m['content'] for m in request['messages'] if m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET'))
   match=re.search(r'available investigation calls: (\d+); available source-result bytes: (\d+)',notice);left_calls,left_bytes=map(int,match.groups())
   assert (left_calls,left_bytes)==(14,12277)
   for scenario in SCENARIOS:
    folder=OUT/variant/scenario;folder.mkdir(parents=True,exist_ok=False)
    class CountingRetriever(LocAgentProcessRetriever):
     def retrieve(self,query):
      retrieval_processes.append({'variant':variant,'scenario':scenario,'query':query});return super().retrieve(query)
    retriever=CountingRetriever(snap,python=engine/'.venv/bin/python',engine_root=engine)
    session=ToolSession(snap,retriever=retriever,limits=Limits(max_requests=4));session.calls=16-left_calls;session.used=14336-left_bytes
    tools={t.name:t for spec in register_readonly_tools(session) for t in resolve_tool(spec,None)}
    for name,tool in tools.items():
     spec=next(t['function'] for t in request['tools'] if t['function']['name']==name)
     tool=tool.model_copy(update={'description':spec['description']});tools[name]=tool
     assert tool.to_openai_tool(add_security_risk_prediction=True)['function']==spec
    if scenario=='closed_executor':session.close_investigation()
    answer={'message':{'files':[],'entities':[],'answer':'Scripted offline plumbing check only; no model quality measurement.'}}
    name,args=('locagent_retrieve',{'query':'_parse_set_item_assignment'})
    if scenario=='select_read':name,args='read_file',{'path':'sqlglot/parser.py','start_line':5969,'end_line':5987}
    elif scenario=='finish_now':name,args='finish',answer
    elif scenario=='overlong_query':args={'query':'x'*257}
    elif scenario=='unknown_tool':name='not_registered'
    raw=reply(name,args,'length' if scenario=='truncated' else 'tool_calls')
    requests=[];status=error=None;delivered=False;coverage=False;observation=None
    def handler(req):
     requests.append(bytes(req.content));assert req.headers['authorization']=='Bearer offline-not-a-key'
     if scenario=='timeout':raise httpx.ReadTimeout('offline synthetic timeout')
     return httpx.Response(200,json=raw if len(requests)==1 else reply('finish',answer,identifier='fixture-finish'))
    try:
     data=encoded(request);(folder/'request-1.json').write_bytes(data)
     receipt=exchange_offline(data,httpx.MockTransport(handler));assert receipt.complete and receipt.status==200
     (folder/'response-1.json').write_bytes(receipt.body)
     response,_=usage(receipt.body);native=normalize(response,[t['function']['name'] for t in request['tools']])
     if name=='finish':status='scripted_finish'
     else:
      call=native.message.tool_calls[0];action=tools[name].action_type.model_validate_json(call.arguments)
      obs=tools[name](action);observation=json.loads(obs.text);save_new(folder/'observation.json',observation)
      if obs.is_error:raise RuntimeError('executor_rejected')
      # Preserve the same real message protocol; append the synthetic result to a second mocked request.
      second=json.loads(json.dumps(request));second['messages']=[m for m in second['messages'] if not (m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET'))]
      second['messages'] += [response['choices'][0]['message'],{'role':'tool','tool_call_id':'fixture-call','content':obs.text}]
      nextnotice=notice.replace('response 2 of 4','response 3 of 4').replace('available investigation calls: 14',f'available investigation calls: {16-session.calls}').replace('available source-result bytes: 12277',f'available source-result bytes: {14336-session.used}').replace('at most 1 further investigation responses','at most 0 further investigation responses')
      second['messages'].append({'role':'user','content':nextnotice})
      data2=encoded(second);assert len(data2)<=65536;(folder/'request-2.json').write_bytes(data2)
      final=exchange_offline(data2,httpx.MockTransport(handler));(folder/'response-2.json').write_bytes(final.body)
      finalraw,_=usage(final.body);assert finalraw['choices'][0]['message']['tool_calls'][0]['id']!='fixture-call';normalize(finalraw,[t['function']['name'] for t in second['tools']]);assert finalraw['choices'][0]['message']['tool_calls'][0]['function']['name']=='finish'
      delivered=any(m.get('role')=='tool' and m.get('tool_call_id')=='fixture-call' and m.get('content')==obs.text for m in json.loads(requests[1])['messages'])
      text=observation['text'];received=set()
      source=snap.files['sqlglot/parser.py'].splitlines()
      for n in range(lo,hi+1):
       if name=='read_file':expected=str(n)+': '+source[n-1];matches=expected in text.splitlines()
       else:
        pattern=r'^\s*'+str(n)+r' \| (.*)$';m=re.search(pattern,text,re.M)
        matches=bool(m and (m[1]==source[n-1] or (n==lo and m[1]==source[n-1].lstrip())))
       if matches:received.add(n)
      coverage=len(received)==hi-lo+1;assert coverage and delivered
      assert session.calls==3 and session.used<=14336 and len(encoded(observation))<=4096
      status='scripted_tool_delivery_and_finish'
    except Exception as exc:
     error=type(exc).__name__;status='stopped'
    success=scenario in ('select_retrieval','select_read','finish_now')
    assert (status!='stopped')==success,(variant,scenario,error)
    assert len(requests)==(2 if scenario in ('select_retrieval','select_read') else 1),(variant,scenario)
    expected_errors={'overlong_query':'ValidationError','unknown_tool':'ToolPolicyError','truncated':'OutputTruncatedError','timeout':'ReadTimeout','closed_executor':'RuntimeError'}
    if not success:assert error==expected_errors[scenario],(variant,scenario,error)
    row={'variant':variant,'scenario':scenario,'status':status,'error':error,'mock_requests':len(requests),
     'selected_by':'scripted_fixture_not_model','autonomous_choice_measured':False,'evidence_delivered_to_next_mock_request':delivered,
     'complete_target_body_verified':coverage,'observation_json_bytes':len(encoded(observation)) if observation else None,
     'starting_remaining_calls':left_calls,'starting_remaining_source_bytes':left_bytes,'ending_calls_used':session.calls,'ending_source_bytes_used':session.used,
     'real_provider_requests':0,'actual_cost_cny':0,'retry':False}
    save_new(folder/'result.json',row);results.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
  assert not attempts
 assert len(retrieval_processes)==2 and all(x['scenario']=='select_retrieval' for x in retrieval_processes)
 assert len(results)==16 and sum(r['mock_requests'] for r in results)==20
 for path,expected in before.items():assert sha(ROOT/path)==expected,path
 assert digest(frozen())==h
 report={'passed':True,'variants':2,'scenarios_per_variant':8,'scenario_runs':16,'mock_http_exchanges':20,
 'native_locagent_queries':retrieval_processes,'network_attempts_parent':len(attempts),'real_provider_requests':0,'actual_cost_cny':0,
 'credentials_read':False,'target_code_executed':False,'production_authorizations_created':False,'historical_files_unchanged':len(before),
 'only_input_difference':'/tools/3/function/description','source_state':'constructed historical checkpoint; 2 prior calls and 2059 evidence bytes carried forward',
 'semantic_answer_quality_measured':False,'model_preference_or_causal_effect_measured':False,'results':results}
 save_new(OUT/'acceptance.json',report)
 print('OFFLINE PAIR ACCEPTED; no real model calls or authorization.')
if __name__=='__main__':main()
