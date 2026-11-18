"""Explicit opt-in real GitHub download + fake-model API/worker acceptance."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from fastapi.testclient import TestClient
    from locagent_service.api import create_app
    from locagent_service.config import Settings
    from locagent_service.store import TaskStore
    from locagent_service.worker import run_one
    settings = Settings.from_env()
    assert settings.schema.startswith('public_preview_')
    store = TaskStore(settings)
    store.initialize()
    summary = []
    with TestClient(create_app(settings)) as client:
        for number in range(2):
            response = client.post('/tasks', json={
                'source_id': 'github-v1', 'repository_url': 'https://github.com/pallets/itsdangerous',
                'ref': '2.2.0', 'problem_statement': 'Find how URL safe timed serializer signs data.' + ' ' * number,
                'timeout_seconds': 300, 'max_attempts': 1})
            assert response.status_code == 202, response.text
            task = response.json()
            assert run_one(store, 'public-static-smoke', lease_seconds=15)
            result = client.get(response.headers['Location']).json()
            summary.append({key: result[key] for key in ('id', 'status', 'progress', 'error')})
            print(json.dumps(summary[-1], sort_keys=True), flush=True)
            assert result['status'] == 'completed', result['error']
            assert result['result']['diagnostics']['paid_calls'] == 0
            assert result['progress']['cache_hit'] == bool(number)
        assert summary[0]['progress']['commit'] == summary[1]['progress']['commit']
        assert summary[0]['progress']['source_id'] != summary[1]['progress']['source_id']
    output = ROOT / 'outputs/public-preview/static-smoke.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
