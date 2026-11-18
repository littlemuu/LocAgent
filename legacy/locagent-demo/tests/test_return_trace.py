# Self-contained regression tests; no model entry point or saved graph is used.
import json
import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from util.return_trace import (
    mark_returns_in_context,
    record_return,
    refresh_returns_in_context,
)


# Guard imports as well as test bodies. A swallowed network attempt still fails
# tearDownModule, so a dependency cannot silently fall back after trying online.
def setUpModule():
    global network_guard, network_attempts
    network_guard = ExitStack()
    network_attempts = []
    unittest.addModuleCleanup(network_guard.close)

    def deny_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError('Offline tests forbid network access')

    for target in (
        'socket.create_connection', 'socket.getaddrinfo',
        'socket.socket.connect', 'socket.socket.connect_ex',
        'socket.socket.sendto',
    ):
        network_guard.enter_context(patch(target, side_effect=deny_network))


def tearDownModule():
    if network_attempts:
        raise AssertionError(f'{len(network_attempts)} forbidden network attempts')


class ReturnTraceTests(unittest.TestCase):
    def test_source_and_mode_do_not_change_content_identity(self):
        records = {}
        first = record_return(
            records, 'demo.py:render', 'Source: search\ncode', 'complete',
            comparison_content='code',
        )
        mark_returns_in_context(records, first['content'])
        second = record_return(
            records, 'demo.py:render', 'Source: read\ncode', 'preview',
            comparison_content='code',
        )
        self.assertFalse(first['repeated'])
        self.assertTrue(second['repeated'])
        self.assertTrue(second['previously_in_context'])
        self.assertNotEqual(first['content'], second['content'])

    def test_changed_content_and_other_entities_are_new(self):
        records = {}
        first = record_return(records, 'a', 'original', 'complete')
        mark_returns_in_context(records, first['content'])
        changed = record_return(records, 'a', 'changed', 'complete')
        other = record_return(records, 'b', 'original', 'complete')
        for entry in (changed, other):
            self.assertFalse(entry['repeated'])
            self.assertFalse(entry['previously_in_context'])

    def test_legacy_history_fresh_isolation_and_json_roundtrip(self):
        records = {'a': [{'content': 'code', 'in_context': True}]}
        repeated = record_return(records, 'a', 'code', 'complete')
        self.assertTrue(repeated['repeated'])
        self.assertTrue(repeated['previously_in_context'])
        snapshot = deepcopy(records)
        fresh = {}
        entry = record_return(fresh, 'a', 'code', 'complete')
        self.assertFalse(entry['repeated'])
        self.assertFalse(entry['previously_in_context'])
        self.assertEqual(records, snapshot)
        self.assertEqual(json.loads(json.dumps(records)), records)

    def test_refresh_ignores_stale_flags_and_non_observation_messages(self):
        records = {}
        entries = [record_return(records, name, name, 'complete')
                   for name in ('tool_body', 'observation_body',
                                'ordinary_user_body', 'assistant_body')]
        mark_returns_in_context(records, ' '.join(records))
        refresh_returns_in_context(records, [
            {'role': 'tool', 'content': 'tool_body'},
            {'role': 'user', 'content': 'OBSERVATION:\nobservation_body'},
            {'role': 'user', 'content': 'ordinary_user_body'},
            {'role': 'assistant', 'content': 'assistant_body'},
            {'role': 'tool', 'content': ['ordinary_user_body']},
            {'role': 'tool'},
        ])
        self.assertEqual([e['in_context'] for e in entries],
                         [True, True, False, False])
        refresh_returns_in_context(records, [])
        self.assertFalse(any(e['in_context'] for e in entries))


class RepeatOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import production tools only after the module network guard is active.
        import networkx as nx
        from dependency_graph import RepoEntitySearcher
        from dependency_graph.build_graph import (
            NODE_TYPE_FILE, NODE_TYPE_CLASS, NODE_TYPE_FUNCTION, EDGE_TYPE_CONTAINS,
        )
        from plugins.location_tools.repo_ops import repo_ops
        from plugins.location_tools.utils.result_format import QueryInfo, QueryResult
        cls.nx = nx
        cls.searcher_type = RepoEntitySearcher
        cls.file_type = NODE_TYPE_FILE
        cls.class_type = NODE_TYPE_CLASS
        cls.function_type = NODE_TYPE_FUNCTION
        cls.contains_type = EDGE_TYPE_CONTAINS
        cls.ops = repo_ops
        cls.query_info = QueryInfo
        cls.query_result = QueryResult

    def setUp(self):
        # Graph nodes hold the entire fixture; no disk, parser or BM25 index.
        self.entity = 'demo.py:render'
        self.code = '\n'.join([
            'def render(value):',
            '    # A deliberately long body makes omission save characters.',
            *['    # Keep this deterministic fixture independent of real repos.'] * 8,
            '    return value',
        ])
        graph = self.nx.MultiDiGraph()
        graph.add_node(self.entity, type=self.function_type, code=self.code,
                       start_line=1, end_line=len(self.code.splitlines()))
        graph.add_node('demo.py:tiny', type=self.function_type,
                       code='def tiny(): return 1',
                       start_line=len(self.code.splitlines()) + 2,
                       end_line=len(self.code.splitlines()) + 2)
        graph.add_node('demo.py', type=self.file_type,
                       code=self.code + '\n\ndef tiny(): return 1')
        for entity in (self.entity, 'demo.py:tiny'):
            graph.add_edge('demo.py', entity, type=self.contains_type)
        self.searcher = self.searcher_type(graph)
        injected = patch.multiple(
            self.ops, DP_GRAPH=graph, DP_GRAPH_ENTITY_SEARCHER=self.searcher,
            ALL_FILE=self.searcher.get_all_nodes_by_type(self.file_type),
            ALL_CLASS=self.searcher.get_all_nodes_by_type(self.class_type),
            ALL_FUNC=self.searcher.get_all_nodes_by_type(self.function_type),
        )
        injected.start()
        self.addCleanup(injected.stop)

    def read(self, records, enabled=True, entity=None):
        return self.ops.get_entity_contents(
            [entity or self.entity], _return_records=records,
            _suppress_repeats=enabled,
        )

    def test_search_then_read_switch_preserves_original_ledger(self):
        baseline = self.read(None, enabled=False)
        for enabled in (False, True):
            with self.subTest(suppress_repeats=enabled):
                records = {}
                first_output = self.ops.search_code_snippets(
                    search_terms=[self.entity], _return_records=records,
                    _suppress_repeats=enabled,
                )
                mark_returns_in_context(records, first_output + '\n')
                second_output = self.read(records, enabled)
                first, second = records[self.entity]
                self.assertTrue(second['repeated'])
                self.assertTrue(second['previously_in_context'])
                self.assertEqual(first['comparison_content'],
                                 second['comparison_content'])
                self.assertIn('def render(', second['content'])
                self.assertIn(second['output_content'], second_output + '\n')
                self.assertEqual(json.loads(json.dumps(records)), records)
                if enabled:
                    self.assertIn('Repeated content for', second_output)
                    self.assertNotIn('def render(', second_output)
                    self.assertLess(len(second_output), len(baseline))
                else:
                    self.assertEqual(second_output, baseline)
                    self.assertEqual(second['output_content'], second['content'])

    def test_repeated_but_unseen_content_is_returned_in_full(self):
        records = {}
        first = self.read(records)
        second = self.read(records)
        self.assertEqual(second, first)
        entry = records[self.entity][-1]
        self.assertTrue(entry['repeated'])
        self.assertFalse(entry['previously_in_context'])
        self.assertIn('def render(', second)

    def test_removed_context_restores_full_body(self):
        records = {}
        first = self.read(records)
        mark_returns_in_context(records, first + '\n')
        self.assertTrue(records[self.entity][0]['in_context'])
        refresh_returns_in_context(records, [])
        second = self.read(records)
        self.assertEqual(second, first)
        self.assertTrue(records[self.entity][-1]['repeated'])
        self.assertFalse(records[self.entity][-1]['previously_in_context'])

    def test_changed_code_is_not_suppressed(self):
        records = {}
        first = self.read(records)
        mark_returns_in_context(records, first + '\n')
        self.searcher.G.nodes[self.entity]['code'] = self.code.replace(
            'return value', 'return value + 1',
        )
        second = self.read(records)
        self.assertIn('return value + 1', second)
        self.assertNotIn('Repeated content for', second)
        self.assertFalse(records[self.entity][-1]['repeated'])
        self.assertFalse(records[self.entity][-1]['previously_in_context'])

    def test_short_content_is_not_replaced_by_a_longer_notice(self):
        records = {}
        first = self.read(records, entity='demo.py:tiny')
        mark_returns_in_context(records, first + '\n')
        second = self.read(records, entity='demo.py:tiny')
        self.assertEqual(second, first)
        self.assertTrue(records['demo.py:tiny'][-1]['previously_in_context'])
        self.assertIn('def tiny()', second)

    def test_fold_keeps_entity_hint_when_already_in_context(self):
        records = {}
        query = self.query_result(
            self.query_info(term='render'), 'fold', nid=self.entity,
        )
        first = self.ops._format_and_record(query, self.searcher, records)
        mark_returns_in_context(records, first + '\n')
        second = self.ops._format_and_record(
            query, self.searcher, records, suppress_repeats=True,
        )
        self.assertEqual(second, first)
        self.assertIn(self.entity, second)
        self.assertTrue(records[self.entity][-1]['previously_in_context'])


if __name__ == '__main__':
    unittest.main()
