"""No-cost HTTP/engine contracts. Real DB/process checks are a separate runner."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from locagent_service.api import create_app
from locagent_service.config import Settings
from locagent_service.fixture import localize_demo
from locagent_service.models import CreateTask, RetrievalOptions, TaskRequest, TaskView
from locagent_service.offline import offline_engine
from locagent_service import rag_http
from locagent_service.rag_offline import Version, chunk_snapshot
from locagent_service.sources import canonical, digest


class RetrievalContractTests(unittest.TestCase):
    def test_legacy_persisted_request_gets_bm25_without_cache(self):
        request = CreateTask.model_validate({'problem_statement': 'render'}, context={'persisted_task': True})
        self.assertEqual(request.retrieval.mode, 'bm25')
        with patch.object(rag_http, '_cached', side_effect=AssertionError('cache accessed')):
            lexical = object()
            self.assertIs(rag_http.build_retriever(request.retrieval, lexical, {}, {}), lexical)

    def test_reject_invalid_modes_paths_and_live_grant_reuse(self):
        for retrieval in ({'mode': 'unknown'}, {'mode': 'dense', 'top_k': True},
                          {'mode': 'dense', 'top_k': 51}, {'mode': 'dense', 'index_id': '../x'},
                          {'mode': 'dense', 'provider': 'paid'}, {'mode': 'bm25', 'fallback': 'bm25'}):
            with self.subTest(retrieval=retrieval), self.assertRaises(ValidationError):
                TaskRequest(problem_statement='render', retrieval=retrieval)
        public = dict(source_id='github-v1', repository_url='https://github.com/a/b',
                      problem_statement='render', retrieval={'mode': 'dense'})
        with self.assertRaises(ValidationError):
            TaskRequest(**public)
        public['retrieval']['index_id'] = 'b' * 64
        TaskRequest(**public)
        with self.assertRaises(ValidationError):
            TaskRequest(**public, authorization_id='c' * 64, ref='a' * 40, max_attempts=1)

    def test_demo_runs_real_dense_and_hybrid_retrieval(self):
        for mode in ('dense', 'hybrid'):
            with self.subTest(mode=mode), offline_engine():
                result = localize_demo(CreateTask(problem_statement='Find render', retrieval={'mode': mode}))
                self.assertEqual(result.found_entities, ['demo.py:render'])
                self.assertIn('def render', result.return_records['demo.py:render'][0]['content'])
                trace = result.diagnostics['retrieval']
                self.assertEqual(trace['executed_modes'], [mode])
                self.assertEqual(trace['search_count'], 1)
                self.assertFalse(trace['degraded'])
                self.assertEqual(trace['embedding'], 'synthetic-fixture')
                self.assertFalse(trace['quality_evaluated'])

    def test_no_search_does_not_claim_rag_executed(self):
        result = localize_demo(CreateTask(problem_statement='render', demo_scenario='empty', retrieval={'mode': 'dense'}))
        self.assertEqual(result.diagnostics['retrieval']['executed_modes'], [])
        self.assertEqual(result.diagnostics['retrieval']['search_count'], 0)

    def test_http_serializes_mode_result_and_recovers_by_task_id(self):
        # A disk-backed test double exercises the HTTP wire boundary, NOT PostgreSQL.
        with TemporaryDirectory() as tmp:
            record = Path(tmp) / 'task.json'
            class DiskStore:
                def check_ready(self): pass
                def create(self, request, idempotency_key=None):
                    task = TaskView(id=uuid4(), status='queued', request=CreateTask.model_validate(request.model_dump()),
                        created_at=datetime.now(timezone.utc), started_at=None, finished_at=None,
                        worker_id=None, result=None, error=None)
                    record.write_text(task.model_dump_json())
                    return task
                def get(self, task_id):
                    return TaskView.model_validate_json(record.read_text(), context={'persisted_task': True})
            with patch('locagent_service.api.TaskStore', side_effect=lambda settings: DiskStore()):
                settings = Settings('postgresql://localhost/not-used')
                with TestClient(create_app(settings)) as client:
                    response = client.post('/tasks', json={'problem_statement': 'render', 'retrieval': {'mode': 'hybrid'}})
                    self.assertEqual(response.status_code, 202)
                    location = response.headers['Location']
                payload = json.loads(record.read_text())
                payload.update(status='completed', result=localize_demo(CreateTask(**payload['request'])).to_dict())
                record.write_text(json.dumps(payload))
                with TestClient(create_app(settings)) as restarted:
                    restored = restarted.get(location).json()
                self.assertEqual(restored['request']['retrieval']['mode'], 'hybrid')
                self.assertEqual(restored['result']['diagnostics']['retrieval']['executed_modes'], ['hybrid'])


class CachedRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.snapshot = self.root / 'repo'; self.snapshot.mkdir()
        self.code = 'def render(value):\n' + '    # controlled cache fixture\n' * 8 + '    return value\n'
        (self.snapshot / 'demo.py').write_text(self.code)
        self.version = Version('a/b', 'a' * 40, 'precomputed-test-v1')
        self.chunks = chunk_snapshot({'demo.py': self.code.encode()}, self.version)
        self.graph = {'demo.py', 'demo.py:render'}
        self.task = {'repo': 'a/b', 'base_commit': 'a' * 40}
        self.payload = {'format': 'locagent-rag-cache-v1', 'version': asdict(self.version),
            'dimensions': 2, 'vectors': {c.id: [1, 0] for c in self.chunks},
            'queries': {rag_http.text_key('render'): [1, 0], rag_http.text_key('locate rendering behavior'): [1, 0]}}
        env = patch.dict(os.environ, {'LOCAGENT_RAG_CACHE_ROOT': str(self.root)})
        env.start(); self.addCleanup(env.stop)
        self.lexical = Mock(stemmer=None)
        self.lexical.retrieve.return_value = [SimpleNamespace(text='demo.py:render', score=1)]

    def options(self, **extra):
        raw = canonical(self.payload)
        identity = digest(raw)
        (self.root / (identity + '.json')).write_bytes(raw)
        return RetrievalOptions(mode='hybrid', index_id=identity, **extra)

    def adapter(self, **extra):
        return rag_http.build_retriever(self.options(**extra), self.lexical, self.graph,
                                       self.task, snapshot=self.snapshot)

    def test_cached_dense_and_hybrid_use_real_exact_search(self):
        for mode in ('dense', 'hybrid'):
            options = self.options().model_copy(update={'mode': mode})
            with offline_engine():
                adapter = rag_http.build_retriever(options, self.lexical, self.graph, self.task, snapshot=self.snapshot)
                self.assertEqual([hit.text for hit in adapter.retrieve('render')], ['demo.py:render'])
                self.assertEqual(adapter.last_diagnostics['mode'], mode)
            self.assertEqual(adapter.embedding_kind, 'cache-only')

    def test_missing_query_fails_even_if_tool_swallowed_error(self):
        adapter = self.adapter()
        with self.assertRaises(rag_http.RagExecutionError): adapter.retrieve('unknown query')
        with self.assertRaises(rag_http.RagExecutionError): adapter.finish(SimpleNamespace(diagnostics=None))

    def test_explicit_fallback_is_visible(self):
        adapter = self.adapter(fallback='bm25')
        adapter.retrieve('unknown query')
        adapter.retrieve('render')
        result = adapter.finish(SimpleNamespace(diagnostics=None))
        trace = result.diagnostics['retrieval']
        self.assertTrue(trace['degraded'])
        self.assertEqual(trace['executed_modes'], ['bm25', 'hybrid'])
        self.assertEqual(trace['reasons'], ['ProviderError'])

    def test_reject_cross_commit_changed_source_and_incomplete_membership(self):
        options = self.options()
        with self.assertRaises(rag_http.RagExecutionError):
            rag_http.build_retriever(options, self.lexical, self.graph, dict(self.task, base_commit='b' * 40), snapshot=self.snapshot)
        (self.snapshot / 'demo.py').write_text(self.code.replace('return value', 'return None'))
        with self.assertRaises(rag_http.RagExecutionError):
            rag_http.build_retriever(options, self.lexical, self.graph, self.task, snapshot=self.snapshot)
        (self.snapshot / 'demo.py').write_text(self.code)
        self.payload['vectors'] = {}
        with self.assertRaises(rag_http.RagExecutionError): self.adapter()

    def test_reject_tampered_symlink_and_missing_cache(self):
        options = self.options(); path = self.root / (options.index_id + '.json')
        path.write_text('{}')
        with self.assertRaises(rag_http.RagExecutionError):
            rag_http.build_retriever(options, self.lexical, self.graph, self.task, snapshot=self.snapshot)
        path.unlink(); path.symlink_to(self.snapshot / 'demo.py')
        with self.assertRaises(rag_http.RagExecutionError):
            rag_http.build_retriever(options, self.lexical, self.graph, self.task, snapshot=self.snapshot)
        path.unlink()
        with self.assertRaises(rag_http.RagExecutionError):
            rag_http.build_retriever(options, self.lexical, self.graph, self.task, snapshot=self.snapshot)

    def test_public_pipeline_forwards_mode_to_real_prepared_engine(self):
        # Real graph/BM25 build + cached exact vectors + tool loop. Acquisition and
        # LLM are controlled fixtures; there is no GitHub/embedding/model call.
        from locagent_service.prepare import build_indexes
        from locagent_service.sources import file_hashes
        from locagent_service.public_pipeline import fake_localize
        bundle = self.root / 'bundle'; bundle.mkdir()
        self.snapshot.rename(bundle / 'repo'); self.snapshot = bundle / 'repo'
        with offline_engine():
            build_indexes(self.snapshot, bundle, 'cache-test', top_k=2)
            manifest = {'version': 2, 'bundle': 'bundle', 'task': dict(self.task,
                instance_id='cache-test', problem_statement='locate rendering behavior'),
                'config': {'model': 'fake-only', 'top_k': 2, 'max_calls': 6, 'search_protocol': 'bounded-v1'},
                'artifacts': file_hashes(bundle), 'engine': {}}
            raw = canonical(manifest); source_id = 'prepared-' + digest(raw)
            (self.root / (source_id + '.json')).write_bytes(raw)
            request = CreateTask(source_id='github-v1', repository_url='https://github.com/a/b',
                problem_statement='locate rendering behavior', retrieval=self.options())
            with patch.dict(os.environ, {'LOCAGENT_SOURCE_ROOT': str(self.root)}):
                result = fake_localize(request, source_id)
        self.assertEqual(result.found_files, [])  # Fixed fake finish is not accuracy proof.
        self.assertEqual(result.diagnostics['retrieval']['executed_modes'], ['hybrid'])
        self.assertEqual(result.diagnostics['retrieval']['embedding'], 'cache-only')
        self.assertIn('demo.py:render', result.return_records)
        # Failure/fallback must survive the real tool and public fake-model path.
        self.payload['queries'] = {}
        request.retrieval = self.options()
        with patch.dict(os.environ, {'LOCAGENT_SOURCE_ROOT': str(self.root)}):
            with self.assertRaises(rag_http.RagExecutionError):
                fake_localize(request, source_id)
            request.retrieval = self.options(fallback='bm25')
            degraded = fake_localize(request, source_id)
        self.assertTrue(degraded.diagnostics['retrieval']['degraded'])
        self.assertEqual(degraded.diagnostics['retrieval']['executed_modes'], ['bm25'])
