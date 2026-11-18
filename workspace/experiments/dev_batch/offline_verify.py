"""Exercise admitted live code with fake credentials and ONLY MockTransport.

All artifacts must stay below verification/. Never loads .env. The nested
production ledgers say live because the admission path is being tested; the
external report explicitly labels them mocked, not real provider traffic.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from readonly_agent.core import digest, encoded
from readonly_agent.deepseek_wire import MODEL, OUTPUT, RESPONSE_LIMIT, exchange_offline
from readonly_agent.offline import no_network
from readonly_agent.authority import save_new
from .control import candidate, SuiteAuthority, PROJECT
from .live import execute, worker

FAKE_KEY='SYNTHETIC-BATCH-TEST-NOT-A-CREDENTIAL'


def mock_arm_runner(fault=None, counters=None):
    counters=counters if counters is not None else []
    def run_arm(suite,child,identifier,arm,key):
        import httpx
        case_auth=child.authority
        case=json.loads((PROJECT/case_auth.item['case_file']).read_text())
        script=iter(case['scripts'][arm]);turn=0
        def exchange(data,provided_key,*,admission,ledger,reservation,enabled):
            nonlocal turn
            turn+=1
            assert provided_key==FAKE_KEY and enabled is True
            ledger.start_transport(reservation,data,admission)
            counters.append((identifier,arm,turn))
            request=json.loads(data)
            if fault=='historical_length_replay' and identifier=='d01_cache' and arm=='baseline':
                incident=json.loads((PROJECT/'tests_sdk/fixtures/dev_batch_length_incident.json').read_text())
                raw=incident['calls'][turn-1]['response']
                return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,json=raw)))
            if fault=='oversized_receipt' and identifier=='d01_cache' and arm=='baseline' and turn==3:
                return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*(RESPONSE_LIMIT+1))))
            if fault=='timeout_second_arm' and identifier=='d01_cache' and arm=='retrieval' and turn==1:
                raise TimeoutError('synthetic_unknown_outcome')
            response=next(script)
            tool_calls=[]
            for block in response['content']:
                name=block['name'];args=block['input']
                if name=='finish':args={'message':args}
                if fault=='bad_closing_second_arm' and identifier=='d01_cache' and arm=='retrieval' and turn==4:
                    name='read_file';args={'path':case['source_files'][0],'offset':0}
                tool_calls.append({'id':f'{identifier}-{arm}-{turn}-{block["id"]}','type':'function',
                                   'function':{'name':name,'arguments':json.dumps(args)}})
            assert request['model']==MODEL
            raw={'id':'synthetic-batch-response','model':MODEL,
                 'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':tool_calls}}],
                 'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
            if fault in ('actual_truncation_first_arm','truncation_at_new_limit') and identifier=='d01_cache' and arm=='baseline' and turn==4:
                # Historical receipt stays byte-for-byte in its original ledger.
                # Replay only this non-secret fixture through the mock transport.
                raw=json.loads((PROJECT/'tests_sdk/fixtures/dev_batch_truncation_incident.json').read_text())['response']
                if fault=='truncation_at_new_limit':
                    raw['usage']['completion_tokens']=OUTPUT
                    raw['usage']['total_tokens']=raw['usage']['prompt_tokens']+OUTPUT
            return exchange_offline(data,httpx.MockTransport(lambda request:httpx.Response(200,json=raw)))
        with patch('readonly_agent.live_session.exchange_live',side_effect=exchange):
            return worker(suite.authority,suite.hash,identifier,arm,
                          {'suite_token':suite.token,'case_token':child.token,'key':key},alive=lambda:None)
    return run_arm


def verify(output,fault=None):
    output=Path(output).resolve()
    if not output.is_relative_to(PROJECT/'verification'):raise PermissionError('verification_artifacts_only')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    calls=[]
    with no_network(output/'profiles') as attempts:
        plan=candidate();h=digest(plan);authority=SuiteAuthority(output/'mock-authority')
        authority.approve(plan,h,consent=f'APPROVE SUITE {h} CNY 102',currency='CNY',
                          input_ceiling='2',output_ceiling='8',all_charges_included=True)
        result=execute(authority.claim(h),FAKE_KEY,mock_arm_runner(fault,calls))
        from .report import write_report
        measurements=write_report(authority,h)
        assert measurements['simulation'] and all(r['localization_score'] is None for r in measurements['rows'])
    report={'mode':'mocked_live_transport','fault':fault,'suite_hash':h,
            'real_provider_requests':0,'network_attempts':len(attempts),'fake_transport_calls':len(calls),
            'calls':calls,'result':result,'credential':'synthetic literal only; no .env read'}
    save_new(output/'verification.json',report)
    print(json.dumps({'mode':report['mode'],'fault':fault,'status':result['status'],
                     'fake_transport_calls':len(calls),'real_provider_requests':0,'reason':result.get('reason')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fault',choices=['timeout_second_arm','bad_closing_second_arm',
                                         'actual_truncation_first_arm','truncation_at_new_limit',
                                         'historical_length_replay','oversized_receipt'])
    args=parser.parse_args();verify(args.output,args.fault)
