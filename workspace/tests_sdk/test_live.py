import base64
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from readonly_agent.authority import Authority, now
from readonly_agent.core import Limits, Snapshot, digest, encoded
from readonly_agent.deepseek_wire import MODEL, RESERVATION, payload
from readonly_agent.journal import Ledger
from readonly_agent.live_run import parent_alive, run_pair
from readonly_agent.live_session import LiveSession
from readonly_agent.live_transport import exchange_live
from readonly_agent.offline import no_network
from readonly_agent.preparation import BudgetedWire, make_plan

FAKE_KEY = 'SYNTHETIC-TEST-NOT-A-CREDENTIAL'


class LiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard_dir = TemporaryDirectory()
        cls.guard = no_network(Path(cls.guard_dir.name)/'profiles')
        cls.guard.__enter__()
        import httpx
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool import FinishTool
        cls.httpx, cls.Message, cls.TextContent = httpx, Message, TextContent
        cls.finish_tools = FinishTool.create()

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None, None, None)
        cls.guard_dir.cleanup()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'code.py').write_text('def hello():\n    return "hello"\n')
        engine = self.root/'engine'
        (engine/'evaluation').mkdir(parents=True)
        (engine/'evaluation/eval_metric.py').write_text('# reviewed synthetic engine fixture\n')
        self.snapshot = Snapshot(self.root, ['code.py'])
        self.plan = make_plan(self.snapshot, 'Find hello.', engine)
        self.authority = Authority(self.root/'authority')
        self.plan_hash = digest(self.plan)
        self.confirm = dict(currency='CNY', input_ceiling='2', output_ceiling='8',
            all_charges_included=True, consent=f'APPROVE {self.plan_hash} CNY 17')
        self.messages = [self.Message(role='user', content=[self.TextContent(text='Find hello.')])]

    def admitted(self):
        self.authority.approve(self.plan, self.plan_hash, **self.confirm)
        admission = self.authority.claim(self.plan_hash)
        ledger = Ledger.create(self.authority.folder(self.plan_hash)/'run/ledger.sqlite', self.plan, admission=admission)
        return admission, ledger

    def response(self):
        answer = {'files':['code.py'], 'entities':['code.py:hello'], 'answer':'Found hello.'}
        return {'id':'synthetic-live-wire', 'model':MODEL,
            'choices':[{'index':0, 'finish_reason':'tool_calls', 'message':{
                'role':'assistant', 'content':None, 'tool_calls':[{'id':'end1','type':'function',
                    'function':{'name':'finish','arguments':json.dumps({'message':answer})}}]}}],
            'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}}

    def helper(self, *args, **kwargs):
        # Runs in lieu of subprocess.run: no transport process or sockets.
        self.assertNotIn(FAKE_KEY, str(args))
        self.assertNotIn(FAKE_KEY, str(kwargs['env']))
        self.assertEqual(json.loads(kwargs['input'])['key'], FAKE_KEY)
        self.assertEqual(kwargs['timeout'], 60)
        raw = {'status':200,'complete':True,'body':base64.b64encode(encoded(self.response())).decode()}
        return subprocess.CompletedProcess(args[0], 0, encoded(raw), b'')

    def test_default_lock_never_prompts_or_starts_transport(self):
        with patch('readonly_agent.live_run.getpass.getpass') as prompt, \
             patch('readonly_agent.live_transport.subprocess.run') as http, \
             patch('readonly_agent.live_run.Authority', return_value=self.authority):
            with self.assertRaises(PermissionError):
                run_pair(self.plan_hash)
            with self.assertRaises(PermissionError):
                exchange_live(b'{}', FAKE_KEY)
            with self.assertRaises(FileNotFoundError):
                run_pair(self.plan_hash, live=True, prompt_api_key=True)
            prompt.assert_not_called()
            http.assert_not_called()

    def test_exact_consent_hash_and_account_prices_required(self):
        for field, value in [('currency','USD'),('input_ceiling','3'),('output_ceiling','9'),
                             ('all_charges_included',False),('consent','yes')]:
            bad = dict(self.confirm, **{field:value})
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.authority.approve(self.plan, self.plan_hash, **bad)
        with self.assertRaises(PermissionError):
            self.authority.approve(self.plan, '0'*64, **self.confirm)
        self.assertFalse(self.authority.root.exists())

    def test_approve_and_claim_are_each_one_use(self):
        self.authority.approve(self.plan, self.plan_hash, **self.confirm)
        with self.assertRaises(FileExistsError):
            self.authority.approve(self.plan, self.plan_hash, **self.confirm)
        self.authority.claim(self.plan_hash)
        with self.assertRaises(FileExistsError):
            self.authority.claim(self.plan_hash)

    def test_expiry_changed_runtime_engine_and_copied_grant_block(self):
        self.authority.approve(self.plan, self.plan_hash, **self.confirm)
        with patch('readonly_agent.authority.now', return_value=now()+timedelta(hours=25)):
            with self.assertRaises(PermissionError):
                self.authority.claim(self.plan_hash)
        with patch('readonly_agent.authority.runtime_identity', return_value='changed'):
            with self.assertRaises(PermissionError):
                self.authority.read(self.plan_hash)
        copied = self.root/'copied'
        shutil.copytree(self.authority.root, copied)
        with self.assertRaises(PermissionError):
            Authority(copied).read(self.plan_hash)
        (self.root/'engine/evaluation/eval_metric.py').write_text('# changed')
        with self.assertRaises(PermissionError):
            self.authority.read(self.plan_hash)

    def test_ledger_binding_and_simulation_separation(self):
        admission, ledger = self.admitted()
        with self.assertRaises(PermissionError):
            Ledger.create(self.root/'wrong.sqlite', self.plan, admission=admission)
        with self.assertRaises(PermissionError):
            BudgetedWire(ledger, 'baseline')
        self.assertFalse(ledger.summary()['simulation'])

    def test_specific_ticket_consumed_once_before_helper(self):
        admission, ledger = self.admitted()
        token = ledger.claim('baseline')
        data = payload(self.messages, self.finish_tools)
        identifier = ledger.reserve('baseline', token, data)
        def observed(*a, **kw):
            with sqlite3.connect(ledger.path) as db:
                self.assertEqual(db.execute('SELECT transport_started FROM calls').fetchone()[0], 1)
            return self.helper(*a, **kw)
        with patch('readonly_agent.live_transport.subprocess.run', side_effect=observed) as http:
            with self.assertRaises(PermissionError):
                exchange_live(b'wrong', FAKE_KEY, admission=admission, ledger=ledger, reservation=identifier, enabled=True)
            exchange_live(data, FAKE_KEY, admission=admission, ledger=ledger, reservation=identifier, enabled=True)
            with self.assertRaises(PermissionError):
                exchange_live(data, FAKE_KEY, admission=admission, ledger=ledger, reservation=identifier, enabled=True)
            self.assertEqual(http.call_count, 1)

    def test_timeout_preserves_reservation_and_prevents_retry(self):
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        with patch('readonly_agent.live_transport.subprocess.run', side_effect=subprocess.TimeoutExpired('synthetic',60)) as http:
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
            self.assertEqual(http.call_count, 1)
        self.assertEqual(ledger.summary()['reserved_micro_cny'], RESERVATION)
        self.assertTrue(ledger.summary()['needs_review'])

    def test_parent_death_fences_requests(self):
        read, write = os.pipe()
        with os.fdopen(read) as source, patch('readonly_agent.live_run.sys.stdin', source):
            parent_alive()
            os.close(write)
            with self.assertRaises(RuntimeError):
                parent_alive()
        admission, ledger = self.admitted()
        def dead():
            raise RuntimeError('parent gone')
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY, dead)
        with patch('readonly_agent.live_transport.subprocess.run') as http:
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
            http.assert_not_called()
        self.assertEqual(ledger.summary()['calls'], [])

    def test_real_sdk_live_path_with_mocked_helper_and_no_key_persistence(self):
        from readonly_agent.openhands_replay import run_sdk_case
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        with patch('readonly_agent.live_transport.subprocess.run', side_effect=self.helper) as http:
            result = run_sdk_case(snapshot=self.snapshot, issue='Find hello.', script=None,
                output_dir=self.root/'output', limits=Limits(max_requests=4), live=session)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(ledger.summary()['spent_upper_micro_cny'], 2800)
        self.assertIsNone(session._key)
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(FAKE_KEY.encode(), path.read_bytes(), str(path))

    def test_http_helper_fixed_endpoint_no_redirect_no_proxy_no_retry(self):
        from readonly_agent.transport_worker import main
        observed = []
        def handler(request):
            observed.append(str(request.url))
            self.assertEqual(request.headers['authorization'], 'Bearer '+FAKE_KEY)
            return self.httpx.Response(302, headers={'location':'https://example.invalid'}, content=b'redirect')
        body = payload(self.messages, self.finish_tools)
        input_stream = SimpleNamespace(buffer=io.BytesIO(encoded({'body':body.decode(),'key':FAKE_KEY})))
        output = io.StringIO()
        with patch('httpx.HTTPTransport', return_value=self.httpx.MockTransport(handler)) as transport, \
             patch('readonly_agent.transport_worker.sys.stdin', input_stream), \
             patch('readonly_agent.transport_worker.sys.stdout', output):
            main()
        transport.assert_called_once_with(retries=0)
        self.assertEqual(observed, ['https://api.deepseek.com/chat/completions'])
        self.assertEqual(json.loads(output.getvalue())['status'], 302)
        self.assertNotIn(FAKE_KEY, output.getvalue())

    def test_live_sdk_fourth_request_offers_finish_only(self):
        from readonly_agent.openhands_replay import run_sdk_case
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        sent = []
        def helper(*args, **kwargs):
            request = json.loads(json.loads(kwargs['input'])['body'])
            sent.append(request)
            raw = self.response()
            if len(sent) < 4:
                raw['choices'][0]['message']['tool_calls'] = [{'id':f's{len(sent)}','type':'function',
                    'function':{'name':'search_text','arguments':'{"query":"hello","offset":0}'}}]
            output = {'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}
            return subprocess.CompletedProcess(args[0], 0, encoded(output), b'')
        with patch('readonly_agent.live_transport.subprocess.run', side_effect=helper):
            result = run_sdk_case(snapshot=self.snapshot, issue='Find hello.', script=None,
                output_dir=self.root/'output', limits=Limits(max_requests=4), live=session)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['requests'], 4)
        self.assertEqual([t['function']['name'] for t in sent[-1]['tools']], ['finish'])
        self.assertEqual(sent[-1]['tool_choice']['function']['name'], 'finish')
        from readonly_agent.control import CLOSING_INSTRUCTION
        self.assertTrue(sent[-1]['messages'][-1]['content'].endswith(CLOSING_INSTRUCTION))
        self.assertIn('response 4 of 4',sent[-1]['messages'][-1]['content'])
        for index,request in enumerate(sent,1):
            notices=[m for m in request['messages'] if m['role']=='user' and m['content'].startswith('CONTROLLER BUDGET')]
            self.assertEqual(len(notices),1)
            self.assertIn(f'response {index} of 4',notices[0]['content'])
        self.assertEqual(sent[2]['tool_choice'],'auto')
        self.assertEqual(ledger.summary()['reserved_micro_cny'], 0)

    def test_original_closing_violation_stops_sdk_without_extra_tools_or_calls(self):
        from readonly_agent.openhands_replay import run_sdk_case
        original=json.loads((Path(__file__).parent/'fixtures/crossfile_closing_incident.json').read_text())
        admission,ledger=self.admitted()
        session=LiveSession(ledger,'baseline',admission,FAKE_KEY)
        seen=[]
        def helper(*args,**kwargs):
            request=json.loads(json.loads(kwargs['input'])['body'])
            seen.append(request)
            raw=self.response()
            if len(seen)<4:
                raw['choices'][0]['message']['tool_calls']=[{'id':f'r{len(seen)}','type':'function',
                    'function':{'name':'search_text','arguments':'{"query":"hello","offset":0}'}}]
            else:
                raw=original['response']
            reply={'status':200,'complete':True,'body':base64.b64encode(encoded(raw)).decode()}
            return subprocess.CompletedProcess(args[0],0,encoded(reply),b'')
        with patch('readonly_agent.live_transport.subprocess.run',side_effect=helper) as http:
            result=run_sdk_case(snapshot=self.snapshot,issue='Find hello.',script=None,
                output_dir=self.root/'output',limits=Limits(max_requests=4),live=session)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure'],'closing_tool_violation')
        self.assertEqual(http.call_count,4)
        self.assertEqual(result['tool_calls'],3)
        self.assertTrue(ledger.summary()['halted'])
        self.assertEqual(ledger.summary()['reserved_micro_cny'],0)
        self.assertTrue(all(c['status']=='settled' for c in ledger.summary()['calls']))

    def test_sensitive_helper_reply_is_not_persisted_and_retains_reservation(self):
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        reflected = {'status':200,'complete':True,'body':base64.b64encode(FAKE_KEY.encode()).decode()}
        fake = subprocess.CompletedProcess([], 0, encoded(reflected), b'')
        with patch('readonly_agent.live_transport.subprocess.run', return_value=fake):
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
        self.assertEqual(ledger.summary()['reserved_micro_cny'], RESERVATION)
        self.assertNotIn(FAKE_KEY.encode(), ledger.path.read_bytes())

    def test_live_receipt_disk_failure_stops_without_second_call(self):
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        with patch('readonly_agent.live_transport.subprocess.run', side_effect=self.helper) as http, \
             patch.object(ledger, 'received', side_effect=OSError('synthetic disk full')):
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
            with self.assertRaises(RuntimeError):
                session.generate(self.messages, self.finish_tools, True)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(ledger.summary()['reserved_micro_cny'], RESERVATION)

    def test_source_change_blocks_sdk_before_transport(self):
        from readonly_agent.openhands_replay import run_sdk_case
        admission, ledger = self.admitted()
        session = LiveSession(ledger, 'baseline', admission, FAKE_KEY)
        (self.root/'code.py').write_text('changed source')
        changed = Snapshot(self.root, ['code.py'])
        with patch('readonly_agent.live_transport.subprocess.run') as http:
            with self.assertRaises(PermissionError):
                run_sdk_case(snapshot=changed, issue='Find hello.', script=None,
                    output_dir=self.root/'output', limits=Limits(max_requests=4), live=session)
            http.assert_not_called()

    def test_helper_retains_partial_response_without_retry(self):
        from readonly_agent.transport_worker import main
        httpx = self.httpx
        class Broken(httpx.SyncByteStream):
            def __iter__(self):
                yield b'{"partial":'
                raise httpx.ReadError('synthetic disconnect')
        mock = httpx.MockTransport(lambda r: httpx.Response(200, stream=Broken()))
        data = encoded({'body':payload(self.messages, self.finish_tools).decode(),'key':FAKE_KEY})
        output = io.StringIO()
        with patch('httpx.HTTPTransport', return_value=mock), \
             patch('readonly_agent.transport_worker.sys.stdin', SimpleNamespace(buffer=io.BytesIO(data))), \
             patch('readonly_agent.transport_worker.sys.stdout', output):
            main()
        raw = json.loads(output.getvalue())
        self.assertFalse(raw['complete'])
        self.assertEqual(base64.b64decode(raw['body']), b'{"partial":')


if __name__ == '__main__':
    unittest.main()
