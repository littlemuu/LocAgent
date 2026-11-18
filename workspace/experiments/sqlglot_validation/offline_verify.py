"""Fake-key MockTransport only, including new read continuation and failures."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
from readonly_agent.core import digest
from readonly_agent.authority import save_new
from readonly_agent.offline import no_network
from readonly_agent.deepseek_wire import MODEL,OUTPUT,RESPONSE_LIMIT,exchange_offline
from .control import PROJECT,candidate,SuiteAuthority
from .live import execute,worker
FAKE_KEY='SYNTHETIC-SQLGLOT-TEST-NOT-A-CREDENTIAL'
FAULTS=('timeout_first','timeout_second','bad_closing','invalid_finish','truncation','oversized_receipt','worker_second','no_paging')

def runner(fault,counters):
 def run_arm(suite,child,identifier,arm,key):
  if fault=='worker_second' and arm=='baseline':raise TimeoutError('synthetic_worker_stop')
  import httpx
  turn=0
  def exchange(data,provided_key,*,admission,ledger,reservation,enabled):
   nonlocal turn
   turn+=1;assert enabled and provided_key==FAKE_KEY
   ledger.start_transport(reservation,data,admission);counters.append((arm,turn))
   req=json.loads(data);assert req['model']==MODEL and req['max_tokens']==OUTPUT
   assert req['temperature']==0 and req['thinking']=={'type':'disabled'}
   offered={t['function']['name']:t for t in req['tools']}
   if turn<4:
    assert req['tool_choice']=='auto'
    props=offered['read_file']['function']['parameters']['properties']
    assert 'start_line' in props and 'cursor' in props and 'offset' not in props
    assert ('locagent_retrieve' in offered)==(arm=='retrieval')
   else:assert list(offered)==['finish']
   if (fault=='timeout_first' and arm=='retrieval' and turn==1) or (fault=='timeout_second' and arm=='baseline' and turn==1):
    raise TimeoutError('synthetic_unknown_outcome')
   if fault=='oversized_receipt' and arm=='retrieval' and turn==4:
    return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*(RESPONSE_LIMIT+1))))
   if turn==1:name='search_text';args={'query':'_parse_set_item','offset':0}
   elif turn==2:name='read_file';args={'path':'sqlglot/parser.py','start_line':5969,'end_line':5987 if fault=='no_paging' else 6100}
   elif turn==3:
    if fault=='no_paging':name='search_text';args={'query':'SET TAG','offset':0}
    else:
     previous=json.loads(next(m['content'] for m in reversed(req['messages']) if m['role']=='tool'))
     assert previous['start_line']==5969 and previous['next_cursor']
     name='read_file';args={'path':'sqlglot/parser.py','cursor':previous['next_cursor']}
   else:name='finish';args={'message':{'files':[],'entities':[],'answer':'Offline read protocol fixture, no model quality claim.'}}
   if arm=='retrieval' and turn==4:
    if fault=='bad_closing':name='read_file';args={'path':'sqlglot/parser.py','start_line':5969}
    if fault=='invalid_finish':args['message'].pop('entities')
   raw={'id':'synthetic-only','model':MODEL,'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
     'tool_calls':[{'id':f'{arm}-{turn}','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}}],
     'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
   if fault=='truncation' and arm=='retrieval' and turn==4:
    raw['choices'][0]['finish_reason']='length';raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"message":'
   return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,json=raw)))
  with patch('readonly_agent.live_session.exchange_live',side_effect=exchange):
   return worker(suite.authority,suite.hash,identifier,arm,{'suite_token':suite.token,'case_token':child.token,'key':key},alive=lambda:None)
 return run_arm

def verify(output,fault=None):
 output=Path(output).resolve()
 if not output.is_relative_to(PROJECT/'verification'):raise PermissionError('verification_only')
 output.mkdir(mode=0o700,parents=True,exist_ok=False);calls=[]
 with no_network(output/'profiles') as attempts,patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('no_key_read')):
  plan=candidate();h=digest(plan);a=SuiteAuthority(output/'mock-authority')
  a.approve(plan,h,consent=f'APPROVE SQLGLOT {h} CNY 17',currency='CNY',input_ceiling='2',output_ceiling='8',all_charges_included=True)
  result=execute(a.claim(h),FAKE_KEY,runner(fault,calls))
  from .report import write_report
  report=write_report(a,h)
  assert result['requests']==len(calls)<=8 and result['limit_micro_cny']==17_000_000
  success=fault in (None,'no_paging');assert result['status']==('completed' if success else 'halted')
  assert report['simulation'] and report['planned_cases']==1 and report['planned_arms']==2
  assert all(r['localization_score'] is None for r in report['rows'])
  if success:
   assert result['requests']==8 and result['request_pending_micro_cny']==0 and report['completed_arms']==2
   for row in report['rows']:
    r=row['read_protocol'];assert r['full_reference_body_entered_model_context']
    assert all(c['tool_succeeded'] and c['line_evidence_matches_source'] and c['in_immediate_next_model_request'] for c in r['read_calls'])
    assert r['paging_observed']==(fault!='no_paging')
    assert r['paging_protocol_valid']==(True if fault!='no_paging' else None)
    assert row['observability']['retrieval_calls']==0
  if fault in ('timeout_first','timeout_second','oversized_receipt'):assert result['request_pending_micro_cny']==2113536
  if fault=='worker_second':assert result['request_pending_micro_cny']==0 and result['requests']==4
  try:a.claim(h)
  except FileExistsError:pass
  else:raise AssertionError('duplicate_start_allowed')
 assert not attempts
 saved={'fault':fault,'suite_hash':h,'execution_mode':'mocked_live_transport','real_provider_requests':0,'network_attempts':0,
  'result':result,'fake_calls':calls,'duplicate_start_blocked':True,'assertions_passed':True,
  'read_protocol':[r['read_protocol'] for r in report['rows']]}
 save_new(output/'verification.json',saved)
 print(json.dumps({'fault':fault,'status':result['status'],'mock_calls':len(calls),'reason':result['reason'],'real_provider_requests':0}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--fault',choices=FAULTS)
 args=p.parse_args();verify(args.output,args.fault)
