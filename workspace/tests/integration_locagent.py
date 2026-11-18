"""Run with the reviewed LocAgent venv/PYTHONPATH; never import target repositories."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from readonly_agent.core import FileTools, Snapshot
from readonly_agent.locagent import LocAgentRetriever
from readonly_agent.paired import run_pair
from test_readonly_agent import call, response, finish


class LocAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/greeting.py').write_text(
            'def greeting(name):\n    return "hello " + name\n\n'
            'def farewell(name):\n    return "bye " + name\n')
        self.snapshot = Snapshot(self.root, ['src/greeting.py'])

    def test_real_graph_builder_retriever_and_shared_pair(self):
        from locagent_service.offline import offline_engine
        with offline_engine():
            from dependency_graph.build_graph import build_graph
            from plugins.location_tools.repo_ops import repo_ops as ops
            graph = build_graph(str(self.root), global_import=True)
            prior = (ops.CURRENT_ISSUE_ID, ops.DP_GRAPH)
            retriever = LocAgentRetriever(self.snapshot, graph)
            exact = retriever.retrieve('src/greeting.py:greeting')
            self.assertIn('return "hello " + name', exact)
            lexical = retriever.retrieve('greeting')
            self.assertIn('greeting', lexical)
            self.assertEqual((ops.CURRENT_ISSUE_ID, ops.DP_GRAPH), prior)
            results = run_pair(issue='Locate the greeting behavior.', snapshot=self.snapshot,
                scripts={'baseline': [response(call('search_text', {'query': 'greeting', 'offset': 0})),
                                      finish(['src/greeting.py'])],
                         'retrieval': [response(call('locagent_retrieve', {'query': 'greeting', 'offset': 0})),
                                       finish(['src/greeting.py'])]},
                retriever_factory=lambda s: LocAgentRetriever(s, graph), output_dir=self.root / 'pair')
            self.assertTrue(all(r['status'] == 'completed' for r in results.values()))
            b = (self.root / 'pair/retrieval.jsonl').read_text()
            self.assertIn('hello', b)
            self.assertNotIn('tool_error', b)

    def test_wrong_graph_content_is_rejected(self):
        from locagent_service.offline import offline_engine
        with offline_engine():
            from dependency_graph.build_graph import build_graph
            graph = build_graph(str(self.root), global_import=True)
            graph.nodes['src/greeting.py']['code'] = 'other task secret'
            with self.assertRaisesRegex(ValueError, 'graph_source_content_mismatch'):
                LocAgentRetriever(self.snapshot, graph)

    def test_ast_segments_with_trailing_comments_and_exact_binding(self):
        from copy import deepcopy
        from locagent_service.offline import offline_engine
        text = ('class C:\n'
                '    async def hello(self):\n'
                '        return "héllo"  # kept in file, excluded by AST segment\n')
        (self.root/'src/greeting.py').write_text(text)
        snapshot = Snapshot(self.root, ['src/greeting.py'])
        with offline_engine():
            from dependency_graph.build_graph import build_graph
            graph = build_graph(str(self.root), global_import=True)
            retriever = LocAgentRetriever(snapshot, graph)
            self.assertIn('héllo', retriever.retrieve('src/greeting.py:C.hello'))
            for field, bad in [('code','async def hello(self):\n        return "different"'),
                               ('start_line',1), ('end_line',2)]:
                changed = deepcopy(graph)
                changed.nodes['src/greeting.py:C.hello'][field] = bad
                with self.assertRaisesRegex(ValueError,'graph_entity_content_mismatch'):
                    LocAgentRetriever(snapshot, changed)
            changed = deepcopy(graph)
            import networkx as nx
            nx.relabel_nodes(changed, {'src/greeting.py:C.hello':'src/greeting.py:C.forged'}, copy=False)
            with self.assertRaisesRegex(ValueError,'graph_entity_content_mismatch'):
                LocAgentRetriever(snapshot, changed)

    def test_graph_session_restored_on_error_and_next_case(self):
        from locagent_service.offline import offline_engine
        with offline_engine():
            from dependency_graph.build_graph import build_graph
            from plugins.location_tools.repo_ops import repo_ops as ops
            from unittest.mock import patch
            graph = build_graph(str(self.root), global_import=True)
            retriever = LocAgentRetriever(self.snapshot, graph)
            prior = (ops.CURRENT_ISSUE_ID, ops.DP_GRAPH)
            with patch.object(ops, 'get_entity_contents', side_effect=RuntimeError('controlled')):
                with self.assertRaises(RuntimeError):
                    retriever.retrieve('src/greeting.py:greeting')
            self.assertEqual((ops.CURRENT_ISSUE_ID, ops.DP_GRAPH), prior)
            (self.root / 'src/second.py').write_text('def second():\n    return 2\n')
            second = Snapshot(self.root, ['src/second.py'])
            # Construct a second source-only graph, not a graph of both tasks.
            graph2 = graph.__class__()
            graph2.add_node('src/second.py', type='file', code=second.files['src/second.py'])
            graph2.add_node('src/second.py:second', type='function',
                            code='def second():\n    return 2', start_line=1, end_line=2)
            other = LocAgentRetriever(second, graph2)
            output = other.retrieve('src/second.py')
            self.assertNotIn('greeting', output)
            self.assertIn('second', output)
            self.assertEqual((ops.CURRENT_ISSUE_ID, ops.DP_GRAPH), prior)


if __name__ == '__main__':
    unittest.main()
