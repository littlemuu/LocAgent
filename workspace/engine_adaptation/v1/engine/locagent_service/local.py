"""Local CLI for the real graph/BM25 engine, with explicit one-run paid consent.

No database or HTTP server. A plan is preparation, never permission to call a
model. Only ``run --allow-paid --approve-plan SHA`` consumes a fresh grant.
"""
import argparse
import atexit
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import hashlib
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4

FORMAT = 'locagent-local-v1'
# A stable sink avoids third-party logging handlers retaining a closed stream.
_QUIET = open(os.devnull, 'w')
atexit.register(_QUIET.close)


class LocalError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_json(path):
    from locagent_service.public_authorization import read_json as private_read
    return private_read(path)


def save_new(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def environment(root, *, live=False):
    """Only this process is configured; never load .env or change shell settings."""
    values = {
        'LOCAGENT_SOURCE_ROOT': str(root / 'sources'),
        'LOCAGENT_PUBLIC_ROOT': str(root / 'sources'),
        'LOCAGENT_PUBLIC_AUTH_ROOT': str(root / 'authority'),
        'LOCAGENT_PUBLIC_PREVIEW': '1',
        'LOCAGENT_PUBLIC_LIVE': '1' if live else '0',
        'LOCAGENT_ALLOW_PAID': '0',
        'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
        'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
    }
    # Older HTTPX cannot parse socks5h during imports. Match the worker's scoped
    # cleanup; the actual provider uses pinned HTTPS and no proxy regardless.
    values.update({name: None for name in os.environ
                   if name.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')})
    old = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def checked_root(value):
    from locagent_service.public_authorization import private
    path = Path(value).absolute()
    if path != path.resolve():
        raise LocalError('linked_run_directory')
    private(path, directory=True)
    return path


def summary(plan, root):
    from locagent_service.public_authorization import reserve
    from locagent_service.sources import canonical, digest, load_manifest
    manifest, _ = load_manifest(plan['source_id'])
    config = plan['provider']
    return {
        'format': FORMAT, 'prepared': True, 'authorized': False, 'paid_calls': 0,
        'run_dir': str(root), 'plan_sha256': digest(canonical(plan)),
        'repository_url': plan['binding']['repository_url'],
        'commit': plan['binding']['commit'],
        'problem_statement': manifest['task']['problem_statement'],
        'retrieval': 'bm25', 'endpoint': config['endpoint'], 'model': config['model'],
        'currency': config['currency'], 'budget': config['budget'],
        'reservation_per_call': format(reserve(config), 'f'),
        'maximum_calls': config['max_calls'],
        'full_reservation_all_calls': format(reserve(config) * config['max_calls'], 'f'),
        'data_shared_on_run': 'Question, code snippets, graph/tool results and conversation history',
        'quality_evaluated': False,
    }


def prepare_source(repository_url, question, provider_config, run_dir, *, ref=None):
    from locagent_service import public_repo, public_authorization as auth
    from locagent_service.public_pipeline import index, publish
    from locagent_service.sources import canonical, digest, registry
    url = public_repo.normalize_url(repository_url)
    public_repo.validate_ref(ref)
    if not isinstance(question, str) or not question.strip() or len(question) > 8000:
        raise LocalError('invalid_question')
    config = auth.ProviderConfig.model_validate(provider_config).model_dump()
    if config['input_bound'] != 'full-context':
        raise LocalError('local_requires_full_context_reservation')
    if config['pricing_confirmation'].startswith('REPLACE'):
        raise LocalError('pricing_not_confirmed')
    root = Path(run_dir).absolute()
    if root != root.resolve():
        raise LocalError('linked_run_directory')
    # Never reuse a directory or copy/reset an old authorization.
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    with environment(root):
        commit = public_repo.resolve(url, ref)
        with redirect_stdout(_QUIET), redirect_stderr(_QUIET):
            manifest = index(url, commit, lambda **_: None)
        manifest = {**manifest, 'task': {**manifest['task'], 'problem_statement': question}}
        data = canonical(manifest)
        source = 'prepared-' + digest(data)
        publish(registry() / (source + '.json'), data)
        plan = auth.make_plan(source, config)
        save_new(root / 'plan.json', plan)
        result = summary(plan, root)
        save_new(root / 'preview.json', result)
        return result


def preload_engine():
    from locagent_service.offline import offline_engine
    # Import-time metadata/model downloads are forbidden even for a paid run.
    with offline_engine():
        for name in ('plugins.location_tools.repo_ops.repo_ops', 'util.localization_engine',
                     'util.process_output', 'util.runtime.function_calling',
                     'util.localization_protocol', 'locagent_service.rag_http'):
            importlib.import_module(name)


def evidence(result, manifest, bundle):
    """Source evidence is reconstructed locally, never invented by the model.

    Pickle is loaded only after load_manifest verified our private, self-built
    artifact hashes. Source snippets are original snapshot bytes, not normalized
    graph text. This proves the location exists, not that it fixes the problem.
    """
    with (bundle / 'graph.pkl').open('rb') as stream:
        graph = pickle.load(stream)
    base = 'https://github.com/' + manifest['task']['repo'] + '/blob/' + manifest['task']['base_commit']
    items = []
    names = list(dict.fromkeys(result.found_files + result.found_entities + result.found_modules))
    for name in names:
        if name not in graph:
            raise LocalError('result_evidence_missing')
        path = name.partition(':')[0]
        target = bundle / 'repo' / path
        if target.is_symlink() or not target.resolve().is_relative_to((bundle / 'repo').resolve()):
            raise LocalError('result_evidence_path')
        raw = target.read_bytes()
        # Existing graph builder accepts UTF-8. Keep original line contents.
        lines = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        node = graph.nodes[name]
        start = node.get('start_line', 1)
        end = node.get('end_line', max(1, len(lines)))
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= max(1, len(lines)):
            raise LocalError('result_evidence_range')
        snippet_end = min(end, start + 39)
        selected = lines[start - 1:snippet_end]
        # Bound both line count and bytes; expose truncation instead of implying
        # that a huge single-line body was delivered in full.
        snippet = '\n'.join(selected)
        clipped = snippet.encode('utf-8')[:12000].decode('utf-8', errors='ignore')
        items.append({'id': name, 'kind': node['type'], 'path': path,
            'start_line': start, 'end_line': end, 'snippet_end_line': snippet_end,
            'snippet': clipped, 'truncated': snippet_end < end or clipped != snippet,
            'file_sha256': hashlib.sha256(raw).hexdigest(),
            'url': base + '/' + quote(path, safe='/') + '#L' + str(start) + '-L' + str(end)})
    return {'format': FORMAT, 'commit': manifest['task']['base_commit'],
            'verification': 'source location exists; relevance is not independently verified',
            'items': items}


def execute(root, identity, *, raw_completion=None):
    """One execution; injection is used by offline tests, never exposed by CLI."""
    from locagent_service import public_authorization as auth
    from locagent_service.models import CreateTask
    from locagent_service.sources import localize_prepared, load_manifest
    preload_engine()
    marker, manifest = auth.grant(identity)
    plan = marker['plan']
    request = CreateTask(source_id='github-v1',
        repository_url=plan['binding']['repository_url'], ref=plan['binding']['commit'],
        problem_statement=manifest['task']['problem_statement'], authorization_id=identity,
        options={'max_iterations': plan['provider']['max_calls'],
                 'suppress_repeats': plan['binding']['suppress_repeats']}, max_attempts=1)
    claim = SimpleNamespace(id=uuid4(), token=uuid4())
    provider = auth.AuthorizedProvider(request, claim, lambda _: None,
                                       raw_completion=raw_completion)
    prepared = CreateTask(source_id=plan['source_id'], problem_statement=request.problem_statement,
                          options=request.options, max_attempts=1)
    result = localize_prepared(prepared, provider)
    provider.finish()
    manifest, bundle = load_manifest(plan['source_id'])
    record = result.to_dict()
    record['local_run'] = {'format': FORMAT, 'retrieval': 'bm25',
        'provider': 'operator-authorized', 'commit': manifest['task']['base_commit'],
        'authorization_id': identity, 'quality_evaluated': False}
    # Persist engine trajectory before evidence rendering. A render error must not
    # erase a completed paid answer or permit another model run.
    save_new(root / 'result.json', record)
    save_new(root / 'evidence.json', evidence(result, manifest, bundle))
    return {'status': result.status.value, 'found_files': result.found_files,
            'found_entities': result.found_entities, 'result': str(root / 'result.json'),
            'evidence': str(root / 'evidence.json'), 'authorization_id': identity}


def child(root_text, identity, connection):
    root = Path(root_text)
    try:
        with environment(root, live=True), redirect_stdout(_QUIET), redirect_stderr(_QUIET):
            child_limits()
            result = execute(root, identity)
        connection.send({'state': 'completed', **result})
    except BaseException:
        # No raw provider/SDK errors, prompts, snippets or credential values.
        connection.send({'state': 'needs_review', 'code': 'execution_stopped',
                         'authorization_id': identity})
    finally:
        connection.close()



def child_limits():
    """Unix per-process caps; macOS has no reliable RLIMIT_AS memory isolation."""
    import resource
    caps = [(resource.RLIMIT_CPU, 180), (resource.RLIMIT_FSIZE, 128 * 1024 ** 2),
            (resource.RLIMIT_NOFILE, 256), (resource.RLIMIT_CORE, 0)]
    if sys.platform != 'darwin':
        caps.append((resource.RLIMIT_AS, 6 * 1024 ** 3))
    for kind, value in caps:
        _, hard = resource.getrlimit(kind)
        bound = value if hard == resource.RLIM_INFINITY else min(value, hard)
        resource.setrlimit(kind, (bound, bound))


def supervise(target, arguments, timeout_seconds):
    """The parent owns startup, deadline, interruption and child cleanup."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 900:
        raise LocalError('invalid_timeout')
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(*arguments, sender))
    try:
        process.start()
        sender.close()
        if receiver.poll(timeout_seconds):
            try:
                return receiver.recv()
            except EOFError:
                return {'state': 'needs_review', 'code': 'child_exited'}
        return {'state': 'needs_review', 'code': 'deadline_exceeded'}
    except KeyboardInterrupt:
        return {'state': 'needs_review', 'code': 'interrupted'}
    except Exception:
        return {'state': 'needs_review', 'code': 'child_start_or_transport_failed'}
    finally:
        sender.close()
        if process.pid is not None:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join()
        receiver.close()


def prepare_child(repository_url, question, provider_config, run_dir, ref, connection):
    try:
        child_limits()
        value = prepare_source(repository_url, question, provider_config, run_dir, ref=ref)
        connection.send({'state': 'prepared', **value})
    except Exception as exc:
        from locagent_service.public_repo import PipelineError
        code = exc.code if isinstance(exc, (LocalError, PipelineError)) else 'preparation_failed'
        connection.send({'state': 'failed', 'error': code, 'paid_calls': 0})
    finally:
        connection.close()


def prepare(repository_url, question, provider_config, run_dir, *, ref=None, timeout_seconds=300):
    return supervise(prepare_child, (repository_url, question, provider_config, run_dir, ref), timeout_seconds)

def run(run_dir, expected_hash, *, allow_paid=False, timeout_seconds=300):
    from locagent_service import public_authorization as auth
    from locagent_service.sources import canonical, digest
    if allow_paid is not True:
        raise LocalError('paid_confirmation_required')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 900:
        raise LocalError('invalid_timeout')
    root = checked_root(run_dir)
    with environment(root, live=True):
        plan = read_json(root / 'plan.json')
        auth.validate_plan(plan)
        if digest(canonical(plan)) != expected_hash:
            raise LocalError('plan_confirmation_mismatch')
        if (root / 'run-started.json').exists() or (root / 'authority' / expected_hash).exists():
            raise LocalError('already_consumed_needs_review')
        if not os.environ.get(plan['provider']['credential_env']):
            raise LocalError('credential_environment_missing')
        # Permanent marker precedes grant and process creation; ambiguous startup
        # is review-only, not a fresh paid attempt on retry.
        save_new(root / 'run-started.json', {'format': FORMAT, 'plan_sha256': expected_hash})
        identity = auth.authorize(plan, expected_hash)
        outcome = supervise(child, (str(root), identity), timeout_seconds)
        outcome['authorization_id'] = identity
        outcome['run_dir'] = str(root)
        save_new(root / 'run.json', outcome)
        return outcome


def demo():
    from tempfile import TemporaryDirectory
    from locagent_service.fixture import localize_demo
    from locagent_service.models import CreateTask
    with TemporaryDirectory(prefix='locagent-local-demo-') as tmp:
        with environment(Path(tmp)), redirect_stdout(_QUIET), redirect_stderr(_QUIET):
            result = localize_demo(CreateTask(problem_statement='Locate render.'))
    return {'mode': 'synthetic-demo', 'paid_calls': 0, 'quality_evaluated': False,
            'result': result.to_dict()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('demo', help='Synthetic fixture only; no network or model key')
    prep = commands.add_parser('prepare', help='Download public Python source and prepare a reviewable plan; no model call')
    prep.add_argument('repository_url')
    prep.add_argument('question')
    prep.add_argument('--ref')
    prep.add_argument('--provider-config', required=True)
    prep.add_argument('--run-dir', required=True)
    prep.add_argument('--timeout-seconds', type=int, default=300)
    live = commands.add_parser('run', help='Consume one exact approved plan and call the configured model')
    live.add_argument('--run-dir', required=True)
    live.add_argument('--approve-plan', required=True)
    live.add_argument('--allow-paid', action='store_true')
    live.add_argument('--timeout-seconds', type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            value = demo()
        elif args.command == 'prepare':
            config = json.loads(Path(args.provider_config).read_text())
            value = prepare(args.repository_url, args.question, config, args.run_dir, ref=args.ref, timeout_seconds=args.timeout_seconds)
        else:
            value = run(args.run_dir, args.approve_plan, allow_paid=args.allow_paid,
                        timeout_seconds=args.timeout_seconds)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        if value.get('state') == 'needs_review':
            return 3
        if value.get('state') == 'failed':
            return 2
        if value.get('status') in ('empty', 'iteration_limit'):
            return 4
        return 0
    except Exception as exc:
        from locagent_service.public_repo import PipelineError
        if isinstance(exc, LocalError):
            code = exc.code
        elif isinstance(exc, PipelineError):
            code = exc.code
        elif isinstance(exc, ModuleNotFoundError):
            code = 'dependency_missing'
        elif isinstance(exc, FileExistsError):
            code = 'output_already_exists'
        else:
            code = 'local_validation_or_io_failed'
        print(json.dumps({'error': code, 'details': 'No automatic retry. Review inputs, run directory and README.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
