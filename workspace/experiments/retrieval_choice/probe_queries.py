"""Offline human-selected query probes; never a model tool-choice evaluation."""
import argparse
import json
from pathlib import Path

from readonly_agent.bridge import LocAgentProcessRetriever
from readonly_agent.core import FileTools, Snapshot, encoded, page
from readonly_agent.offline import no_network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    case_path = project / 'examples/crossfile/case.json'
    case = json.loads(case_path.read_text())
    snapshot = Snapshot(case_path.parent / case['root'], case['source_files'])
    engine = Path('/Users/xiaomu/Documents/Codex/locagent-demo-20261108')
    retriever = LocAgentProcessRetriever(snapshot, python=engine / '.venv/bin/python', engine_root=engine)
    file_tools = FileTools(snapshot)
    records = []
    with no_network(args.output.parent / 'offline-probe-profiles') as attempts:
        for query in ('webhook', 'retry', 'delivery_key',
                      'dispatch/retry.py:schedule_retry', 'zzzxqv_nonexistent_92831'):
            result = retriever.retrieve(query)
            literal, _ = file_tools.render('search_text', {'query': query, 'offset': 0})
            first_page = page(result, 0, 4096)
            records.append({'query': query, 'literal_search': literal, 'retrieval_raw': result,
                            'first_page': first_page, 'first_page_bytes': len(encoded(first_page))})
    report = {'kind': 'offline_human_selected_query_probe', 'model_calls': 0,
              'network_attempts': len(attempts), 'snapshot': snapshot.identity,
              'queries': records, 'claims_autonomous_selection': False,
              'claims_retrieval_benefit': False}
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'queries': len(records), 'model_calls': 0, 'network_attempts': len(attempts)}))


if __name__ == '__main__':
    main()
