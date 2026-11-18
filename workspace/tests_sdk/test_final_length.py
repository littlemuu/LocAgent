"""Historical truncation, bounded finish and transport/budget regression; no network."""
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from readonly_agent.control import MAX_RESPONSE_BYTES, MAX_OUTPUT_TOKENS, CLOSING_INSTRUCTION
from readonly_agent.core import Snapshot, Limits, encoded, validate_finish
from readonly_agent.deepseek_wire import (OUTPUT, RESERVATION, FinishProtocolError,
    OutputTruncatedError, RESPONSE_LIMIT, exchange_offline, normalize, payload, structured_finish, usage)
from readonly_agent.journal import Ledger
from readonly_agent.preparation import BudgetedWire, make_plan
from readonly_agent.offline import no_network


class FinalLengthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.root=Path(cls.tmp.name).resolve()
        cls.guard=no_network(cls.root/'profiles');cls.attempts=cls.guard.__enter__()
        import httpx
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool import FinishTool
        cls.httpx=httpx;cls.tools=FinishTool.create()
        cls.messages=[Message(role='user',content=[TextContent(text='Explain code with evidence.')])]
        cls.incident=json.loads((Path(__file__).parent/'fixtures/dev_batch_truncation_incident.json').read_text())
        (cls.root/'code.py').write_text('def hello(): return "hello"\n')
        cls.snapshot=Snapshot(cls.root,['code.py'])

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None,None,None);cls.tmp.cleanup()

    def test_real_receipt_confirms_truncation_not_wrong_tool(self):
        q,r=self.incident['request'],self.incident['response']
        self.assertEqual(q['max_tokens'],1024)
        self.assertEqual(q['tools'][0]['function']['parameters']['properties']['message']['properties']['answer']['maxLength'],4096)
        self.assertEqual(q['tool_choice']['function']['name'],'finish')
        fn=r['choices'][0]['message']['tool_calls'][0]['function']
        self.assertEqual(fn['name'],'finish')
        self.assertEqual(r['choices'][0]['finish_reason'],'length')
        self.assertEqual(r['usage']['completion_tokens'],1024)
        with self.assertRaises(json.JSONDecodeError):json.loads(fn['arguments'])
        with self.assertRaises(OutputTruncatedError):normalize(r,{'finish'},closing=True)

    def test_schema_system_closing_and_budget_agree(self):
        from readonly_agent.openhands_replay import SDK_SYSTEM
        for closing in (False,True):
            q=json.loads(payload(self.messages,self.tools,closing=closing))
            self.assertEqual(q['max_tokens'],2048)
            schema=q['tools'][0]['function']['parameters']['properties']['message']
            self.assertNotIn('maxLength',schema['properties']['answer'])
        self.assertIn('1200 characters',SDK_SYSTEM)
        self.assertIn('style target, not a hard limit',SDK_SYSTEM)
        self.assertIn('2048 output tokens',CLOSING_INSTRUCTION)
        self.assertEqual(Limits().response_bytes,RESPONSE_LIMIT)
        self.assertEqual(RESPONSE_LIMIT,MAX_RESPONSE_BYTES)
        self.assertEqual(Limits().max_output_tokens,OUTPUT)
        self.assertEqual(OUTPUT,MAX_OUTPUT_TOKENS)
        self.assertEqual(RESERVATION,2_113_536)
        self.assertEqual(RESERVATION*48,101_449_728)
        self.assertLessEqual(RESERVATION*8,17_000_000)
        self.assertLessEqual(RESERVATION*48,102_000_000)

    def test_bounded_unicode_answer_roundtrips_without_coercion(self):
        # Character count is not a token estimate. This checks format/validation.
        for text in ('x'*1200,'x'*1201,'x'*1527,'x'*5000,'证'*5000,('"\\\n'*1600)):
            value={'files':['code.py'],'entities':['code.py:hello'],'answer':text}
            self.assertEqual(structured_finish(value),value)
            self.assertEqual(validate_finish(value,self.snapshot),value)
            raw=deepcopy(self.incident['response']);raw['choices'][0]['finish_reason']='tool_calls'
            raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']=encoded({'message':value}).decode()
            out=normalize(raw,{'finish'},closing=True)
            self.assertEqual(json.loads(json.loads(out.message.tool_calls[0].arguments)['message']),value)

    def test_historical_complete_reply_preserved_exactly(self):
        incident=json.loads((Path(__file__).parent/'fixtures/dev_batch_length_incident.json').read_text())
        raw=incident['calls'][-1]['response'];before=deepcopy(raw)
        expected=json.loads(raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['message']
        self.assertEqual(len(expected['answer']),1527)
        self.assertEqual(raw['usage']['completion_tokens'],542)
        out=normalize(raw,{'finish'},closing=False)
        actual=json.loads(json.loads(out.message.tool_calls[0].arguments)['message'])
        self.assertEqual(actual,expected)
        self.assertEqual(raw,before)

    def test_actual_and_new_cap_truncation_settle_then_block_retry(self):
        for tokens in (1024,OUTPUT):
            ledger=Ledger.create(self.root/f'truncated-{tokens}.sqlite',make_plan(self.snapshot,'Explain hello.'))
            wire=BudgetedWire(ledger,'baseline');raw=deepcopy(self.incident['response'])
            raw['usage']['completion_tokens']=tokens
            raw['usage']['total_tokens']=raw['usage']['prompt_tokens']+tokens
            seen=[]
            def response(request):
                seen.append(1);return self.httpx.Response(200,json=raw)
            transport=self.httpx.MockTransport(response)
            with self.assertRaises(OutputTruncatedError):wire.generate(self.messages,self.tools,True,transport)
            state=ledger.summary()
            self.assertEqual(state['reason'],'model_output_truncated')
            self.assertEqual(state['reserved_micro_cny'],0)
            self.assertEqual(state['spent_upper_micro_cny'],raw['usage']['prompt_tokens']*2+tokens*8)
            with self.assertRaises(RuntimeError):wire.generate(self.messages,self.tools,True,transport)
            self.assertEqual(len(seen),1)

    def test_answer_above_style_target_is_accepted_with_settled_cost(self):
        ledger=Ledger.create(self.root/'long-answer.sqlite',make_plan(self.snapshot,'Explain hello.'))
        wire=BudgetedWire(ledger,'baseline');raw=deepcopy(self.incident['response'])
        raw['choices'][0]['finish_reason']='tool_calls'
        raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']=encoded(
            {'message':{'files':[],'entities':[],'answer':'x'*1201}}).decode()
        out=wire.generate(self.messages,self.tools,True,self.httpx.MockTransport(lambda r:self.httpx.Response(200,json=raw)))
        self.assertEqual(json.loads(json.loads(out.message.tool_calls[0].arguments)['message'])['answer'],'x'*1201)
        self.assertFalse(ledger.summary()['halted'])
        self.assertEqual(ledger.summary()['spent_upper_micro_cny'],12660)
        self.assertEqual(ledger.summary()['reserved_micro_cny'],0)

    def test_raw_byte_limit_exact_boundary_and_oversize_stops_without_retry(self):
        # Byte cap limits the entire untrusted HTTP receipt, not answer prose.
        for size in (RESPONSE_LIMIT,RESPONSE_LIMIT+1):
            raw=exchange_offline(b'{}',self.httpx.MockTransport(lambda r:self.httpx.Response(200,content=b'x'*size)))
            self.assertEqual(len(raw.body),RESPONSE_LIMIT)
            self.assertEqual(raw.complete,size==RESPONSE_LIMIT)
        ledger=Ledger.create(self.root/'oversized.sqlite',make_plan(self.snapshot,'Explain hello.'))
        wire=BudgetedWire(ledger,'baseline');seen=[]
        def respond(request):
            seen.append(1);return self.httpx.Response(200,content=b'x'*(RESPONSE_LIMIT+1))
        transport=self.httpx.MockTransport(respond)
        with self.assertRaises(RuntimeError):wire.generate(self.messages,self.tools,True,transport)
        state=ledger.summary()
        self.assertTrue(state['halted'])
        self.assertEqual(state['reserved_micro_cny'],RESERVATION)
        self.assertEqual(state['spent_upper_micro_cny'],0)
        self.assertEqual(state['calls'][0]['status'],'unknown')
        with self.assertRaises(RuntimeError):wire.generate(self.messages,self.tools,True,transport)
        self.assertEqual(seen,[1])

    def test_usage_above_new_cap_is_not_silently_settled(self):
        raw=deepcopy(self.incident['response'])
        raw['usage']['completion_tokens']=OUTPUT+1
        raw['usage']['total_tokens']=raw['usage']['prompt_tokens']+OUTPUT+1
        with self.assertRaises(ValueError):usage(encoded(raw))

    def test_isolated_http_helper_accepts_exact_new_cap_only(self):
        # Exercise the actual helper entry with a synthetic pipe and mocked HTTP.
        from readonly_agent import transport_worker
        q=json.loads(payload(self.messages,self.tools,closing=True))
        fake=MagicMock();fake.__enter__.return_value=fake
        response=MagicMock();response.status_code=200;response.iter_bytes.return_value=iter([b'{}'])
        fake.stream.return_value.__enter__.return_value=response
        for cap in (2048,1024,2049):
            q['max_tokens']=cap
            stdin=SimpleNamespace(buffer=io.BytesIO(encoded({'body':encoded(q).decode(),'key':'synthetic-nonsecret-key'})))
            with patch.object(transport_worker.sys,'stdin',stdin), patch.object(transport_worker.sys,'stdout',io.StringIO()), \
                 patch('httpx.Client',return_value=fake) as client, patch('httpx.HTTPTransport'):
                if cap==2048:
                    transport_worker.main();client.assert_called_once()
                else:
                    with self.assertRaisesRegex(ValueError,'fixed_payload_required'):transport_worker.main()
                    client.assert_not_called()

    def test_historical_suite_cannot_restart_or_read_key_after_code_change(self):
        from experiments.dev_batch.live import run
        for old in ('d172860ae92d532c0ff60d6eded56b2d11de63a7672737076611c8be8610badb',
                    '4958a23e559dd53269cb04cebfb00cb5c1d73d527c29baf2fb6cc0fb0fc5dffd'):
            with patch('readonly_agent.local_env.load_selected_key') as key:
                with self.assertRaises(PermissionError):run(old,live=True,env_api_key=True)
                key.assert_not_called()


if __name__=='__main__':unittest.main()
