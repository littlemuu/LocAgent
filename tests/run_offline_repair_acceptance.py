"""Replay already-settled responses locally; no paid provider or authorization access.

Historical manifests are verified for artifact integrity, but deliberately NOT
accepted as current experiments: their engine hash identifies the old code.
This forensic runner writes a fresh output directory and never edits old evidence.
"""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import pickle
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from locagent_service.offline import offline_engine
from locagent_service.sources import canonical, digest, file_hashes
from util.localization_contract import LocalizationOptions, LocalizationRequest, LocalizationError
from util.localizer import GraphLocalizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    historical = ROOT / 'outputs/stage4/followup5-live-20261008'
    ledger_bytes = (historical/'budget.json').read_bytes()
    ledger = json.loads(ledger_bytes)
    groups = {}
    for call in ledger['calls']:
        assert call['status'] == 'settled'
        assert digest(call['raw_body_utf8'].encode()) == call['raw_body_sha256']
        groups.setdefault((call['source_id'], call['arm']), []).append(call)
    report = {'mode': 'offline_saved_response_regression',
              'real_provider_calls': 0, 'quality_claim_allowed': False,
              'historical_ledger_sha256': digest(ledger_bytes), 'cases': []}
    with offline_engine(), redirect_stdout((args.output/'tools.log').open('w')):
        from litellm import ModelResponse
        from dependency_graph import RepoEntitySearcher
        from plugins.location_tools.retriever.bm25_retriever import build_module_retriever_from_graph
        from plugins.location_tools.repo_ops import repo_ops as ops
        from util.localization_protocol import request_estimate

        for (source, arm), calls in groups.items():
            data = (ROOT/'outputs/stage4/sources'/f'{source}.json').read_bytes()
            assert digest(data) == source[9:]
            manifest = json.loads(data)
            bundle = ROOT/'outputs/stage4/sources'/manifest['bundle']
            assert file_hashes(bundle) == manifest['artifacts']
            graph = pickle.loads((bundle/'graph.pkl').read_bytes())
            retriever = build_module_retriever_from_graph(
                entity_searcher=RepoEntitySearcher(graph), similarity_top_k=5)
            request = LocalizationRequest(**manifest['task'])
            raw = [json.loads(c['raw_body_utf8']) for c in calls]
            sent = []

            def engine(provider, protocol='bounded-v1', limit=3):
                return GraphLocalizer.from_graph(
                    graph, provider=provider, model_name=manifest['config']['model'],
                    options=LocalizationOptions(limit, arm == 'true', protocol),
                    bm25_index_dir=bundle/'bm25', module_retriever=retriever)

            if len(raw) == 3:
                values = iter(raw)
                def provider(**kw):
                    sent.append(deepcopy(kw))
                    return ModelResponse(**next(values))
                result = engine(provider).localize(request)
                assert not result.found_files
                # Independently classify original last response under final-only protocol.
                terminal = engine(lambda **kw: ModelResponse(**raw[-1]), limit=1).localize(request)
                expected = ('output_truncated' if raw[-1]['choices'][0]['finish_reason'] == 'length'
                            else 'iteration_limit')
                assert terminal.diagnostics['termination_reason'] == expected
                row = {'sample': request.instance_id, 'arm': arm,
                       'replayed_settled_responses': len(sent),
                       'terminal_response_reason': expected,
                       'full_trace_reason': result.diagnostics['termination_reason'],
                       'max_request_estimate': max(result.diagnostics['request_byte_estimates']),
                       'tool_message_bytes': result.diagnostics['total_tool_message_json_bytes']}
                filename = request.instance_id + '-' + arm + '.json'
                (args.output/filename).write_text(json.dumps(result.to_dict(), indent=2))
                row['evidence'] = filename
                report['cases'].append(row)
            else:
                assert request.instance_id == 'psf__requests-2317' and len(raw) == 1
                baseline_estimates = []
                def legacy_provider(**kw):
                    baseline_estimates.append(request_estimate(kw))
                    if len(baseline_estimates) == 1:
                        return ModelResponse(**raw[0])
                    raise RuntimeError('OFFLINE stop at uncaptured second response')
                # Restore ONLY the original root alias behavior for exact forensic comparison.
                with patch.object(ops, '_root_alias', side_effect=lambda value: value):
                    try:
                        engine(legacy_provider, 'legacy').localize(request)
                    except LocalizationError:
                        pass
                assert len(baseline_estimates) == 2 and baseline_estimates[-1] == 80352
                def bounded_provider(**kw):
                    sent.append(deepcopy(kw))
                    if len(sent) == 1:
                        return ModelResponse(**raw[0])
                    assert len(sent) == 2
                    # Deliberately synthetic EMPTY submission; never a quality prediction.
                    return ModelResponse(model='synthetic-offline-finish', choices=[{'index': 0,
                        'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                        'tool_calls': [{'id': 'synthetic-end', 'type': 'function', 'function': {
                            'name': 'finish', 'arguments': '{"files":[],"entities":[]}'}}]}}],
                        usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
                result = engine(bounded_provider).localize(request)
                assert result.status.value == 'empty' and len(sent) == 2
                assert request_estimate(sent[-1]) <= 65536
                assert any(a['truncation_reason'] for a in result.diagnostics['tool_messages'])
                assert 'invalid' not in result.diagnostics['tool_outputs']['output-1']['raw'].lower()
                withheld = [e for history in result.return_records.values() for e in history
                            if not e['in_context']]
                assert withheld and all(not e['previously_in_context'] for e in withheld)
                filename = request.instance_id + '-bounded-synthetic-end.json'
                (args.output/filename).write_text(json.dumps(result.to_dict(), indent=2))
                report['cases'].append({
                    'sample': request.instance_id, 'arm': arm, 'replayed_settled_responses': 1,
                    'synthetic_empty_finish_responses': 1,
                    'legacy_next_request_estimate': baseline_estimates[-1],
                    'bounded_next_request_estimate': request_estimate(sent[-1]),
                    'max_tool_message_bytes': max(a['message_json_bytes'] for a in result.diagnostics['tool_messages']),
                    'total_tool_message_bytes': result.diagnostics['total_tool_message_json_bytes'],
                    'withheld_return_records_not_marked_seen': len(withheld), 'evidence': filename})
    assert (historical/'budget.json').read_bytes() == ledger_bytes
    report['historical_ledger_unchanged'] = True
    (args.output/'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
