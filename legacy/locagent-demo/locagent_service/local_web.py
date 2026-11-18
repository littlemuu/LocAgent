"""Single-user loopback UI for local.py. Paid execution is off unless enabled.

No arbitrary paths, key input, cross-origin access, retry, queue, or public bind.
Each subprocess uses the exact local CLI engine and an isolated private run.
"""
import argparse
import fcntl
import getpass
import warnings
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from locagent_service import local

ASSETS = Path(__file__).with_name('local_web_assets')
IDENTIFIER = re.compile(r'^[0-9a-f]{32}$')
SHA = re.compile(r'^[0-9a-f]{64}$')
MAX_BODY = 65536
MAX_FILE = 8 * 1024 * 1024
ACTIVE = {'preparing', 'running', 'demo_running'}


class WebError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def read(path):
    from locagent_service.public_authorization import private
    private(path)
    if path.stat().st_size > MAX_FILE:
        raise WebError('artifact_too_large')
    return json.loads(path.read_text())


def replace(path, value):
    tmp = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    local.save_new(tmp, value)
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def config_value(value):
    from locagent_service.public_authorization import ProviderConfig
    config = ProviderConfig.model_validate(value).model_dump()
    if config['input_bound'] != 'full-context' or config['pricing_confirmation'].startswith('REPLACE'):
        raise WebError('verified_full_context_config_required')
    return config


class Controller:
    def __init__(self, root, config=None, *, enable_paid=False, timeout=300):
        self.root = Path(root).absolute()
        if self.root != self.root.resolve():
            raise WebError('linked_storage_directory')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        local.checked_root(self.root)
        lock_path = self.root / '.server.lock'
        self.lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.lock_fd)
            raise WebError('storage_already_in_use') from None
        self.config = config_value(config) if config is not None else None
        self.enable_paid = bool(enable_paid)
        if not 1 <= timeout <= 900:
            raise WebError('invalid_timeout')
        self.timeout = timeout
        self.lock = threading.RLock()
        self.active = None
        self.process = None
        self.closed = False
        self.interrupted_fence = False
        # Never resume jobs on restart, even if their previous launch was unclear.
        for folder in self.root.iterdir():
            if IDENTIFIER.fullmatch(folder.name) and folder.is_dir() and not folder.is_symlink():
                state = read(folder / 'job.json')
                if state.get('state') in ACTIVE:
                    replace(folder / 'job.json', state | {'state': 'needs_review', 'error': 'server_interrupted_no_retry', 'interrupted_fence': True})
                    self.interrupted_fence = True
                elif state.get('interrupted_fence'):
                    self.interrupted_fence = True

    def available(self):
        return bool(not self.interrupted_fence and self.enable_paid and self.config and os.environ.get(self.config['credential_env']))

    def session(self):
        return {'mode': 'local-single-user', 'retrieval': 'bm25', 'paid_enabled': self.enable_paid,
                'credential_ready': bool(self.config and os.environ.get(self.config['credential_env'])),
                'provider_configured': self.config is not None, 'provider': self.config,
                'quality_evaluated': False, 'interrupted_fence': self.interrupted_fence}

    def folder(self, identity):
        if not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity):
            raise WebError('invalid_job_id')
        path = self.root / identity
        try:
            local.checked_root(path)
        except Exception:
            raise WebError('job_not_found', 404) from None
        return path

    def verified_preview(self, folder):
        from locagent_service.public_authorization import reserve
        from locagent_service.sources import canonical, digest
        plan = read(folder / 'run' / 'plan.json')
        saved = read(folder / 'run' / 'preview.json')
        config = config_value(plan['provider'])
        if (config != read(folder / 'provider.json') or
                digest(canonical(plan)) != saved['plan_sha256'] or
                digest(saved['problem_statement'].encode()) != plan['binding']['problem_sha256']):
            raise WebError('plan_or_display_changed_needs_review', 409)
        return {'plan_sha256': digest(canonical(plan)), 'repository_url': plan['binding']['repository_url'],
                'commit': plan['binding']['commit'], 'problem_statement': saved['problem_statement'],
                'endpoint': config['endpoint'], 'model': config['model'], 'currency': config['currency'],
                'budget': config['budget'], 'reservation_per_call': format(reserve(config), 'f'),
                'maximum_calls': config['max_calls'],
                'full_reservation_all_calls': format(reserve(config) * config['max_calls'], 'f'),
                'data_shared_on_run': 'Question, code snippets, graph/tool results and conversation history',
                'provider': config}

    def get(self, identity):
        with self.lock:
            folder = self.folder(identity)
            result = read(folder / 'job.json')
            run = folder / 'run'
            for filename, key in [('preview.json', 'preview'), ('run.json', 'run'),
                                  ('evidence.json', 'evidence'), ('result.json', 'result')]:
                path = run / filename
                if path.exists():
                    result[key] = self.verified_preview(folder) if key == 'preview' else read(path)
            if (folder / 'demo.json').exists():
                result['demo'] = read(folder / 'demo.json')
            # Never expose authority grants, credential values or raw HTTP bodies.
            if (run / 'run-started.json').exists():
                identity = read(run / 'run-started.json').get('plan_sha256', '')
                if SHA.fullmatch(identity):
                    ledger = run / 'authority' / identity / 'ledger.json'
                    if ledger.exists():
                        value = read(ledger)
                        result['accounting'] = {k: value.get(k) for k in ('spent', 'reserved', 'finished', 'halted')}
                        result['paid_calls'] = len(value.get('calls', []))
                        result['accounting']['calls'] = [
                            {k: call.get(k) for k in ('status', 'usage', 'cost')} for call in value.get('calls', [])]
            result['can_run'] = (result['state'] == 'prepared' and self.available()
                and not (folder / 'paid-request.json').exists() and not (run / 'run-started.json').exists())
            return result

    def create(self, data, kind):
        keys = {'id'} if kind == 'demo' else {'id', 'repository_url', 'question', 'ref'}
        if set(data) != keys or not isinstance(data['id'], str) or not IDENTIFIER.fullmatch(data['id']):
            raise WebError('invalid_input')
        if kind == 'prepare':
            from locagent_service.public_repo import normalize_url, validate_ref
            if not self.config:
                raise WebError('provider_config_required')
            try:
                normalize_url(data['repository_url'])
                validate_ref(data['ref'])
            except Exception:
                raise WebError('invalid_repository_or_ref') from None
            if not isinstance(data['question'], str) or not data['question'].strip() or len(data['question']) > 8000:
                raise WebError('invalid_question')
        with self.lock:
            folder = self.root / data['id']
            if folder.exists():
                raise WebError('job_id_already_used_read_status_no_retry', 409)
            if self.interrupted_fence:
                raise WebError('interrupted_server_read_only_review_processes_and_ledger', 409)
            if self.closed or self.active:
                raise WebError('another_job_active', 409)
            folder.mkdir(mode=0o700)
            local.save_new(folder / 'input.json', data)
            if kind == 'prepare':
                local.save_new(folder / 'provider.json', self.config)
            state = {'id': data['id'], 'kind': kind, 'state': 'demo_running' if kind == 'demo' else 'preparing',
                     'paid_calls': 0, 'quality_evaluated': False}
            local.save_new(folder / 'job.json', state)
            self._start(folder, kind)
            return state

    def run(self, identity, data):
        if set(data) != {'plan_sha256', 'consent'} or data['consent'] is not True or not isinstance(data['plan_sha256'], str) or not SHA.fullmatch(data['plan_sha256']):
            raise WebError('exact_plan_consent_required')
        with self.lock:
            folder = self.folder(identity)
            state = read(folder / 'job.json')
            if state['kind'] != 'prepare' or state['state'] != 'prepared':
                raise WebError('not_prepared_or_already_consumed', 409)
            if not self.available():
                raise WebError('paid_disabled_or_credential_missing', 403)
            if self.interrupted_fence:
                raise WebError('interrupted_server_read_only_review_processes_and_ledger', 409)
            if self.closed or self.active:
                raise WebError('another_job_active', 409)
            preview = self.verified_preview(folder)
            if preview['plan_sha256'] != data['plan_sha256']:
                raise WebError('plan_confirmation_mismatch', 409)
            # Do not apply a new server provider/key to an older provider plan.
            if read(folder / 'provider.json') != self.config:
                raise WebError('server_provider_changed_prepare_new_plan', 409)
            try:
                local.save_new(folder / 'paid-request.json', data)
            except FileExistsError:
                raise WebError('already_consumed_needs_review', 409) from None
            replace(folder / 'job.json', state | {'state': 'running', 'paid_calls': None})
            self._start(folder, 'run')
            return {'id': identity, 'state': 'running'}

    def _start(self, folder, kind):
        self.active = folder.name
        worker = threading.Thread(target=self._work, args=(folder, kind), daemon=True)
        try:
            worker.start()
        except Exception:
            self.active = None
            state = read(folder / 'job.json')
            replace(folder / 'job.json', state | {'state': 'needs_review', 'error': 'launch_unknown_no_retry'})
            raise WebError('launch_unknown_read_status', 503) from None

    def _command(self, folder, kind):
        return [sys.executable, '-B', '-m', 'locagent_service.local_web', '_job',
                '--job-dir', str(folder), '--kind', kind, '--timeout', str(self.timeout)]

    def _work(self, folder, kind):
        state = None
        try:
            env = {k: os.environ[k] for k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR') if k in os.environ}
            env.update({'PYTHONDONTWRITEBYTECODE': '1', 'LOCAGENT_ALLOW_PAID': '0',
                        'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'})
            if kind == 'run':
                key = self.config['credential_env']
                env[key] = os.environ[key]
            command = self._command(folder, kind)
            with self.lock:
                if self.closed:
                    raise WebError('server_stopped')
                self.process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                process = self.process
            try:
                code = process.wait(timeout=self.timeout + 30)
            except subprocess.TimeoutExpired:
                self._stop_process(process)
                raise WebError('deadline_unknown_no_retry') from None
            self._stop_process(process)  # Also clean orphan descendants after a parent failure.
            state = read(folder / ('outcome-' + kind + '.json')) if code == 0 else None
            if not isinstance(state, dict):
                raise WebError('child_exited_no_retry')
        except Exception:
            state = {'state': 'needs_review', 'error': 'execution_interrupted_no_retry'}
        finally:
            with self.lock:
                old = read(folder / 'job.json')
                replace(folder / 'job.json', old | state)
                self.process = None
                self.active = None

    @staticmethod
    def _stop_process(process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        # A terminated CLI parent is not proof its worker has exited.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()

    def close(self):
        with self.lock:
            self.closed = True
            process = self.process
        if process:
            self._stop_process(process)
        # Remain locked until the worker has persisted its terminal state.
        if self.active:
            import time
            deadline = time.monotonic() + 5
            while self.active and time.monotonic() < deadline:
                time.sleep(.05)
        fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        os.close(self.lock_fd)


def job_main(folder, kind, timeout):
    folder = local.checked_root(folder)
    try:
        if kind == 'demo':
            local.save_new(folder / 'demo.json', local.demo())
            value = {'state': 'demo_completed', 'paid_calls': 0}
        elif kind == 'prepare':
            data = read(folder / 'input.json')
            value = local.prepare(data['repository_url'], data['question'], read(folder / 'provider.json'),
                                  folder / 'run', ref=data['ref'], timeout_seconds=timeout)
        else:
            consent = read(folder / 'paid-request.json')
            value = local.run(folder / 'run', consent['plan_sha256'], allow_paid=consent['consent'], timeout_seconds=timeout)
    except BaseException:
        # Never return exception text, provider payloads, environment or keys.
        value = {'state': 'needs_review', 'error': 'local_validation_or_execution_stopped_no_retry'}
    local.save_new(folder / ('outcome-' + kind + '.json'), value)


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocAgentLocal'
    def log_message(self, *_):
        pass  # No query/question/token logging.

    def respond(self, code, value, mime='application/json; charset=utf-8'):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def guard(self, *, api=False, mutation=False, navigation=False):
        if self.client_address[0] != '127.0.0.1' or self.headers.get('Host') != self.server.host:
            raise WebError('loopback_host_required', 403)
        if not navigation and self.headers.get('Sec-Fetch-Site', 'none') not in ('same-origin', 'none'):
            raise WebError('cross_origin_denied', 403)
        if mutation and self.headers.get('Origin') != 'http://' + self.server.host:
            raise WebError('same_origin_required', 403)
        if api and not hmac.compare_digest(self.headers.get('X-LocAgent-Session', ''), self.server.token):
            raise WebError('session_required', 403)
        if self.headers.get('Origin') not in (None, 'http://' + self.server.host):
            raise WebError('cross_origin_denied', 403)

    def do_GET(self):
        try:
            navigation = ((self.path == '/' or self.path.startswith('/?job=')) and
                          self.headers.get('Sec-Fetch-Dest') == 'document' and
                          self.headers.get('Sec-Fetch-Mode') == 'navigate')
            self.guard(navigation=navigation)
            if self.path == '/api/session':
                self.respond(200, self.server.controller.session() | {'session': self.server.token})
                return
            routes = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.path in routes or self.path.startswith('/?job='):
                name, mime = routes.get(self.path, routes['/'])
                self.respond(200, (ASSETS / name).read_bytes(), mime)
                return
            self.guard(api=True)
            parts = self.path.split('/')
            if len(parts) == 4 and parts[1:3] == ['api', 'jobs']:
                self.respond(200, self.server.controller.get(parts[3]))
            else:
                raise WebError('not_found', 404)
        except WebError as exc:
            self.respond(exc.status, {'error': exc.code})
        except Exception:
            self.respond(500, {'error': 'local_read_failed'})

    def do_POST(self):
        try:
            self.guard(api=True, mutation=True)
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type') != 'application/json':
                raise WebError('json_required', 415)
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= MAX_BODY:
                raise WebError('body_size_limit', 413)
            data = json.loads(self.rfile.read(int(lengths[0])))
            if not isinstance(data, dict):
                raise WebError('json_object_required')
            if self.path in ('/api/prepare', '/api/demo'):
                result = self.server.controller.create(data, self.path.split('/')[-1])
            else:
                parts = self.path.split('/')
                if len(parts) != 5 or parts[1:3] != ['api', 'jobs'] or parts[4] != 'run':
                    raise WebError('not_found', 404)
                result = self.server.controller.run(parts[3], data)
            self.respond(202, result)
        except WebError as exc:
            self.respond(exc.status, {'error': exc.code})
        except Exception:
            self.respond(400, {'error': 'invalid_input_or_local_operation_failed'})

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, controller, port):
        super().__init__(('127.0.0.1', port), Handler)
        self.controller = controller
        self.host = '127.0.0.1:' + str(self.server_address[1])
        self.token = secrets.token_urlsafe(32)


def prompt_api_key(config):
    """Read only from an interactive terminal, never fall back to echoed input."""
    if not config:
        raise WebError('provider_config_required')
    if not sys.stdin.isatty():
        raise WebError('interactive_terminal_required')
    print('API Key 只用于本次服务，不写入文件；关闭服务后需重新输入。')
    print('接收方：' + config['endpoint'])
    print('请核实接收方。输入不会显示；直接回车或 Ctrl-C 取消。')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('API Key: ')
    if not key or key != key.strip() or any(ord(c) < 32 or ord(c) == 127 for c in key):
        raise WebError('key_input_cancelled_or_invalid')
    return key


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8765)
    serve.add_argument('--data-dir', default='web-runs')
    serve.add_argument('--provider-config')
    serve.add_argument('--enable-paid-run', action='store_true')
    serve.add_argument('--prompt-api-key', action='store_true', help='Hidden terminal input; process-only, never saved')
    serve.add_argument('--timeout', type=int, default=300)
    job = sub.add_parser('_job', help=argparse.SUPPRESS)
    job.add_argument('--job-dir', required=True)
    job.add_argument('--kind', choices=['demo', 'prepare', 'run'], required=True)
    job.add_argument('--timeout', type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == '_job':
        job_main(Path(args.job_dir), args.kind, args.timeout)
        return 0
    controller = None
    server = None
    credential_name = None
    previous_credential = None
    try:
        config = json.loads(Path(args.provider_config).read_text()) if args.provider_config else None
        controller = Controller(args.data_dir, config, enable_paid=args.enable_paid_run, timeout=args.timeout)
        server = Server(controller, args.port)
        if args.prompt_api_key:
            key = prompt_api_key(controller.config)
            credential_name = controller.config['credential_env']
            previous_credential = os.environ.get(credential_name)
            os.environ[credential_name] = key
            del key
        print('LocAgent local UI: http://' + server.host, flush=True)
        print('Paid run: ' + ('enabled; exact browser plan consent still required' if args.enable_paid_run else 'disabled'), flush=True)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except (KeyboardInterrupt, EOFError):
        print('已取消，未启动新的服务或模型请求。', file=sys.stderr)
        return 2
    except Exception:
        print('Local web startup failed. Check private data directory, verified provider config, port and README_LOCAL_WEB.md.', file=sys.stderr)
        return 2
    finally:
        if server:
            server.server_close()
        if controller:
            controller.close()
        if credential_name:
            if previous_credential is None:
                os.environ.pop(credential_name, None)
            else:
                os.environ[credential_name] = previous_credential
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
