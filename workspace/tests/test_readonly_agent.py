import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from readonly_agent.core import (FileTools, Limits, ScriptedProvider, Snapshot,
                                 encoded, page, run)
from readonly_agent.paired import run_pair


def call(name, args, call_id='c1'):
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': args}


def response(*calls):
    return {'stop_reason': 'tool_use', 'content': list(calls)}


def finish(files=None):
    return response(call('finish', {'files': files or [], 'entities': [], 'answer': 'Uncertain.'}))


class FakeRetriever:
    def __init__(self, snapshot):
        self.snapshot_id = snapshot.identity
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        return 'src/a.py:hello\n1: def hello():\n2:     return "你好"'


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/a.py').write_text('def hello():\n    return "你好"\n')
        (self.root / 'gold.json').write_text('never expose labels')
        self.snapshot = Snapshot(self.root, ['src/a.py'])
        self.counter = 0

    def run_script(self, script, **kwargs):
        self.counter += 1
        provider = ScriptedProvider(script)
        path = self.root / f'trace{self.counter}.jsonl'
        result = run(issue='Find greeting behavior.', snapshot=self.snapshot, provider=provider,
                     trace_path=path, **kwargs)
        events = [json.loads(s) for s in path.read_text().splitlines()]
        self.assertEqual(events[-1]['event'], 'terminal')
        self.assertEqual(result['live_calls'], 0)
        return result, provider, events

    def test_search_read_finish_and_trace(self):
        before = (self.root / 'src/a.py').read_bytes()
        result, provider, events = self.run_script([
            response(call('search_text', {'query': 'hello', 'offset': 0})),
            response(call('read_file', {'path': 'src/a.py', 'start_line': 1})), finish(['src/a.py'])])
        self.assertEqual(result['status'], 'completed')
        self.assertIn('你好', json.dumps(provider.requests, ensure_ascii=False))
        self.assertNotIn('never expose labels', json.dumps(events))
        self.assertEqual(before, (self.root / 'src/a.py').read_bytes())

    def test_source_exhaustion_reserves_finish(self):
        result, provider, _ = self.run_script([
            response(call('read_file', {'path': 'src/a.py', 'start_line': 1})), finish()],
            limits=Limits(source_bytes=1))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['requests'], 2)
        self.assertEqual(result['source_bytes'], 0)
        self.assertEqual([t['name'] for t in provider.requests[-1]['tools']], ['finish'])

    def test_actual_source_exhaustion_in_both_arms(self):
        (self.root / 'src/a.py').write_text('"你好"\\n' * 2000)
        self.snapshot = Snapshot(self.root, ['src/a.py'])
        for retrieval in (False, True):
            result, provider, _ = self.run_script([
                response(call('read_file', {'path': 'src/a.py', 'start_line': 1})), finish()],
                limits=Limits(source_bytes=256),
                retriever=FakeRetriever(self.snapshot) if retrieval else None)
            self.assertEqual(result['status'], 'completed')
            self.assertLessEqual(result['source_bytes'], 256)
            self.assertGreater(result['source_bytes'], 192)
            self.assertEqual([t['name'] for t in provider.requests[-1]['tools']], ['finish'])

    def test_only_retrieval_tool_schema_differs(self):
        _, a, _ = self.run_script([finish()])
        _, b, _ = self.run_script([finish()], retriever=FakeRetriever(self.snapshot))
        left, right = a.requests[0], b.requests[0]
        right['tools'] = [t for t in right['tools'] if t['name'] != 'locagent_retrieve']
        self.assertEqual(left, right)

    def test_retrieval_pagination_is_stable_without_reexecution(self):
        retriever = FakeRetriever(self.snapshot)
        tools = FileTools(self.snapshot, retriever)
        raw, _ = tools.render('locagent_retrieve', {'query': 'hello', 'offset': 0})
        again, cursor = tools.render('locagent_retrieve', {'query': 'hello', 'offset': 5})
        self.assertEqual(raw, again)
        self.assertEqual(cursor, 5)
        self.assertEqual(retriever.queries, ['hello'])

    def test_call_budget_mid_batch_preserves_ids_and_finishes(self):
        result, provider, _ = self.run_script([
            response(call('list_files', {'offset': 0}, 'a'), call('list_files', {'offset': 0}, 'b')),
            finish()], limits=Limits(max_tool_calls=1))
        outputs = provider.requests[-1]['messages'][-2]['content']
        self.assertEqual([r['tool_use_id'] for r in outputs], ['a', 'b'])
        self.assertTrue(outputs[1]['is_error'])
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(result['status'], 'completed')

    def test_last_request_is_finish_only(self):
        result, provider, _ = self.run_script([finish()], limits=Limits(max_requests=1))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([t['name'] for t in provider.requests[0]['tools']], ['finish'])

    def test_final_request_ignoring_finish_is_failure(self):
        result, _, _ = self.run_script([response(call('list_files', {'offset': 0}))],
                                       limits=Limits(max_requests=1))
        self.assertEqual(result['status'], 'finish_required')
        self.assertEqual(result['tool_calls'], 0)

    def test_non_tool_text_is_not_success(self):
        result, _, _ = self.run_script([{'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'done'}]}])
        self.assertEqual(result['status'], 'missing_finish')

    def test_retrieval_disabled_cannot_be_called(self):
        result, provider, _ = self.run_script([
            response(call('locagent_retrieve', {'query': 'hello', 'offset': 0})), finish()])
        self.assertNotIn('locagent_retrieve', [t['name'] for t in provider.requests[0]['tools']])
        self.assertTrue(provider.requests[1]['messages'][-1]['content'][0]['is_error'])
        self.assertEqual(result['status'], 'completed')

    def test_pagination_handles_utf8_and_escaping_without_loss(self):
        raw = '你好\\\"\n' * 200
        offset, chunks = 0, []
        while True:
            p = page(raw, offset, 100)
            self.assertLessEqual(len(encoded(p)), 100)
            chunks.append(p['text'])
            if p['next_offset'] is None:
                break
            self.assertGreater(p['next_offset'], offset)
            offset = p['next_offset']
        self.assertEqual(''.join(chunks), raw)

    def test_allowlist_traversal_absolute_and_hidden(self):
        tools = FileTools(self.snapshot)
        for name in ('../gold.json', '/etc/passwd', 'gold.json', 'src/../gold.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                tools.render('read_file', {'path': name, 'offset': 0})
        (self.root / '.env').write_text('private')
        with self.assertRaises(ValueError):
            Snapshot(self.root, ['.env'])

    def test_symlink_and_directory_link_rejected(self):
        (self.root / 'link.py').symlink_to(self.root / 'src/a.py')
        (self.root / 'linked').symlink_to(self.root / 'src', target_is_directory=True)
        for name in ('link.py', 'linked/a.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                Snapshot(self.root, [name])

    def test_snapshot_stays_frozen(self):
        (self.root / 'src/a.py').write_text('changed')
        raw, _ = FileTools(self.snapshot).render('read_file', {'path': 'src/a.py', 'offset': 0})
        self.assertIn('hello', raw)

    def test_bad_cursor_fields_unknown_tool_are_errors(self):
        tools = FileTools(self.snapshot)
        for name, args in [('read_file', {'path': 'src/a.py', 'offset': True}),
                           ('list_files', {'offset': 1000}), ('bash', {'command': 'touch bad'}),
                           ('list_files', {'offset': 0, 'extra': 1})]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                tools.render(name, args)

    def test_malformed_duplicate_and_mixed_tool_calls(self):
        scripts = [response(call('list_files', {'offset': 0}), call('list_files', {'offset': 0})),
                   response(call('finish', {'files': [], 'entities': [], 'answer': ''}),
                            call('list_files', {'offset': 0}, 'b')),
                   response({'type': 'tool_use', 'id': 4, 'name': 'list_files', 'input': {}})]
        for scripted in scripts:
            result, _, _ = self.run_script([scripted])
            self.assertNotEqual(result['status'], 'completed')
            self.assertEqual(result['tool_calls'], 0)

    def test_finish_outside_source_refused(self):
        result, _, _ = self.run_script([finish(['gold.json'])])
        self.assertEqual(result['status'], 'invalid_finish')

    def test_request_response_caps(self):
        result, provider, _ = self.run_script([finish()], limits=Limits(request_bytes=1))
        self.assertEqual(result['status'], 'request_budget_exhausted')
        self.assertEqual(len(provider.requests), 0)
        result, _, _ = self.run_script([finish()], limits=Limits(response_bytes=1))
        self.assertEqual(result['status'], 'response_budget_exhausted')

    def test_no_live_provider_injection(self):
        called = []
        with self.assertRaisesRegex(ValueError, 'only_offline'):
            run(issue='hello', snapshot=self.snapshot, provider=lambda req: called.append(req),
                trace_path=self.root / 'blocked.jsonl')
        self.assertEqual(called, [])

    def test_trace_no_overwrite_and_provider_error(self):
        result, _, _ = self.run_script([])
        self.assertEqual(result['status'], 'provider_error')
        with self.assertRaises(FileExistsError):
            run(issue='hello', snapshot=self.snapshot, provider=ScriptedProvider([finish()]),
                trace_path=self.root / 'trace1.jsonl')

    def test_pair_contract_and_case_isolation(self):
        created = []
        def factory(snapshot):
            retriever = FakeRetriever(snapshot)
            created.append(retriever)
            return retriever
        for i in range(2):
            results = run_pair(issue='hello', snapshot=self.snapshot,
                scripts={'baseline': [finish()], 'retrieval': [response(call('locagent_retrieve',
                    {'query': 'hello', 'offset': 0})), finish()]}, retriever_factory=factory,
                output_dir=self.root / f'pair{i}')
            a, b = results['baseline']['manifest'].copy(), results['retrieval']['manifest'].copy()
            self.assertFalse(a.pop('retrieval'))
            self.assertTrue(b.pop('retrieval'))
            self.assertEqual(a, b)
        self.assertIsNot(created[0], created[1])
        self.assertEqual([r.queries for r in created], [['hello'], ['hello']])

    def test_plugin_snapshot_mismatch(self):
        plugin = FakeRetriever(self.snapshot)
        plugin.snapshot_id = 'wrong'
        with self.assertRaises(ValueError):
            FileTools(self.snapshot, plugin)

    def test_invalid_limits(self):
        for kwargs in ({'max_requests': True}, {'max_requests': 33}, {'source_bytes': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Limits(**kwargs)


if __name__ == '__main__':
    unittest.main()
