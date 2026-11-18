"""Offline compatibility probe; only reviewed engines, never target-code imports."""
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import pickle
import pickletools
import resource
import sys
import tempfile
import time

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def restricted_graph(path, expected):
    import networkx as nx
    from networkx.classes.coreviews import MultiAdjacencyView
    data = path.read_bytes()
    assert sha(data) == expected and len(data) < 16 * 1024 * 1024
    forbidden = {'REDUCE', 'NEWOBJ_EX', 'PERSID', 'BINPERSID', 'EXT1', 'EXT2', 'EXT4'}
    assert not any(op.name in forbidden for op, _, _ in pickletools.genops(data))
    allowed = {('networkx.classes.multidigraph', 'MultiDiGraph'): nx.MultiDiGraph,
               ('networkx.classes.coreviews', 'MultiAdjacencyView'): MultiAdjacencyView}
    class Reader(pickle.Unpickler):
        def find_class(self, module, name):
            if (module, name) not in allowed:
                raise ValueError('unapproved_pickle_global')
            return allowed[(module, name)]
        def persistent_load(self, pid):
            raise ValueError('pickle_persistent_reference')
    graph = Reader(io.BytesIO(data)).load()
    assert type(graph) is nx.MultiDiGraph
    assert len(graph) < 20000
    for name, attrs in graph.nodes(data=True):
        assert isinstance(name, str) and type(attrs) is dict
        assert set(attrs) <= {'type', 'code', 'start_line', 'end_line'}
        assert all(type(v) in (str, int) for v in attrs.values())
    return graph


def summary(graph):
    nodes = {name: {k: (sha(v.encode()) if k == 'code' else v)
                    for k, v in data.items()} for name, data in sorted(graph.nodes(data=True))}
    edges = sorted((a, b, d['type']) for a, b, d in graph.edges(data=True))
    return {'nodes': nodes, 'node_count': len(nodes), 'edge_count': len(edges),
            'edges_sha256': sha(encode(edges)), 'nodes_sha256': sha(encode(nodes))}


def probe_retrieval(snapshot, graph, queries):
    from readonly_agent.locagent import LocAgentRetriever
    try:
        retriever = LocAgentRetriever(snapshot, graph)
    except Exception as exc:
        return {'accepted': False, 'error_type': type(exc).__name__, 'reason': str(exc)}
    rows = {}
    for query in queries:
        try:
            text = retriever.retrieve(query)
            rows[query] = {'text': text, 'bytes': len(text.encode()), 'sha256': sha(text.encode())}
        except Exception as exc:
            rows[query] = {'error_type': type(exc).__name__, 'reason': str(exc)}
    return {'accepted': True, 'queries': rows}


def main():
    request = json.load(sys.stdin)
    sys.path.insert(1, request['engine_root'])
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    from locagent_service.offline import offline_engine
    from readonly_agent.core import Snapshot
    result = {'engine': request['engine'], 'case': request['case'], 'model_requests': 0,
              'packages': {p: importlib.metadata.version(p) for p in
                  ('networkx', 'bm25s', 'llama-index-core', 'llama-index-retrievers-bm25', 'tree-sitter')}}
    start = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr), offline_engine():
        from dependency_graph.build_graph import build_graph, VERSION
        result['graph_version'] = VERSION
        with tempfile.TemporaryDirectory(prefix='engine-compare-source-') as temporary:
            root = Path(temporary)
            if request['case'] == 'synthetic':
                sources = {
                    'core.py': 'class Box:\n    def __init__(self):\n        def nested():\n            return 1\n        self.value = nested()\n    def fetch(self):\n        return self.value\n',
                    '.github/tasks.py': 'def hidden_task():\n    return 2\n',
                    'pkg.github/worker.py': 'def visible_task():\n    return 3\n'}
            else:
                bundle = Path(request['bundle'])
                sources = {}
                for name, expected in request['source_hashes'].items():
                    data = (bundle / 'repo' / name).read_bytes()
                    assert sha(data) == expected
                    sources[name] = data.decode('utf-8')
            for name, text in sources.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode())
            graph = build_graph(str(root), global_import=True)
            result['fresh_graph'] = summary(graph)
            if request['case'] == 'synthetic':
                try:
                    Snapshot(root, list(sources))
                except ValueError as exc:
                    result['hidden_snapshot_rejection'] = str(exc)
                # OpenHands forbids hidden paths. Its real projection is tested separately.
                (root / '.github/tasks.py').unlink()
                sources.pop('.github/tasks.py')
                graph = build_graph(str(root), global_import=True)
                snapshot = Snapshot(root, list(sources))
                result['adapter_projection'] = probe_retrieval(snapshot, graph, request['queries'])
                # CRLF is an independent source-byte validation boundary.
                crlf = root / 'crlf'
                crlf.mkdir()
                (crlf / 'windows.py').write_bytes(b'def windows():\r\n    return 1\r\n')
                cs = Snapshot(crlf, ['windows.py'])
                result['crlf_adapter'] = probe_retrieval(cs, build_graph(str(crlf), global_import=True), ['windows'])
            else:
                snapshot = Snapshot(root, list(sources))
                result['snapshot'] = snapshot.identity
                result['fresh_retrieval'] = probe_retrieval(snapshot, graph, request['queries'])
                archived = restricted_graph(bundle / 'graph.pkl', request['graph_sha256'])
                result['archived_graph'] = summary(archived)
                result['archived_retrieval'] = probe_retrieval(snapshot, archived, request['queries'])
                # Format compatibility only: body BM25 is NOT the OpenHands ID retriever.
                from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir, retrieve_nonempty
                corpus = build_retriever_from_persist_dir(str(bundle / 'bm25' / request['case']))
                result['persisted_corpus'] = {}
                for query in request['queries']:
                    result['persisted_corpus'][query] = [
                        {'file_path': v.node.metadata.get('file_path'),
                         'start_line': v.node.metadata.get('start_line'),
                         'end_line': v.node.metadata.get('end_line'),
                         'text_sha256': sha(v.node.text.encode()), 'score': float(v.score)}
                        for v in retrieve_nonempty(corpus, query)]
            # Source path normalization has a deterministic relative-root counterexample.
            relative = Path('relative-repo')
            relative.mkdir()
            (relative / 'relative-repo_utils.py').write_text('def helper():\n    return 1\n')
            name = str(relative / 'relative-repo_utils.py')
            if request['engine'] == 'batch134':
                from repo_index.source_path import source_relative_path
                result['relative_path_metadata'] = source_relative_path(name, str(relative))
                rejected = []
                for unsafe in ['../outside.py', str(relative / '../outside.py')]:
                    try:
                        source_relative_path(unsafe, str(relative))
                    except ValueError:
                        rejected.append(unsafe)
                result['relative_path_rejected'] = rejected
            else:
                result['relative_path_metadata'] = name.replace(str(relative), '').lstrip('/')
    result['elapsed_seconds'] = time.monotonic() - start
    result['offline_guard'] = 'passed_no_attempts; Python guard, not an OS sandbox'
    sys.stdout.buffer.write(encode(result))


if __name__ == '__main__':
    main()
