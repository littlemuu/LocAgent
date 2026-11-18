import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from readonly_agent.core import Limits, Snapshot, encoded
from readonly_agent.offline import no_network
from readonly_agent.openhands_replay import run_sdk_case


def call(name, args):
    return {'stop_reason': 'tool_use', 'content': [
        {'type': 'tool_use', 'id': 'fixture-call', 'name': name, 'input': args}]}


def finish():
    return call('finish', {'files': [], 'entities': [], 'answer': 'Unknown; offline fixture.'})


class FakeRetriever:
    def __init__(self, snapshot):
        self.snapshot_id = snapshot.identity
        self.calls = 0

    def retrieve(self, query):
        self.calls += 1
        return 'src/a.py:hello\n' * 100


class OpenHandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard_dir = TemporaryDirectory()
        cls.guard = no_network(Path(cls.guard_dir.name) / 'oh')
        cls.attempts = cls.guard.__enter__()
        from openhands.sdk.tool import resolve_tool
        from readonly_agent.openhands_tools import ToolSession, register_readonly_tools
        cls.resolve = staticmethod(resolve_tool)
        cls.session_type = ToolSession
        cls.register = staticmethod(register_readonly_tools)

    @classmethod
    def tearDownClass(cls):
        cls.guard.__exit__(None, None, None)
        cls.guard_dir.cleanup()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/a.py').write_text('def hello():\n    return "你好"\n' + '# padding\n' * 200)
        self.snapshot = Snapshot(self.root, ['src/a.py'])

    def resolved(self, session):
        return {tool.name: tool for spec in self.register(session) for tool in self.resolve(spec, None)}

    def test_registered_tool_surface_only_differs_by_retrieval(self):
        a = self.resolved(self.session_type(self.snapshot))
        b = self.resolved(self.session_type(self.snapshot, retriever=FakeRetriever(self.snapshot)))
        self.assertEqual(set(a), {'list_files', 'search_text', 'read_file'})
        self.assertEqual(set(b)-set(a), {'locagent_retrieve'})
        for name in a:
            self.assertEqual(a[name].to_openai_tool(), b[name].to_openai_tool())
            self.assertTrue(a[name].annotations.readOnlyHint)
            self.assertFalse(a[name].annotations.openWorldHint)

    def test_real_executor_reads_only_snapshot_and_rejects_escape(self):
        session = self.session_type(self.snapshot)
        tool = self.resolved(session)['read_file']
        observation = tool(tool.action_type(path='src/a.py', start_line=1))
        self.assertIn('你好', observation.text)
        refused = tool(tool.action_type(path='../secret', start_line=1))
        self.assertTrue(refused.is_error)
        self.assertNotIn('secret', refused.text)
        with self.assertRaises(ValueError):
            tool.action_type(path='src/a.py', start_line=True)

    def test_native_source_budget_stops_executor_in_both_arms(self):
        for on in (False, True):
            plugin = FakeRetriever(self.snapshot) if on else None
            session = self.session_type(self.snapshot, retriever=plugin, limits=Limits(source_bytes=200))
            tool = self.resolved(session)['read_file']
            result = tool(tool.action_type(path='src/a.py', start_line=1))
            self.assertLessEqual(len(result.text.encode()), 200)
            self.assertTrue(session.closed)
            calls = session.calls
            again = tool(tool.action_type(path='src/a.py', start_line=1))
            self.assertEqual(session.calls, calls)
            self.assertTrue(again.is_error)

    def test_distinct_registered_sessions_do_not_rebind_each_other(self):
        a = self.session_type(self.snapshot)
        tools_a = self.resolved(a)
        b = self.session_type(self.snapshot)
        self.resolved(b)
        tool = tools_a['list_files']
        tool(tool.action_type(offset=0))
        self.assertEqual(a.calls, 1)
        self.assertEqual(b.calls, 0)

    def test_sdk_loop_source_exhaustion_still_finishes(self):
        for on in (False, True):
            result = run_sdk_case(snapshot=self.snapshot, issue='Locate greeting.',
                script=[call('read_file', {'path': 'src/a.py', 'start_line': 1}), finish()],
                output_dir=self.root / str(on), limits=Limits(source_bytes=200),
                retriever=FakeRetriever(self.snapshot) if on else None)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['requests'], 2)
            self.assertEqual(result['network_attempts'], 0)
            events = [json.loads(s) for s in (self.root / str(on) / 'trace.jsonl').read_text().splitlines()]
            last = [e for e in events if e['event'] == 'request'][-1]
            self.assertTrue(last['request']['closing'])
            self.assertEqual([t['function']['name'] for t in last['request']['tools']], ['finish'])
            self.assertIn('INVESTIGATION IS CLOSED', last['request']['controller_notice'])
            self.assertIn('available investigation calls: 0', last['request']['controller_notice'])
            self.assertEqual(last['request']['closure_reason'], 'investigation_budget')

    def test_sdk_hard_last_request_and_no_extra_retry(self):
        result = run_sdk_case(snapshot=self.snapshot, issue='Locate greeting.',
            script=[call('read_file', {'path': 'src/a.py', 'start_line': 1}), finish()],
            output_dir=self.root / 'last', limits=Limits(max_requests=1))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure'], 'unavailable_tool')
        self.assertEqual(result['requests'], 1)
        self.assertEqual(result['tool_calls'], 0)

    def test_sdk_missing_finish_is_failure(self):
        result = run_sdk_case(snapshot=self.snapshot, issue='Locate greeting.',
            script=[{'stop_reason': 'end_turn', 'content': []}], output_dir=self.root / 'missing')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure'], 'missing_finish')
        self.assertEqual(result['requests'], 1)


if __name__ == '__main__':
    unittest.main()
