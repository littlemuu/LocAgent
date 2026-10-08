"""Manage only this local demo's PostgreSQL container, API and worker processes."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

import httpx

from locagent_service.config import Settings
from locagent_service.models import CreateTask, DemoScenario
from locagent_service.store import TaskStore


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'outputs/stage2/demo'
CONFIG = RUNTIME / 'runtime.json'
CONTAINER = 'locagent-stage2-pg'
VOLUME = 'locagent-stage2-pg-data'
LABEL = 'locagent.stage2'
IMAGE = 'postgres:16-bookworm'
API_PORT = 8000
PG_PORT = 55432


def load_runtime():
    if CONFIG.is_symlink():
        raise RuntimeError('Demo runtime file must not be a symlink')
    if not CONFIG.exists():
        raise RuntimeError('Run python -m locagent_service.demo db or up first')
    return json.loads(CONFIG.read_text(encoding='utf-8'))


def save_runtime(data):
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    if RUNTIME.is_symlink() or CONFIG.is_symlink():
        raise RuntimeError('Demo runtime paths must not be symlinks')
    temporary = RUNTIME / 'runtime.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
    temporary.replace(CONFIG)


def settings_from_runtime(data=None):
    return Settings((data or load_runtime())['database_url'])


def process_env(settings):
    return {**os.environ, 'LOCAGENT_DATABASE_URL': settings.database_url,
            'LOCAGENT_SCHEMA': settings.schema, 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
            'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}


def docker(*args, env=None, allow_missing=False):
    process = subprocess.run(['docker', *args], capture_output=True, text=True, env=env)
    if process.returncode and not allow_missing:
        # Never render a command/environment containing the generated password.
        raise RuntimeError('Docker action failed; inspect the named local demo container')
    return process


def require_own_resource(kind, name):
    process = docker(kind, 'inspect', '--format', '{{index .Config.Labels "locagent.stage2"}}'
                     if kind == 'container' else '{{index .Labels "locagent.stage2"}}',
                     name, allow_missing=True)
    if process.returncode == 0 and process.stdout.strip() != 'demo':
        raise RuntimeError('Named resource exists without the demo ownership label; leaving it alone')
    return process.returncode == 0


def database_up():
    exists = require_own_resource('container', CONTAINER)
    volume_exists = require_own_resource('volume', VOLUME)
    if CONFIG.exists():
        data = load_runtime()
    else:
        if exists or volume_exists:
            raise RuntimeError('Existing demo data has no runtime settings; do not recreate credentials')
        password = secrets.token_urlsafe(32)
        data = {'database_url': f'postgresql://locagent_demo:{password}@127.0.0.1:{PG_PORT}/locagent_demo',
                'api_port': API_PORT, 'pg_port': PG_PORT, 'processes': {}}
        save_runtime(data)
    if not volume_exists:
        docker('volume', 'create', '--label', LABEL + '=demo', VOLUME)
    if not exists:
        password = data['database_url'].split(':', 2)[2].split('@', 1)[0]
        env = {**os.environ, 'POSTGRES_PASSWORD': password}
        docker('run', '-d', '--name', CONTAINER, '--label', LABEL + '=demo',
               '-e', 'POSTGRES_USER=locagent_demo', '-e', 'POSTGRES_DB=locagent_demo',
               '-e', 'POSTGRES_PASSWORD', '-p', f'127.0.0.1:{PG_PORT}:5432',
               '-v', f'{VOLUME}:/var/lib/postgresql/data', IMAGE, env=env)
    else:
        docker('start', CONTAINER)
    store = TaskStore(settings_from_runtime(data))
    deadline = time.monotonic() + 45
    while True:
        try:
            with store.connect() as connection:
                version = connection.execute('SHOW server_version').fetchone()['server_version']
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError('PostgreSQL readiness timed out; inspect demo container logs') from None
            time.sleep(0.25)
    store.initialize()
    print(f'PostgreSQL {version} ready on 127.0.0.1:{PG_PORT}; schema version 2', flush=True)
    return data


def process_identity(pid):
    try:
        proc = Path('/proc') / str(pid)
        stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        return {'pid': pid, 'start': stat[19]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def is_own_process(record, module):
    if not record or process_identity(record['pid']) != record:
        return False
    proc = Path('/proc') / str(record['pid'])
    command = (proc / 'cmdline').read_bytes().split(b'\0')
    return module.encode() in command and (proc / 'cwd').resolve() == ROOT


def start_process(data, kind, module, *args):
    record = data['processes'].get(kind)
    if is_own_process(record, module):
        return
    with (RUNTIME / f'{kind}.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, '-B', '-m', module, *args], cwd=ROOT,
                                   env=process_env(settings_from_runtime(data)),
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    data['processes'][kind] = process_identity(process.pid)
    save_runtime(data)


def up():
    data = database_up()
    if not is_own_process(data['processes'].get('api'), 'locagent_service.api'):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', API_PORT))
    start_process(data, 'api', 'locagent_service.api', '--port', str(API_PORT))
    deadline = time.monotonic() + 30
    with httpx.Client(base_url=f'http://127.0.0.1:{API_PORT}', trust_env=False, timeout=2) as client:
        while True:
            try:
                if client.get('/health').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('API readiness timed out; inspect outputs/stage2/demo/api.log')
            time.sleep(0.2)
    start_process(data, 'worker', 'locagent_service.worker')
    print(f'API ready: http://127.0.0.1:{API_PORT}/docs; independent worker started', flush=True)


def down():
    data = load_runtime()
    for kind in ('worker', 'api'):
        record = data['processes'].get(kind)
        module = 'locagent_service.' + kind
        if is_own_process(record, module):
            os.kill(record['pid'], signal.SIGTERM)
            deadline = time.monotonic() + 15
            while is_own_process(record, module) and time.monotonic() < deadline:
                time.sleep(0.1)
            if is_own_process(record, module):
                raise RuntimeError('Demo process did not stop; PostgreSQL left running for inspection')
        data['processes'].pop(kind, None)
    save_runtime(data)
    if require_own_resource('container', CONTAINER):
        docker('stop', '--time', '10', CONTAINER)
    print('Demo processes/container stopped; PostgreSQL volume and task history retained')


def status():
    data = load_runtime()
    print(json.dumps({
        'api_url': f'http://127.0.0.1:{API_PORT}', 'postgres_port': PG_PORT,
        'processes': {kind: {'running': is_own_process(record, 'locagent_service.' + kind),
                             'pid': record['pid']} for kind, record in data['processes'].items()},
        'container': CONTAINER, 'volume': VOLUME,
    }, indent=2))


def submit_and_wait(scenario='success'):
    body = CreateTask(problem_statement='Locate the render function and inspect repeat suppression.',
                      demo_scenario=scenario).model_dump(mode='json')
    with httpx.Client(base_url=f'http://127.0.0.1:{API_PORT}', trust_env=False, timeout=5) as client:
        response = client.post('/tasks', json=body)
        response.raise_for_status()
        location = response.headers['Location']
        print(f'Accepted {response.json()["id"]}; poll {location}', flush=True)
        deadline = time.monotonic() + 45
        while True:
            response = client.get(location)
            response.raise_for_status()
            task = response.json()
            if task['status'] in ('completed', 'failed'):
                result = task['result']
                print(json.dumps({'task_id': task['id'], 'task_status': task['status'],
                                  'worker_id': task['worker_id'], 'error': task['error'],
                                  'result_status': result['status'] if result else None,
                                  'found_files': result['found_files'] if result else None,
                                  'found_entities': result['found_entities'] if result else None,
                                  'iterations': result['iterations'] if result else None}, indent=2))
                return task
            if time.monotonic() >= deadline:
                raise RuntimeError('Task wait timed out; inspect task state and worker log')
            time.sleep(0.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('db', 'up', 'down', 'status', 'run'))
    parser.add_argument('--scenario', choices=[item.value for item in DemoScenario], default='success')
    args = parser.parse_args()
    try:
        if args.command == 'db':
            database_up()
        elif args.command == 'run':
            submit_and_wait(args.scenario)
        else:
            {'up': up, 'down': down, 'status': status}[args.command]()
    except Exception:
        raise SystemExit('Demo action failed; inspect the local demo logs/settings without deleting its data') from None


if __name__ == '__main__':
    main()
