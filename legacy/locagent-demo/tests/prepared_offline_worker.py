"""Test-only worker entrypoint: real supervision/source path, scripted provider, no network."""
import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SENTINEL = 'GOLD_ONLY_SENTINEL_981aaed6'


def execute_offline(request, channel, parent_pid):
    from locagent_service.offline import offline_engine
    from locagent_service.worker import execute
    assert SENTINEL not in json.dumps(request)
    from locagent_service.sources import canonical, digest
    class AuditedChannel:
        def send(self, value):
            status, payload = value
            if status == 'completed':
                payload.setdefault('diagnostics', {})['offline_acceptance'] = {
                    'child_input_sha256': digest(canonical(request)),
                    'child_input_keys': sorted(request),
                    'label_sentinel_absent': True,
                    'logical_isolation_only': True,
                    'scripted_provider': True, 'paid_calls': 0}
            channel.send((status, payload))
        def close(self):
            channel.close()
    with offline_engine():
        from litellm import ModelResponse
        steps = iter([
            ('explore_tree_structure', {'start_entities': ['/'], 'traversal_depth': 1}),
            ('explore_tree_structure', {'start_entities': ['/'], 'traversal_depth': 1}),
            ('finish', {'files': [], 'entities': []}),
        ])
        def provider(**kwargs):
            assert SENTINEL not in json.dumps(kwargs)
            assert any(request['problem_statement'] in (m.get('content') or '')
                       for m in kwargs['messages'])
            name, arguments = next(steps)
            return ModelResponse(model='offline-service-compatibility', choices=[{
                'index':0, 'finish_reason':'tool_calls',
                'message':{'role':'assistant','content':None,'tool_calls':[{
                    'id':'offline-'+name,'type':'function','function':{
                        'name':name,'arguments':json.dumps(arguments)}}]}}],
                usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
        with patch('locagent_service.followup.SettlingBudgetProvider.from_env', return_value=provider), \
             patch('locagent_service.budget.BudgetProvider.from_env', return_value=provider):
            execute(request, AuditedChannel(), parent_pid)


if __name__ == '__main__':
    from locagent_service.config import Settings
    from locagent_service.store import TaskStore
    from locagent_service.worker import run_one
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', required=True)
    args=parser.parse_args()
    os.environ['LOCAGENT_ALLOW_PAID']='0'
    os.environ.pop('DEEPSEEK_API_KEY',None)
    store=TaskStore(Settings.from_env());store.check_ready()
    if not run_one(store,'offline-compatibility-'+str(os.getpid()),executor=execute_offline):
        raise SystemExit('No queued task')
