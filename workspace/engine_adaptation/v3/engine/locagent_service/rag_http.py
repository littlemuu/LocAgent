"""HTTP retrieval integration: explicit modes, immutable cache, no live transport.

Cached bundles are operator-owned JSON addressed by SHA256. They contain existing
document/query vectors, never credentials or instructions to download a model.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from locagent_service.rag_graph_adapter import GraphModuleRetriever
from locagent_service.rag_offline import (
    ExactIndex, ProviderError, SearchConfig, Version, chunk_snapshot, vector,
)


class RagExecutionError(ValueError):
    code = 'rag_unavailable'

    def __init__(self):
        super().__init__('Requested retrieval could not execute with the pinned cache')


def text_key(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class CachedEmbeddings:
    def __init__(self, model, dimensions, queries):
        self.model, self.dimensions, self.queries = model, dimensions, queries

    def embed(self, texts):
        try:
            return [self.queries[text_key(text)] for text in texts]
        except KeyError:
            raise ProviderError('Query embedding is absent from the pinned cache') from None


class FixtureEmbeddings:
    """Synthetic vectors for demo-v1 only; not a semantic embedding model."""
    model = 'synthetic-demo-v1'
    dimensions = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class TracedRetriever(GraphModuleRetriever):
    def __init__(self, *args, index_id, embedding_kind, **kwargs):
        super().__init__(*args, **kwargs)
        self.index_id, self.embedding_kind = index_id, embedding_kind
        self.searches = []
        self.failure = None

    def retrieve(self, query):
        try:
            hits = super().retrieve(query)
        except Exception:
            self.failure = RagExecutionError()
            raise self.failure from None
        self.searches.append(dict(self.last_diagnostics))
        return hits

    def finish(self, result):
        # Legacy tool execution can convert an exception into tool feedback. A
        # failed RAG search must still fail the task, even if a model later finishes.
        if self.failure is not None:
            raise self.failure
        result.diagnostics = dict(result.diagnostics or {})
        result.diagnostics['retrieval'] = {
            'requested_mode': self.config.mode,
            'executed_modes': sorted({s['mode'] for s in self.searches}),
            'search_count': len(self.searches),
            'degraded': any(s['degraded'] for s in self.searches),
            'reasons': sorted({s['reason'] for s in self.searches if s['reason']}),
            'index_id': self.index_id,
            'embedding': self.embedding_kind,
            'version': asdict(self.version),
            'quality_evaluated': False,
        }
        return result


def _cached(options, task, snapshot, graph):
    root = Path(os.environ.get('LOCAGENT_RAG_CACHE_ROOT', ''))
    if not root.is_absolute() or root != root.resolve():
        raise RagExecutionError()
    path = root / (options.index_id + '.json')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise RagExecutionError()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != options.index_id:
        raise RagExecutionError()
    payload = json.loads(raw)
    if set(payload) != {'format', 'version', 'dimensions', 'vectors', 'queries'} or payload['format'] != 'locagent-rag-cache-v1':
        raise RagExecutionError()
    version = Version(**payload['version'])
    if (version.repo, version.commit) != (task['repo'], task['base_commit']):
        raise RagExecutionError()
    dimensions = payload['dimensions']
    if type(dimensions) is not int or not 1 <= dimensions <= 2000:
        raise RagExecutionError()
    files = {}
    from locagent_service.rag_offline import allowed
    for p in snapshot.rglob('*.py'):
        relative = p.relative_to(snapshot).as_posix()
        if not allowed(relative):
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(snapshot.resolve()):
            raise RagExecutionError()
        files[relative] = p.read_bytes()
    chunks = tuple(c for c in chunk_snapshot(files, version)
                   if c.path + (':' + c.entity if c.entity else '') in graph)
    values, queries = payload['vectors'], payload['queries']
    if not chunks or not isinstance(values, dict) or set(values) != {c.id for c in chunks}:
        raise RagExecutionError()
    if not isinstance(queries, dict) or len(queries) > 20000:
        raise RagExecutionError()
    import re
    if any(not re.fullmatch('[a-f0-9]{64}', k) for k in queries):
        raise RagExecutionError()
    queries = {k: vector(v, dimensions) for k, v in queries.items()}
    index = ExactIndex(version, dimensions, tuple((c, vector(values[c.id], dimensions)) for c in chunks))
    return version, chunks, index, CachedEmbeddings(version.model, dimensions, queries)


def build_retriever(options, lexical, graph, task, *, snapshot=None, demo_code=None):
    if options.mode == 'bm25':
        return lexical
    try:
        if demo_code is not None:
            provider = FixtureEmbeddings()
            version = Version(task['repo'], task['base_commit'], provider.model)
            chunks = chunk_snapshot({'demo.py': demo_code.encode()}, version)
            index = ExactIndex.build(version, chunks, provider)
            index_id, kind = 'demo-v1', 'synthetic-fixture'
        else:
            version, chunks, index, provider = _cached(options, task, snapshot, graph)
            index_id, kind = options.index_id, 'cache-only'
        return TracedRetriever(lexical, version, chunks, graph,
            index=index, provider=provider,
            config=SearchConfig(options.mode, options.fallback, options.top_k),
            index_id=index_id, embedding_kind=kind)
    except RagExecutionError:
        raise
    except Exception:
        raise RagExecutionError() from None


def localize(engine, task, retriever):
    try:
        result = engine.localize(task)
    except Exception:
        if isinstance(retriever, TracedRetriever) and retriever.failure is not None:
            raise retriever.failure from None
        raise
    return retriever.finish(result) if isinstance(retriever, TracedRetriever) else result
