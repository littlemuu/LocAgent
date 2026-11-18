"""Portable synthetic cohorts and protocol responses; no historical execution data."""
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
from unittest.mock import patch

from locagent_service import phased
from locagent_service.engine_binding import behavior_hashes
from locagent_service.sources import canonical, digest


def synthetic_cohorts(root=None):
    root = Path(root or phased.ROOT)
    template = Path(__file__).resolve().parents[1] / 'locagent_service/phased_cohorts.example.json'
    cohorts = json.loads(template.read_text())
    for name, count in [('new20', 20), ('regression5', 5)]:
        spec = cohorts[name]
        spec['limit_cny'] = '8' if name == 'new20' else '5'  # Mock accounting only.
        spec['engine_hashes'] = behavior_hashes(root)
        spec['samples'] = [
            {'instance_id': f'synthetic__fixture-{i}', 'base_commit': 'a' * 40,
             'source_id': 'prepared-' + hashlib.sha256(f'{name}-{i}'.encode()).hexdigest(),
             'arm_order': [False, True] if i % 2 == 0 else [True, False]}
            for i in range(count)]
        spec['function_applicable_sources'] = [
            item['source_id'] for item in spec['samples'][:18 if count == 20 else count]]
    return cohorts


def install_synthetic_cohorts(test):
    cohorts = synthetic_cohorts()
    patches = [
        patch.object(phased, 'specs', side_effect=lambda: deepcopy(cohorts)),
        patch.object(phased, 'runtime_hashes', side_effect=lambda spec: {
            **behavior_hashes(phased.ROOT),
            'locagent_service/phased_cohorts.json': digest(canonical(cohorts))}),
    ]
    for context in patches:
        context.start()
        test.addCleanup(context.stop)


def protocol_body(variant, ordinal):
    """Handwritten malformed JSON, synthetic IDs/usage, never a saved provider body."""
    if ordinal == 0:
        arguments = '{"search_terms": ["render"], "file_path_or_pattern": "demo.py"}'
    elif variant == 'old':
        arguments = '{"line_nums": 10, 15, "file_path_or_pattern": "demo.py"}'
    else:
        arguments = '{"line_nums": [10, 15, "file_path_or_pattern": "demo.py"}'
    completion = 142 if ordinal else 12
    return canonical({
        'id': f'synthetic-{variant}-{ordinal}', 'object': 'chat.completion',
        'created': 0, 'model': 'deepseek-flash',
        'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [{
                'id': f'synthetic-call-{ordinal}', 'type': 'function',
                'function': {'name': 'search_code_snippets', 'arguments': arguments}}]}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': completion,
                  'total_tokens': 100 + completion,
                  'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 100}})


def continuation_oracle():
    conditions = (
        'allowlisted_protocol_error', 'all_arm_calls_settled',
        'raw_evidence_valid_and_durable', 'failure_evidence_valid_and_durable',
        'child_exit_confirmed', 'ownership_fence_current',
        'no_concurrent_executor', 'no_unsettled_calls_global')
    return [{'conditions': dict(zip(conditions, values)), 'may_continue': all(values)}
            for values in itertools.product([False, True], repeat=len(conditions))]
