from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from readonly_agent.core import Snapshot, digest, encoded
from readonly_agent.deepseek_wire import (MODEL, CONTEXT, OUTPUT, RESERVATION,
    RawHTTP, exchange_live, exchange_offline, payload, usage)
from readonly_agent.journal import Ledger
from readonly_agent.offline import no_network
from readonly_agent.preparation import BudgetedWire, make_plan


def raw_reply(**changes):
    data = {'id': 'offline-r1', 'model': MODEL, 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
        'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'c1', 'type': 'function', 'function': {'name': 'finish', 'arguments': '{"message":{"files":[],"entities":[],"answer":"unknown"}}'}}]}}],
        'usage': {'prompt_tokens': 1000, 'completion_tokens': 100, 'total_tokens': 1100}}
    data.update(changes)
    return data


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard_dir = TemporaryDirectory()
        cls.guard = no_network(Path(cls.guard_dir.name) / 'profiles')
        cls.guard.__enter__()
        import httpx
        from openhands.sdk.llm import Message, TextContent
        from openhands.sdk.tool import FinishTool
        cls.httpx = httpx
        cls.Message = Message
        cls.TextContent = TextContent
        cls.finish_tools = FinishTool.create()

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None, None, None)
        cls.guard_dir.cleanup()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'code.py').write_text('def hello():\n    return "hello"\n')
        snapshot = Snapshot(self.root, ['code.py'])
        self.plan = make_plan(snapshot, 'Find the greeting.')
        self.ledger = Ledger.create(self.root / 'ledger.sqlite', self.plan)
        self.messages = [self.Message(role='user', content=[self.TextContent(text='Find greeting')])]

    def transport(self, body=None, status=200):
        return self.httpx.MockTransport(lambda r: self.httpx.Response(status, json=body or raw_reply()))

    def test_reservation_is_committed_before_transport_and_receipt_settles(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        def handler(request):
            reopened = Ledger(self.ledger.path, digest(self.plan))
            self.assertEqual(reopened.summary()['reserved_micro_cny'], RESERVATION)
            data = json.loads(request.content)
            self.assertEqual(data['model'], 'deepseek-flash')
            self.assertEqual(data['thinking'], {'type': 'disabled'})
            self.assertFalse(data['stream'])
            self.assertEqual(data['max_tokens'], 2048)
            self.assertEqual(str(request.url), 'https://api.deepseek.com/chat/completions')
            return self.httpx.Response(200, json=raw_reply())
        response = wire.generate(self.messages, self.finish_tools, True, self.httpx.MockTransport(handler))
        self.assertEqual(response.message.tool_calls[0].name, 'finish')
        summary = self.ledger.summary()
        self.assertEqual(summary['spent_upper_micro_cny'], 2800)
        self.assertEqual(summary['reserved_micro_cny'], 0)

    def test_timeout_is_unknown_and_never_retried(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        seen = []
        def handler(request):
            seen.append(1)
            raise self.httpx.ReadTimeout('offline timeout')
        transport = self.httpx.MockTransport(handler)
        with self.assertRaises(self.httpx.ReadTimeout):
            wire.generate(self.messages, self.finish_tools, False, transport)
        with self.assertRaises(RuntimeError):
            wire.generate(self.messages, self.finish_tools, False, transport)
        self.assertEqual(seen, [1])
        self.assertEqual(self.ledger.summary()['calls'][0]['status'], 'unknown')
        self.assertEqual(self.ledger.summary()['reserved_micro_cny'], RESERVATION)

    def test_restart_with_inflight_reservation_fails_closed(self):
        token = self.ledger.claim('baseline')
        self.ledger.reserve('baseline', token, b'{}')
        other = Ledger(self.ledger.path, digest(self.plan))
        self.assertTrue(other.summary()['needs_review'])
        with self.assertRaises(RuntimeError):
            other.reserve('baseline', token, b'{}')
        with self.assertRaises(RuntimeError):
            other.claim('retrieval')

    def test_process_exit_after_commit_cannot_replay(self):
        program = ('import os,sys; from readonly_agent.journal import Ledger; '
                   'l=Ledger(sys.argv[1],sys.argv[2]); t=l.claim("baseline"); '
                   'l.reserve("baseline",t,b"{}"); os._exit(17)')
        child = subprocess.run([sys.executable, '-B', '-c', program, str(self.ledger.path), digest(self.plan)],
                               capture_output=True, timeout=10)
        self.assertEqual(child.returncode, 17, child.stderr.decode())
        reopened = Ledger(self.ledger.path, digest(self.plan))
        self.assertTrue(reopened.summary()['needs_review'])
        self.assertEqual(reopened.summary()['reserved_micro_cny'], RESERVATION)
        with self.assertRaises(RuntimeError):
            reopened.claim('retrieval')

    def test_raw_receipt_durable_before_usage_validation(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        with self.assertRaises(ValueError):
            wire.generate(self.messages, self.finish_tools, False,
                self.transport(raw_reply(usage={'prompt_tokens': True,'completion_tokens':100,'total_tokens':101})))
        with sqlite3.connect(self.ledger.path) as db:
            row = db.execute('SELECT response,status FROM calls').fetchone()
        self.assertIn(b'true', row[0])
        self.assertEqual(row[1], 'unknown')

    def test_protocol_error_keeps_known_cost_and_halts(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        body = raw_reply()
        body['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = '{bad'
        with self.assertRaises(ValueError):
            wire.generate(self.messages, self.finish_tools, False, self.transport(body))
        summary = self.ledger.summary()
        self.assertTrue(summary['halted'])
        self.assertEqual(summary['calls'][0]['status'], 'settled')
        self.assertEqual(summary['spent_upper_micro_cny'], 2800)
        self.assertEqual(summary['reserved_micro_cny'], 0)

    def test_http_redirect_error_and_partial_never_retry(self):
        for status in (302, 429, 500):
            with self.subTest(status=status):
                ledger = Ledger.create(self.root / f'{status}.sqlite', self.plan)
                wire = BudgetedWire(ledger, 'baseline')
                with self.assertRaises(RuntimeError):
                    wire.generate(self.messages, self.finish_tools, False, self.transport(status=status))
                self.assertEqual(ledger.summary()['reserved_micro_cny'], RESERVATION)
        token = self.ledger.claim('baseline')
        identifier = self.ledger.reserve('baseline', token, b'{}')
        self.ledger.received(identifier, RawHTTP(200, b'{"partial":', False))
        with self.assertRaises(RuntimeError):
            self.ledger.settle(identifier)

    def test_http_stream_failure_preserves_received_prefix(self):
        httpx = self.httpx
        class Broken(httpx.SyncByteStream):
            def __iter__(self):
                yield b'{"id":"prefix"'
                raise httpx.ReadError('scripted disconnect')
        wire = BudgetedWire(self.ledger, 'baseline')
        transport = httpx.MockTransport(lambda req: httpx.Response(200, stream=Broken()))
        with self.assertRaises(RuntimeError):
            wire.generate(self.messages, self.finish_tools, False, transport)
        with sqlite3.connect(self.ledger.path) as db:
            row = db.execute('SELECT response,complete,status FROM calls').fetchone()
        self.assertEqual(row, (b'{"id":"prefix"', 0, 'unknown'))

    def test_reservation_write_failure_prevents_transport(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        seen = []
        transport = self.httpx.MockTransport(lambda req: seen.append(req))
        with patch.object(self.ledger, 'reserve', side_effect=OSError('scripted disk full')):
            with self.assertRaises(OSError):
                wire.generate(self.messages, self.finish_tools, False, transport)
        self.assertEqual(seen, [])

    def test_usage_model_token_sum_and_cache_validation(self):
        cases = [raw_reply(model='unexpected'), raw_reply(usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':3}),
                 raw_reply(usage={'prompt_tokens':CONTEXT+1,'completion_tokens':0,'total_tokens':CONTEXT+1}),
                 raw_reply(usage={'prompt_tokens':1,'completion_tokens':OUTPUT+1,'total_tokens':OUTPUT+2}),
                 raw_reply(usage={'prompt_tokens':10,'completion_tokens':0,'total_tokens':10,
                                  'prompt_cache_hit_tokens':8,'prompt_cache_miss_tokens':8})]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(ValueError):
                usage(encoded(body))

    def test_duplicate_json_usage_is_rejected(self):
        body = encoded(raw_reply()).replace(b'"prompt_tokens":1000', b'"prompt_tokens":1000,"prompt_tokens":1')
        with self.assertRaises(ValueError):
            usage(body)

    def test_copy_and_corruption_are_rejected(self):
        copied = self.root / 'copy.sqlite'
        shutil.copyfile(self.ledger.path, copied)
        with self.assertRaises(ValueError):
            Ledger(copied, digest(self.plan))
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("UPDATE run SET hash='wrong'")
        with self.assertRaises(ValueError):
            self.ledger.summary()

    def test_concurrent_reservations_allow_only_one_inflight(self):
        token = self.ledger.claim('baseline')
        def attempt(_):
            try:
                return self.ledger.reserve('baseline', token, b'{}')
            except RuntimeError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_eight_maximum_receipts_stay_below_seventeen_cny(self):
        body = raw_reply(usage={'prompt_tokens':CONTEXT,'completion_tokens':OUTPUT,'total_tokens':CONTEXT+OUTPUT})
        for arm in ('baseline', 'retrieval'):
            wire = BudgetedWire(self.ledger, arm)
            for _ in range(4):
                wire.generate(self.messages, self.finish_tools, False, self.transport(body))
            with self.assertRaises(RuntimeError):
                wire.generate(self.messages, self.finish_tools, False, self.transport(body))
        self.assertEqual(self.ledger.summary()['spent_upper_micro_cny'], 16908288)
        self.assertLess(self.ledger.summary()['spent_upper_micro_cny'], 17000000)

    def test_existing_claim_and_finished_arm_cannot_run_again(self):
        token = self.ledger.claim('baseline')
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.claim('baseline')
        self.ledger.finish('baseline', token)
        with self.assertRaises(RuntimeError):
            self.ledger.reserve('baseline', token, b'{}')

    def test_response_write_failure_retains_pre_call_reservation(self):
        wire = BudgetedWire(self.ledger, 'baseline')
        with patch.object(self.ledger, 'received', side_effect=OSError('simulated disk full')):
            with self.assertRaises(OSError):
                wire.generate(self.messages, self.finish_tools, False, self.transport())
        self.assertEqual(self.ledger.summary()['reserved_micro_cny'], RESERVATION)
        self.assertTrue(self.ledger.summary()['needs_review'])

    def test_live_entry_and_non_mock_transport_remain_disabled(self):
        with self.assertRaises(PermissionError):
            exchange_live()
        wire = BudgetedWire(self.ledger, 'baseline')
        with self.assertRaises(ValueError):
            wire.generate(self.messages, self.finish_tools, False, object())
        self.assertEqual(self.ledger.summary()['calls'], [])

    def test_wire_disallows_orphan_tool_results(self):
        bad = [self.Message(role='tool', name='read_file', tool_call_id='missing', content=[self.TextContent(text='data')])]
        with self.assertRaises(ValueError):
            payload(bad, self.finish_tools)


if __name__ == '__main__':
    unittest.main()
