"""Offline controller/SDK/ledger boundary tests, including the real failure."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from readonly_agent.control import CLOSING_INSTRUCTION, budget_notice
from readonly_agent.core import Snapshot, encoded
from readonly_agent.deepseek_wire import (ClosingToolPolicyError, ClosingFinishMissingError,
    FinishProtocolError, OutputTruncatedError, normalize, payload)
from readonly_agent.journal import Ledger
from readonly_agent.live_run import stopped_report
from readonly_agent.offline import no_network
from readonly_agent.preparation import BudgetedWire, make_plan


class ClosingControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.guard=no_network(Path(cls.temp.name)/'profiles')
        cls.guard.__enter__()
        import httpx
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.llm.message import MessageToolCall
        from openhands.sdk.tool import FinishTool
        from readonly_agent.openhands_tools import ToolSession
        cls.httpx,cls.Message,cls.TextContent,cls.MessageToolCall=httpx,Message,TextContent,MessageToolCall
        cls.ToolSession=ToolSession
        cls.tools=FinishTool.create()
        cls.original=json.loads((Path(__file__).parent/'fixtures/crossfile_closing_incident.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None,None,None)
        cls.temp.cleanup()

    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        (self.root/'code.py').write_text('def hello(): return "hello"\n')
        self.snapshot=Snapshot(self.root,['code.py'])
        self.messages=[self.Message(role='user',content=[self.TextContent(text='Locate hello.')])]

    def historic_messages(self):
        result=[]
        names={c['id']:c['function']['name'] for item in self.original['request']['messages']
               for c in item.get('tool_calls',[])}
        for item in self.original['request']['messages']:
            kwargs={'role':item['role'],'content':[self.TextContent(text=item['content'])] if item.get('content') else []}
            if item.get('tool_call_id'):
                kwargs['tool_call_id']=item['tool_call_id']
                kwargs['name']=names[item['tool_call_id']]
            if item.get('tool_calls'):
                kwargs['tool_calls']=[self.MessageToolCall(id=c['id'],name=c['function']['name'],
                    arguments=c['function']['arguments'],origin='completion') for c in item['tool_calls']]
            result.append(self.Message(**kwargs))
        return result

    def test_real_failure_is_distinguished_from_finish_json_error(self):
        self.assertEqual(self.original['request']['tool_choice']['function']['name'],'finish')
        self.assertEqual(self.original['request']['messages'][-1]['role'],'tool')
        with self.assertRaises(ClosingToolPolicyError):
            normalize(self.original['response'],{'finish'},closing=True)

    def test_wire_fallback_notice_follows_tool_results_without_rewriting_them(self):
        messages=self.historic_messages()
        before=[m.model_dump(mode='json') for m in messages]
        value=json.loads(payload(messages,self.tools,closing=True))
        self.assertEqual(value['messages'][:-1],self.original['request']['messages'])
        self.assertEqual(value['messages'][-1],{'role':'user','content':CLOSING_INSTRUCTION})
        self.assertEqual(before,[m.model_dump(mode='json') for m in messages])
        self.assertEqual([t['function']['name'] for t in value['tools']],['finish'])

    def test_notice_exposes_budget_and_reserves_last_response(self):
        text=budget_notice(turn=3,maximum=4,tool_calls_left=6,source_bytes_left=11017,closing=False)
        self.assertIn('response 3 of 4',text)
        self.assertIn('at most 0 further investigation responses',text)
        self.assertIn('Tool selection is your choice',text)
        last=budget_notice(turn=4,maximum=4,tool_calls_left=6,source_bytes_left=11017,closing=True,reason='request_limit')
        self.assertIn('available investigation calls: 0',last)
        self.assertIn('available source-result bytes: 0',last)
        self.assertTrue(last.endswith(CLOSING_INSTRUCTION))
        with self.assertRaises(ValueError):
            budget_notice(turn=5,maximum=4,tool_calls_left=1,source_bytes_left=10,closing=False)

    def test_closing_notice_not_duplicated_in_outbound_request(self):
        text=budget_notice(turn=4,maximum=4,tool_calls_left=6,source_bytes_left=11017,closing=True)
        messages=self.messages+[self.Message(role='user',content=[self.TextContent(text=text)])]
        value=json.loads(payload(messages,self.tools,closing=True))
        self.assertEqual(sum(CLOSING_INSTRUCTION in (m.get('content') or '') for m in value['messages']),1)

    def test_closed_executor_does_not_render_any_more_source(self):
        session=self.ToolSession(self.snapshot)
        session.close_investigation()
        session.close_investigation()
        with patch.object(session.tools,'respond',side_effect=AssertionError('must not read')) as render:
            observation=session.execute('read_file',{'path':'code.py','start_line':1})
            render.assert_not_called()
        self.assertTrue(observation.is_error)
        self.assertEqual(session.calls,0)
        self.assertEqual(session.used,0)

    def test_closing_failures_remain_settled_stop_and_never_retry(self):
        failures=[]
        original=deepcopy(self.original['response'])
        failures.append((original,ClosingToolPolicyError,'closing_tool_violation'))
        missing=deepcopy(original)
        missing['choices'][0]['finish_reason']='stop'
        missing['choices'][0]['message']={'role':'assistant','content':'I would read more.'}
        failures.append((missing,ClosingFinishMissingError,'closing_finish_missing'))
        truncated=deepcopy(original)
        truncated['choices'][0]['finish_reason']='length'
        failures.append((truncated,OutputTruncatedError,'model_output_truncated'))
        malformed=deepcopy(original)
        malformed['choices'][0]['message']['tool_calls']=[{'id':'f1','type':'function',
            'function':{'name':'finish','arguments':'{"message":{}}'}}]
        failures.append((malformed,FinishProtocolError,'finish_message_contract_error'))
        for index,(body,error_type,code) in enumerate(failures):
            with self.subTest(code=code):
                ledger=Ledger.create(self.root/f'{index}.sqlite',make_plan(self.snapshot,'Locate hello.'))
                wire=BudgetedWire(ledger,'baseline')
                seen=[]
                def handler(request):
                    seen.append(1)
                    return self.httpx.Response(200,json=body)
                with self.assertRaises(error_type):
                    wire.generate(self.messages,self.tools,True,self.httpx.MockTransport(handler))
                state=ledger.summary()
                self.assertEqual(state['reason'],code)
                self.assertEqual(state['reserved_micro_cny'],0)
                self.assertEqual(state['calls'][0]['status'],'settled')
                with self.assertRaises(RuntimeError):
                    wire.generate(self.messages,self.tools,True,self.httpx.MockTransport(handler))
                self.assertEqual(seen,[1])

    def test_notice_bytes_count_before_reservation_and_network(self):
        ledger=Ledger.create(self.root/'size.sqlite',make_plan(self.snapshot,'Locate hello.'))
        wire=BudgetedWire(ledger,'baseline')
        big=[self.Message(role='user',content=[self.TextContent(text='x'*65536)])]
        seen=[]
        with self.assertRaises(ValueError):
            wire.generate(big,self.tools,True,self.httpx.MockTransport(lambda r:seen.append(r)))
        self.assertEqual(seen,[])
        self.assertEqual(ledger.summary()['calls'],[])

    def test_incomplete_history_cannot_be_hidden_by_closing_notice(self):
        orphan=self.Message(role='tool',name='read_file',tool_call_id='missing',content=[self.TextContent(text='source')])
        with self.assertRaises(ValueError):
            payload([orphan],self.tools,closing=True)

    def test_stop_report_explains_closing_boundary(self):
        report=stopped_report({'reason':'closing_tool_violation','calls':[{}]*4,
            'spent_upper_micro_cny':18574,'reserved_micro_cny':0})
        self.assertIn('收尾轮',report['explanation'])
        self.assertIn('工具未执行',report['explanation'])
        self.assertEqual(report['spent_upper_cny'],0.018574)
