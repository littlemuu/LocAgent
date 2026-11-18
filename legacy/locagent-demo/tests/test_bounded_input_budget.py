"""Offline money/transport contracts; never a real localization quality test."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from locagent_service import public_authorization as auth, deepseek_input_bound as bound, response_store
from locagent_service.deepseek_http import RawHTTP
from test_public_authorization import prepare_grant, raw_response

CONFIG = {'endpoint': 'https://api.deepseek.com/chat/completions', 'model': 'deepseek-flash',
    'response_models': ['deepseek-flash'], 'credential_env': 'NEVER_READ_TEST_KEY',
    'disable_thinking': True, 'currency': 'CNY', 'input_per_million': '2',
    'output_per_million': '8', 'budget': '1', 'context_tokens': 1048576,
    'output_tokens': 1024, 'max_calls': 3, 'request_bytes': 32768, 'timeout_seconds': 60,
    'input_bound': bound.POLICY, 'input_token_cap': 131072,
    'pricing_confirmation': 'OFFLINE TEST: reviewed peak rates; no model call authorized'}

TOOL = {'type':'function','function':{'name':'finish','description':'Submit verified IDs.',
    'parameters':{'type':'object','properties':{'entities':{'type':'array','items':{'type':'string'}}},
                  'required':['entities'],'additionalProperties':False}}}


def response(pt=10, ct=5):
    raw = json.loads(raw_response(pt, ct).body)
    raw['model'] = 'deepseek-flash'
    return RawHTTP(200, json.dumps(raw).encode())


def request():
    return {'messages':[{'role':'system','content':'Locate code with tools.'},
                        {'role':'user','content':'Find unicode decoding.'}], 'tools':[copy.deepcopy(TOOL)]}


class BoundedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bounded-input-')
        root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {'LOCAGENT_SOURCE_ROOT':str(root/'sources'),
            'LOCAGENT_PUBLIC_ROOT':str(root/'sources'), 'LOCAGENT_PUBLIC_AUTH_ROOT':str(root/'authority'),
            'LOCAGENT_PUBLIC_PREVIEW':'1', 'LOCAGENT_PUBLIC_LIVE':'1',
            'LITELLM_LOCAL_MODEL_COST_MAP':'True'})
        self.environment.start()
        self.clock = patch.object(bound, 'utcnow', return_value=datetime(2026,11,1,4,tzinfo=timezone.utc))
        self.clock.start()
        self.transport = patch.object(auth, 'exchange', side_effect=AssertionError('Network forbidden'))
        self.transport.start()
        self.claim = SimpleNamespace(id=uuid4(),token=uuid4())
        self.sent = []

    def tearDown(self):
        self.transport.stop()
        self.clock.stop()
        self.environment.stop()
        self.temp.cleanup()

    def provider(self, config=None, callback=None):
        _, task = prepare_grant(config or CONFIG)
        def send(config, data, capacity):
            self.sent.append(data)
            return callback(config,data,capacity) if callback else response()
        provider = auth.AuthorizedProvider(task,self.claim,lambda _:None,raw_completion=send)
        return provider

    def state(self, provider):
        return auth.read_json(provider.path)

    def test_full_context_default_unchanged_and_three_caps_below_one_yuan(self):
        legacy = dict(CONFIG, input_bound='full-context', input_token_cap=None)
        self.assertEqual(auth.reserve(legacy), auth.money('2.105344'))
        with self.assertRaises(ValueError): auth.ProviderConfig.model_validate(legacy)
        config = auth.ProviderConfig.model_validate(CONFIG).model_dump()
        self.assertEqual(auth.reserve(config), auth.money('0.270336'))
        self.assertEqual(auth.reserve(config)*3, auth.money('0.811008'))

    def test_scope_changes_rejected(self):
        for changes in ({'model':'other'}, {'endpoint':'https://other.example/chat/completions'},
                        {'disable_thinking':False}, {'context_tokens':10000}, {'input_token_cap':131073},
                        {'max_calls':4}, {'request_bytes':32769}, {'output_tokens':1025},
                        {'input_per_million':'1'}, {'budget':'1.01'}, {'currency':'USD'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                auth.ProviderConfig.model_validate(CONFIG | changes)

    def test_unicode_native_tools_and_forced_finish_are_preserved(self):
        value = request()
        value['messages'].extend([
            {'role':'assistant','content':None,'tool_calls':[{'id':'call-1','type':'function','index':0,
                'function':{'name':'search_code_snippets','arguments':json.dumps({'search_terms':['解码😀']})}}]},
            {'role':'tool','tool_call_id':'call-1','content':'def decode():\n    return "中文"'},
            {'role':'user','content':'Finish using the returned evidence.'}])
        value['tool_choice'] = {'type':'function','function':{'name':'finish'}}
        data = auth.request_payload(CONFIG,value)
        self.assertEqual(json.loads(data)['messages'], value['messages'])
        proof = auth.request_proof(CONFIG,data)
        self.assertGreater(proof['prompt_token_upper_bound'],len(data))
        self.assertLessEqual(proof['prompt_token_upper_bound'],CONFIG['input_token_cap'])

    def test_multibyte_wire_limit_rejects_before_transport_and_reservation(self):
        provider = self.provider()
        with self.assertRaises(ValueError):
            provider(messages=[{'role':'user','content':'界'*12000}])
        self.assertEqual(self.sent,[])
        self.assertEqual(self.state(provider)['calls'],[])

    def test_small_wire_large_dsml_expansion_is_rejected(self):
        config = CONFIG | {'input_token_cap':12000}
        provider = self.provider(config)
        value = request()
        value['messages'].append({'role':'assistant','content':None,'tool_calls':[
            {'id':'c','type':'function','function':{'name':'finish',
             'arguments':json.dumps({f'p{i}':'' for i in range(64)})}}]})
        self.assertLess(len(json.dumps(value).encode()),32768)
        with self.assertRaises(ValueError): provider(**value)
        self.assertEqual(self.sent,[])
        self.assertEqual(self.state(provider)['calls'],[])

    def test_images_server_tools_and_unproved_shapes_fail_closed(self):
        cases = [
            {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://example.org/x'}}]}]},
            {'messages':[{'role':'user','content':'<｜deepseek_image｜>'}]},
            request() | {'tools':[{'type':'web_search','name':'search'}]},
            {'messages':[{'role':'user','content':'x','name':'hidden-prefix'}]},
            request() | {'stop':['anything']},
            {'messages':[{'role':'assistant','content':None,'tool_calls':[{'id':'x','type':'function',
                'function':{'name':'finish','arguments':'{"x":[1e15,1e15]}'}}]}]},
            {'messages':[{'role':'assistant','content':None,'tool_calls':[{'id':'x','type':'function',
                'function':{'name':'finish','arguments':'{"x":1,"x":2}'}}]}]},
            {'messages':[{'role':'assistant','content':None,'tool_calls':[{'id':'x','type':'function',
                'function':{'name':'finish','arguments':'"{\\"x\\":1}"'}}]}]},
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError): auth.request_payload(CONFIG,value)

    def test_many_tiny_messages_are_charged_for_wrappers(self):
        value = {'messages':[{'role':'user','content':''} for _ in range(64)]}
        data = auth.request_payload(CONFIG,value)
        proof = auth.request_proof(CONFIG,data)
        self.assertEqual(proof['envelope_units'],64)
        self.assertGreater(proof['prompt_token_upper_bound'],64*512)
        with self.assertRaises(ValueError):
            auth.request_payload(CONFIG,{'messages':value['messages']+[{'role':'user','content':''}]})

    def test_actual_request_is_durable_before_send_and_three_call_limit_is_shared(self):
        def send(config,data,capacity):
            state = self.state(provider)
            call = state['calls'][-1]
            self.assertEqual(state['reserved'],'0.270336')
            self.assertEqual(call['input_proof'],auth.request_proof(config,data))
            self.assertEqual(response_store.read(auth.request_ledger(provider.path),call['index'],call['request_body']),data)
            return response()
        provider = self.provider(callback=send)
        for _ in range(3): provider(**request())
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),3)
        self.assertEqual(len(self.state(provider)['calls']),3)
        self.assertEqual(self.state(provider)['spent'],'0.00018')
        provider.finish()
        with self.assertRaises(ValueError):
            auth.AuthorizedProvider(provider.request,self.claim,lambda _:None,raw_completion=send)

    def test_next_reservation_blocks_when_cumulative_money_would_exceed_budget(self):
        provider = self.provider(CONFIG | {'budget':'0.28'}, lambda *_:response(6000,1024))
        provider(**request())
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.state(provider)['spent'],'0.020192')

    def test_concurrent_attempts_cannot_bypass_shared_budget(self):
        provider = self.provider(CONFIG | {'budget':'0.28'}, lambda *_:response(6000,1024))
        def call(_):
            try: provider(**request()); return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(call,range(5)))
        self.assertEqual(sum(outcomes),1)
        self.assertEqual(len(self.sent),1)

    def test_timeout_keeps_reservation_and_forbids_same_or_new_executor_retry(self):
        def fail(*_): raise TimeoutError('synthetic timeout')
        provider = self.provider(callback=fail)
        with self.assertRaises(TimeoutError): provider(**request())
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),1)
        state = self.state(provider)
        self.assertTrue(state['halted'])
        self.assertEqual(state['reserved'],'0.270336')
        self.assertEqual(state['calls'][0]['status'],'outcome_unknown')
        with self.assertRaises(ValueError):
            auth.AuthorizedProvider(provider.request,self.claim,lambda _:None,raw_completion=fail)

    def test_usage_exceeding_proof_is_unknown_even_if_below_reserved_cap(self):
        def oversized(config,data,_):
            return response(auth.request_proof(config,data)['prompt_token_upper_bound']+1,0)
        provider = self.provider(callback=oversized)
        with self.assertRaises(ValueError): provider(**request())
        self.assertTrue(self.state(provider)['halted'])
        self.assertEqual(self.state(provider)['reserved'],'0.270336')
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),1)

    def test_input_proof_cannot_be_tampered_to_allow_another_call(self):
        provider = self.provider()
        provider(**request())
        state = self.state(provider)
        state['calls'][0]['input_proof']['prompt_token_upper_bound'] += 1
        response_store.save_json(provider.path,state)
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),1)

    def test_actual_request_body_tampering_is_detected(self):
        provider = self.provider()
        provider(**request())
        call = self.state(provider)['calls'][0]
        path = response_store.directory(auth.request_ledger(provider.path))/call['request_body']['file']
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError): provider(**request())
        self.assertEqual(len(self.sent),1)

    def test_request_evidence_write_failure_cannot_send(self):
        provider = self.provider()
        with patch.object(response_store,'persist',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError): provider(**request())
        self.assertEqual(self.sent,[])
        self.assertEqual(self.state(provider)['calls'],[])

    def test_expired_release_cannot_send_but_existing_evidence_remains_auditable(self):
        provider = self.provider()
        provider(**request())
        with patch.object(bound,'utcnow',return_value=bound.VALID_UNTIL):
            with self.assertRaises(ValueError): provider(**request())
            marker,_=auth.grant(provider.request.authorization_id)
            auth.validate_state(provider.path,self.state(provider),marker)
        self.assertEqual(len(self.sent),1)

    def test_changed_cap_cannot_reuse_the_reviewed_plan_hash(self):
        plan,task = prepare_grant(CONFIG)
        changed=copy.deepcopy(plan)
        changed['provider']['input_token_cap']=130000
        with self.assertRaises(ValueError): auth.authorize(changed,task.authorization_id)


    def test_existing_graph_engine_three_round_payloads_fit_without_truncation(self):
        from locagent_service.offline import offline_engine
        with offline_engine():
            import networkx as nx
            from litellm import ModelResponse
            from util.localizer import GraphLocalizer
            from util.localization_contract import LocalizationOptions, LocalizationRequest
            graph=nx.MultiDiGraph()
            code='def render(value):\n    return value'
            graph.add_node('demo.py',type='file',code=code)
            graph.add_node('demo.py:render',type='function',code=code,start_line=1,end_line=2)
            graph.add_edge('demo.py','demo.py:render',type='contains')
            replies=iter([
                ('search_code_snippets',{'search_terms':['demo.py:render']}),
                ('get_entity_contents',{'entity_names':['demo.py:render']}),
                ('finish',{'files':['demo.py'],'entities':['demo.py:render']})])
            proofs=[]
            def provider(**kwargs):
                data=auth.request_payload(CONFIG,kwargs)
                proofs.append(auth.request_proof(CONFIG,data))
                name,args=next(replies)
                return ModelResponse(model='deepseek-flash',choices=[{'index':0,
                    'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                    'tool_calls':[{'id':'call-'+str(len(proofs)),'type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}}]}}],
                    usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15})
            engine=GraphLocalizer.from_graph(graph,provider=provider,model_name='deepseek-flash',
                options=LocalizationOptions(max_iterations=3,search_protocol='bounded-v1'))
            result=engine.localize(LocalizationRequest('demo__demo-1','demo/demo','a'*40,
                'Locate the function that renders a value.'))
            self.assertEqual(len(proofs),3)
            self.assertEqual(result.to_dict()['found_entities'],['demo.py:render'])
            self.assertTrue(all(p['wire_bytes']<=32768 and p['prompt_token_upper_bound']<=131072 for p in proofs))


if __name__=='__main__': unittest.main()
