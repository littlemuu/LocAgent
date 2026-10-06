import io
import json
import os
import pickle
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch

from util.localization_contract import (
    ErrorCode, InvalidRequestError, LocalizationError, LocalizationOptions,
    LocalizationRequest, LocalizationResult, ResultStatus, TokenUsage,
)
from util.localizer import GraphLocalizer, LiteLLMProvider, write_result


def setUpModule():
    global network_attempts, network_guard
    network_attempts = []
    network_guard = ExitStack()
    unittest.addModuleCleanup(network_guard.close)
    network_guard.enter_context(patch.dict(os.environ, {'LITELLM_LOCAL_MODEL_COST_MAP': 'True'}))

    def deny(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError('Stage 1 tests forbid network access')

    for name in ('socket.create_connection', 'socket.getaddrinfo',
                 'socket.socket.connect', 'socket.socket.connect_ex',
                 'socket.socket.sendto'):
        network_guard.enter_context(patch(name, side_effect=deny))


def tearDownModule():
    if network_attempts:
        raise AssertionError(f'{len(network_attempts)} forbidden network attempts')


class ContractSafetyTests(unittest.TestCase):
    def values(self):
        return dict(instance_id='demo__demo-1', repo='demo/demo',
                    base_commit='a' * 40, problem_statement='Find render.')

    def test_rejects_unsafe_instance_ids(self):
        for value in ('..', '../escape', 'a/b', 'a\\b', '/abs', 'C:foo',
                      'x\x00y', 'CON', 'x.', 'a' * 129):
            with self.subTest(value=value):
                values = self.values()
                values['instance_id'] = value
                with self.assertRaises(InvalidRequestError) as error:
                    LocalizationRequest(**values)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_REQUEST)

    def test_rejects_non_string_fields(self):
        for name in self.values():
            with self.subTest(field=name):
                values = self.values()
                values[name] = None
                with self.assertRaisesRegex(ValueError, name + ' must be a string'):
                    LocalizationRequest(**values)

    def test_repo_and_revision_validation(self):
        for field, value in (('repo', '../repo'), ('repo', 'https://example/repo'),
                             ('base_commit', 'HEAD'), ('base_commit', 'z' * 40)):
            with self.subTest(field=field, value=value):
                values = self.values()
                values[field] = value
                with self.assertRaises(InvalidRequestError):
                    LocalizationRequest(**values)

    def test_task_canonicalization_preserves_request(self):
        values = {key: f' \t{value}\n ' for key, value in self.values().items()}
        request = LocalizationRequest(**values)
        task = request.as_task()
        self.assertEqual(asdict(request), values)
        self.assertEqual(task['instance_id'], 'demo__demo-1')
        self.assertEqual(task['problem_statement'], values['problem_statement'])

    def test_options_reject_invalid_limits_and_flags(self):
        for value in (True, 0, -1, 101, 1.5):
            with self.subTest(limit=value), self.assertRaises(InvalidRequestError):
                LocalizationOptions(max_iterations=value)
        with self.assertRaises(InvalidRequestError):
            LocalizationOptions(suppress_repeats=1)

    def test_result_and_usage_invariants(self):
        for tokens in (-1, True, 1.5):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                TokenUsage(prompt_tokens=tokens)
        with self.assertRaises(ValueError):
            LocalizationResult('demo', ResultStatus.SUCCESS)
        with self.assertRaises(ValueError):
            LocalizationResult('demo', ResultStatus.EMPTY, found_files=['src/demo.py'])
        with self.assertRaises(ValueError):
            LocalizationResult('demo', ResultStatus.SUCCESS, found_files=['../escape.py'])
        with self.assertRaises(ValueError):
            LocalizationResult('demo', ResultStatus.SUCCESS, found_files='src/demo.py')


class StageOneIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import networkx as nx
        from litellm import ModelResponse
        from plugins.location_tools.repo_ops import repo_ops
        cls.nx = nx
        cls.response_type = ModelResponse
        cls.ops = repo_ops

    def setUp(self):
        self.request = LocalizationRequest('demo__demo-1', 'demo/demo', 'a' * 40,
                                           'Locate the render function.')
        self.entity = 'src/demo.py:render'
        code = '\n'.join(['def render(value):',
                          *['    # Long deterministic body for the suppression case.'] * 8,
                          '    return value'])
        self.graph = self.nx.MultiDiGraph()
        self.graph.add_node('src/demo.py', type='file', code=code)
        self.graph.add_node(self.entity, type='function', code=code,
                            start_line=1, end_line=len(code.splitlines()))
        self.graph.add_edge('src/demo.py', self.entity, type='contains')
        self.original = {key: getattr(self.ops, key) for key in (
            'CURRENT_ISSUE_ID', 'CURRENT_INSTANCE', 'DP_GRAPH',
            'DP_GRAPH_ENTITY_SEARCHER', 'DP_GRAPH_DEPENDENCY_SEARCHER',
            'ALL_FILE', 'ALL_CLASS', 'ALL_FUNC', 'REPO_SAVE_DIR',
            'GRAPH_INDEX_DIR', 'BM25_INDEX_DIR', 'bm25_content_retrieve',
            'setup_repo', 'build_code_retriever', 'build_module_retriever',
        )}
        self.addCleanup(self.assert_state_restored)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def assert_state_restored(self):
        for key, value in self.original.items():
            self.assertIs(getattr(self.ops, key), value, key)

    def response(self, content=None, tool=None, arguments=None):
        message = {'role': 'assistant', 'content': content}
        if tool:
            message['tool_calls'] = [{'id': 'offline_call', 'type': 'function',
                                     'function': {'name': tool,
                                                  'arguments': json.dumps(arguments or {})}}]
        return self.response_type(
            model='offline-test', choices=[{'index': 0, 'message': message,
                                            'finish_reason': 'tool_calls' if tool else 'stop'}],
            usage={'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3},
        )

    def final(self):
        return self.response('```\nsrc/demo.py\nfunction: render\n```\n<finish></finish>')

    def engine(self, responses=None, provider=None, **kwargs):
        if provider is None:
            provider = Mock(side_effect=responses)
        return GraphLocalizer.from_graph(self.graph, provider=provider,
                                         model_name='offline-test', **kwargs)

    def test_real_loop_tools_parser_and_suppression(self):
        sent = []
        responses = iter([
            self.response(tool='search_code_snippets', arguments={'search_terms': [self.entity]}),
            self.response(tool='get_entity_contents', arguments={'entity_names': [self.entity]}),
            self.final(),
        ])

        def provider(**kwargs):
            sent.append(deepcopy(kwargs['messages']))
            return next(responses)

        engine = self.engine(provider=provider, options=LocalizationOptions(suppress_repeats=True))
        result = engine.localize(self.request)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.found_files, ['src/demo.py'])
        self.assertEqual(result.found_entities, [self.entity])
        self.assertEqual(result.found_modules, [self.entity])
        self.assertEqual(result.iterations, 3)
        self.assertEqual(result.usage, TokenUsage(3, 6))
        self.assertEqual(json.loads(json.dumps(result.to_dict()))['status'], 'success')
        history = result.return_records[self.entity]
        self.assertEqual([row['repeated'] for row in history], [False, True])
        self.assertIn('def render(', history[1]['content'])
        observations = [m['content'] for m in sent[-1] if m['role'] == 'tool']
        self.assertIn('Repeated content for', observations[1])
        self.assertNotIn('def render(', observations[1])
        self.assertIn(self.request.problem_statement, sent[0][1]['content'])

    def test_normal_empty_result(self):
        result = self.engine([self.response('<finish></finish>')]).localize(self.request)
        self.assertEqual(result.status, ResultStatus.EMPTY)
        self.assertEqual(result.found_files, [])
        self.assertEqual(result.iterations, 1)

    def test_root_file_localization_uses_real_parser_and_tools(self):
        graph = self.nx.relabel_nodes(self.graph, {
            'src/demo.py': 'demo.py', self.entity: 'demo.py:render',
        }, copy=True)
        responses = [
            self.response(tool='get_entity_contents',
                          arguments={'entity_names': ['demo.py:render']}),
            self.response('```\ndemo.py\nfunction: render\n```\n<finish></finish>'),
        ]
        result = GraphLocalizer.from_graph(
            graph, provider=Mock(side_effect=responses), model_name='offline-test',
        ).localize(self.request)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.found_files, ['demo.py'])
        self.assertEqual(result.found_entities, ['demo.py:render'])
        self.assertEqual(result.found_modules, ['demo.py:render'])
        self.assertIn('demo.py:render', result.return_records)

    def test_root_file_parser_does_not_accept_unsafe_or_unknown_paths(self):
        graph = self.nx.relabel_nodes(self.graph, {
            'src/demo.py': 'demo.py', self.entity: 'demo.py:render',
        }, copy=True)
        for path in ('../demo.py', '/demo.py', './demo.py', 'C:\\demo.py',
                     '..\\demo.py', 'other/demo.py', 'unknown.py'):
            with self.subTest(path=path):
                response = self.response(f'{path}\nfunction: render\n<finish></finish>')
                with self.assertRaises(LocalizationError) as error:
                    GraphLocalizer.from_graph(
                        graph, provider=Mock(side_effect=[response]), model_name='offline-test',
                    ).localize(self.request)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)

    def test_shared_parser_keeps_nested_cli_path_behavior(self):
        from util.process_output import parse_raw_loc_output
        valid_files = ['demo.py', 'src/demo.py']
        for nested in ('src/demo.py', '/checkout/src/demo.py'):
            with self.subTest(nested=nested):
                files, edits = parse_raw_loc_output(
                    f'demo.py\nfunction: render\n{nested}\nfunction: render', valid_files,
                )
                self.assertEqual(files, valid_files)
                self.assertEqual(edits, ['demo.py:function: render',
                                         'src/demo.py:function: render'])

    def test_finish_tool_rejects_missing_unknown_and_non_string_arguments(self):
        invalid = ({}, {'other': 'src/demo.py'}, {'thought': 123},
                   {'thought': True}, {'thought': None}, {'thought': []},
                   {'thought': {}}, {'extra': 'src/demo.py', 'thought': ''},
                   {'thought': '', 'extra': 'src/demo.py'})
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                response = self.response(tool='finish', arguments=arguments)
                with self.assertRaises(LocalizationError) as error:
                    self.engine([response]).localize(self.request)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)
                self.assertEqual(error.exception.message, 'Provider returned an invalid response')
                self.assert_state_restored()
        for raw in ('null', '[]', '123', None):
            with self.subTest(raw=raw):
                response = self.response(tool='finish', arguments={'thought': ''})
                response.choices[0].message.tool_calls[0].function.arguments = raw
                with self.assertRaises(LocalizationError) as error:
                    self.engine([response]).localize(self.request)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)
        self.assertEqual(self.engine([self.final()]).localize(self.request).status,
                         ResultStatus.SUCCESS)

    def test_finish_tool_accepts_string_and_advertises_matching_schema(self):
        from util.runtime.finish import FinishTool
        original_schema = deepcopy(FinishTool)
        for thought, status in (('src/demo.py\nfunction: render', ResultStatus.SUCCESS),
                                ('', ResultStatus.EMPTY)):
            with self.subTest(thought=thought):
                provider = Mock(return_value=self.response(tool='finish',
                                                           arguments={'thought': thought}))
                result = self.engine(provider=provider).localize(self.request)
                self.assertEqual(result.status, status)
                schema = provider.call_args.kwargs['tools'][0]['function']['parameters']
                self.assertEqual(schema['required'], ['thought'])
                self.assertEqual(schema['properties']['thought']['type'], 'string')
                self.assertFalse(schema['additionalProperties'])
                self.assertEqual(FinishTool, original_schema)

    def test_iteration_limit_is_not_normal_empty(self):
        result = self.engine([self.response('Still searching.')],
                             options=LocalizationOptions(max_iterations=1)).localize(self.request)
        self.assertEqual(result.status, ResultStatus.ITERATION_LIMIT)
        self.assertEqual(result.found_files, [])
        self.assertEqual(result.iterations, 1)

    def test_two_runs_keep_separate_ledgers(self):
        responses = [self.response(tool='get_entity_contents',
                                   arguments={'entity_names': [self.entity]}), self.final()]
        engine = self.engine(responses * 2)
        first = engine.localize(self.request)
        snapshot = deepcopy(first.to_dict())
        second = engine.localize(self.request)
        self.assertFalse(second.return_records[self.entity][0]['repeated'])
        second.return_records[self.entity][0]['content'] = 'changed by caller'
        self.assertEqual(first.to_dict(), snapshot)
        self.assertEqual(self.graph.nodes[self.entity]['code'].splitlines()[0], 'def render(value):')

    def test_provider_failure_is_sanitized_and_state_restored(self):
        previous = os.environ.get('LITELLM_LOCAL_MODEL_COST_MAP')
        with self.assertRaises(LocalizationError) as error:
            self.engine(provider=Mock(side_effect=RuntimeError('secret=do-not-expose'))).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.MODEL_ERROR)
        self.assertNotIn('secret', json.dumps(error.exception.to_dict()))
        self.assert_state_restored()
        self.assertEqual(os.environ.get('LITELLM_LOCAL_MODEL_COST_MAP'), previous)
        self.assertEqual(self.engine([self.final()]).localize(self.request).status, ResultStatus.SUCCESS)

    def test_provider_timeout(self):
        with self.assertRaises(LocalizationError) as error:
            self.engine(provider=Mock(side_effect=TimeoutError('private detail'))).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.TIMEOUT)

    def test_sdk_timeout(self):
        from litellm import Timeout
        timeout = Timeout(message='private detail', model='offline-test', llm_provider='openai')
        with self.assertRaises(LocalizationError) as error:
            self.engine(provider=Mock(side_effect=timeout)).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.TIMEOUT)

    def test_invalid_provider_response(self):
        for response in (None, object(), self.response(tool='unknown_tool')):
            with self.subTest(response=type(response).__name__):
                with self.assertRaises(LocalizationError) as error:
                    self.engine([response]).localize(self.request)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)

    def test_invalid_final_output(self):
        with self.assertRaises(LocalizationError) as error:
            self.engine([self.response('unknown.py\n<finish></finish>')]).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)

    def test_arbitrary_python_is_rejected_without_execution(self):
        with TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'must-not-exist'
            response = self.response(
                f'<execute_ipython>open({str(sentinel)!r}, "w").write("bad")</execute_ipython>',
            )
            with self.assertRaises(LocalizationError) as error:
                self.engine([response]).localize(self.request)
            self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)
            self.assertFalse(sentinel.exists())

    def test_internal_tool_arguments_are_rejected(self):
        response = self.response(tool='get_entity_contents',
                                 arguments={'entity_names': [self.entity], '_return_records': {}})
        with self.assertRaises(LocalizationError) as error:
            self.engine([response]).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.INVALID_RESPONSE)

    def test_tool_error_restores_state(self):
        response = self.response(tool='get_entity_contents', arguments={'entity_names': [self.entity]})
        with patch.object(self.ops, 'get_entity_contents', side_effect=RuntimeError('private')):
            with self.assertRaises(LocalizationError) as error:
                self.engine([response]).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.EXECUTION_ERROR)

    def test_cancellation_restores_state_and_releases_lock(self):
        with self.assertRaises(KeyboardInterrupt):
            self.engine(provider=Mock(side_effect=KeyboardInterrupt)).localize(self.request)
        self.assert_state_restored()
        self.assertEqual(self.engine([self.final()]).localize(self.request).status, ResultStatus.SUCCESS)

    def test_missing_bm25_never_builds_or_downloads(self):
        response = self.response(tool='search_code_snippets',
                                 arguments={'search_terms': ['nonexistent_unique_keyword']})
        with patch.object(self.ops, 'setup_repo') as setup:
            with self.assertRaises(LocalizationError) as error:
                self.engine([response]).localize(self.request)
            setup.assert_not_called()
        self.assertEqual(error.exception.code, ErrorCode.INDEX_UNAVAILABLE)

    def test_prepared_bm25_keyword_search_is_offline(self):
        from dependency_graph import RepoEntitySearcher
        from llama_index.core.schema import TextNode
        from llama_index.retrievers.bm25 import BM25Retriever
        from plugins.location_tools.retriever.bm25_retriever import (
            build_module_retriever_from_graph,
        )
        module_retriever = build_module_retriever_from_graph(
            entity_searcher=RepoEntitySearcher(self.graph), similarity_top_k=2,
        )
        node = TextNode(text=self.graph.nodes[self.entity]['code'], metadata={
            'file_path': 'src/demo.py', 'span_ids': ['render'],
            'start_line': 1, 'end_line': 10,
        })
        content_retriever = BM25Retriever.from_defaults(nodes=[node], similarity_top_k=1)
        with TemporaryDirectory() as directory:
            content_retriever.persist(str(Path(directory) / self.request.instance_id))
            response = self.response(tool='search_code_snippets',
                                     arguments={'search_terms': ['deterministic']})
            result = self.engine([response, self.final()],
                                 module_retriever=module_retriever,
                                 bm25_index_dir=directory).localize(self.request)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn(self.entity, result.return_records)
        self.assertIn('def render(', result.return_records[self.entity][0]['content'])

    def test_mutated_request_rejected_before_graph_loader(self):
        loader = Mock(return_value=self.graph)
        provider = Mock()
        engine = GraphLocalizer(loader, provider=provider, model_name='offline-test')
        self.request.instance_id = '../escape'
        with self.assertRaises(InvalidRequestError):
            engine.localize(self.request)
        loader.assert_not_called()
        provider.assert_not_called()

    def test_unsafe_graph_paths_are_rejected_before_provider(self):
        self.graph.add_node('../escape.py', type='file', code='pass')
        provider = Mock()
        with self.assertRaises(LocalizationError) as error:
            self.engine(provider=provider).localize(self.request)
        self.assertEqual(error.exception.code, ErrorCode.INDEX_UNAVAILABLE)
        provider.assert_not_called()

    def test_trusted_index_loading_and_symlink_rejection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / (self.request.instance_id + '.pkl')
            with path.open('wb') as stream:
                pickle.dump(self.graph, stream)
            engine = GraphLocalizer.from_index_dir(root, provider=Mock(side_effect=[self.final()]),
                                                    model_name='offline-test')
            self.assertEqual(engine.localize(self.request).status, ResultStatus.SUCCESS)
            path.unlink()
            with self.assertRaises(LocalizationError) as error:
                engine.localize(self.request)
            self.assertEqual(error.exception.code, ErrorCode.INDEX_UNAVAILABLE)
            elsewhere = root / 'elsewhere.pkl'
            elsewhere.write_bytes(b'not a graph')
            path.symlink_to(elsewhere)
            with self.assertRaises(LocalizationError) as error:
                engine.localize(self.request)
            self.assertEqual(error.exception.code, ErrorCode.INDEX_UNAVAILABLE)

    def test_overlapping_calls_are_explicitly_busy(self):
        entered, release = Event(), Event()
        outcomes = []

        def provider(**kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError()
            return self.response('<finish></finish>')

        engine = self.engine(provider=provider)

        def run():
            try:
                outcomes.append(engine.localize(self.request))
            except BaseException as error:
                outcomes.append(error)

        thread = Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaises(LocalizationError) as error:
                self.engine([self.final()]).localize(self.request)
            self.assertEqual(error.exception.code, ErrorCode.BUSY)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], LocalizationResult)

    def test_legacy_queue_wrapper_uses_shared_core(self):
        import auto_search_main as main
        queue = Queue()
        with patch.object(main, 'request_model', return_value=self.final()), \
                patch.object(main.litellm, 'completion', side_effect=AssertionError('No live models')):
            main.auto_search_process(queue, 'offline-test', [{'role': 'user', 'content': 'Find render'}],
                                     'Continue', max_iteration_num=2)
        raw, messages, trajectory = queue.get_nowait()
        self.assertIn('src/demo.py', raw)
        self.assertEqual(trajectory['termination_reason'], 'finished')
        self.assertEqual(trajectory['iterations'], 1)
        self.assertEqual(messages[-1]['role'], 'assistant')

    def test_legacy_bad_request_queue_protocol(self):
        import auto_search_main as main
        import litellm
        queue = Queue()
        exception = litellm.BadRequestError('offline', 'offline-test', 'openai')
        with patch.object(main, 'request_model', side_effect=exception):
            main.auto_search_process(queue, 'offline-test', [{'role': 'user', 'content': 'Find render'}],
                                     'Continue', max_iteration_num=1)
        self.assertEqual(queue.get_nowait()['type'], 'BadRequestError')

    def test_explicit_export_and_no_overwrite(self):
        result = self.engine([self.final()]).localize(self.request)
        with TemporaryDirectory() as directory:
            path = write_result(result, directory)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['status'], 'success')
            original = path.read_bytes()
            with self.assertRaises(LocalizationError) as error:
                write_result(result, directory)
            self.assertEqual(error.exception.code, ErrorCode.OUTPUT_ERROR)
            self.assertEqual(path.read_bytes(), original)

    def test_export_rejects_symlink_and_mutated_id(self):
        result = self.engine([self.final()]).localize(self.request)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'untouched.txt'
            target.write_text('original')
            (root / (result.instance_id + '.json')).symlink_to(target)
            with self.assertRaises(LocalizationError):
                write_result(result, root)
            self.assertEqual(target.read_text(), 'original')
            output_alias = root / 'alias'
            output_alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(LocalizationError):
                write_result(result, output_alias)
            result.instance_id = '../escape'
            with self.assertRaises(LocalizationError):
                write_result(result, root)


if __name__ == '__main__':
    unittest.main()
