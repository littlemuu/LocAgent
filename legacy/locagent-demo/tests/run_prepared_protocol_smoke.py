"""Build a new bounded-v1 source and exercise it with a synthetic provider only."""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from locagent_service.offline import offline_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with offline_engine(), patch.dict(os.environ, {
            'LOCAGENT_SOURCE_ROOT': str((args.output/'sources').resolve())}):
        from litellm import ModelResponse
        from locagent_service.prepare import prepare
        from locagent_service.models import CreateTask
        from locagent_service.sources import load_manifest, localize_prepared
        historical = ROOT/'outputs/stage4/sources/prepared-dc840ecdb40c5aaf443e0e4cbc30d09f391a659f6488fe10bdeab7b90d561f2f.json'
        old = json.loads(historical.read_text())
        sample = args.output/'sample.json'
        sample.write_text(json.dumps({**old['task'], **old['dataset']}, indent=2))
        with (args.output/'build.log').open('w') as log, redirect_stdout(log):
            source = prepare(ROOT/'outputs/day1/requests', sample,
                             followup5=True, search_protocol='bounded-v1')
            manifest, _ = load_manifest(source)
            assert manifest['config']['search_protocol'] == 'bounded-v1'
            sent = []
            def provider(**kw):
                sent.append(kw)
                name, value = ('explore_tree_structure', {'start_entities': ['/']}) if len(sent)==1 else (
                    'finish', {'files': [], 'entities': []})
                return ModelResponse(model='synthetic-offline', choices=[{'index': 0,
                    'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                    'tool_calls': [{'id': f'offline-{len(sent)}', 'type': 'function',
                                   'function': {'name': name, 'arguments': json.dumps(value)}}]}}],
                    usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
            request = CreateTask(source_id=source, problem_statement=manifest['task']['problem_statement'],
                options={'max_iterations': 3, 'suppress_repeats': True}, max_attempts=1)
            result = localize_prepared(request, provider)
            assert result.status.value == 'empty' and len(sent) == 2
            assert result.diagnostics['protocol'] == 'bounded-v1'
            assert 'invalid' not in result.diagnostics['tool_outputs']['output-1']['raw'].lower()
        (args.output/'result.json').write_text(json.dumps(result.to_dict(), indent=2))
        summary = {'source_id': source, 'fixed_commit': old['task']['base_commit'],
            'new_manifest_config_verified': True, 'synthetic_provider_responses': len(sent),
            'real_provider_calls': 0, 'quality_claim_allowed': False,
            'status': result.status.value, 'protocol': result.diagnostics['protocol']}
        (args.output/'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
