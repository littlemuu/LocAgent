"""No network, credentials, paid ledger, or saved benchmark data required."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import Mock, patch

from locagent_service.offline import offline_engine
from util.localization_contract import LocalizationOptions, LocalizationRequest, ResultStatus
from util.localizer import GraphLocalizer


def setUpModule():
    global guard
    guard = offline_engine()
    guard.__enter__()


def tearDownModule():
    guard.__exit__(None, None, None)


class BoundedProtocolTests(unittest.TestCase):
    def setUp(self):
        import networkx as nx
        from litellm import ModelResponse
        self.Response = ModelResponse
        self.graph = nx.MultiDiGraph()
        self.entity = 'src/demo.py:render'
        code = 'def render(value):\n' + '    # repeatable long code\n' * 20 + '    return value'
        self.graph.add_node('.', type='directory')
        self.graph.add_node('src/demo.py', type='file', code=code)
        self.graph.add_node(self.entity, type='function', code=code, start_line=1, end_line=22)
        self.graph.add_edge('.', 'src/demo.py', type='contains')
        self.graph.add_edge('src/demo.py', self.entity, type='contains')
        self.request = LocalizationRequest('demo__demo-1', 'demo/demo', 'a'*40, 'Find render.')
        self.sent = []
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def response(self, name=None, args=None, text=None, reason=None, calls=None):
        message = {'role': 'assistant', 'content': text}
        if name:
            calls = [{'id': 'call-1', 'type': 'function', 'function': {
                'name': name, 'arguments': json.dumps(args)}}]
        if calls:
            message['tool_calls'] = calls
        return self.Response(model='offline', choices=[{'index': 0, 'message': message,
            'finish_reason': reason or ('tool_calls' if calls else 'stop')}],
            usage={'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3})

    def finish(self, **kw):
        return self.response('finish', {'files': ['src/demo.py'], 'entities': [self.entity]}, **kw)

    def run_steps(self, steps, *, max_iterations=3, suppress=True, protocol='bounded-v1'):
        values = iter(steps)
        def provider(**kwargs):
            self.sent.append(deepcopy(kwargs))
            return next(values)
        return GraphLocalizer.from_graph(self.graph, provider=provider, model_name='offline',
            options=LocalizationOptions(max_iterations, suppress, protocol)).localize(self.request)

    def test_forced_last_round_and_exact_locations(self):
        result = self.run_steps([self.response(text='Thinking'), self.finish()], max_iterations=2)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        final = self.sent[-1]
        self.assertEqual([t['function']['name'] for t in final['tools']], ['finish'])
        self.assertEqual(final['tool_choice']['function']['name'], 'finish')
        self.assertEqual(result.found_entities, [self.entity])
        self.assertEqual(result.diagnostics['termination_reason'], 'finished')

    def test_last_round_never_executes_retrieval(self):
        with patch('util.localizer._execute_tool', side_effect=AssertionError('must not execute')):
            result = self.run_steps([self.response('get_entity_contents',
                {'entity_names': [self.entity]})], max_iterations=1)
        self.assertEqual(result.diagnostics['termination_reason'], 'iteration_limit')
        self.assertEqual(result.found_files, [])

    def test_prose_with_legacy_finish_tags_is_not_success(self):
        result = self.run_steps([self.response(text='src/demo.py\nfunction: render\n<finish></finish>')],
                                max_iterations=1)
        self.assertEqual(result.diagnostics['termination_reason'], 'missing_finish')
        self.assertEqual(result.status, ResultStatus.ITERATION_LIMIT)

    def test_length_rejects_even_valid_finish_and_retains_raw(self):
        result = self.run_steps([self.finish(reason='length')])
        self.assertEqual(result.diagnostics['termination_reason'], 'output_truncated')
        self.assertEqual(result.found_files, [])
        self.assertEqual(result.iterations, 1)
        self.assertTrue(result.messages[-1]['tool_calls'])

    def test_length_with_malformed_arguments_is_diagnostic_not_execution(self):
        response = self.finish(reason='length')
        response.choices[0].message.tool_calls[0].function.arguments = '{"files":['
        result = self.run_steps([response])
        self.assertEqual(result.diagnostics['termination_reason'], 'output_truncated')

    def test_strict_finish_rejects_unknown_partial_prose_and_wrong_types(self):
        cases = [{}, {'thought': 'src/demo.py'}, {'files': ['src/demo.py'], 'entities': ['unknown']},
                 {'files': ['src/demo.py'], 'entities': [self.entity], 'extra': 1},
                 {'files': ['../src/demo.py'], 'entities': []},
                 {'files': ['src/demo.py', 'src/demo.py'], 'entities': []},
                 {'files': 'src/demo.py', 'entities': []},
                 {'files': [], 'entities': [self.entity]}]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_steps([self.response('finish', args)])
                self.assertEqual(result.diagnostics['termination_reason'], 'invalid_finish')
                self.assertEqual(result.found_files, [])

    def test_malformed_finish_and_mixed_batch_never_success(self):
        malformed = self.finish()
        malformed.choices[0].message.tool_calls[0].function.arguments = 'not JSON'
        mixed = self.finish()
        mixed.choices[0].message.tool_calls += self.response('get_entity_contents',
            {'entity_names': [self.entity]}).choices[0].message.tool_calls
        for response in [malformed, mixed]:
            result = self.run_steps([response])
            self.assertEqual(result.diagnostics['termination_reason'], 'invalid_finish')

    def test_explicit_empty_finish(self):
        result = self.run_steps([self.response('finish', {'files': [], 'entities': []})])
        self.assertEqual(result.status, ResultStatus.EMPTY)
        self.assertEqual(result.diagnostics['termination_reason'], 'finished')

    def test_root_aliases_all_real_tools_both_graph_spellings(self):
        import networkx as nx
        from plugins.location_tools.repo_ops import repo_ops as ops
        for root in ('.', '/'):
            graph = nx.relabel_nodes(self.graph, {'.': root})
            for alias in ('.', '/'):
                for tool, args in [
                    ('explore_tree_structure', {'start_entities': [alias], 'traversal_depth': 1}),
                    ('get_entity_contents', {'entity_names': [alias]}),
                    ('search_code_snippets', {'search_terms': [alias]})]:
                    with self.subTest(root=root, alias=alias, tool=tool):
                        responses = iter([self.response(tool, args), self.finish()])
                        with patch.object(ops, 'bm25_module_retrieve', side_effect=AssertionError('no fallback')):
                            result = GraphLocalizer.from_graph(graph, provider=lambda **kw: next(responses),
                                model_name='offline', options=LocalizationOptions(search_protocol='bounded-v1')).localize(self.request)
                        raw = result.diagnostics['tool_outputs']['output-1']['raw']
                        self.assertNotIn('invalid', raw.lower())
                        self.assertIn(root, raw)

    def test_root_alias_does_not_rewrite_other_paths(self):
        from util.localizer import _graph_session
        from plugins.location_tools.repo_ops import repo_ops as ops
        with _graph_session(self.graph, self.request.as_task(), None, None):
            for path in ('src/', './src', '../src', '/src/demo.py', '..', '//', '...'):
                self.assertEqual(ops._root_alias(path), path)

    def test_seen_repeats_fold_and_reach_next_provider(self):
        steps = [self.response('search_code_snippets', {'search_terms': [self.entity]}),
                 self.response('get_entity_contents', {'entity_names': [self.entity]}), self.finish()]
        result = self.run_steps(steps)
        self.assertIn('Repeated content for', self.sent[-1]['messages'][-2]['content'])
        self.assertTrue(result.return_records[self.entity][1]['previously_in_context'])

    def test_unseen_tail_never_folded_or_marked_seen(self):
        code = 'def render(value):\n' + '    # ' + 'z' * 30000
        self.graph.nodes[self.entity]['code'] = code
        self.graph.nodes[self.entity]['end_line'] = 2
        result = self.run_steps([
            self.response('get_entity_contents', {'entity_names': [self.entity]}),
            self.response('get_entity_contents', {'entity_names': [self.entity]}), self.finish()])
        for entry in result.return_records[self.entity]:
            self.assertFalse(entry['in_context'])
            self.assertFalse(entry['previously_in_context'])
            self.assertNotIn('Repeated content for', entry['output_content'])
        self.assertTrue(all(a['truncation_reason'] for a in result.diagnostics['tool_messages']))
        self.assertGreater(len(result.diagnostics['tool_outputs']['output-1']['raw']), 30000)

    def test_continuation_uses_per_run_cache_and_rejects_unknown_id(self):
        result = self.run_steps([self.response('get_entity_contents', {'entity_names': [self.entity]}),
            self.response('read_tool_output', {'output_id': 'output-1', 'offset': 0}), self.finish()])
        self.assertEqual(len(result.diagnostics['tool_outputs']), 1)
        self.assertEqual(len(result.diagnostics['tool_messages']), 2)
        second = self.run_steps([self.response('read_tool_output', {'output_id': 'output-1', 'offset': 0})])
        self.assertEqual(second.diagnostics['termination_reason'], 'invalid_tool_arguments')

    def test_request_gate_stops_before_provider_without_retries(self):
        self.request.problem_statement = 'x' * 70000
        result = self.run_steps([])
        self.assertEqual(self.sent, [])
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.diagnostics['termination_reason'], 'context_limit')

    def test_legacy_default_schema_and_serialization(self):
        response = self.response('finish', {'thought': 'src/demo.py\nfunction: render'})
        result = self.run_steps([response], protocol='legacy')
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertNotIn('diagnostics', result.to_dict())
        from locagent_service.models import LocalizationResultView
        self.assertEqual(LocalizationResultView.model_validate(result.to_dict()).model_dump(),
                         result.to_dict())
        self.assertNotIn('tool_choice', self.sent[0])
        self.assertEqual(self.sent[0]['tools'][0]['function']['parameters']['required'], ['thought'])

    def test_schema_response_preserves_diagnostics(self):
        from locagent_service.models import LocalizationResultView
        result = self.run_steps([self.finish()])
        view = LocalizationResultView.model_validate(result.to_dict()).model_dump()
        self.assertEqual(view['diagnostics'], result.diagnostics)

    def test_graph_globals_restored_for_new_failure_path(self):
        from plugins.location_tools.repo_ops import repo_ops as ops
        before = ops.DP_GRAPH
        self.run_steps([self.finish(reason='length')])
        self.assertIs(ops.DP_GRAPH, before)


class ToolPageTests(unittest.TestCase):
    def test_utf8_json_escaping_long_lines_and_lossless_continuation(self):
        from util.localization_protocol import ToolPages, encoded, TOOL_MESSAGE_BYTES
        pages = ToolPages()
        raw = ('中"\\\\\t' * 700) + '\nsecond line\n'
        key = pages.add(raw, 'test', {})
        offset, collected = 0, ''
        while offset < len(raw):
            msg = pages.page(key, offset, 'test-call', 'read_tool_output')
            audit = pages.audit[-1]
            self.assertLessEqual(len(encoded(msg)), TOOL_MESSAGE_BYTES)
            self.assertEqual(audit['message_json_bytes'], len(encoded(msg)))
            self.assertGreater(audit['end_offset'], offset)
            collected += raw[offset:audit['end_offset']]
            offset = audit['end_offset']
        self.assertEqual(collected, raw)
        self.assertEqual(pages.outputs[key]['raw'], raw)

    def test_whole_output_cumulative_limit_and_raw_retention(self):
        from util.localization_protocol import ToolPages, TOTAL_TOOL_MESSAGE_BYTES
        pages = ToolPages()
        key = pages.add('x'*80000, 'test', {})
        offset = 0
        with self.assertRaises(BufferError):
            for _ in range(20):
                pages.page(key, offset, 'call', 'test')
                offset = pages.audit[-1]['end_offset']
        self.assertLessEqual(pages.delivered_bytes, TOTAL_TOOL_MESSAGE_BYTES)
        self.assertEqual(len(pages.outputs[key]['raw']), 80000)
        self.assertLess(offset, 80000)

    def test_prefer_complete_entity_boundary(self):
        from util.localization_protocol import ToolPages
        pages = ToolPages()
        first = 'Found function `one`.\n' + 'a'*5000 + '\n'
        key = pages.add(first + 'Found function `two`.\n' + 'b'*9000, 'test', {})
        pages.page(key, 0, 'call', 'test')
        self.assertEqual(pages.audit[-1]['end_offset'], len(first))

    def test_invalid_offset_and_metadata_bounds(self):
        from util.localization_protocol import ToolPages
        pages = ToolPages()
        key = pages.add('abc', 'test', {})
        for offset in (-1, True, 4, '0'):
            with self.assertRaises(ValueError):
                pages.page(key, offset, 'call', 'test')
        with self.assertRaises(BufferError):
            pages.page(key, 0, 'x'*9000, 'test')


if __name__ == '__main__':
    unittest.main()
