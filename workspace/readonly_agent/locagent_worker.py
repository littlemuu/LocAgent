"""One query per isolated LocAgent process. Called only by bridge.py."""
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    # Operator-controlled paths only; the evaluated source never enters sys.path.
    engine = Path(sys.argv[1]).resolve(strict=True)
    sys.path[:0] = [str(Path(__file__).parent.parent), str(engine)]
    from readonly_agent.core import Snapshot, encoded, safe_name
    from readonly_agent.locagent import LocAgentRetriever
    from locagent_service.offline import offline_engine
    raw = sys.stdin.buffer.read(128 * 1024 * 1024 + 1)
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError('oversized_request')
    request = json.loads(raw)
    if set(request) != {'snapshot', 'sources', 'query', 'hidden_python_paths'} or not isinstance(request['sources'], dict):
        raise ValueError('invalid_request')
    with TemporaryDirectory(prefix='locagent-source-') as temporary:
        root = Path(temporary)
        for name, text in request['sources'].items():
            safe_name(name)
            if not isinstance(text, str):
                raise ValueError('invalid_source')
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode('utf-8'))
        snapshot = Snapshot(root, list(request['sources']), hidden_python_paths=request['hidden_python_paths'])
        if snapshot.identity != request['snapshot']:
            raise ValueError('snapshot_mismatch')
        with redirect_stdout(sys.stderr), offline_engine():
            from dependency_graph.build_graph import build_graph
            graph = build_graph(str(root), global_import=True)
            result = LocAgentRetriever(snapshot, graph).retrieve(request['query'])
    sys.stdout.buffer.write(encoded({'snapshot': snapshot.identity, 'text': result}))


if __name__ == '__main__':
    main()
