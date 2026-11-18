"""Regression from the first paid response; all replays are offline."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from readonly_agent.core import Snapshot, digest, encoded, validate_finish
from readonly_agent.deepseek_wire import FinishProtocolError, normalize, payload
from readonly_agent.journal import Ledger
from readonly_agent.live_run import stopped_report
from readonly_agent.offline import no_network
from readonly_agent.preparation import BudgetedWire, make_plan


class FinishContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory()
        cls.guard = no_network(Path(cls.temporary.name)/'profiles')
        cls.guard.__enter__()
        import httpx
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool import FinishTool
        cls.httpx = httpx
        cls.tools = FinishTool.create()
        cls.messages = [Message(role='user', content=[TextContent(text='Find greeting.')])]
        cls.incident = json.loads((Path(__file__).parent/'fixtures/first_live_finish_incident.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None, None, None)
        cls.temporary.cleanup()

    def test_original_response_reproduces_schema_mismatch(self):
        final = self.incident['calls'][-1]
        schema = next(t for t in final['request']['tools'] if t['function']['name']=='finish')
        self.assertEqual(schema['function']['parameters']['properties']['message']['type'], 'string')
        args = json.loads(final['response']['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
        self.assertIsInstance(args['message'], str)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(args['message'])
        with self.assertRaises(FinishProtocolError):
            normalize(final['response'], {'finish'})

    def test_wire_declares_structured_message_without_mutating_sdk_tool(self):
        native = deepcopy(self.tools[0].to_openai_tool())
        wire = json.loads(payload(self.messages, self.tools, closing=True))
        schema = wire['tools'][0]['function']['parameters']['properties']['message']
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(set(schema['required']), {'files','entities','answer'})
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(self.tools[0].to_openai_tool(), native)

    def test_structured_wire_converts_to_native_sdk_finish_without_mutating_receipt(self):
        raw = deepcopy(self.incident['calls'][-1]['response'])
        fn = raw['choices'][0]['message']['tool_calls'][0]['function']
        answer = {'files':['src/greeting.py'],'entities':['src/greeting.py:greeting'], 'answer':'Constructs hello + name.'}
        fn['arguments'] = encoded({'message':answer,'summary':'Submit result'}).decode()
        original = deepcopy(raw)
        response = normalize(raw, {'finish'})
        args = json.loads(response.message.tool_calls[0].arguments)
        self.assertEqual(json.loads(args['message']), answer)
        self.assertEqual(raw, original)
        snapshot = Snapshot(Path(__file__).resolve().parent.parent/'examples/source',['src/greeting.py'])
        self.assertEqual(validate_finish(json.loads(args['message']), snapshot), answer)

    def test_invalid_message_shapes_rejected_without_coercion(self):
        bad = ['prose', '{}', None, [], {},
               {'files':[],'entities':[],'answer':12},
               {'files':['a','a'],'entities':[],'answer':'x'},
               {'files':[1],'entities':[],'answer':'x'},
               {'files':[],'entities':[],'answer':'x','extra':True}]
        for value in bad:
            raw = deepcopy(self.incident['calls'][-1]['response'])
            raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = encoded({'message':value}).decode()
            with self.subTest(value=value), self.assertRaises(FinishProtocolError):
                normalize(raw, {'finish'})

    def test_actual_reply_settles_before_protocol_stop_and_cannot_retry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'code.py').write_text('def greeting(): pass\n')
            plan = make_plan(Snapshot(root, ['code.py']), 'Locate greeting.')
            ledger = Ledger.create(root/'ledger.sqlite', plan)
            wire = BudgetedWire(ledger, 'baseline')
            seen=[]
            def respond(request):
                seen.append(1)
                return self.httpx.Response(200, json=self.incident['calls'][-1]['response'])
            with self.assertRaises(FinishProtocolError):
                wire.generate(self.messages, self.tools, True, self.httpx.MockTransport(respond))
            first = ledger.summary()['reason']
            ledger.halt(None, 'RuntimeError')
            self.assertEqual(ledger.summary()['reason'], first)
            self.assertEqual(ledger.summary()['spent_upper_micro_cny'], 3756)
            self.assertEqual(ledger.summary()['reserved_micro_cny'], 0)
            with self.assertRaises(RuntimeError):
                wire.generate(self.messages, self.tools, True, self.httpx.MockTransport(respond))
            self.assertEqual(seen, [1])

    def test_stop_report_explains_known_cause_without_exception_text(self):
        summary = {'reason':'finish_message_contract_error','calls':[{}, {}, {}],
                   'spent_upper_micro_cny':8236,'reserved_micro_cny':0}
        report = stopped_report(summary)
        self.assertIn('终答格式',report['explanation'])
        self.assertEqual(report['spent_upper_cny'], 0.008236)
        summary['reason']='SYNTHETIC-UNTRUSTED-EXCEPTION-TEXT'
        self.assertNotIn(summary['reason'], encoded(stopped_report(summary)).decode())
