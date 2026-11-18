"""Real BM25 boundary and safe error-chain tests; no model or repository execution."""
import json
import tempfile
import traceback
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from locagent_service.offline import offline_engine
from util.localizer import _execute_tool, _graph_session, _tool_cause_chain
from util.localization_contract import LocalizationError, ErrorCode
import test_bounded_protocol as fixtures


def setUpModule():
    global guard
    guard = offline_engine()
    guard.__enter__()


def tearDownModule():
    guard.__exit__(None, None, None)


class EmptyQueryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from llama_index.retrievers.bm25 import BM25Retriever
        from llama_index.core.schema import TextNode
        from plugins.location_tools.retriever.bm25_retriever import retrieve_nonempty, has_bm25_tokens
        cls.retrieve = staticmethod(retrieve_nonempty)
        cls.has_tokens = staticmethod(has_bm25_tokens)
        cls.retriever = BM25Retriever.from_defaults(
            nodes=[TextNode(text='alpha rendering validator'),TextNode(text='beta validation renderer')],
            similarity_top_k=2)

    def test_real_upstream_minimal_reproduction_and_guard(self):
        fragment = r'[\w.@+-]+$'
        with self.assertRaises(IndexError):
            self.retriever.retrieve(fragment)
        self.assertEqual(self.retrieve(self.retriever,fragment),[])

    def test_empty_punctuation_regex_stopwords_do_not_retrieve(self):
        for query in ['', ' \t\n', '!!!', r'[\w.@+-]+$', 'the and or', 'a', 'x']:
            with self.subTest(query=query),patch.object(type(self.retriever),'retrieve',
                                                       side_effect=AssertionError('must not rank empty tokens')):
                self.assertFalse(self.has_tokens(query))
                self.assertEqual(self.retrieve(self.retriever,query),[])

    def test_nonempty_ranking_scores_and_format_unchanged(self):
        for query in ['alpha','validation','alpha beta','^validator$','zzunknownzz']:
            with self.subTest(query=query):
                expected=self.retriever.retrieve(query)
                actual=self.retrieve(self.retriever,query)
                self.assertEqual([(n.node.node_id,n.score,n.text) for n in actual],
                                 [(n.node.node_id,n.score,n.text) for n in expected])

    def test_persisted_retriever_uses_same_guard(self):
        from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
        with tempfile.TemporaryDirectory() as temp:
            self.retriever.persist(temp)
            loaded=build_retriever_from_persist_dir(temp)
            self.assertEqual(self.retrieve(loaded,'the and or'),[])
            self.assertEqual([n.text for n in self.retrieve(loaded,'alpha')],
                             [n.text for n in loaded.retrieve('alpha')])

    def test_nonempty_internal_indexerror_is_not_silently_empty(self):
        with patch.object(type(self.retriever),'retrieve',side_effect=IndexError('internal failure')):
            with self.assertRaises(IndexError):self.retrieve(self.retriever,'validator')

    def test_module_internal_indexerror_is_not_swallowed(self):
        from plugins.location_tools.repo_ops import repo_ops as ops
        with patch.object(ops,'get_graph_entity_searcher'),patch.object(ops,'build_module_retriever',return_value=self.retriever),patch.object(type(self.retriever),'retrieve',side_effect=IndexError('internal failure')):
            with self.assertRaises(IndexError):ops.bm25_module_retrieve('validator')

    def test_content_internal_indexerror_is_not_swallowed(self):
        from plugins.location_tools.repo_ops import repo_ops as ops
        from plugins.location_tools.utils.result_format import QueryInfo
        with patch.object(ops,'BM25_INDEX_DIR','unused-local-index'),patch.object(ops,'get_current_issue_data',return_value={'instance_id':'test'}),patch.object(ops.os.path,'exists',return_value=True),patch.object(ops,'load_retriever',return_value=self.retriever),patch.object(type(self.retriever),'retrieve',side_effect=IndexError('internal failure')):
            with self.assertRaises(IndexError):ops.bm25_content_retrieve(QueryInfo(term='validator'))


class GraphQueryBoundaryTests(unittest.TestCase):
    setUp = fixtures.BoundedProtocolTests.setUp

    def test_tokenless_queries_do_not_fuzzy_match_or_record_content(self):
        with _graph_session(deepcopy(self.graph),self.request.as_task(),None,None) as ops:
            for query in ['', ' ', '!!!', r'[\w.@+-]+$', 'the and or']:
                records={}
                with self.subTest(query=query),patch.object(ops,'fuzzy_retrieve',side_effect=AssertionError('no fuzzy search')),patch.object(ops,'bm25_content_retrieve',side_effect=AssertionError('no content search')):
                    result=ops.search_code_snippets(search_terms=[query],_return_records=records)
                    self.assertEqual(result,'No locations found.')
                    self.assertEqual(records,{})

    def test_exact_stopword_entity_is_still_accessible(self):
        graph=deepcopy(self.graph)
        graph.add_node('src/demo.py:the',type='function',code='def the(): pass',start_line=25,end_line=25)
        graph.add_edge('src/demo.py','src/demo.py:the',type='contains')
        with _graph_session(graph,self.request.as_task(),None,None) as ops:
            result=ops.search_code_snippets(search_terms=['the'])
            self.assertIn('def the()',result)

    def test_mixed_empty_and_valid_query_preserves_dedup_records(self):
        for suppress in [False,True]:
            captured=[]
            for queries in [[self.entity],[r'[\w.@+-]+$',self.entity]]:
                with _graph_session(deepcopy(self.graph),self.request.as_task(),None,None) as ops:
                    records={}
                    from util.return_trace import mark_returns_in_context
                    outputs=[ops.search_code_snippets(search_terms=queries,_return_records=records,_suppress_repeats=suppress)]
                    mark_returns_in_context(records,outputs[0]+'\n')
                    outputs.append(ops.search_code_snippets(search_terms=queries,_return_records=records,_suppress_repeats=suppress))
                    if suppress:self.assertIn('Repeated content',outputs[1])
                    captured.append((outputs,records))
            self.assertEqual(captured[0],captured[1])

    def test_context_eviction_restores_content_after_tokenless_query(self):
        from util.return_trace import mark_returns_in_context,refresh_returns_in_context
        with _graph_session(deepcopy(self.graph),self.request.as_task(),None,None) as ops:
            records={}
            first=ops.search_code_snippets(search_terms=[self.entity],_return_records=records,_suppress_repeats=True)
            mark_returns_in_context(records,first+'\n')
            self.assertIn('Repeated content',ops.search_code_snippets(search_terms=[self.entity],_return_records=records,_suppress_repeats=True))
            before=deepcopy(records)
            self.assertEqual(ops.search_code_snippets(search_terms=['!!!'],_return_records=records,_suppress_repeats=True),'No locations found.')
            self.assertEqual(records,before)
            refresh_returns_in_context(records,[])
            restored=ops.search_code_snippets(search_terms=[self.entity],_return_records=records,_suppress_repeats=True)
            self.assertEqual(restored,first)

    def test_default_and_explicit_suppression_false_identical(self):
        with _graph_session(deepcopy(self.graph),self.request.as_task(),None,None) as ops:
            self.assertEqual(ops.search_code_snippets(search_terms=[self.entity]),
                             ops.search_code_snippets(search_terms=[self.entity],_suppress_repeats=False))


class SafeToolDiagnosticsTests(unittest.TestCase):
    def test_nested_causes_keep_type_and_frames_without_secret_messages(self):
        secret='SENSITIVE_'+'diagnostic_canary_734'
        def fail(**kwargs):
            try:raise ValueError(secret)
            except ValueError as exc:
                error=IndexError(secret);error.add_note(secret)
                raise error from exc
        error=None
        try:_execute_tool(SimpleNamespace(search_code_snippets=fail),'print(search_code_snippets(**{}))',
                          return_records={},suppress_repeats=False)
        except LocalizationError as exc:error=exc
        self.assertIsNotNone(error)
        self.assertEqual(error.to_dict(),{'code':'execution_error','message':'Graph tool execution failed'})
        self.assertIsNone(error.__context__)
        self.assertEqual(error.__cause__.original_type,'builtins.IndexError')
        self.assertEqual(error.__cause__.__cause__.original_type,'builtins.ValueError')
        self.assertTrue(error.__cause__.frames)
        formatted=''.join(traceback.format_exception(error))
        self.assertNotIn(secret,formatted)
        self.assertIn('fail',formatted)

    def test_exception_str_is_never_evaluated(self):
        class Unsafe(Exception):
            def __str__(self):raise AssertionError('must not stringify original')
        safe=_tool_cause_chain(Unsafe())
        self.assertIn('Unsafe',str(safe))

    def test_cycles_are_bounded(self):
        error=RuntimeError('private');error.__cause__=error
        safe=_tool_cause_chain(error)
        self.assertIn('cycle',str(safe.__cause__))

    def test_stable_localization_error_classification_is_preserved(self):
        original=LocalizationError(ErrorCode.INDEX_UNAVAILABLE,'Prepared index unavailable')
        def fail(**kwargs):raise original
        with self.assertRaises(LocalizationError) as caught:
            _execute_tool(SimpleNamespace(search_code_snippets=fail),'print(search_code_snippets(**{}))',
                          return_records={},suppress_repeats=False)
        self.assertIs(caught.exception,original)

    def test_falsey_explicit_cause_is_preserved_without_bool(self):
        secret = 'R3_FALSE_' + 'synthetic_canary'
        bool_calls = []
        class FalseCause(ValueError):
            def __bool__(self):
                bool_calls.append(True)
                return False
        def fail(**kwargs):
            raise IndexError(secret) from FalseCause(secret)
        with self.assertRaises(LocalizationError) as caught:
            _execute_tool(SimpleNamespace(search_code_snippets=fail),
                          'print(search_code_snippets(**{}))',
                          return_records={},suppress_repeats=False)
        error = caught.exception
        self.assertEqual(bool_calls, [])
        self.assertEqual(error.to_dict(), {'code':'execution_error','message':'Graph tool execution failed'})
        self.assertIsNone(error.__context__)
        self.assertEqual(error.__cause__.original_type, 'builtins.IndexError')
        self.assertTrue(error.__cause__.__cause__.original_type.endswith('FalseCause'))
        self.assertNotIn(secret, ''.join(traceback.format_exception(error)))

    def test_raising_cause_bool_cannot_escape_safe_projection(self):
        secret = 'R3_BOOL_' + 'synthetic_canary'
        bool_calls = []
        class UnsafeBool(ValueError):
            def __bool__(self):
                bool_calls.append(True)
                raise RuntimeError(secret)
        def fail(**kwargs):
            raise IndexError(secret) from UnsafeBool(secret)
        error = None
        try:
            _execute_tool(SimpleNamespace(search_code_snippets=fail),
                          'print(search_code_snippets(**{}))',
                          return_records={},suppress_repeats=False)
        except Exception as caught:
            error = caught
        self.assertIsInstance(error, LocalizationError)
        self.assertEqual(bool_calls, [])
        self.assertEqual(error.to_dict(), {'code':'execution_error','message':'Graph tool execution failed'})
        self.assertIsNone(error.__context__)
        self.assertTrue(error.__cause__.__cause__.original_type.endswith('UnsafeBool'))
        self.assertNotIn(secret, ''.join(traceback.format_exception(error)))
        cause = error.__cause__
        while cause is not None:
            self.assertIsNone(cause.__context__)
            self.assertIsNone(cause.__traceback__)
            self.assertFalse(hasattr(cause, '__notes__'))
            cause = cause.__cause__
