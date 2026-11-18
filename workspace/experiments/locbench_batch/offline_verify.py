"""Exercise the live admission path with a fake credential and MockTransport only.

Only writes below verification/. Never reads .env. Inner ledgers use the live
schema to test that path, while outer execution reports explicitly mark mocks.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from readonly_agent.core import digest
from readonly_agent.deepseek_wire import MODEL, OUTPUT, RESPONSE_LIMIT, exchange_offline
from readonly_agent.offline import no_network
from readonly_agent.authority import save_new
from .control import candidate, SuiteAuthority, PROJECT
from .live import execute, worker

FAKE_KEY='SYNTHETIC-LOCBENCH-TEST-NOT-A-CREDENTIAL'
FIRST='Delgan__loguru-1239'
SECOND='tobymao__sqlglot-3417'
FAULTS=('timeout_second_arm','bad_closing_second_arm','truncation_first_arm',
        'invalid_finish','missing_finish','oversized_receipt','timeout_second_case',
        'historical_sqlglot_replay','nonnull_extension','unknown_null_extension','missing_required')


def mock_arm_runner(fault=None,counters=None):
    counters=counters if counters is not None else []
    def run_arm(suite,child,identifier,arm,key):
        import httpx
        case=json.loads((PROJECT/child.authority.item['case_file']).read_text())
        script=iter(case['scripts'][arm]);turn=0
        def exchange(data,provided_key,*,admission,ledger,reservation,enabled):
            nonlocal turn
            turn+=1
            assert provided_key==FAKE_KEY and enabled is True
            ledger.start_transport(reservation,data,admission)
            counters.append((identifier,arm,turn))
            request=json.loads(data)
            assert request['model']==MODEL and request['max_tokens']==OUTPUT
            assert request['thinking']=={'type':'disabled'} and request['temperature']==0
            if turn==4:
                assert [t['function']['name'] for t in request['tools']]==['finish']
            else:
                assert request['tool_choice']=='auto'
            if fault=='historical_sqlglot_replay' and identifier==SECOND and arm=='retrieval':
                fixture=json.loads((PROJECT/'tests_sdk/fixtures/locbench_extra_field_incident.json').read_text())
                saved=fixture['calls'][turn-1]
                body=base64.b64decode(saved['response_base64'],validate=True)
                assert hashlib.sha256(body).hexdigest()==saved['response_sha256']
                return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,content=body)))
            if ((fault=='timeout_second_arm' and identifier==FIRST and arm=='retrieval' and turn==1)
                    or (fault=='timeout_second_case' and identifier==SECOND and turn==1)):
                raise TimeoutError('synthetic_unknown_outcome')
            if fault=='oversized_receipt' and identifier==FIRST and arm=='baseline' and turn==3:
                return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*(RESPONSE_LIMIT+1))))
            response=next(script)
            calls=[]
            for block in response['content']:
                name=block['name'];args=block['input']
                if name=='finish':args={'message':args}
                if fault=='bad_closing_second_arm' and identifier==FIRST and arm=='retrieval' and turn==4:
                    name='read_file';args={'path':case['source_files'][0],'offset':0}
                if fault=='invalid_finish' and identifier==FIRST and arm=='baseline' and turn==4:
                    args={'message':{'files':['outside.py'],'entities':[],'answer':'Synthetic invalid location.'}}
                if identifier==FIRST and arm=='baseline' and turn==4:
                    if fault=='nonnull_extension':args['message']['entities_note']='Preserve this information; do not silently discard.'
                    if fault=='unknown_null_extension':args['message']['instructions']=None
                    if fault=='missing_required':args['message'].pop('entities')
                calls.append({'id':f'{identifier}-{arm}-{turn}-{block["id"]}','type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}})
            raw={'id':'synthetic-locbench-response','model':MODEL,
                'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':calls}}],
                'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}
            if fault=='truncation_first_arm' and identifier==FIRST and arm=='baseline' and turn==4:
                raw['choices'][0]['finish_reason']='length'
                raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{"message":'
                raw['usage'].update(completion_tokens=OUTPUT,total_tokens=1000+OUTPUT)
            if fault=='missing_finish' and identifier==FIRST and arm=='baseline' and turn==4:
                raw['choices'][0].update(finish_reason='stop',message={'role':'assistant','content':'No structured finish.'})
            return exchange_offline(data,httpx.MockTransport(lambda r:httpx.Response(200,json=raw)))
        with patch('readonly_agent.live_session.exchange_live',side_effect=exchange):
            return worker(suite.authority,suite.hash,identifier,arm,
                {'suite_token':suite.token,'case_token':child.token,'key':key},alive=lambda:None)
    return run_arm


def verify(output,fault=None):
    output=Path(output).resolve()
    if not output.is_relative_to(PROJECT/'verification'):
        raise PermissionError('verification_artifacts_only')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    calls=[]
    with no_network(output/'profiles') as attempts, \
         patch('readonly_agent.local_env.load_selected_key',side_effect=AssertionError('no_credentials_in_offline_verification')):
        plan=candidate();h=digest(plan);authority=SuiteAuthority(output/'mock-authority')
        authority.approve(plan,h,consent=f'APPROVE LOCBENCH {h} CNY 34',currency='CNY',
            input_ceiling='2',output_ceiling='8',all_charges_included=True)
        result=execute(authority.claim(h),FAKE_KEY,mock_arm_runner(fault,calls))
        from .report import write_report
        measurements=write_report(authority,h)
        assert measurements['simulation'] and all(r['localization_score'] is None for r in measurements['rows'])
        success=fault in (None,'historical_sqlglot_replay')
        assert result['status']==('completed' if success else 'halted')
        assert len(calls)==result['requests'] and len(set(calls))==len(calls)
        assert result['requests']<=16 and result['limit_micro_cny']==34_000_000
        if fault and fault.startswith('timeout_'):
            assert result['request_pending_micro_cny']==2_113_536
        if success:
            assert result['requests']==16 and result['case_budget_hold_micro_cny']==0
            assert result['request_pending_micro_cny']==0 and measurements['completed_arms']==4
        if fault=='historical_sqlglot_replay':
            item=next(c for c in plan['base_manifest']['cases'] if c['id']==SECOND)
            pair=Path(authority.read(h,fresh=False)['run_dir'])/'children'/item['plan_hash']/'run'
            trace=[json.loads(line) for line in (pair/'retrieval/trace.jsonl').read_text().splitlines()]
            events=[e for e in trace if e['event']=='finish_normalization']
            assert len(events)==1 and events[0]['canonicalized_null_fields']==['entities_note']
            import sqlite3
            fixture=json.loads((PROJECT/'tests_sdk/fixtures/locbench_extra_field_incident.json').read_text())
            with sqlite3.connect((pair/'ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
                receipts=db.execute('SELECT response,response_hash FROM calls WHERE arm=? ORDER BY turn',('retrieval',)).fetchall()
            assert len(receipts)==4
            for (body,sha),saved in zip(receipts,fixture['calls']):
                assert body==base64.b64decode(saved['response_base64']) and sha==saved['response_sha256']
            canonical=json.loads((pair/'retrieval/result.json').read_text())['answer']
            original=json.loads(fixture['calls'][-1]['response']['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['message']
            assert canonical=={k:original[k] for k in ('files','entities','answer')}
        try:authority.claim(h)
        except FileExistsError:pass
        else:raise AssertionError('duplicate_claim_not_blocked')
    report={'mode':'mocked_live_transport','fault':fault,'suite_hash':h,'real_provider_requests':0,
        'network_attempts':len(attempts),'fake_transport_calls':len(calls),'calls':calls,'result':result,
        'credential':'synthetic literal only; .env loader replaced with failing stub',
        'duplicate_claim_blocked':True,'assertions_passed':True}
    assert not attempts
    save_new(output/'verification.json',report)
    print(json.dumps({'fault':fault,'status':result['status'],'fake_transport_calls':len(calls),
        'real_provider_requests':0,'reason':result.get('reason')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fault',choices=FAULTS)
    args=parser.parse_args();verify(args.output,args.fault)
