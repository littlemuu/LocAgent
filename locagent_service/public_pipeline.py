"""Opt-in public-repository pipeline. Defaults to fake; live requires a separate exact operator grant."""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import fcntl
import json
import logging
import os
from pathlib import Path
import resource
import shutil
from uuid import uuid4

from locagent_service import public_repo
from locagent_service.public_repo import PipelineError
from locagent_service.sources import canonical, digest, file_hashes, load_manifest, registry


def enabled(settings=None):
    if settings is not None and not settings.schema.startswith('public_preview_'):
        raise ValueError('Public preview requires a public_preview_ schema')
    # Require an explicit isolated root; never default to the historical source root.
    root = os.environ.get('LOCAGENT_PUBLIC_ROOT')
    if os.environ.get('LOCAGENT_PUBLIC_PREVIEW') != '1' or not root or not Path(root).is_absolute():
        raise ValueError('Public preview requires an explicit absolute cache root')
    if Path(root).resolve() != registry():
        raise ValueError('Public preview source root must equal its isolated cache root')


def limits():
    # Linux per-process limits, not an OS sandbox. Supervisor adds wall-clock deadline.
    resource.setrlimit(resource.RLIMIT_AS, (6 * 1024**3, 6 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024**2, 128 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    # Import-only workaround for LiteLLM/HTTPX: do not change global proxy settings.
    for name in list(os.environ):
        if name.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
            os.environ.pop(name)


def publish(path, data):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def cache_lock(key):
    root = registry()
    root.mkdir(parents=True, exist_ok=True)
    with (root / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def index(url, commit, report):
    from locagent_service.engine_binding import behavior_hashes
    from locagent_service.prepare import build_indexes
    engine = behavior_hashes(Path(__file__).resolve().parents[1])
    config = {'model': 'offline-public-preview', 'max_calls': 3, 'top_k': 1,
        'search_protocol': 'bounded-v1', 'global_import': True, 'fuzzy_search': True,
        'chunk_size': 500, 'min_chunk_size': 100, 'max_chunk_size': 2000,
        'hard_token_limit': 2000, 'max_chunks': 200, 'provider': 'fake-only',
        'acquisition_policy': public_repo.POLICY}
    key = digest(canonical({'repo': url, 'commit': commit, 'config': config, 'engine': engine}))
    report(stage='waiting_for_index', cache_key=key)
    with cache_lock(key):
        pointer = registry() / (key + '.ready')
        if pointer.exists():
            source = pointer.read_text()
            manifest, _ = load_manifest(source)
            if (manifest['engine'] != engine or manifest['config'] != config
                    or manifest['task']['base_commit'] != commit
                    or manifest['task']['repo'] != url.removeprefix('https://github.com/')
                    or manifest['task']['instance_id'] != key
                    or manifest['bundle'] != 'public-index-' + key):
                raise PipelineError('cache_integrity_error')
            report(stage='index_ready', cache_hit=True)
            return manifest
        # Only this lock owner may rebuild the deterministic private partial bundle.
        bundle = registry() / ('public-index-' + key)
        if bundle.exists():
            if bundle.is_symlink() or bundle.parent != registry():
                raise PipelineError('cache_integrity_error')
            shutil.rmtree(bundle)
        snapshot = bundle / 'repo'
        snapshot.mkdir(parents=True)
        report(stage='downloading', cache_hit=False)
        archive, blobs = public_repo.download(url, commit)
        report(stage='extracting')
        audit = public_repo.extract(archive, snapshot, blobs)
        (bundle / 'archive-audit.json').write_bytes(canonical(audit))
        report(stage='building_index')
        try:
            with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
                build_indexes(snapshot, bundle, key, top_k=1)
        except Exception:
            raise PipelineError('index_build_failed') from None
        manifest = {'version': 2, 'bundle': bundle.name, 'task': {
            'instance_id': key, 'repo': url.removeprefix('https://github.com/'),
            'base_commit': commit, 'problem_statement': 'Index template; not a user question'},
            'config': config, 'engine': engine, 'artifacts': file_hashes(bundle)}
        data = canonical(manifest)
        source = 'prepared-' + digest(data)
        publish(registry() / (source + '.json'), data)
        # Read back through the existing integrity gate before publishing the pointer.
        load_manifest(source)
        publish(pointer, source.encode())
        report(stage='index_ready', cache_hit=False)
        return manifest


def fake_localize(request, source):
    from locagent_service.models import CreateTask
    from locagent_service.offline import offline_engine
    from locagent_service.sources import localize_prepared
    with offline_engine():
        from litellm import ModelResponse
        # A real search/tool/finish loop with deterministic fake output, not accuracy proof.
        steps = iter([
            ('search_code_snippets', {'search_terms': [request.problem_statement[:200]]}),
            ('explore_tree_structure', {'start_entities': ['.'], 'traversal_depth': 1}),
            ('finish', {'files': [], 'entities': []}),
        ])
        def provider(**kwargs):
            tool, arguments = next(steps)
            return ModelResponse(model='offline-public-preview', choices=[{
                'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': None, 'tool_calls': [{
                        'id': 'fake-' + tool, 'type': 'function', 'function': {
                            'name': tool, 'arguments': json.dumps(arguments)}}]}}],
                usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
        prepared = CreateTask(source_id=source, problem_statement=request.problem_statement,
            options=request.options,
            max_attempts=1)
        return localize_prepared(prepared, provider)


def execute_pipeline(request, channel):
    diagnostic = uuid4().hex
    provider_kind = 'operator-authorized' if request.authorization_id is not None else 'fake-only'
    stage = 'starting'
    def report(**values):
        nonlocal stage
        stage = values.get('stage', stage)
        channel.report({**values, 'diagnostic_id': diagnostic, 'provider': provider_kind})
    try:
        enabled(channel.settings)
        limits()
        if request.authorization_id is not None:
            from locagent_service.public_authorization import localize_authorized
            with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
                result = localize_authorized(request, channel, report)
            payload = result.to_dict()
            payload.setdefault('diagnostics', {}).update({
                'provider': provider_kind, 'authorization_id': request.authorization_id,
                'commit': request.ref, 'diagnostic_id': diagnostic, 'quality_evaluated': False})
            report(stage='completed')
            channel.send(('completed', payload))
            return
        report(stage='resolving')
        commit = channel.progress.get('commit')
        if not commit:
            commit = public_repo.resolve(request.repository_url, request.ref)
        # Synchronous fenced DB write: a restart MUST reuse this exact commit.
        report(stage='resolved', commit=commit)
        manifest = index(request.repository_url, commit, report)
        manifest = {**manifest, 'config': {**manifest['config'], 'max_calls': request.options.max_iterations}, 'task': {**manifest['task'],
                    'problem_statement': request.problem_statement}}
        data = canonical(manifest)
        source = 'prepared-' + digest(data)
        publish(registry() / (source + '.json'), data)
        load_manifest(source)
        report(stage='localizing', source_id=source)
        with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            result = fake_localize(request, source)
        result_dict = result.to_dict()
        result_dict.setdefault('diagnostics', {}).update({
            'provider': 'fake-only', 'paid_calls': 0, 'commit': commit,
            'source_id': source, 'diagnostic_id': diagnostic,
            'quality_evaluated': False})
        report(stage='completed')
        channel.send(('completed', result_dict))
    except Exception as exc:
        from util.localization_contract import LocalizationError
        code = exc.code if isinstance(exc, PipelineError) else (
            exc.code.value if isinstance(exc, LocalizationError) else 'pipeline_failed')
        # Never log raw exceptions, URLs, source content, environment or model inputs.
        logging.getLogger(__name__).error('public_pipeline diagnostic=%s stage=%s type=%s code=%s',
            diagnostic, stage, type(exc).__name__, code)
        channel.send(('failed', {'code': code,
            'message': f'Public preview failed at {stage}; diagnostic {diagnostic}'}))
