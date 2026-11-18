"""Offline pair CLI. Each invocation is one isolated case process."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import Snapshot, digest
from .locagent import LocAgentRetriever
from .paired import run_pair


def main():
    parser = argparse.ArgumentParser(description='Offline read-only LocAgent paired replay; no live calls.')
    parser.add_argument('--case', type=Path, required=True,
                        help='JSON: root, source_files, issue, scripts (baseline/retrieval). No labels.')
    parser.add_argument('--output', type=Path, required=True, help='New directory; refuses overwrite.')
    args = parser.parse_args()
    case = json.loads(args.case.read_text())
    if not isinstance(case, dict) or set(case) != {'root', 'source_files', 'issue', 'scripts'}:
        parser.error('case must contain exactly root, source_files, issue, scripts')
    root = Path(case['root'])
    if not root.is_absolute():
        root = args.case.resolve().parent / root
    snapshot = Snapshot(root, case['source_files'])
    # Only the operator's reviewed engine is imported via PYTHONPATH, never root.
    from locagent_service.offline import offline_engine
    from locagent_service.engine_binding import behavior_hashes
    import locagent_service
    engine_root = Path(locagent_service.__file__).parent.parent
    engine_before = behavior_hashes(engine_root)
    with offline_engine(), TemporaryDirectory(prefix='readonly-agent-') as temporary:
        from dependency_graph.build_graph import build_graph
        # Parse only the explicit snapshot, not the surrounding evaluation files.
        source = Path(temporary) / 'source'
        source.mkdir()
        for name, content in snapshot.files.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
        graph = build_graph(str(source), global_import=True)
        results = run_pair(issue=case['issue'], snapshot=snapshot, scripts=case['scripts'],
            retriever_factory=lambda s: LocAgentRetriever(s, graph), output_dir=args.output)
    engine_after = behavior_hashes(engine_root)
    record = {'root': str(engine_root), 'before': engine_before, 'after_hash': digest(engine_after),
              'before_hash': digest(engine_before), 'unchanged': engine_before == engine_after}
    (args.output / 'engine-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    summary = {arm: {'status': r['status'], 'requests': r['requests'], 'live_calls': r['live_calls']}
               for arm, r in results.items()}
    print(json.dumps(summary, indent=2))
    if engine_before != engine_after or any(r['status'] != 'completed' for r in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
